"""点渗流内核：向量化重写的**等价性**护栏 + 判据语义。

这次改动的形状是"把逐格 Python 出队换成『边表 + 逐层数组推进』"，于是真正需要钉住的
不是某个数字，而是**两条实现路径给出同一个答案**：

1. 边表必须与 ``_adjacent`` + ``direction_allows`` 逐条一致 —— 少一条边就是悄悄改掉了
   连通性（而且自检里的 p_c 只会轻微浮动，不一定看得出来）；
2. 向量化的逐层推进必须与"用公开接口写的朴素 BFS"得到相同的蔓延集合、**相同分层**与
   相同判定（层号 = 到注水点集合的最短距离）；
3. "有没有纵贯簇"的快路径（顶行整行一次推进）必须与"逐簇扫描"的慢路径答案一致。

有了这三条，自检里那些统计数字的浮动（p_c 表）就只是随机源换代造成的噪声，
而不是算法被改坏的信号。测试会用到 ``_adjacent`` / ``_edge_src`` 这些私有成员 ——
这是刻意的白盒护栏：要护栏就得能直接看到被保护的那条不变量。
"""

from __future__ import annotations

import unittest
from collections import deque
from typing import Dict, List, Sequence, Set, Tuple

from prismath.models.site_percolation.model import (
    SitePercolation,
    batch_spread_probability,
    encode_sites,
)

#: 覆盖全部格子类型 × 全部方向模式
COMBOS: Tuple[Tuple[str, str], ...] = tuple(
    (lattice, direction)
    for lattice in ("square", "triangular")
    for direction in ("undirected", "no_up", "down_right", "down_left")
)


def _naive_bfs(model: SitePercolation, origins: Sequence[int],
               ) -> Tuple[Set[int], bool, bool, Dict[int, int]]:
    """参照实现：用公开接口 ``neighbors()`` 做双端队列 BFS（旧代码的形状）。

    返回 ``(蔓延集合, 是否碰到顶行, 是否碰到底行, 每个格子的深度)``。
    多个注水点同属第 0 层 —— 与 ``_spread`` 的语义一致。
    """
    cols = model.cols
    last_row_start = (model.rows - 1) * cols
    seen: Set[int] = set()
    depth_of: Dict[int, int] = {}
    queue: deque = deque()
    for index in origins:
        if index not in seen:
            seen.add(index)
            depth_of[index] = 0
            queue.append(index)
    while queue:
        index = queue.popleft()
        for neighbour in model.neighbors(index):
            if neighbour not in seen:
                seen.add(neighbour)
                depth_of[neighbour] = depth_of[index] + 1
                queue.append(neighbour)
    touches_top = any(index < cols for index in seen)
    touches_bottom = any(index >= last_row_start for index in seen)
    return seen, touches_top, touches_bottom, depth_of


class StructureChangeTest(unittest.TestCase):
    """就地改尺寸 / 形状后，内核必须自己重建内部表（界面走的就是这条路）。

    与 ``test_percolation.py`` 里同名的那组对应：``base.py`` 是就地改
    ``model.rows`` / ``cols`` / ``lattice`` / ``direction`` 再调 ``regenerate()`` 的，
    而 ``_nbr`` / ``_last_row_start`` 都是按尺寸预编译的 —— 忘了重建就是
    "长宽比不为 1 就 ``IndexError: bytearray index out of range``"。
    """

    def test_resize_in_place_rebuilds_tables(self) -> None:
        from prismath.models.site_percolation.model import SitePercolation

        grid = SitePercolation(rows=20, cols=20, p=0.6, rng=1)
        for rows, cols in ((20, 30), (30, 20), (15, 25), (25, 15)):
            with self.subTest(shape=(rows, cols)):
                grid.rows, grid.cols = rows, cols
                grid.regenerate()                    # 界面改尺寸就是这么重排的
                self.assertEqual(grid.node_count, rows * cols)
                self.assertEqual(grid._last_row_start, (rows - 1) * cols)
                result = grid.simulate()
                self.assertEqual((result.rows, result.cols), (rows, cols))
                size, _top, _bottom = grid.spread_stats()
                self.assertLessEqual(size, rows * cols)
                self.assertTrue(grid.spanning_nodes() is not None)

    def test_resize_without_regenerate_is_still_safe(self) -> None:
        """没调 ``regenerate`` 就直接读，也要安全：入口会自己对齐。"""
        from prismath.models.site_percolation.model import SitePercolation

        grid = SitePercolation(rows=20, cols=20, p=0.6, rng=1)
        grid.rows, grid.cols = 12, 34
        result = grid.simulate()
        self.assertEqual((result.rows, result.cols), (12, 34))
        self.assertLessEqual(grid.spread_stats()[0], 12 * 34)

    def test_switch_lattice_and_direction_in_place(self) -> None:
        from prismath.models.site_percolation.model import SitePercolation

        grid = SitePercolation(rows=16, cols=24, p=0.6, rng=1)
        for lattice in ("square", "triangular"):
            for direction in ("undirected", "down_right"):
                if lattice == "triangular" and direction != "undirected":
                    continue
                with self.subTest(lattice=lattice, direction=direction):
                    grid.lattice, grid.direction = lattice, direction
                    grid.regenerate()
                    result = grid.simulate()
                    self.assertEqual((result.rows, result.cols), (16, 24))
                    self.assertLessEqual(grid.spread_stats()[0], 16 * 24)
                    self.assertEqual(len(grid._nbr), 16 * 24)


class EdgeTableTest(unittest.TestCase):
    """``_build_edges`` 是"几何 + 方向"的编译结果，必须与逐格判定逐条一致。"""

    def test_matches_adjacent_and_direction(self) -> None:
        for lattice, direction in COMBOS:
            with self.subTest(lattice=lattice, direction=direction):
                model = SitePercolation(rows=6, cols=5, p=0.5, lattice=lattice,
                                        direction=direction, rng=1)
                expected = set()
                for index in range(model.node_count):
                    for neighbour, dr, dc in model._adjacent(index):
                        if model.direction_allows(dr, dc):
                            expected.add((index, neighbour))
                actual = {(int(a), int(b))
                          for a, b in zip(model._edge_src, model._edge_dst)}
                self.assertEqual(actual, expected)

    def test_edge_count_is_sane(self) -> None:
        """方格网无向：水平 2·rows·(cols-1) + 垂直 2·(rows-1)·cols。"""
        model = SitePercolation(rows=6, cols=5, lattice="square", direction="undirected")
        expected = 2 * 6 * 4 + 2 * 5 * 5
        self.assertEqual(model._edge_src.size, expected)


class WavefrontEquivalenceTest(unittest.TestCase):
    """向量化的逐层推进必须与朴素 BFS 完全等价（集合、分层、判定）。"""

    def test_spread_stats_matches_naive_bfs(self) -> None:
        for lattice, direction in COMBOS:
            for p in (0.30, 0.55, 0.80):
                with self.subTest(lattice=lattice, direction=direction, p=p):
                    model = SitePercolation(rows=8, cols=9, p=p, lattice=lattice,
                                            direction=direction, inject="top", rng=7)
                    origins = model.source_nodes()
                    seen, top, bottom, _depths = _naive_bfs(model, origins)
                    self.assertEqual(model.spread_stats(origins), (len(seen), top, bottom))

    def test_spread_layers_match_naive_depths(self) -> None:
        """分层必须与最短距离一致（层内次序允许不同，层号不允许不同）。"""
        for lattice, direction in COMBOS:
            with self.subTest(lattice=lattice, direction=direction):
                model = SitePercolation(rows=8, cols=8, p=0.6, lattice=lattice,
                                        direction=direction, inject="top", rng=3)
                origins = model.source_nodes()
                seeds = [index for index in origins if model.is_occupied(index)]
                spread, layers, reached = model._spread(origins)
                seen, _top, bottom, depth_of = _naive_bfs(model, seeds)

                self.assertEqual(set(spread), seen)          # 同一批格子
                self.assertEqual(reached, bottom)            # 同一判定
                for depth, members in enumerate(layers):
                    self.assertTrue(members, "空层不该出现")
                    for index in members:
                        self.assertEqual(depth_of[index], depth)
                self.assertEqual(len(layers), max(depth_of.values()) + 1)

    def test_single_origin_matches_naive_bfs(self) -> None:
        """单点注水（随机 / 中心）也要一致 —— 起点是随机挑的，正好顺带覆盖挑选逻辑。"""
        for inject in ("random", "center"):
            for trial in range(5):
                with self.subTest(inject=inject, trial=trial):
                    model = SitePercolation(rows=10, cols=12, p=0.5, inject=inject,
                                            rng=trial)
                    origins = model.source_nodes()
                    seen, top, bottom, _depths = _naive_bfs(model, origins)
                    self.assertEqual(model.spread_stats(origins), (len(seen), top, bottom))


class SpanningFastPathTest(unittest.TestCase):
    """「有没有纵贯簇」的快路径必须与「逐簇扫描」答案一致。"""

    def test_fast_path_matches_cluster_scan(self) -> None:
        for lattice, direction in COMBOS:
            for trial in range(12):
                with self.subTest(lattice=lattice, direction=direction, trial=trial):
                    model = SitePercolation(rows=10, cols=10, p=0.62, lattice=lattice,
                                            direction=direction, rng=trial)
                    self.assertEqual(model.has_spanning_cluster(),
                                     bool(model.spanning_nodes()))

    def test_spanning_cluster_really_touches_both_rows(self) -> None:
        """被判定为纵贯的那一簇，确实同时碰到顶行与末行（判据的字面意思）。

        小格地上"有没有纵贯簇"本身是个概率事件（``p`` 略高于 ``p_c`` 也不保证出现），
        所以这里扫若干组 ``(p, 种子)``，对**确实纵贯**的那些逐一验证，并要求至少验证到
        一组 —— 否则这条测试会退化成"随机地什么也没检查"。
        """
        checked = 0
        for p in (0.60, 0.70, 0.80):
            for seed in range(8):
                model = SitePercolation(rows=14, cols=14, p=p, rng=seed)
                members = model.spanning_nodes()
                if not members:
                    continue
                checked += 1
                with self.subTest(p=p, seed=seed):
                    self.assertTrue(model.has_spanning_cluster())
                    last_row_start = (model.rows - 1) * model.cols
                    self.assertTrue(any(index < model.cols for index in members))
                    self.assertTrue(any(index >= last_row_start for index in members))
        self.assertGreater(checked, 0, "一个纵贯簇都没抽到，这条测试等于没跑")


class CriticalSweepTest(unittest.TestCase):
    """单遍扫描（临界 p）必须与逐 p 重跑的曲线一致，且结构上更"整"。"""

    def test_matches_per_point_path(self) -> None:
        """默认组合走单遍扫描；与"每点独立重跑"应在统计容差内一致。"""
        from prismath.models.site_percolation.model import scan_curve

        points = [0.45, 0.55, 0.60, 0.65, 0.72]
        trials = 300
        sweep = scan_curve(points, rows=20, cols=20, trials=trials, rng=7)
        self.assertEqual([res.p for res in sweep], points)
        for res in sweep:
            direct = batch_spread_probability(rows=20, cols=20, p=res.p, trials=trials,
                                              rng=7, inject="top")
            sigma = (max(res.probability, 1e-6) * (1 - res.probability) / trials) ** 0.5
            with self.subTest(p=res.p):
                self.assertLess(abs(res.probability - direct.probability),
                                4 * sigma + 0.02)
                # "平均蔓延比例"两条路径说的是同一个量（顶端整行的簇大小），要对得上。
                # 容差比 P 的宽松：p 略高于 p_c 时簇大小分布重尾，两个独立样本的均值差
                # 会明显大于二项那套直觉（系统性错误仍远在这条线之外）。
                self.assertLess(abs(res.mean_ratio - direct.mean_ratio), 0.10)

    def test_curve_is_monotone_and_hits_the_extremes(self) -> None:
        from prismath.models.site_percolation.model import scan_curve

        points = [0.05, 0.30, 0.50, 0.65, 0.80, 0.95]
        results = scan_curve(points, rows=16, cols=16, trials=200, rng=11)
        probabilities = [res.probability for res in results]
        self.assertEqual(probabilities, sorted(probabilities))       # 随 p 单调不减
        self.assertEqual(results[0].success, 0)                      # 很小 p：不贯通
        self.assertEqual(results[-1].success, results[-1].trials)    # 很大 p：必贯通
        # 整条曲线共用一遍扫描：每个结果里的 elapsed 是同一遍的耗时
        self.assertEqual(len({res.elapsed for res in results}), 1)

    def test_mean_ratio_comes_from_the_top_cluster(self) -> None:
        from prismath.models.site_percolation.model import scan_curve

        results = scan_curve([0.65], rows=20, cols=20, trials=150, rng=5)
        self.assertGreater(results[0].mean_ratio, 0.2)

    def test_other_combinations_keep_the_per_point_path(self) -> None:
        from prismath.models.site_percolation.model import scan_curve

        results = scan_curve([0.3, 0.5, 0.7], rows=12, cols=12, trials=40, rng=3,
                             inject="random")
        self.assertEqual(len(results), 3)
        self.assertGreater(len({res.elapsed for res in results}), 1)


class InjectDefaultTest(unittest.TestCase):
    """注水方式的默认值（``top``）与"标签 / 内部取值都认"的换算。"""

    def test_model_default_is_top(self) -> None:
        """默认与边渗流对齐，也对齐 p_c 的经典实验（顶端整行注水 → 能否到底端）。"""
        self.assertEqual(SitePercolation(rows=8, cols=8, p=0.6, rng=1).inject, "top")

    def test_options_accept_label_and_internal_value(self) -> None:
        """``_pick`` 必须同时认中文标签与内部取值。

        批量动作是分块的：payload 会把上一次结果的字段回传，而那些字段存的是**内部取值**
        （``"random"`` / ``"center"`` / ``"top"``）。早先的实现只查标签表，于是回传的内部
        取值会落到 fallback —— 默认值是 ``random`` 时这个 bug 被掩盖，换成 ``top`` 就会
        静默改掉注水方式。
        """
        from prismath.models.site_percolation.spec import _options

        self.assertEqual(_options({})["inject"], "top")                            # 缺省
        self.assertEqual(_options({"inject": "顶端整行占据格"})["inject"], "top")     # 中文标签
        self.assertEqual(_options({"inject": "center"})["inject"], "center")        # 内部取值
        self.assertEqual(_options({"inject": "随机一个占据格"})["inject"], "random")
        self.assertEqual(_options({"inject": "认不出来的选项"})["inject"], "top")     # 无法识别 → 回退


class EncodeTest(unittest.TestCase):
    """格地的压缩表示（前端按行优先还原）。"""

    def test_matches_occupied_grid(self) -> None:
        model = SitePercolation(rows=7, cols=5, p=0.5, rng=11)
        text = encode_sites(model)
        self.assertEqual(len(text), 35)
        self.assertEqual(
            text,
            "".join("1" if flag else "0" for row in model.occupied for flag in row),
        )
        self.assertEqual(text.count("1"), model.occupied_count())


class BatchAndScanTest(unittest.TestCase):
    """批量统计与扫描的对外契约（把它们钉住，重构时不会悄悄改口径）。"""

    def test_batch_is_reproducible_with_a_seed(self) -> None:
        from prismath.models.site_percolation.model import batch_spread_probability

        first = batch_spread_probability(rows=20, cols=20, p=0.6, trials=40, rng=99)
        second = batch_spread_probability(rows=20, cols=20, p=0.6, trials=40, rng=99)
        self.assertEqual(first.success, second.success)
        self.assertEqual(first.trials, 40)
        self.assertAlmostEqual(first.mean_ratio, second.mean_ratio, places=12)

    def test_probability_is_a_rate(self) -> None:
        from prismath.models.site_percolation.model import batch_spread_probability

        result = batch_spread_probability(rows=12, cols=12, p=0.9, trials=50, rng=3)
        self.assertLessEqual(0.0, result.probability)
        self.assertLessEqual(result.probability, 1.0)
        self.assertEqual(result.probability, result.success / result.trials)

    def test_scan_reports_every_point_and_is_monotone_at_the_extremes(self) -> None:
        from prismath.models.site_percolation.model import scan_curve

        points = [0.05, 0.95]
        seen: List[Tuple[int, float]] = []
        results = scan_curve(points, rows=12, cols=12, trials=30, rng=4,
                             progress=lambda done, total, res: seen.append((done, res.p)))
        self.assertEqual([res.p for res in results], points)
        self.assertEqual(seen, [(1, 0.05), (2, 0.95)])
        self.assertLessEqual(results[0].probability, results[1].probability)

    def test_span_criterion_ignores_injection(self) -> None:
        """文档里那句"贯通判据与注水方式无关"必须在同一批格地上逐次成立。"""
        from prismath.models.site_percolation.model import batch_spread_probability

        for p in (0.5, 0.62, 0.75):
            with self.subTest(p=p):
                base = batch_spread_probability(rows=16, cols=16, p=p, trials=60,
                                                rng=2026, inject="top")
                other = batch_spread_probability(rows=16, cols=16, p=p, trials=60,
                                                 rng=2026, inject="random")
                self.assertEqual(base.success, other.success)


if __name__ == "__main__":
    unittest.main()
