"""万有引力多星内核：守恒量、开普勒轨道、辛积分器的收敛阶、场景库。

这里的断言分三类，各自的"该有多严"不一样：

* **精确恒等式**（总动量守恒、开普勒第三定律、编码长度）—— 与实现细节无关，
  容差只留给浮点舍入；
* **积分器精度**（能量漂移随 dt 按 dt² 下降、误差有界不漂移）—— 这是本模型的核心结论，
  容差按"数量级"给（二阶方法实测比值 4.00，断言 3.0–5.5 足以抓住"写成一阶"这类真问题）；
* **场景库自洽**（每个场景都跑得动、随机场景可复现）—— 只断言结构与有限性，
  不断言具体数值（混沌场景换个种子就是另一条轨迹）。

**为什么不断言混沌场景的具体数值**：随机星团对初值敏感，断言"第 600 帧长什么样"等于
把某个随机种子的实现细节钉死；要钉的那部分在 ``tests/golden/n_body.txt`` 里（自检输出），
那里有固定种子下的完整表格。
"""

from __future__ import annotations

import json
import math
import unittest
from types import SimpleNamespace

import numpy as np

from awe_math.models.n_body.model import (
    FIGURE_EIGHT_PERIOD,
    GRAVITY,
    MIN_MASS,
    SCENARIO_CLUSTER,
    SCENARIO_DISK,
    SCENARIO_FIGURE_EIGHT,
    SCENARIO_ORDER,
    NBody,
    build_scenario,
    circular_velocity,
    encode_positions,
    scan_drift,
)
from awe_math.models import n_body  # noqa: F401  导入即注册模型
from awe_math.registry import get

try:                                                    # pragma: no cover
    import tkinter as tk
except Exception:                                       # pragma: no cover
    tk = None


def _tk_available() -> bool:
    """能不能真的起一个 Tk 窗口（无图形环境时视图交互测试整体跳过）。"""
    if tk is None:
        return False
    try:
        root = tk.Tk()
    except Exception:
        return False
    root.destroy()
    return True


TK_OK = _tk_available()


def _circular_pair(radius: float, dt: float = 0.002) -> NBody:
    """两个等质量星体的圆轨道（各自离质心 ``radius``，于是间距 = 2·radius）。"""
    separation = 2.0 * radius
    v_rel = math.sqrt(GRAVITY * 2.0 / separation)
    return NBody(
        positions=[[-radius, 0.0], [radius, 0.0]],
        velocities=[[0.0, -v_rel / 2.0], [0.0, v_rel / 2.0]],
        masses=[1.0, 1.0], dt=dt, softening=0.0, trail=0, scenario="two_body",
    )


class TwoBodyTest(unittest.TestCase):
    """两体问题有解析解：用它来钉住积分器"走对了没有"。"""

    def test_circular_orbit_returns_after_one_period(self) -> None:
        body = _circular_pair(0.5)
        period = 2.0 * math.pi * math.sqrt(1.0 ** 3 / (GRAVITY * 2.0))
        start = body.pos.copy()
        radius_error = 0.0
        for _ in range(int(round(period / body.dt))):
            body.step()
            radius_error = max(radius_error, abs(float(np.hypot(*body.pos[0])) - 0.5))
        self.assertLess(radius_error, 1e-4, "圆轨道的半径不该越跑越偏")
        self.assertLess(float(np.max(np.abs(body.pos - start))), 1e-3,
                        "一个周期后应当回到出发点")

    def test_kepler_third_law(self) -> None:
        """T² ∝ a³：半径翻倍，周期应当变成 2^1.5 ≈ 2.828 倍。"""
        first = 2.0 * math.pi * math.sqrt(0.5 ** 3 / (GRAVITY * 2.0))
        second = 2.0 * math.pi * math.sqrt(1.0 ** 3 / (GRAVITY * 2.0))
        self.assertAlmostEqual(second / first, 2.0 ** 1.5, places=9)

    def test_momentum_is_conserved(self) -> None:
        """内力成对抵消，所以总动量只能有浮点舍入量级的漂移。"""
        body = _circular_pair(0.5)
        for _ in range(500):
            body.step()
        self.assertLess(float(np.linalg.norm(body.momentum())), 1e-12)

    def test_angular_momentum_is_conserved(self) -> None:
        body = _circular_pair(0.5)
        before = body.angular_momentum()
        for _ in range(500):
            body.step()
        self.assertAlmostEqual(body.angular_momentum(), before, places=10)

    def test_energy_error_is_bounded_not_drifting(self) -> None:
        """辛积分器的能量误差在真值附近振荡 —— 三个周期里的最大值应当同量级。

        这正是速度 Verlet 与"同阶显式方法"的分水岭：后者会单调漂移，跑得越久越离谱。
        """
        body = _circular_pair(0.5)
        period = 2.0 * math.pi * math.sqrt(1.0 ** 3 / (GRAVITY * 2.0))
        steps = int(round(period / body.dt))
        base = abs(body.initial_energy)
        worst: list = []
        for _ in range(3):
            peak = 0.0
            for _ in range(steps):
                body.step()
                peak = max(peak, abs(body.total_energy() - body.initial_energy) / base)
            worst.append(peak)
        self.assertGreater(worst[0], 0.0)
        self.assertLess(worst[-1] / worst[0], 3.0, "能量误差应当有界，不该随周期数增长")


class IntegratorTest(unittest.TestCase):
    """积分器本身：收敛阶、步数记账、两个"不会崩"的兜底。"""

    def test_second_order_convergence(self) -> None:
        points = scan_drift((0.008, 0.004, 0.002))
        drifts = [point.drift for point in points]
        for coarse, fine in zip(drifts, drifts[1:]):
            ratio = coarse / fine
            self.assertGreater(ratio, 3.0, "dt 减半后漂移应当明显下降")
            self.assertLess(ratio, 5.5, "速度 Verlet 是二阶方法：比值应当在 4 附近")

    def test_steps_and_time_are_counted(self) -> None:
        body = _circular_pair(0.5, dt=0.01)
        for _ in range(7):
            body.step()
        self.assertEqual(body.steps, 7)
        self.assertAlmostEqual(body.time, 0.07, places=12)

    def test_advance_records_one_trail_point_per_frame(self) -> None:
        body = _circular_pair(0.5, dt=0.01)
        body.trail_len = 5
        for _ in range(4):
            body.advance(3)
        self.assertEqual(body.steps, 12)
        self.assertEqual(body.trail_array().shape, (5, 2, 2), "轨迹只保留最近 5 个快照")

    def test_coincident_bodies_are_flagged_not_raised(self) -> None:
        """两星位置完全重合时引力发散：模型应当标记 blown_up，而不是抛异常。"""
        body = NBody([[0.0, 0.0], [0.0, 0.0]], [[0.0, 0.0], [0.0, 0.0]], [1.0, 1.0],
                     dt=0.01, softening=0.0, trail=0)
        body.step()
        self.assertTrue(body.blown_up)

    def test_softening_keeps_close_pair_finite(self) -> None:
        """同样的重合初值，给一个软化半径 ε 就完全正常（力被限制在有限值）。"""
        body = NBody([[0.0, 0.0], [0.0, 0.0]], [[0.0, 0.0], [0.0, 0.0]], [1.0, 1.0],
                     dt=0.01, softening=0.1, trail=0)
        for _ in range(50):
            body.step()
        self.assertFalse(body.blown_up)
        self.assertTrue(bool(np.isfinite(body.pos).all()))
        # 重合两星 + 软化引力：势能 = −G·m²/ε = −10
        self.assertAlmostEqual(body.total_energy(), -GRAVITY * 1.0 / 0.1, places=6)

    def test_circular_velocity_softening_formula(self) -> None:
        self.assertAlmostEqual(circular_velocity(1.0, 1.0), 1.0, places=12)
        softened = circular_velocity(1.0, 1.0, 0.5)
        self.assertLess(softened, 1.0, "软化后的引力更弱，圆轨道速度也该更小")
        expected = math.sqrt(1.0 / (1.0 + 0.25) ** 1.5)
        self.assertAlmostEqual(softened, expected, places=12)


class ScenarioTest(unittest.TestCase):
    """场景库：每个场景都构造得出来、跑得动，随机场景可复现。"""

    def test_figure_eight_returns_after_one_period(self) -> None:
        """8 字三体是精确周期解：一个周期后应当回到初始构型（这是最强的精度断言）。"""
        preset = build_scenario(SCENARIO_FIGURE_EIGHT)
        body = NBody(preset.positions, preset.velocities, preset.masses,
                     dt=0.002, softening=0.0, trail=0, period=preset.period)
        for _ in range(int(round(FIGURE_EIGHT_PERIOD / body.dt))):
            body.step()
        self.assertLess(float(np.max(np.abs(body.pos - preset.positions))), 5e-3)

    def test_every_scenario_runs_finite(self) -> None:
        for key in SCENARIO_ORDER:
            with self.subTest(scenario=key):
                preset = build_scenario(key, seed=7)
                body = NBody(preset.positions, preset.velocities, preset.masses,
                             dt=0.004, softening=preset.softening, trail=8)
                run = body.run(frames=60, substeps=3)
                self.assertFalse(run.blown_up, f"{key} 在默认参数下不该数值爆炸")
                self.assertEqual(body.pos.shape, (preset.count, 2))
                self.assertEqual(run.frames[0].shape, (preset.count, 2))
                self.assertTrue(np.isfinite(body.total_energy()))

    def test_cluster_total_momentum_starts_at_zero(self) -> None:
        """随机场景的初值都做了"质心速度归零"，否则整团会整体平移着漂出画面。"""
        for key in (SCENARIO_CLUSTER, SCENARIO_DISK):
            with self.subTest(scenario=key):
                preset = build_scenario(key, seed=3)
                body = NBody(preset.positions, preset.velocities, preset.masses,
                             softening=preset.softening, trail=0)
                self.assertLess(float(np.linalg.norm(body.momentum())), 1e-12)

    def test_random_scenarios_are_reproducible_with_seed(self) -> None:
        first = build_scenario(SCENARIO_CLUSTER, seed=11)
        second = build_scenario(SCENARIO_CLUSTER, seed=11)
        other = build_scenario(SCENARIO_CLUSTER, seed=12)
        self.assertTrue(np.array_equal(first.positions, second.positions))
        self.assertFalse(np.array_equal(first.positions, other.positions))

    def test_star_count_applies_to_random_scenarios_only(self) -> None:
        self.assertEqual(build_scenario(SCENARIO_CLUSTER, stars=7, seed=5).count, 7)
        self.assertEqual(build_scenario(SCENARIO_DISK, stars=9, seed=5).count, 9)
        # 精确解场景的星体数是场景本身决定的，不受 stars 影响
        self.assertEqual(build_scenario(SCENARIO_FIGURE_EIGHT, stars=99).count, 3)

    def test_escape_detection(self) -> None:
        """给一颗星远高于逃逸速度的初速度，它应当被计入"逃逸"。"""
        body = NBody([[0.0, 0.0], [1.0, 0.0]], [[0.0, 0.0], [0.0, 5.0]], [1.0, 1.0],
                     dt=0.01, softening=0.0, trail=0)
        for _ in range(200):
            body.step()
        self.assertGreaterEqual(body.escaped_count(), 1)

    def test_run_stride_keeps_frames_bounded(self) -> None:
        """帧数超过上限时按 stride 抽样，但末帧必须保留（否则动画看不到结局）。"""
        preset = build_scenario(SCENARIO_FIGURE_EIGHT)
        body = NBody(preset.positions, preset.velocities, preset.masses,
                     dt=0.004, softening=0.0, trail=0)
        run = body.run(frames=2000, substeps=1, max_frames=50)
        self.assertGreater(run.stride, 1)
        self.assertLessEqual(run.frame_count, 51)
        self.assertAlmostEqual(run.samples[-1][0], run.time, places=9)
        self.assertTrue(np.allclose(run.frames[-1], body.pos))


class EncodeTest(unittest.TestCase):
    """给前端的扁平位置编码。"""

    def test_flat_roundtrip(self) -> None:
        preset = build_scenario(SCENARIO_FIGURE_EIGHT)
        flat = encode_positions(preset.positions)
        self.assertEqual(len(flat), preset.count * 2)
        restored = np.array(flat).reshape(-1, 2)
        self.assertTrue(np.allclose(restored, preset.positions, atol=1e-3))


class SpecTest(unittest.TestCase):
    """数据级契约：界面参数 -> 内部取值 -> payload（都要能被 JSON 序列化）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = get("n_body")

    def test_options_from_ui_translates_chinese_labels(self) -> None:
        from awe_math.models.n_body.spec import options_from_ui

        internal = options_from_ui({
            "scenario": "随机星团（混沌）", "stars": 12, "dt": 0.01,
            "substeps": 4, "softening": 0.2, "trail": 30, "seed": 5,
        })
        self.assertEqual(internal["scenario"], SCENARIO_CLUSTER)
        self.assertEqual(internal["stars"], 12)
        self.assertAlmostEqual(internal["softening"], 0.2)

    def test_build_nbody_falls_back_to_scenario_softening(self) -> None:
        from awe_math.models.n_body.spec import build_nbody

        cluster = build_nbody({"scenario": SCENARIO_CLUSTER, "softening": None, "seed": 1})
        self.assertGreater(cluster.softening, 0.0, "随机星团需要软化长度")
        exact = build_nbody({"scenario": SCENARIO_FIGURE_EIGHT, "softening": None})
        self.assertEqual(exact.softening, 0.0, "精确解场景必须用严格牛顿引力")

    def test_values_are_clamped(self) -> None:
        from awe_math.models.n_body.spec import build_nbody

        body = build_nbody({"scenario": SCENARIO_FIGURE_EIGHT, "stars": 10 ** 6,
                            "dt": 99.0, "trail": 10 ** 6, "softening": 99.0})
        self.assertLessEqual(body.count, 3)          # 场景决定的星体数
        self.assertLessEqual(body.dt, 0.05)
        self.assertLessEqual(body.softening, 0.5)
        self.assertLessEqual(body.trail_len, 1200)

    def test_handler_payload_is_json_serializable(self) -> None:
        payload = self.spec.run("simulate", {"scenario": SCENARIO_FIGURE_EIGHT,
                                             "dt": 0.004, "substeps": 2})
        text = json.dumps(payload, ensure_ascii=False)     # 不可序列化会在这里抛异常
        self.assertIn("nbody-orbit", text)
        self.assertEqual(payload["view"], "nbody-orbit")
        self.assertEqual(payload["count"], 3)
        self.assertEqual(len(payload["frames"][0]), 6)
        self.assertEqual(len(payload["samples"]), len(payload["frames"]))
        self.assertEqual(len(payload["extent"]), 4)
        self.assertFalse(payload["blownUp"])

    def test_handler_rejects_unknown_action(self) -> None:
        with self.assertRaises(ValueError):
            self.spec.run("nope", {})


class EditTest(unittest.TestCase):
    """编辑单颗星：挪位置 / 改质量 / 重锚基准（桌面画布上"选中并拖动"的内核部分）。"""

    def _body(self) -> NBody:
        preset = build_scenario(SCENARIO_FIGURE_EIGHT)
        return NBody(preset.positions, preset.velocities, preset.masses,
                     dt=0.002, softening=0.0, trail=0)

    def test_move_star_changes_position_only(self) -> None:
        body = self._body()
        velocity = body.vel.copy()
        body.move_star(0, 2.0, -1.0)
        self.assertTrue(np.allclose(body.pos[0], (2.0, -1.0)))
        self.assertTrue(np.array_equal(body.vel, velocity), "挪位置不该改速度")

    def test_set_mass_is_clamped(self) -> None:
        body = self._body()
        body.set_mass(1, 2.5)
        self.assertAlmostEqual(float(body.mass[1]), 2.5, places=12)
        body.set_mass(1, -5.0)
        self.assertAlmostEqual(float(body.mass[1]), MIN_MASS, places=12)

    def test_out_of_range_edits_are_rejected(self) -> None:
        body = self._body()
        with self.assertRaises(IndexError):
            body.move_star(99, 0.0, 0.0)
        with self.assertRaises(IndexError):
            body.set_mass(-1, 1.0)

    def test_rebase_resets_the_drift_baseline(self) -> None:
        """编辑之后重锚基准：漂移归零，再跑一段也仍然很小（基准是编辑后的状态）。"""
        body = self._body()
        for _ in range(200):
            body.step()
        self.assertNotEqual(body.relative_energy_drift(), 0.0)
        body.move_star(0, 1.4, 0.3)
        self.assertGreater(abs(body.relative_energy_drift()), 1e-9,
                           "改过位置之后、重锚之前，旧基准已经对不上了")
        body.rebase()
        self.assertAlmostEqual(body.relative_energy_drift(), 0.0, places=12)
        self.assertEqual(body.max_drift, 0.0)
        self.assertEqual(body.escaped_count(), 0, "重锚时逃逸判据也要跟着重算")
        for _ in range(50):
            body.step()
        self.assertLess(abs(body.relative_energy_drift()), 1e-3)


@unittest.skipUnless(TK_OK, "没有可用的图形环境（tk.Tk() 起不来）")
class ViewInteractionTest(unittest.TestCase):
    """桌面视图的交互：缩放 / 平移 / 恢复视图 / 选中并拖动星体 / 质量滑块 / 曲线窗口。

    这些路径平时只有人手点得到，最容易在重构时悄悄坏掉（而且坏了也不报错），
    所以按"合成事件 -> 断言状态"的方式钉住：调的是画布的真实处理函数，
    只是把 ``event`` 换成一个带 ``x / y / delta`` 的轻量对象。
    """

    def setUp(self) -> None:
        from awe_math.models.n_body.views.tk import NBodyView
        from awe_math.ui.tk.theme import install_theme

        self.root = tk.Tk()
        install_theme(self.root)
        host = tk.Frame(self.root)
        host.pack(fill="both", expand=True)
        self.view = NBodyView(self.root, host, get("n_body"))
        self.root.update()

    def tearDown(self) -> None:
        self.view.shutdown()
        self.root.destroy()

    @staticmethod
    def _event(x: int = 0, y: int = 0, delta: int = 0):
        return SimpleNamespace(x=x, y=y, delta=delta)

    def test_wheel_zoom_keeps_the_point_under_cursor(self) -> None:
        for _ in range(5):
            self.view._step_once()
        before = self.view._screen_to_world(400.0, 220.0)
        self.view._on_wheel(self._event(400, 220, 120))
        after = self.view._screen_to_world(400.0, 220.0)
        self.assertAlmostEqual(before[0], after[0], places=6, msg="光标下的世界点不该跑")
        self.assertAlmostEqual(before[1], after[1], places=6)
        self.assertTrue(self.view._cam_manual, "手动缩放后应当退出自动视角")
        radius = self.view._cam_radius
        self.view._on_wheel(self._event(400, 220, -120))
        self.assertGreater(self.view._cam_radius, radius, "反方向滚轮应当把视野拉回")

    def test_drag_on_empty_space_pans_and_restore_fits_back(self) -> None:
        for _ in range(5):
            self.view._step_once()
        center = self.view._cam_center.copy()
        self.view._on_canvas_click(self._event(4, 4))          # 空白处按下 -> 平移
        self.assertEqual(self.view._drag_mode, "pan")
        self.view._on_canvas_drag(self._event(80, 60))
        self.view._on_canvas_release(self._event())
        self.assertFalse(np.allclose(center, self.view._cam_center), "拖动应当平移视角")
        self.view._restore_view()
        self.assertFalse(self.view._cam_manual, "恢复视图之后应回到自动视角")
        self.assertLess(float(np.hypot(*self.view._cam_center)), 1e-9)

    def test_click_selects_a_star_and_drag_moves_it(self) -> None:
        self.view._pause(silent=True)
        px, py = self.view._world_to_screen(*self.view.body.pos[0])
        self.view._on_canvas_click(self._event(int(round(px)), int(round(py))))
        self.assertEqual(self.view._selected, 0, "点中星体应当选中它")
        before = self.view.body.pos[0].copy()
        self.view._on_canvas_drag(self._event(int(round(px)) + 40, int(round(py)) + 15))
        self.view._on_canvas_release(self._event())
        self.assertFalse(np.allclose(before, self.view.body.pos[0]), "拖动应当移动星体")
        self.assertLess(abs(self.view._curve_base - self.view.body.initial_energy), 1e-9)
        self.assertEqual(len(self.view._energy_history), 1, "改过初值，曲线从这一刻重画")

    def test_mass_slider_is_logarithmic_and_rebases(self) -> None:
        self.view._select_star(1)
        for mass in (MIN_MASS, 0.01, 1.0, 5.0):
            with self.subTest(mass=mass):
                self.assertAlmostEqual(
                    self.view._scale_to_mass(self.view._mass_to_scale(mass)), mass, places=9)
        before = float(self.view.body.mass[1])
        self.view._on_mass_scale("0.8")
        self.assertNotAlmostEqual(float(self.view.body.mass[1]), before)
        self.assertEqual(len(self.view._energy_history), 1)

    def test_cycle_selection_and_clear(self) -> None:
        self.view._cycle_selection(1)
        self.assertEqual(self.view._selected, 0)
        self.view._cycle_selection(1)
        self.assertEqual(self.view._selected, 1)
        self.view._cycle_selection(-1)
        self.assertEqual(self.view._selected, 0)
        self.view._select_star(None)
        self.assertIsNone(self.view._selected)

    def test_energy_curve_fills_the_plot_width_after_the_window_slides(self) -> None:
        """回归：窗口滑到最后时，曲线也必须铺满整幅图，而不是缩在右边一角。

        以前横轴固定从 t = 0 起算，而历史只保留最近一段 —— 于是曲线被越挤越靠右。
        现在横轴映射的是"保留下来的这一段"，所以无论历史多长，左端都应当贴着 y 轴。
        """
        base = self.view._curve_base
        count = 1600                                   # = CURVE_HISTORY_MAX：窗口已经滑到底
        self.view._energy_history = [
            (100.0 + index * 0.024, base + (1e-6 if index % 2 else -1e-6))
            for index in range(count)
        ]
        self.view._update_energy_curve()
        items = self.view.curve.find_all()
        polyline = max(items, key=lambda item: len(self.view.curve.coords(item)))
        x0, _y0, x1, _y1 = self.view.curve.bbox(polyline)
        width = max(self.view.curve.winfo_width(), 160)
        self.assertLess(x0, width * 0.25,
                        f"曲线左端应当贴着 y 轴（x0 = {x0}，画布宽 {width}）")
        self.assertGreater(x1, width * 0.75,
                           f"曲线右端应当到横轴末端（x1 = {x1}，画布宽 {width}）")


if __name__ == "__main__":
    unittest.main()
