"""Mandelbrot 集内核：逃逸时间、对称性、解析子集、视图几何、面积估计。

这里的断言分三类，各自的"该有多严"不一样：

* **精确结论**（已知点的归属、共轭对称逐点相等、|c| > 2 必逃逸、解析子集 ⊆ M）——
  它们是数学事实、与实现细节无关，所以要求严格相等，容差只留给浮点；
* **几何恒等式**（屏幕像素反查与网格同式、"点哪放大哪"的锚点不动点、屏幕序是翻转的数学序）
  —— 这是"界面点到的格子"与"内核算的格子"必须对上的地方，错了会一路偏到画布外；
* **统计量与参数换算**（面积估计随迭代上限收敛、倍率与跨度互为对数）——
  只断单调趋势与量级，具体数字钉在 ``tests/golden/mandelbrot.txt`` 里。

**为什么不断言"某一处放大 10 倍长什么样"**：那是实现细节；要钉的是"放大之后锚点没动、
跨度按倍率缩小、像素网格跟着换了取景框"这三件可验证的事。
"""

from __future__ import annotations

import gc
import json
import time
import unittest

import numpy as np

from prismath.models.mandelbrot.model import (
    AREA_REFERENCE,
    AUTO_ITERATIONS_BASE,
    AUTO_ITERATIONS_SLOPE,
    DEFAULT_ITERATIONS,
    DEFAULT_PIXELS,
    DEFAULT_SPAN,
    INTERIOR_BIG_DISK,
    INTERIOR_BIG_DISK_MAX_X,
    INTERIOR_DISKS,
    LEVELS,
    MAX_ITERATIONS,
    MAX_MAGNIFICATION,
    MAX_PIXELS,
    MAX_SPAN,
    MIN_SPAN,
    PALETTES,
    Mandelbrot,
    Viewport,
    complex_grid,
    escape_counts,
    in_main_bulb,
    interior_mask,
    iterations_for,
    make_viewport,
    mandelbrot_levels,
    resample_to,
    scan_iterations,
)
from prismath.models.mandelbrot.spec import (
    PALETTE_LABELS,
    build_mandelbrot,
    handle,
    options_from_ui,
    payload_for,
)
from prismath.models import mandelbrot  # noqa: F401  导入即注册模型
from prismath.registry import all_models, get, load_models

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


# ----------------------------------------------------------------------
# 逃逸时间
# ----------------------------------------------------------------------
class EscapeTimeTest(unittest.TestCase):
    """逃逸判据本身：已知点、迭代步数、平滑值、色带下标。"""

    def _counts(self, points, max_iter=200):
        counts, smooth = escape_counts(np.asarray(points, dtype=complex), max_iter)
        return counts, smooth

    def test_known_points_inside_the_set(self) -> None:
        """0、-1、-0.5+0.5i、尖点 0.25、最左端 -2 都在 M 里（迭代到上限仍未逃逸）。"""
        for c in (0j, -1 + 0j, -0.5 + 0.5j, 0.25 + 0j, -2 + 0j):
            with self.subTest(c=c):
                counts, smooth = self._counts([c])
                self.assertEqual(int(counts[0]), 0, f"{c} 不应逃逸")
                self.assertEqual(float(smooth[0]), 200.0, "未逃逸点的平滑值应等于迭代上限")

    def test_known_points_outside_the_set(self) -> None:
        """1 与 0.5 都会逃逸；c = 1 的轨道 0 → 1 → 2 → 5 给出确定的第 3 步。"""
        counts, _smooth = self._counts([1 + 0j, 0.5 + 0j])
        self.assertEqual(int(counts[0]), 3, "c = 1 应当第 3 步逃逸（0 → 1 → 2 → 5）")
        self.assertEqual(int(counts[1]), 5, "c = 0.5 应当第 5 步逃逸")

    def test_smooth_value_sits_just_below_the_escape_step(self) -> None:
        """平滑迭代数落在 (n−1, n+1) 里 —— 它就是把整数台阶之间的差补上。

        上界严格小于 n+1 是因为逃逸点的模一定已经超过半径 R；下界由"逃逸前一步
        |z| ≤ R² + 2"给出（见模块说明的推导）。
        """
        points = np.array([complex(x, y) for x in (-1.8, -1.0, -0.5, 0.2, 0.6) for y in (-0.7, 0.0, 0.7)])
        counts, smooth = self._counts(points, 200)
        escaped = counts > 0
        self.assertTrue(escaped.any(), "这组点里应当有逃逸的")
        n = counts[escaped].astype(float)
        mu = smooth[escaped]
        self.assertTrue(np.all(mu < n + 1.0), "平滑值不应超过 n+1")
        self.assertTrue(np.all(mu > n - 1.0), "平滑值不应低于 n−1")

    def test_levels_are_in_range_and_inside_is_darkest(self) -> None:
        model = Mandelbrot(max_iter=100, pixels=80)
        counts, smooth = escape_counts(model.points(), model.max_iter)
        levels = mandelbrot_levels(smooth, model.max_iter, counts > 0)
        self.assertEqual(levels.shape, counts.shape)
        self.assertGreaterEqual(int(levels.min()), 0)
        self.assertLess(int(levels.max()), LEVELS)
        self.assertEqual(int(np.count_nonzero(levels[counts == 0] != 0)), 0,
                         "集合内部的色带下标必须固定为 0（最暗）")
        self.assertGreater(int(levels[counts > 0].max()), 0,
                           "逃逸点里应当有亮起来的（否则色带全黑）")

    def test_empty_input_is_safe(self) -> None:
        counts, smooth = escape_counts(np.empty(0, dtype=complex), 50)
        self.assertEqual(counts.size, 0)
        self.assertEqual(smooth.size, 0)


# ----------------------------------------------------------------------
# 对称性与解析子集
# ----------------------------------------------------------------------
class SymmetryTest(unittest.TestCase):
    """实轴对称（逐位精确）与"解析子集一定在 M 里"这两条护栏。"""

    def test_grid_mirror_is_exact_negation(self) -> None:
        """网格构造本身的护栏：轴对齐时上下两行的虚部**严格**互为相反数。

        共轭对称的逐点比对之所以能要求"严格相等"，全靠这一条（坐标是精确相反数 →
        共轭轨道逐位镜像）。
        """
        grid = complex_grid(Viewport(0.0, 0.0, 2.4), rows=301, cols=201)
        # 实部是列坐标（每行相同），虚部是行坐标 —— 上下翻转让虚部取负、实部不变
        self.assertTrue(np.array_equal(grid.real[::-1, :], grid.real), "实部不该随行号变化")
        self.assertTrue(np.array_equal(grid.imag[::-1, :], -grid.imag), "虚部应当是精确相反数")

    def test_conjugate_symmetry_is_bit_exact(self) -> None:
        """c 与它的共轭：整数迭代数逐点相等（不是"近似"）。"""
        grid = complex_grid(Viewport(0.0, 0.0, 2.4), rows=301, cols=201)
        counts, smooth = escape_counts(grid, 200)
        self.assertEqual(int(np.count_nonzero(counts != counts[::-1, :])), 0,
                         "共轭轨道的逃逸步数必须完全相同")
        self.assertTrue(np.array_equal(smooth, smooth[::-1, :]), "平滑值也应逐位镜像")

    def test_render_symmetry_shortcut_preserves_full_field(self) -> None:
        """中心在实轴时只算半幅也必须与完整迭代逐像素一致。"""
        model = Mandelbrot(center_x=-0.6, center_y=0.0, span=3.2,
                           max_iter=180, pixels=73, aspect=0.71)
        field = model.render()
        full_counts, full_smooth = escape_counts(model.points(), model.max_iter)
        self.assertTrue(np.array_equal(field.counts, full_counts))
        self.assertTrue(np.array_equal(field.smooth, full_smooth))

    def test_analytic_subset_never_escapes(self) -> None:
        """主心形 + 周期 2 圆盘整体在 M 里：解析判为内的点，逃逸判据不能说它跑了。"""
        grid = complex_grid(Viewport(-0.6, 0.0, 3.2), rows=240, cols=320)
        analytic = in_main_bulb(grid)
        self.assertGreater(int(np.count_nonzero(analytic)), 100, "解析判据应当圈出一大片")
        counts, _smooth = escape_counts(grid, 200)
        self.assertEqual(int(np.count_nonzero(analytic & (counts > 0))), 0,
                         "解析内点被逃逸判据判成发散了 —— 逃逸迭代写错了")

    def test_analytic_known_points(self) -> None:
        """解析判据自己的已知点（它是**子集**判据，所以在边界点上也说得通）。"""
        self.assertTrue(bool(in_main_bulb(0j)), "0 在主心形里")
        self.assertTrue(bool(in_main_bulb(-1 + 0j)), "-1 在周期 2 圆盘里")
        self.assertTrue(bool(in_main_bulb(0.25 + 0j)), "0.25 是主心形的尖点（含边界）")
        self.assertFalse(bool(in_main_bulb(1 + 0j)), "1 不在两个吸引域里")
        self.assertFalse(bool(in_main_bulb(-2 + 0j)), "-2 属于 M，但不在解析子集里（子集判据）")

    def test_points_outside_radius_two_all_escape(self) -> None:
        """c ∈ M ⇒ |c| ≤ 2，所以 |c| > 2 的点必须全部逃逸。"""
        grid = complex_grid(Viewport(-0.6, 0.0, 3.2), rows=240, cols=320)
        outside = grid[np.abs(grid) > 2.0]
        self.assertGreater(outside.size, 1000)
        counts, _smooth = escape_counts(outside, 200)
        self.assertEqual(int(np.count_nonzero(counts == 0)), 0, "|c| > 2 的点不该有未逃逸的")


# ----------------------------------------------------------------------
# 直接判内部（提速）+ 迭代上限自适应
# ----------------------------------------------------------------------
class InteriorSkipTest(unittest.TestCase):
    """"不用迭代就知道在集合内"那批判据：**准不准**（覆盖到的点一个都不能逃逸）。"""

    def _sample_disk(self, cx: float, cy: float, radius: float, n: int = 40):
        """圆盘内的采样点与它的掩码（注意：要按**圆盘**取样，不是外接正方形）。"""
        xs = np.linspace(cx - radius, cx + radius, n)
        ys = np.linspace(cy - radius, cy + radius, n)
        grid = xs[None, :] + 1j * ys[:, None]
        disk = (grid.real - cx) ** 2 + (grid.imag - cy) ** 2 <= radius * radius
        return grid, disk

    def test_every_disk_is_really_inside(self) -> None:
        """每个内切圆盘都要真的在集合内 —— 圆盘不能凭印象抄，得逐个验证。

        取**圆盘内**的采样点用朴素迭代（不跳过内部）跑 2000 次：必须一个都不逃逸。
        这是那条提速路径的安全底线：判据宁可少覆盖，不能误判（误判会把边界画成黑的）。
        """
        for cx, cy, radius in INTERIOR_DISKS:
            with self.subTest(disk=(cx, cy, radius)):
                grid, disk = self._sample_disk(cx, cy, radius)
                counts, _smooth = escape_counts(grid, 2000, skip_interior=False)
                bad = int(np.count_nonzero(disk & (counts > 0)))
                self.assertEqual(bad, 0, f"圆盘 ({cx}, {cy}, r={radius}) 里有 {bad} 个逃逸点")

    def test_big_disk_needs_its_x_limit(self) -> None:
        """大圆盘只在 ``x ≤ 0.1`` 那一侧成立：另一侧**确实**有会逃逸的点（所以要那个条件），
        而判据本身只会圈住真的属于集合内的点。"""
        cx, cy, radius = INTERIOR_BIG_DISK
        grid, disk = self._sample_disk(cx, cy, radius, n=60)
        outside_limit = disk & (grid.real > INTERIOR_BIG_DISK_MAX_X)
        counts, _smooth = escape_counts(grid, 2000, skip_interior=False)
        self.assertGreater(int(np.count_nonzero(outside_limit & (counts > 0))), 0,
                           "x > 0.1 那一侧本来就有点会逃逸 —— 所以大圆盘必须带这个限制")
        mask = interior_mask(grid)
        claimed = int(np.count_nonzero(mask))
        self.assertGreater(claimed, 100, "判据应当盖住一大片")
        self.assertEqual(int(np.count_nonzero(mask & (counts > 0))), 0,
                         "判为内部的点里混进了会逃逸的")

    def test_skip_interior_changes_nothing(self) -> None:
        """**等价性护栏**：跳内部与不跳内部，逐点迭代数必须完全一致。

        判据只对"本来就会被判为集合内"的点生效（那些点 ``counts == 0``），所以打开它
        不该改变任何像素的结果 —— 这条一旦变红，说明判据圈到了集合外。
        """
        views = (
            ("默认取景", Viewport(-0.6, 0.0, 3.2), 200),
            ("海马谷", Viewport(-0.743643887, 0.131825904, 0.05), 400),
            ("深放大", Viewport(-0.743643887, 0.131825904, 0.0002), 400),
            ("远处空场", Viewport(3.0, 2.0, 1.0), 200),
        )
        for label, view, limit in views:
            with self.subTest(view=label):
                points = complex_grid(view, 90, 120)
                fast, fast_smooth = escape_counts(points, limit)
                naive, naive_smooth = escape_counts(points, limit, skip_interior=False)
                self.assertTrue(np.array_equal(fast, naive),
                                f"{label}：跳过内部改变了整数迭代数")
                self.assertTrue(np.array_equal(fast_smooth, naive_smooth),
                                f"{label}：跳过内部改变了平滑迭代数")

    def test_analytic_inside_is_reported(self) -> None:
        """渲染结果要报出"有多少像素是判据直接判的"（界面与文档里的"省了多少"）。"""
        field = Mandelbrot(max_iter=200, pixels=200).render()
        self.assertGreater(field.analytic_inside, 0)
        self.assertLessEqual(field.analytic_inside, field.inside_count)
        self.assertEqual(field.as_dict()["analyticInside"], field.analytic_inside)
        far = Mandelbrot(center_x=4.0, center_y=4.0, span=0.5, max_iter=200, pixels=120).render()
        self.assertEqual(far.analytic_inside, 0, "空场上不该有解析判据命中")

    def test_interior_mask_can_turn_off_the_disks(self) -> None:
        """``disks=False`` 只留教科书判据（主心形 + 周期 2）—— 用来对照覆盖面。"""
        points = complex_grid(Viewport(-0.6, 0.0, 3.2), 60, 80)
        full = interior_mask(points)
        basic = interior_mask(points, disks=False)
        self.assertTrue(np.all(basic <= full), "额外的圆盘只该让覆盖面变大")
        self.assertLess(int(np.count_nonzero(basic)), int(np.count_nonzero(full)))


class AutoIterationsTest(unittest.TestCase):
    """迭代上限随放大自适应（``max_iter = 0`` = 自动）。"""

    def test_default_view_keeps_the_base_value(self) -> None:
        self.assertEqual(iterations_for(DEFAULT_SPAN), DEFAULT_ITERATIONS)
        self.assertEqual(Mandelbrot(max_iter=0).max_iter, DEFAULT_ITERATIONS)

    def test_grows_with_zoom_and_is_capped(self) -> None:
        """放大越深给得越多，并且不会超过 ``MAX_ITERATIONS``。"""
        previous = 0
        for mag in (0, 2, 4, 6, 8, 12, 24):
            with self.subTest(magnification=mag):
                limit = iterations_for(DEFAULT_SPAN / (2.0 ** mag))
                self.assertGreaterEqual(limit, previous)
                self.assertLessEqual(limit, MAX_ITERATIONS)
                previous = limit
        self.assertGreater(iterations_for(DEFAULT_SPAN / 8.0), iterations_for(DEFAULT_SPAN))
        self.assertEqual(iterations_for(MIN_SPAN), MAX_ITERATIONS)
        # 规则本身：base · 2**(slope · mag)
        self.assertAlmostEqual(
            iterations_for(DEFAULT_SPAN / 4.0),
            round(AUTO_ITERATIONS_BASE * 2.0 ** (AUTO_ITERATIONS_SLOPE * 2.0)), delta=1)

    def test_wide_view_does_not_shrink_below_base(self) -> None:
        """比默认取景还宽（负的放大倍率）时不该把上限压到基准值以下。"""
        self.assertEqual(iterations_for(DEFAULT_SPAN * 4.0), DEFAULT_ITERATIONS)

    def test_explicit_value_still_wins(self) -> None:
        self.assertEqual(Mandelbrot(max_iter=777).max_iter, 777)
        self.assertEqual(Mandelbrot(span=0.01, max_iter=1500).max_iter, 1500)


# ----------------------------------------------------------------------
# 视窗几何
# ----------------------------------------------------------------------
class ViewportTest(unittest.TestCase):
    """取景框与像素：反查、缩放、倍率。"""

    def test_pixel_matches_grid_construction(self) -> None:
        """屏幕序的 (行, 列) 与数学序网格**逐点同式**（差一个上下翻转）。

        界面点击走 :meth:`Viewport.pixel`，内核算的是 :func:`complex_grid` ——
        两者一旦不同式，"点哪放大哪"就会偏掉半个像素乃至整行。
        """
        view = Viewport(-0.6, 0.1, 3.2)
        rows, cols = 27, 41
        grid = complex_grid(view, rows, cols)
        for row, col in ((0, 0), (rows - 1, cols - 1), (5, 7), (rows // 2, cols // 2)):
            with self.subTest(row=row, col=col):
                self.assertEqual(grid[rows - 1 - row, col], view.pixel(row, col, rows, cols))

    def test_pixel_corners(self) -> None:
        """第 0 行在顶部：左上角的虚部最大、实部最小（像素中心，不是格点）。"""
        view = Viewport(0.0, 0.0, 4.0)
        rows, cols = 3, 5
        top_left = view.pixel(0, 0, rows, cols)
        bottom_right = view.pixel(rows - 1, cols - 1, rows, cols)
        self.assertLess(top_left.real, 0.0)
        self.assertGreater(top_left.imag, 0.0)
        self.assertGreater(bottom_right.real, 0.0)
        self.assertLess(bottom_right.imag, 0.0)

    def test_height_keeps_square_pixels(self) -> None:
        """虚部跨度 = 实部跨度 × 行数 / 列数（换分辨率不会把画面拉扁）。"""
        view = Viewport(0.0, 0.0, 3.2)
        rows, cols = 300, 400
        dx = view.span / cols
        dy = view.height(rows, cols) / rows
        self.assertAlmostEqual(dx, dy, places=15)

    def test_zoom_keeps_anchor_at_same_relative_position(self) -> None:
        """"点哪放大哪"的严格说法：锚点在视窗里的相对位置不变。"""
        view = Viewport(-0.6, 0.0, 3.2)
        anchor = complex(-0.743643887, 0.131825904)
        zoomed = view.zoomed(2.0, anchor)
        for old, new, point in ((view.center_x, zoomed.center_x, anchor.real),
                                (view.center_y, zoomed.center_y, anchor.imag)):
            was = (point - old) / view.span
            now = (point - new) / zoomed.span
            self.assertAlmostEqual(was, now, places=12)
        self.assertAlmostEqual(zoomed.span, view.span / 2.0, places=15)

    def test_zoom_is_clamped_at_both_ends(self) -> None:
        """放大与缩小都夹在允许区间里：倍率超出时不至于把 span 弄成 0 或 inf。"""
        view = Viewport(-0.6, 0.0, 3.2)
        self.assertAlmostEqual(view.zoomed(1e12).span, MIN_SPAN, places=15)
        self.assertAlmostEqual(view.zoomed(1e-12).span, MAX_SPAN, places=3)
        self.assertAlmostEqual(view.zoomed(1.0).span, view.span, places=15)

    def test_resample_to_identity_when_view_unchanged(self) -> None:
        """取景没变时重采样是恒等映射（缩放预览不会无端"抖"一格）。"""
        view = Viewport(-0.6, 0.0, 3.2)
        rows, cols = 37, 53
        levels = (np.arange(rows * cols) % 7).reshape(rows, cols)
        out = resample_to(levels, view, view, rows, cols)
        self.assertTrue(np.array_equal(out, levels))

    def test_resample_to_is_nearest_neighbour(self) -> None:
        """最近邻重采样：输出的每个值都来自输入（不凭空造出新颜色）。"""
        source = Viewport(-0.6, 0.0, 3.2)
        levels = (np.arange(40 * 60) % 11).reshape(40, 60)
        for target in (source.zoomed(4.0), source.zoomed(0.25),
                       Viewport(-0.7, 0.1, 0.4)):
            with self.subTest(span=target.span):
                out = resample_to(levels, source, target, 40, 60)
                self.assertEqual(out.shape, levels.shape)
                self.assertTrue(set(np.unique(out)) <= set(np.unique(levels)))

    def test_resample_to_keeps_the_anchor_pixel(self) -> None:
        """"点哪放大哪"的预览版：锚点那一格在新图里还是原来那一格的值。"""
        source = Viewport(-0.6, 0.0, 3.2)
        rows, cols = 40, 60
        levels = (np.arange(rows * cols) % 13).reshape(rows, cols)
        row, col = 12, 30
        anchor = source.pixel(row, col, rows, cols)
        out = resample_to(levels, source, source.zoomed(2.0, anchor), rows, cols)
        self.assertEqual(int(out[row, col]), int(levels[row, col]))

    def test_resample_to_rejects_wrong_shape(self) -> None:
        with self.assertRaises(ValueError):
            resample_to(np.zeros((4, 5), dtype=int), Viewport(), Viewport(), 6, 5)

    def test_magnification_is_log2_of_span(self) -> None:
        for mag in (0.0, 1.0, 6.0, MAX_MAGNIFICATION):
            with self.subTest(mag=mag):
                view = make_viewport(0.0, 0.0, DEFAULT_SPAN / (2.0 ** mag))
                self.assertAlmostEqual(view.magnification, mag, places=10)

    def test_illegal_input_falls_back(self) -> None:
        """乱七八糟的输入不该把视窗弄坏（终端里给错参数时也要能画出来）。"""
        view = make_viewport("abc", None, 0.0)
        self.assertEqual(view.center_x, Viewport().center_x)
        self.assertEqual(view.center_y, Viewport().center_y)
        self.assertAlmostEqual(view.span, MIN_SPAN, places=15)


# ----------------------------------------------------------------------
# 面积估计
# ----------------------------------------------------------------------
class AreaTest(unittest.TestCase):
    """像素计数是"用有限网格量分形"，所以只断趋势与量级。"""

    def test_area_decreases_with_iteration_limit(self) -> None:
        """上限调高只会把"其实会逃逸"的点剔出去，于是面积估计单调下降。"""
        areas = [result.area for _limit, result in scan_iterations([20, 100, 500], pixels=160)]
        self.assertGreater(areas[0], areas[1])
        self.assertGreater(areas[1], areas[2])

    def test_area_approaches_the_reference_value(self) -> None:
        """160×120 采样、上限 1000：估计值应当已经贴近数值真值 ≈ 1.5066。"""
        result = scan_iterations([1000], pixels=160)[0][1]
        self.assertLess(abs(result.area - AREA_REFERENCE), 0.03,
                        f"面积估计 {result.area:.4f} 偏离真值太远")

    def test_ratio_and_counts_agree(self) -> None:
        field = Mandelbrot(max_iter=100, pixels=120, aspect=0.75).render()
        total = field.rows * field.cols
        self.assertEqual(field.inside_count + field.escaped_count, total)
        self.assertAlmostEqual(field.inside_ratio, field.inside_count / total, places=12)
        self.assertAlmostEqual(field.area, field.inside_ratio * field.viewport.area(
            field.rows, field.cols), places=12)

    def test_level_values_are_screen_order(self) -> None:
        """payload 给画布的 ``values`` 是**屏幕序**（第 0 行 = 顶部）。"""
        field = Mandelbrot(max_iter=100, pixels=60, aspect=0.5).render()
        values = field.level_values()
        self.assertEqual(len(values), field.rows * field.cols)
        top_row = values[:field.cols]
        math_top = np.flipud(field.levels)[0].tolist()
        self.assertEqual(top_row, math_top)

    def test_values_are_flipped_to_screen_order(self) -> None:
        """屏幕序第 0 行对应数学序最后一行（翻转不能忘，忘了整幅图就上下颠倒）。"""
        field = Mandelbrot(max_iter=200, pixels=80, aspect=1.0).render()
        values = np.asarray(field.level_values(), dtype=int).reshape(field.rows, field.cols)
        self.assertTrue(np.array_equal(values, np.flipud(field.levels)))


# ----------------------------------------------------------------------
# 参数换算与数据级契约
# ----------------------------------------------------------------------
class SpecContractTest(unittest.TestCase):
    """``spec`` 那一层的换算与 payload：后端（终端 / 网页 / 通用视图）走的就是它。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = get("mandelbrot")

    def _params(self, **overrides):
        base = {param.key: param.default for param in self.spec.params}
        base.update(overrides)
        return base

    def test_view_name_and_registry(self) -> None:
        load_models()
        self.assertEqual(self.spec.view, "mandelbrot")
        self.assertIn("mandelbrot", {spec.key for spec in all_models()})

    def test_every_action_is_handled(self) -> None:
        for action in self.spec.actions:
            with self.subTest(action=action.key):
                payload = handle(action.key, self._params(), {})
                self.assertTrue(str(payload["view"]).startswith("mandelbrot-"))

    def test_unknown_action_raises(self) -> None:
        with self.assertRaises(ValueError):
            handle("teleport", self._params(), {})

    def test_payload_is_json_serializable_and_complete(self) -> None:
        payload = handle("render", self._params(iterations=60, pixels=80), {})
        text = json.dumps(payload, ensure_ascii=False)      # 网页 / 通用视图要能序列化
        self.assertIn("values", payload)
        self.assertEqual(len(payload["values"]), payload["rows"] * payload["cols"])
        self.assertEqual(payload["view"], f"mandelbrot-{payload['palette']}")
        self.assertIn(payload["palette"], PALETTES)
        self.assertTrue(text)
        for key in ("centerX", "centerY", "span", "magnification", "insideRatio",
                    "area", "sizeText", "viewText"):
            self.assertIn(key, payload)

    def test_palette_label_is_translated(self) -> None:
        """界面给的是中文标签，模型内部只认名字。"""
        for name, label in PALETTE_LABELS.items():
            with self.subTest(palette=name):
                self.assertEqual(options_from_ui(self._params(palette=label))["palette"], name)
                self.assertEqual(options_from_ui(self._params(palette=name))["palette"], name)
        self.assertEqual(options_from_ui(self._params(palette="不存在"))["palette"], "magma")

    def test_iterations_zero_means_auto(self) -> None:
        """``iterations = 0``（界面上的默认）由内核按放大倍率补：放大越深，报出来的上限越大。"""
        self.assertEqual(self._params()["iterations"], 0, "默认应当是「自动」")
        near = handle("render", self._params(), {})
        far = handle("render", {**self._params(), "magnification": 6.0}, {})
        self.assertEqual(near["maxIter"], DEFAULT_ITERATIONS)
        self.assertGreater(far["maxIter"], near["maxIter"])
        explicit = options_from_ui({**self._params(), "iterations": 333})
        self.assertEqual(build_mandelbrot(explicit).max_iter, 333)

    def test_magnification_becomes_span(self) -> None:
        span = options_from_ui(self._params(magnification=6.0))["span"]
        self.assertAlmostEqual(span, DEFAULT_SPAN / 64.0, places=12)

    def test_zoom_actions_move_the_window(self) -> None:
        """放大 2 倍后跨度减半；重置视图回到默认取景。"""
        base = handle("render", self._params(), {})
        zoomed = handle("zoom_in", self._params(), {})
        self.assertAlmostEqual(zoomed["span"], base["span"] / 2.0, places=12)
        self.assertAlmostEqual(zoomed["magnification"], base["magnification"] + 1.0, places=12)
        out = handle("zoom_out", self._params(), {})
        self.assertAlmostEqual(out["span"], base["span"] * 2.0, places=12)
        deep = self._params(center_x=-0.743, center_y=0.131, magnification=10.0)
        back = handle("reset_view", deep, {})
        self.assertAlmostEqual(back["span"], DEFAULT_SPAN, places=12)
        self.assertAlmostEqual(back["magnification"], 0.0, places=12)

    def test_params_are_clamped(self) -> None:
        """越界参数被夹回允许范围（界面上的滑块 / 网页表单都可能传进来）。"""
        opts = options_from_ui({"iterations": 10 ** 9, "pixels": 1,
                                "magnification": 10 ** 9, "center_x": 10 ** 9,
                                "center_y": -10 ** 9})
        self.assertLessEqual(opts["span"], MIN_SPAN * 1.000001)
        self.assertEqual(opts["pixels"], 60)
        self.assertGreater(opts["iterations"], DEFAULT_ITERATIONS)
        model = build_mandelbrot(opts)
        self.assertLessEqual(model.max_iter, 4000)

    def test_factory_and_handler_agree_on_the_view(self) -> None:
        """对象级契约（factory）与数据级契约（handler）必须给出同一个取景。"""
        opts = options_from_ui(self._params(magnification=3.0, center_x=-1.0, center_y=0.25))
        model = build_mandelbrot(opts)
        field = model.render()
        payload = payload_for(field, opts["palette"])
        direct = handle("render", self._params(magnification=3.0, center_x=-1.0,
                                              center_y=0.25), {})
        self.assertAlmostEqual(payload["span"], direct["span"], places=15)
        self.assertAlmostEqual(payload["centerX"], direct["centerX"], places=15)
        self.assertEqual(payload["inside"], direct["inside"])

    def test_headless_default_resolution_is_modest(self) -> None:
        """无头后端（网页 / 通用视图 / 终端）用默认分辨率：一次渲染的开销与像素数成正比。

        桌面视图不在这条路上 —— 它按画布大小渲染（分辨率不进 ``params``），所以两边
        各付各的成本。
        """
        field = build_mandelbrot(options_from_ui(self._params())).render()
        self.assertEqual(field.max_iter, DEFAULT_ITERATIONS)
        self.assertEqual(field.cols, DEFAULT_PIXELS)
        self.assertLessEqual(field.rows * field.cols, 200_000)


# ----------------------------------------------------------------------
# 桌面视图交互（点哪放大哪）
# ----------------------------------------------------------------------
@unittest.skipUnless(TK_OK, "没有可用的图形环境（tk.Tk() 起不来）")
class ViewInteractionTest(unittest.TestCase):
    """把"用户在画布上点一下"这条路走通：预览立刻画、清晰图后台换、取景写回表单。

    视图默认按**画布大小**渲染（几十万像素），测试里把上限压小：交互路径与分辨率无关，
    没必要让每条用例都等一整屏。渲染在后台线程里做，所以断言前要把事件循环"泵"起来。
    """

    def setUp(self) -> None:
        from prismath.ui.tk.kit import discover_views
        from prismath.ui.tk.shell import DesktopShell
        from prismath.ui.tk.theme import install_theme

        discover_views()
        self.root = tk.Tk()
        install_theme(self.root)
        self.shell = DesktopShell(self.root, get("mandelbrot"))
        self.root.update()
        self.view = self.shell.view
        self.view.MAX_RENDER_PIXELS = 60_000       # 见类说明：只压测试里的规模
        self.view.run_action("render")
        self.assertTrue(self._wait_settled(), "首屏渲染没能在超时前完成")

    def tearDown(self) -> None:
        if self.shell is not None and self.shell.view is not None:
            self.shell.view.shutdown()
        self.root.destroy()
        # 每条用例都创建独立 Tcl 解释器；主动在主线程清理控件引用与循环引用，
        # 避免下一条用例的计算线程触发 GC，跨线程销毁上一条用例的 Tcl 对象。
        self.view = self.shell = self.root = None
        gc.collect()

    def _wait_sharp(self, timeout: float = 30.0) -> bool:
        """泵事件循环，直到后台算好的那张**清晰**图被采用（预览不算）。"""
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            self.root.update()
            last = self.view._last
            if isinstance(last, dict) and "error" not in last and not last.get("preview"):
                return True
            time.sleep(0.005)
        return False

    def _wait_settled(self, timeout: float = 30.0) -> bool:
        """等这一轮渲染**定下来**：清晰图已采用，而且它就是按当前画布尺寸渲染的。

        （只等"清晰图"不够：窗口还没布局出来时的第一张会按默认尺寸渲，
        画出来后 <Configure> 又会让它重渲一次 —— 那两张都是"清晰图"。）
        """
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            self.root.update()
            last = self.view._last
            if (self.view._render_job is None and isinstance(last, dict)
                    and "error" not in last and not last.get("preview")
                    and (int(last["cols"]), int(last["rows"])) == self.view._render_size()):
                return True
            time.sleep(0.005)
        return False

    # ---------------- 首屏：铺满画布 ----------------
    def test_view_renders_a_field_that_fills_the_canvas(self) -> None:
        """首屏：图像按画布大小渲染并**铺满**（"图太小"那个问题的回归测试）。"""
        view = self.view
        self.assertTrue(self._wait_settled(), "渲染没有在超时前定下来")
        self.assertIsNotNone(view)
        self.assertEqual(view._chart.kind, "grid")
        self.assertTrue(view._chart.clickable)
        self.assertTrue(str(view._last["view"]).startswith("mandelbrot-"))

        canvas_w, canvas_h = view.canvas.winfo_width(), view.canvas.winfo_height()
        boxes = [view.canvas.bbox(item) for item in view.canvas.find_all()
                 if view.canvas.type(item) == "image"]
        self.assertEqual(len(boxes), 1, "连续场应当就是一张位图")
        x0, y0, x1, y1 = boxes[0]
        self.assertGreater((x1 - x0) / canvas_w, 0.9, "图像宽度应当铺满画布")
        self.assertGreater((y1 - y0) / canvas_h, 0.9, "图像高度应当铺满画布")

        # 清晰图会被记下来供下次缩放做预览，且形状与 payload 一致
        self.assertIsNotNone(view._values)
        self.assertEqual(view._values.shape,
                         (int(view._last["rows"]), int(view._last["cols"])))

    def test_render_size_follows_the_canvas(self) -> None:
        """渲染分辨率跟着画布走（等比、两道上限），不再是写死的参数。"""
        from prismath.ui.tk.kit import FIELD_PAD

        view = self.view
        canvas_w = view.canvas.winfo_width()
        canvas_h = view.canvas.winfo_height()
        view.MAX_RENDER_PIXELS = 10 ** 9                    # 先抬掉总数上限
        cols, rows = view._render_size()
        # 单边还有 MAX_PIXELS 这道上限（沉浸模式下画布很宽，会撞上它）
        self.assertEqual(cols, min(canvas_w - 2 * FIELD_PAD, MAX_PIXELS))
        self.assertAlmostEqual(rows / cols,
                               (canvas_h - 2 * FIELD_PAD) / (canvas_w - 2 * FIELD_PAD),
                               delta=0.02)

        view.MAX_RENDER_PIXELS = 40_000                     # 总数上限要压得住
        cols, rows = view._render_size()
        self.assertLessEqual(cols * rows, 45_000)
        self.assertAlmostEqual(rows / cols, canvas_h / canvas_w, delta=0.02,
                               msg="压上限也要保持画布的高宽比，否则图像会被拉扁")

    # ---------------- 点哪放大哪：预览 + 细化 ----------------
    def test_click_shows_a_preview_then_the_sharp_image(self) -> None:
        """点一下：先拿到新取景的**预览**（几毫秒，统计量先空着），随后换成清晰的一张。"""
        from prismath.models.mandelbrot.views.tk import CLICK_ZOOM

        before = dict(self.view._last)
        rows, cols = int(before["rows"]), int(before["cols"])
        row, col = rows // 3, cols // 4

        start = time.perf_counter()
        self.assertIsNone(self.view._on_cell_click(row, col, True), "预览由视图自己画")
        preview = self.view._last
        self.assertTrue(preview.get("preview"), "点完应当先看到预览")
        self.assertAlmostEqual(preview["span"], before["span"] / CLICK_ZOOM, places=12)
        self.assertIsNone(preview["area"], "预览上的统计量应当是空的（这张还没算过）")
        self.assertEqual(preview["values"].shape, (rows, cols))
        self.assertLess(time.perf_counter() - start, 2.0,
                        "预览不该等后台那一整轮渲染（同步渲染才会这么慢）")

        # 锚点：预览里那一格对应的复数必须原地不动
        was = make_viewport(before["centerX"], before["centerY"], before["span"])
        now = make_viewport(preview["centerX"], preview["centerY"], preview["span"])
        a, b = was.pixel(row, col, rows, cols), now.pixel(row, col, rows, cols)
        self.assertAlmostEqual(a.real, b.real, places=12, msg="锚点的实部应当原地不动")
        self.assertAlmostEqual(a.imag, b.imag, places=12, msg="锚点的虚部应当原地不动")

        self.assertTrue(self._wait_sharp(), "后台那张清晰图没到")
        sharp = self.view._last
        self.assertFalse(sharp.get("preview"))
        self.assertAlmostEqual(sharp["span"], before["span"] / CLICK_ZOOM, places=12)
        self.assertGreater(int(sharp["inside"]), 0, "清晰图应当带着统计量")
        self.assertTrue(np.array_equal(sharp["values"], self.view._values))

    def test_chained_clicks_keep_the_zoom_maths_straight(self) -> None:
        """**曾经的真 bug**：连点两下时，预览必须以"那张清晰图自己的取景"为源。

        否则第二次预览会把老图按错的取景映射一遍 —— 画面先"飞"到别处，等清晰图到了再跳回来。
        这里不等后台那张，连点两下，检查每次报出来的跨度都对（1.5、1.5²），
        而且**那片清晰图自己的取景没有被预览改写**（它才是预览的源）。
        """
        from prismath.models.mandelbrot.views.tk import CLICK_ZOOM

        sharp_span = float(self.view._last["span"])
        rows, cols = int(self.view._last["rows"]), int(self.view._last["cols"])
        for step in range(1, 3):
            with self.subTest(step=step):
                self.view._on_cell_click(rows // 3, cols // 3, True)
                preview = self.view._last
                self.assertTrue(preview.get("preview"), "连点也应当立刻看到预览")
                self.assertAlmostEqual(float(preview["span"]),
                                       sharp_span / CLICK_ZOOM ** step, places=9)
                self.assertAlmostEqual(float(self.view._values_view.span), sharp_span,
                                       places=12, msg="清晰图的取景不该被预览改写")

    def test_drag_pans_instead_of_zooming(self) -> None:
        """左键拖动 = 平移：取景中心跟着挪、跨度不变；松手后才去算清晰图。"""
        from types import SimpleNamespace

        before = self.view._current_view()
        self.assertIsNotNone(before)
        self.view._on_canvas_click(SimpleNamespace(x=200, y=200))
        self.view._on_canvas_drag(SimpleNamespace(x=260, y=200))     # 右拖 60 像素
        self.view._on_canvas_release(SimpleNamespace(x=260, y=200))

        moved = self.view._current_view()
        self.assertAlmostEqual(moved.span, before.span, places=12, msg="平移不该改变跨度")
        self.assertLess(moved.center_x, before.center_x, msg="向右拖 = 视野向左移")
        self.assertAlmostEqual(moved.center_y, before.center_y, places=12)
        self.assertTrue(self._wait_sharp(), "松手后应当把清晰图算出来")

    def test_click_without_moving_still_zooms(self) -> None:
        """按下又松开、中间没动过 —— 那就是"点哪放大哪"，不是平移。"""
        from types import SimpleNamespace

        before = float(self.view._last["span"])
        rows, cols = int(self.view._last["rows"]), int(self.view._last["cols"])
        cell, ox, oy, _rows, _cols = self.view._grid_geom
        x, y = int(ox + cell * (cols // 2)), int(oy + cell * (rows // 2))
        self.view._on_canvas_click(SimpleNamespace(x=x, y=y))
        self.view._on_canvas_release(SimpleNamespace(x=x, y=y))
        self.assertLess(float(self.view._last["span"]), before, "单击应当放大")

    def test_undo_and_reset_keys(self) -> None:
        """退格退回上一步；``0`` 回到默认取景。"""
        before = float(self.view._last["span"])
        self.view.on_key("0")                       # 0 = 重置（不一定在默认取景上）
        self.assertTrue(self._wait_sharp(), "重置后应当重渲染")
        self.assertAlmostEqual(float(self.view._last["span"]), DEFAULT_SPAN, places=9)

        rows, cols = int(self.view._last["rows"]), int(self.view._last["cols"])
        self.view._on_cell_click(rows // 3, cols // 3, True)
        zoomed = float(self.view._last["span"])
        self.assertLess(zoomed, DEFAULT_SPAN)
        self.view.on_key("BackSpace")               # 退回上一步
        self.assertTrue(self._wait_sharp(), "退回后应当重渲染")
        self.assertAlmostEqual(float(self.view._last["span"]), DEFAULT_SPAN, places=9)
        self.assertNotEqual(float(self.view._last["span"]), zoomed)

    def test_layout_toggles_between_immersive_and_instrument(self) -> None:
        """沉浸式 <-> 仪器台：两侧栏显隐、画布变宽，**参数不丢**（不重建控件）。"""
        view = self.view
        before_span = float(view._last["span"])
        before_mag = float(view.param_value("magnification"))

        view._toggle_layout()
        self.root.update()
        self.assertFalse(view._immersive)
        self.assertTrue(view._sidebar_area.outer.winfo_ismapped(), "仪器台下参数栏要出来")
        narrow = view.canvas.winfo_width()

        view._toggle_layout()
        self.root.update()
        self.assertTrue(view._immersive)
        self.assertFalse(view._sidebar_area.outer.winfo_ismapped(), "沉浸模式下参数栏要收起来")
        self.assertGreater(view.canvas.winfo_width(), narrow, "沉浸模式下画布应当更宽")
        # 状态没丢：取景与参数都还在原地
        self.assertAlmostEqual(float(view.param_value("magnification")), before_mag, places=9)
        self.assertAlmostEqual(float(view._last["span"]), before_span, places=9)

    def test_immersive_hud_has_something_to_read(self) -> None:
        """沉浸模式下 HUD 是唯一的信息来源：画布上得有可点的提示与几行数字。"""
        self.view._toggle_layout()                  # 先切到仪器台
        self.view._toggle_layout()                  # 再切回沉浸式 → 触发一次重绘
        self.assertTrue(self._wait_settled())
        texts = [self.view.canvas.itemcget(item, "text")
                 for item in self.view.canvas.find_all()
                 if self.view.canvas.type(item) == "text"]
        joined = " ".join(texts)
        self.assertIn("参数面板", joined, "右上角要有可点的提示")
        self.assertIn("平移", joined, "底部要有手势提示")

    def test_click_writes_back_to_the_param_form(self) -> None:
        """点了之后参数表单要跟着走，否则滑块显示的位置和画面对不上。"""
        before = float(self.view.param_value("magnification"))
        self.view._on_cell_click(10, 10, True)
        preview = self.view._last
        self.assertAlmostEqual(float(self.view.param_value("magnification")),
                               float(preview["magnification"]), places=9)
        self.assertGreater(float(self.view.param_value("magnification")), before)
        self.assertAlmostEqual(float(self.view.param_value("center_x")),
                               float(preview["centerX"]), places=9)

    def test_right_click_and_wheel_zoom_out_and_in(self) -> None:
        """右键 = 缩小一倍半；滚轮 = **细步**（一格 1.25 倍），都以光标所在格为锚。"""
        from prismath.models.mandelbrot.views.tk import CLICK_ZOOM, WHEEL_STEP

        before_span = float(self.view._last["span"])
        cell, ox, oy, rows, cols = self.view._grid_geom
        x, y = int(ox + cell * (cols // 2)), int(oy + cell * (rows // 2))

        self.view.canvas.event_generate("<Button-3>", x=x, y=y)
        self.root.update()
        self.assertAlmostEqual(float(self.view._last["span"]), before_span * CLICK_ZOOM,
                               places=9)

        self.view.canvas.event_generate("<MouseWheel>", x=x, y=y, delta=120)
        self.root.update()
        self.assertAlmostEqual(float(self.view._last["span"]),
                               before_span * CLICK_ZOOM / WHEEL_STEP, places=9)

    def test_click_outside_the_image_is_ignored(self) -> None:
        self.assertIsNone(self.view._cell_at(-50, -50))
        before = float(self.view._last["span"])
        self.view._on_right_click(type("E", (), {"x": -50, "y": -50})())
        self.assertEqual(float(self.view._last["span"]), before, "画布外的点击不该缩放")


if __name__ == "__main__":                              # pragma: no cover
    unittest.main()
