"""生命游戏内核：教材结论 + 契约。

这些断言是"这个模型为什么存在"的答案（方块为什么静止、滑翔机为什么每 4 代平移一格），
所以它们属于**契约**：内核重写只许换实现，不许让它们中的任何一条不成立。

关于"精确相等"是否太脆：**不脆**。生命游戏的演化是纯整数运算（无浮点、无随机），
所以 numpy 向量化重写必须做到逐位相同 —— 精确断言才是对的断言。
下面凡是从文献抄来的数字，都先用当前实现实测过再固化（例如 R 五连块在死边界上是
**321 代**收敛，而不是文献里无界平面的 1103 代：死边界上滑翔机会撞墙提前消失）。
"""

from __future__ import annotations

import unittest

from prismath.models.life_game.model import (
    BOUNDARY_DEAD,
    BOUNDARY_TORUS,
    MAX_SIZE,
    MIN_SIZE,
    OUTCOME_CYCLE,
    OUTCOME_EXTINCT,
    OUTCOME_RUNNING,
    OUTCOME_STATIC,
    PATTERN_LABELS,
    PATTERNS,
    RULES,
    LifeBoard,
    LifeRule,
    encode_cells,
    scan_survival,
)


def _coords(board: LifeBoard):
    """活细胞的 ``(行, 列)`` 集合（下标换算只放在测试里，内核不必提供）。"""
    return {(i // board.cols, i % board.cols) for i in board.alive_indices()}


class RuleTest(unittest.TestCase):
    """规则串的解析：现行写法、老写法、脏输入。"""

    def test_current_notation(self) -> None:
        rule = LifeRule.parse("B3/S23")
        self.assertEqual(rule.born, frozenset({3}))
        self.assertEqual(rule.survive, frozenset({2, 3}))
        self.assertEqual(rule.to_string(), "B3/S23")

    def test_legacy_notation_is_reversed(self) -> None:
        """老写法 ``23/3`` 是「存活/新生」的顺序，与现行写法相反。"""
        old = LifeRule.parse("23/3")
        self.assertEqual(old.born, frozenset({3}))
        self.assertEqual(old.survive, frozenset({2, 3}))
        self.assertEqual(old.to_string(), "B3/S23")

    def test_highlife(self) -> None:
        self.assertEqual(LifeRule.parse("B36/S23").born, frozenset({3, 6}))

    def test_junk_falls_back_to_standard(self) -> None:
        for junk in (None, "", "nonsense", "B3S23"):
            with self.subTest(junk=junk):
                self.assertEqual(LifeRule.parse(junk).to_string(), "B3/S23")

    def test_nine_is_not_a_valid_neighbour_count(self) -> None:
        """9 个邻居在 8 邻域里不可能，解析时被丢掉（否则规则会静默失效）。"""
        self.assertEqual(LifeRule.parse("9/9").to_string(), "B/S")

    def test_labels_come_from_the_preset_table(self) -> None:
        self.assertEqual(LifeRule.parse("B3/S23").label, RULES["B3/S23"])
        self.assertEqual(LifeRule.parse("B7/S7").label, "B7/S7")


class PatternTableTest(unittest.TestCase):
    """图案表本身的健康度（放歪了、行宽不一致，界面上就会画错）。"""

    def test_rows_have_uniform_width(self) -> None:
        for name, rows in PATTERNS.items():
            with self.subTest(pattern=name):
                widths = {len(row) for row in rows}
                self.assertEqual(len(widths), 1, f"{name} 的行宽不一致：{sorted(widths)}")

    def test_ui_labels_cover_every_pattern(self) -> None:
        """界面下拉框列的是 ``PATTERN_LABELS``，所以它引用的图案必须真的存在。"""
        for name in PATTERN_LABELS:
            if name in ("blank", "random"):
                continue
            with self.subTest(pattern=name):
                self.assertIn(name, PATTERNS)


class LongRunBehaviourTest(unittest.TestCase):
    """四种长期行为：静止 / 周期 / 消亡 / 仍在演化。"""

    def test_block_is_static(self) -> None:
        board = LifeBoard(rows=10, cols=10, pattern="block")
        run = board.run(20)
        self.assertEqual(run.outcome, OUTCOME_STATIC)
        self.assertEqual(run.period, 1)
        self.assertEqual(run.population, 4)
        self.assertEqual(run.stop_generation, 1)

    def test_blinker_has_period_two(self) -> None:
        board = LifeBoard(rows=10, cols=10, pattern="blinker")
        run = board.run(20)
        self.assertEqual(run.outcome, OUTCOME_CYCLE)
        self.assertEqual(run.period, 2)
        self.assertEqual(run.stop_generation, 2)

    def test_pulsar_has_period_three(self) -> None:
        board = LifeBoard(rows=20, cols=20, pattern="pulsar")
        run = board.run(50)
        self.assertEqual(run.outcome, OUTCOME_CYCLE)
        self.assertEqual(run.period, 3)

    def test_gosper_gun_keeps_growing(self) -> None:
        """滑翔机枪每 30 代射出一架滑翔机 —— 有限棋盘上唯一不会周期化的结局。

        要用**死边界**：环面上射出去的滑翔机绕回来会撞到枪（枪于是也会周期化），
        而死边界上它们飞出棋盘消失，枪可以一直开下去 —— 这样才隔离出"无限增长"本身。
        另外棋盘必须比枪宽（枪宽 36，窄了会被 ``place`` 裁掉、行为就不是枪了）。
        """
        board = LifeBoard(rows=60, cols=60, pattern="gosper_gun", boundary=BOUNDARY_DEAD)
        run = board.run(120)
        self.assertEqual(run.outcome, OUTCOME_RUNNING)
        self.assertGreater(run.population, 36)      # 初始 36 个，射了几架之后更多


class GliderTest(unittest.TestCase):
    """滑翔机：每 4 代整体平移 (1,1)；在环面上跑一圈的"状态周期"是 4×边长。"""

    def test_moves_one_cell_per_four_generations(self) -> None:
        board = LifeBoard(rows=20, cols=20, pattern="glider", boundary=BOUNDARY_DEAD)
        before = _coords(board)
        self.assertEqual(len(before), 5)
        for _ in range(4):
            board.step()
        self.assertEqual(_coords(board), {(r + 1, c + 1) for r, c in before})

    def test_torus_period_is_four_times_the_side(self) -> None:
        """环面上没有边界可"出去"，整体平移 N 格就回到原状态（N = 边长）。"""
        for side in (12, 20):
            with self.subTest(side=side):
                board = LifeBoard(rows=side, cols=side, pattern="glider",
                                  boundary=BOUNDARY_TORUS)
                run = board.run(4 * side + 20)
                self.assertEqual(run.outcome, OUTCOME_CYCLE)
                self.assertEqual(run.period, 4 * side)

    def test_dead_boundary_keeps_streaming(self) -> None:
        """死边界上它一直往外走（不会周期化）—— 与环面的对照。"""
        board = LifeBoard(rows=60, cols=60, pattern="glider", boundary=BOUNDARY_DEAD)
        run = board.run(60)
        self.assertEqual(run.outcome, OUTCOME_RUNNING)


class RPentominoTest(unittest.TestCase):
    """R 五连块：著名的"长寿者"。数字是实测值（死边界 ≠ 文献的无界平面）。"""

    def test_settles_at_321_generations_on_a_dead_board(self) -> None:
        board = LifeBoard(rows=64, cols=64, pattern="r_pentomino", boundary=BOUNDARY_DEAD)
        run = board.run(2000)
        self.assertEqual(run.outcome, OUTCOME_CYCLE)
        self.assertEqual(run.period, 2)
        self.assertEqual(run.stop_generation, 321)
        self.assertEqual(run.population, 73)

    def test_on_torus_it_keeps_going_for_a_long_time(self) -> None:
        """环面上滑翔机绕回来会继续搅动，200 代还远没安定。

        113 是 **64×64 环面**在 200 代的实测值（自检里那个 61 用的是另一种尺寸）——
        又一个"数字不能跨尺寸照抄"的例子。
        """
        board = LifeBoard(rows=64, cols=64, pattern="r_pentomino",
                          boundary=BOUNDARY_TORUS)
        run = board.run(200)
        self.assertEqual(run.outcome, OUTCOME_RUNNING)
        self.assertEqual(run.population, 113)


class EdgeCaseTest(unittest.TestCase):
    """边界情形：全死、全活、尺寸钳制 —— 都不该需要随机源就能复现。"""

    def test_empty_board_dies_immediately(self) -> None:
        board = LifeBoard(rows=8, cols=8, pattern="blank")
        run = board.run(10)
        self.assertEqual(run.outcome, OUTCOME_EXTINCT)
        self.assertEqual(run.stop_generation, 1)
        self.assertEqual(run.population, 0)

    def test_all_alive_board_dies_immediately(self) -> None:
        """全活时每格都有 8 个邻居，8 ∉ {2,3}，于是一代全灭。"""
        board = LifeBoard(rows=8, cols=8, pattern="random", density=1.0)
        self.assertEqual(board.population, 64)
        run = board.run(10)
        self.assertEqual(run.outcome, OUTCOME_EXTINCT)
        self.assertEqual(run.stop_generation, 1)

    def test_size_is_clamped(self) -> None:
        board = LifeBoard(rows=1, cols=10_000)
        self.assertEqual(board.rows, MIN_SIZE)
        self.assertEqual(board.cols, MAX_SIZE)


class BoardEditingTest(unittest.TestCase):
    """编辑（点击涂画）与编码：界面按这些语义工作。"""

    def test_toggle_updates_population_without_touching_generation(self) -> None:
        board = LifeBoard(rows=10, cols=10, pattern="blank")
        self.assertFalse(board.is_alive(0))
        self.assertTrue(board.toggle(0))
        self.assertEqual(board.population, 1)
        self.assertEqual(board.generation, 0)          # 编辑的是"当前这一代"
        self.assertFalse(board.toggle(0))
        self.assertEqual(board.population, 0)

    def test_encode_load_round_trip(self) -> None:
        board = LifeBoard(rows=12, cols=12, pattern="glider")
        text = board.encode()
        self.assertEqual(len(text), board.node_count)
        other = LifeBoard(rows=12, cols=12, pattern="blank")
        other.load(text)
        self.assertEqual(other.encode(), text)
        self.assertEqual(other.population, board.population)

    def test_encode_cells_shape(self) -> None:
        board = LifeBoard(rows=12, cols=20, pattern="glider")
        payload = encode_cells(board)
        self.assertEqual((payload["rows"], payload["cols"]), (12, 20))
        self.assertEqual(len(payload["cells"]), 12 * 20)
        self.assertEqual(payload["alive"], board.population)


class OptionsContractTest(unittest.TestCase):
    """``options_from_ui`` 必须同时认中文标签与内部取值。

    分块动作的 payload 会把上一次结果的字段回传，那些字段存的是**内部取值**
    （``"torus"`` / ``"B3/S23"``），界面表单给的则是中文标签 —— 两条路都要通，否则回传的
    内部取值会被当成"无法识别"而落到 fallback，用户选的规则 / 边界被静默换掉。
    """

    def test_accepts_internal_values(self) -> None:
        from prismath.models.life_game.spec import options_from_ui

        options = options_from_ui({"rule": "B3/S23", "boundary": "torus",
                                   "pattern": "glider"})
        self.assertEqual(options["rule"], "B3/S23")
        self.assertEqual(options["boundary"], "torus")
        self.assertEqual(options["pattern"], "glider")


class RunContractTest(unittest.TestCase):
    """``run`` 的对外承诺：帧与 census 同长、提前收敛时提前停、代数不越界。"""

    def test_frames_and_census_have_equal_length(self) -> None:
        board = LifeBoard(rows=60, cols=60, pattern="gosper_gun", boundary=BOUNDARY_DEAD)
        initial = board.encode()
        run = board.run(120)
        self.assertEqual(len(run.frames), len(run.census))
        self.assertEqual(run.frame_count, len(run.frames))
        self.assertEqual(run.census[0][0], 0)          # 第一帧是初始态
        self.assertEqual(run.frames[0], initial)       # 且与演化前的棋盘逐字相同
        self.assertEqual(run.census_series()[0]["gen"], 0)

    def test_stride_sampling_keeps_frame_budget(self) -> None:
        """代数很多时按 stride 抽样（结局判定仍逐代精确）。

        刻意停在 120 代：死边界上的枪大约第 145 代进入"传送带"稳态（见下面那个测试），
        一旦进入稳态结局就是周期振荡，``stop_generation`` 自然小于请求的代数。
        """
        board = LifeBoard(rows=60, cols=60, pattern="gosper_gun", boundary=BOUNDARY_DEAD)
        run = board.run(120, max_frames=20)
        self.assertGreater(run.stride, 1)
        self.assertLessEqual(run.frame_count, 20)
        self.assertEqual(run.stop_generation, 120)
        self.assertEqual(run.outcome, OUTCOME_RUNNING)

    def test_dead_boundary_gun_reaches_a_conveyor_belt(self) -> None:
        """死边界上枪最终会进入周期稳态：滑翔机撞墙消失的速率 = 新射出的速率。

        周期是 **60**（= 2 × 发射周期），不是 30 —— 因为滑翔机每 4 代才走一格（0.25 格/代），
        30 代只走 7.5 格（非整数），朝向相位也没回到原处；要两个发射周期才能同时对上
        "位移 15 格（整数倍间距）"与"朝向同相位"。于是"无限增长"只在稳态到来之前成立。
        """
        board = LifeBoard(rows=60, cols=60, pattern="gosper_gun", boundary=BOUNDARY_DEAD)
        run = board.run(400)
        self.assertEqual(run.outcome, OUTCOME_CYCLE)
        self.assertEqual(run.period, 60)
        self.assertGreater(run.population, 36)

    def test_settling_stops_the_run_early(self) -> None:
        board = LifeBoard(rows=10, cols=10, pattern="blinker")
        run = board.run(1000)
        self.assertEqual(run.stop_generation, 2)
        self.assertLess(run.stop_generation, run.generations)


class ScanTest(unittest.TestCase):
    """密度扫描：两端的结论是确定的（不需要随机源就能断言）。"""

    def test_both_extremes_die_out(self) -> None:
        results = scan_survival([0.0, 1.0], rows=8, cols=8, generations=5,
                                trials=3, rng=1)
        self.assertEqual(len(results), 2)
        for row in results:
            with self.subTest(density=row.density):
                self.assertEqual(row.trials, 3)
                self.assertEqual(row.extinct, 3)
                self.assertEqual(row.survival_rate, 0.0)
                self.assertEqual(row.mean_life, 1.0)    # 都在第 1 代就归零

    def test_rates_stay_in_range(self) -> None:
        results = scan_survival([0.1, 0.3, 0.9], rows=12, cols=12, generations=40,
                                trials=4, rng=7)
        for row in results:
            with self.subTest(density=row.density):
                self.assertLessEqual(0.0, row.survival_rate)
                self.assertLessEqual(row.survival_rate, 1.0)
                self.assertLessEqual(row.settled_rate, 1.0)
                self.assertLessEqual(row.mean_life, row.generations)


if __name__ == "__main__":
    unittest.main()
