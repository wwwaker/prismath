# -*- coding: utf-8 -*-
"""
Mandelbrot 集核心模型
======================

对复平面上的每一点 ``c`` 迭代

    z₀ = 0,   z_{n+1} = z_n² + c

若某个 ``z_n`` 的模超过逃逸半径 ``R``（这里取 2），轨道就发散到无穷，记下它是**第几步**
逃逸的（逃逸时间）；若迭代 ``max_iter`` 次仍未逃逸，就认为 ``c`` 属于 Mandelbrot 集

    M = { c ∈ ℂ : 序列 z_n 有界 }。

三条确定性的结论（自检与单元测试都钉住它们）
--------------------------------------------
1. **有界 ⇔ 逃逸**：``|z_n| > 2`` 之后必然发散，且 ``c ∈ M ⇒ |c| ≤ 2`` —— 所以
   ``|c| > 2`` 的点**一定**逃逸，视窗取实部 ``[-2.2, 1.0]`` 就装得下整个集合；
2. **实轴对称**：``c ∈ M ⟺ conj(c) ∈ M``。迭代式的系数全是实数，共轭轨道逐位镜像，
   于是**按整数迭代数逐点比对时严格相等**（不是"近似相等"）—— 这是本模型最好用的护栏；
3. **解析子集**：主心形（周期 1 的吸引域）与周期 2 圆盘都有闭式判据，它们整体落在 ``M`` 里，
   可以用来检查逃逸判据有没有"漏判"（把集合内的点算成逃逸）。

视图与像素
----------
视窗由 ``(center_x, center_y, span)`` 三个数确定：``span`` 是复平面上的**实部跨度**，
虚部跨度由像素尺寸按 ``span · rows / cols`` 推出 —— 于是像素永远是正方形，缩放不会变形。
``magnification = log2(DEFAULT_SPAN / span)`` 是放大倍率的对数，界面拿它当"缩放滑块"
（线性拖动 = 等比放大，而不是在 1e-6 与 3 之间做绝望的线性拖动）。

像素网格按"中心对称"的写法构造（``(i − (n−1)/2) · step``），因此**镜像的两行/两列是严格的
相反数**，上面第 2 条才能逐位精确比对。数组是数学序（第 0 行 = 最小虚部），出图前由
:meth:`MandelbrotField.level_values` 翻转成屏幕序（第 0 行 = 顶部）。

平滑逃逸时间
------------
整数迭代数是台阶状的，直接上色会出现明显的同心色环。用

    μ = n + 1 − log₂( ln|z_n| / ln R )

把台阶抹平（``z_n`` 是逃逸当时那个值），得到连续的"平滑逃逸时间"；再压成 ``0..63``
的色带下标：``level = round(sqrt(μ / max_iter) · 63)``。``sqrt`` 让边界附近挤在一起的
细节不至于糊成一个色块，而**集合内部固定为 0（最暗）** —— 于是集合是一块暗色剪影，
它的边界则被一圈亮色描出来，细节全在剪影上（这也是不断放大时最耐看的画法）。

实测（Windows / Python 3.13，中位数）
-------------------------------------
复现命令：``python -m tests.bench mandelbrot``

* 默认取景 360×270（97200 像素）× 200 次迭代 **≈ 45 ms**（波动 ±25 ms）；同一取景把上限
  提到 2000 反而只要 **≈ 50–75 ms** —— 因为"内部像素"已经被下面的解析判据整批剔掉，
  多出来的迭代上限不会再加到它们头上（判据之前是 328 ms）；
* 一大半像素属于集合的深放大视图（海马谷 360×270、宽 0.05、400 次迭代）**≈ 74 ms**
  （判据之前是 384 ms）；几乎没有内部的深放大（宽 2e-4、1000 次迭代）**≈ 170–195 ms**，
  ±70 ms 波动大、别当准数 —— 那种视图的成本全在"贴着边界、迟迟不肯逃逸"的外部位上；
* 成本与「像素数 × 迭代数」近似线性（约 **4 ns / 像素 / 次迭代**）—— 所以桌面视图的
  "按窗口大小渲染"是**拿时间换清晰度**：一屏 40 万像素、200 次迭代，内核要 ≈ 0.2 s。
  画面不会干等它：视图先用上一帧**重采样出预览**（几十毫秒），清晰的那张在后台算完换上
  （见 :mod:`prismath.models.mandelbrot.views.tk`）。

提速手段：两条**实测有效**的，一条**实测被否掉**的
---------------------------------------------------
方向是"**少算**"而不是"把 numpy 写得更花"：纯 numpy 的逐像素向量化在重负载下相对纯 Python
只有 3~6 倍（见 README 引用的对照基准），批次全量算 + 内存带宽就是天花板。于是：

1. **解析判据直接判内部**（:func:`interior_mask`，不迭代）：主心形 + 周期 2 圆盘 + 6 个
   实测验证过的内切圆盘（圆盘内每个采样点都验证过"判为集合内"，见自检第 3 节）。
   覆盖面与提速（360×270，``python -m tests.bench mandelbrot``）：

   ======================  ==============  =============  ============  ============
   取景                    被判"集合内"     判据直接命中    判据前        判据后
   ======================  ==============  =============  ============  ============
   默认取景 ×200            19296           94.3%           73 ms         **45 ms**
   默认取景 ×2000           19056           95.5%          328 ms         **50–75 ms**
   海马谷 宽0.05 ×400        41193           85.4%          384 ms         **74 ms**
   象谷 宽0.05 ×400          45335           94.5%            —             —
   深放大 宽2e-4 ×1000       41              0%             332 ms         170–195 ms
   ======================  ==============  =============  ============  ============

   "命中"= 在被判为集合内的像素里，有多少是判据直接判出来的（这些像素一次迭代都不做）。
   它不改变任何像素的判定（这些区域数学上整体属于 M），所以"判据前 / 后"的图**逐像素相同**。
2. **迭代上限随放大自适应**（:func:`iterations_for`，``max_iter=0`` 即自动）：
   ``≈ 200 · 2**(0.5·放大倍率)``（每放大 4 倍翻一倍），标定方式是扫各放大倍率下
   "集合内占比随上限不再变化"的那个值（实测数据见 ``tests/bench.py`` 的说明与下表）：
   海马谷 mag=9 时，上限 200 会把 **8%** 的像素误判成集合内（真值 0.03%），上限 1600 时
   只剩 0.04% —— 这就是"放大后形状发胖、一片暗"的量化原因。
3. **导数判据（``|D| < eps`` 判内部）实测不用**：它是与周期无关的通用内部检测
   （文献里报过 20 倍级加速），但代价是每轮多一次复数递推（约 +50% 运算）。实测在三个
   视图上**全部更慢**（22→35 ms、50→74 ms、102→215 ms）：因为解析判据已经把 85~94% 的
   内部吃掉了，剩下那点内部省不回来这 50%。同样被否掉的还有"稀疏历史采样的周期检测"——
   它主要抓周期 1（也就是主心形，已经被解析判据覆盖）。**结论：先量再选，别照搬文献。**

本模块只依赖标准库 + ``numpy``，不含任何绘图 / GUI 代码，可单独导入：

    python -m prismath.models.mandelbrot.model      # 跑一段确定性自检
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

__all__ = [
    "DEFAULT_CENTER_X",
    "DEFAULT_CENTER_Y",
    "DEFAULT_SPAN",
    "DEFAULT_ITERATIONS",
    "DEFAULT_PIXELS",
    "DEFAULT_PALETTE",
    "DEFAULT_ASPECT",
    "DEFAULT_ROWS",
    "DEFAULT_COLS",
    "MIN_ITERATIONS",
    "MAX_ITERATIONS",
    "MIN_PIXELS",
    "MAX_PIXELS",
    "MIN_SPAN",
    "MAX_SPAN",
    "MIN_MAGNIFICATION",
    "MAX_MAGNIFICATION",
    "ESCAPE_RADIUS",
    "LEVELS",
    "PALETTES",
    "AREA_REFERENCE",
    "Viewport",
    "complex_grid",
    "escape_counts",
    "mandelbrot_levels",
    "resample_to",
    "in_main_bulb",
    "interior_mask",
    "iterations_for",
    "INTERIOR_DISKS",
    "INTERIOR_BIG_DISK",
    "AUTO_ITERATIONS_BASE",
    "AUTO_ITERATIONS_SLOPE",
    "MandelbrotField",
    "Mandelbrot",
    "scan_iterations",
]

#: 默认视窗中心（Mandelbrot 集"主体"大致在实轴 [-2, 0.25] 上，这个取景留了余量）
DEFAULT_CENTER_X: float = -0.6
DEFAULT_CENTER_Y: float = 0.0
#: 默认实部跨度：视窗 ≈ [-2.2, 1.0] × [-1.2, 1.2]
DEFAULT_SPAN: float = 3.2

#: 默认最大迭代次数（判"是否属于 M"的上限）
DEFAULT_ITERATIONS: int = 200
#: 图像宽度（像素）；高度由 :data:`DEFAULT_ASPECT` 推出
DEFAULT_PIXELS: int = 360
#: 高 / 宽
DEFAULT_ASPECT: float = 0.75
#: 默认像素尺寸（由 DEFAULT_PIXELS / DEFAULT_ASPECT 推出，界面与终端共用）
DEFAULT_COLS: int = DEFAULT_PIXELS
DEFAULT_ROWS: int = int(round(DEFAULT_PIXELS * DEFAULT_ASPECT))

MIN_ITERATIONS: int = 10
MAX_ITERATIONS: int = 4000
MIN_PIXELS: int = 60
#: 单边像素数上限。桌面视图真正吃的是"像素总数上限"（见视图的 MAX_RENDER_PIXELS），
#: 这里放宽到 2000 是为了让 1920 宽的大窗口也能**一格对一格**渲染，而不是被单边截断
#: 之后再拉伸（拉伸出来的图会糊）。
MAX_PIXELS: int = 2000
#: 放大倍率的对数上限（``span = DEFAULT_SPAN / 2**mag``）：进得去、也退得出
MAX_MAGNIFICATION: float = 24.0
#: 缩小倍率的对数下限：负值表示视窗比默认取景还宽（``mag = -1`` 即缩小 2 倍）
MIN_MAGNIFICATION: float = -MAX_MAGNIFICATION
#: 复平面跨度的下限 / 上限：分别对应放大、缩小 ``2**MAX_MAGNIFICATION`` 倍。
#: 下限再小就到 float64 的精度极限了（1.9e-7 处还能分辨 1e-9 量级的像素）。
MIN_SPAN: float = DEFAULT_SPAN / (2.0 ** MAX_MAGNIFICATION)
MAX_SPAN: float = DEFAULT_SPAN * (2.0 ** MAX_MAGNIFICATION)

#: 逃逸半径：``|z| > R`` 即判为发散（数学上 R = 2 就够）
ESCAPE_RADIUS: float = 2.0

#: 色带档数：与 ``prismath.ui.tk.kit.chart.CMAPS`` 的 64 级色带一一对应
LEVELS: int = 64

#: 可选色带（名字与 ``ui/tk/kit/chart.py`` 的 ``CMAPS`` 一致）
PALETTES: Tuple[str, ...] = ("magma", "viridis", "ice", "heat")
DEFAULT_PALETTE: str = "magma"

#: Mandelbrot 集的面积（数值估计值，常被引用作 1.50659…）—— 用来对照像素计数
AREA_REFERENCE: float = 1.5065918849

# ----------------------------------------------------------------------
# 提速：直接判内部（不迭代）+ 迭代上限随放大自适应
#
# 两条都是"实测标定"过的，数字与结论见模块说明末尾；这里是参数。
# ----------------------------------------------------------------------
#: 已知必然落在集合内的圆盘 ``(圆心 x, 圆心 y, 半径)``。
#:
#: 列表来自 fractalforums / Geek3 的"快速拒绝过滤器"（``outcircle``），**每一个都实测验证过**：
#: 圆盘内 160×160 个采样点在 3000 次迭代下无一逃逸（见 ``tests/test_mandelbrot.py``）。
#: 大圆 ``(-0.11, 0, 0.63)`` 只在 ``x ≤ 0.1`` 那一侧成立（另一半会跑到集合外），
#: 所以它单独用一个条件限制。
INTERIOR_DISKS: Tuple[Tuple[float, float, float], ...] = (
    (-1.0, 0.0, 0.25),        # 周期 2 圆盘（与解析判据重复，留着是为了列表自身完整）
    (-0.125, 0.744, 0.092),
    (-0.125, -0.744, 0.092),
    (-1.308, 0.0, 0.058),
    (0.0, 0.25, 0.35),
    (0.0, -0.25, 0.35),
)
#: 大圆盘 + 它的附加条件（``x ≤ 0.1``）
INTERIOR_BIG_DISK: Tuple[float, float, float] = (-0.11, 0.0, 0.63)
INTERIOR_BIG_DISK_MAX_X: float = 0.1

#: 自动迭代上限：``base · 2**(slope · 放大倍率)``。
#: 标定方法见模块说明（按"集合内占比随上限不再变化"扫各放大倍率），实测够用的规律是
#: **每放大 4 倍（mag +2），上限翻一倍**，于是取 slope = 0.5。
AUTO_ITERATIONS_BASE: float = float(DEFAULT_ITERATIONS)
AUTO_ITERATIONS_SLOPE: float = 0.5


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


def _clamp_int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


# ----------------------------------------------------------------------
# 视窗
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Viewport:
    """复平面上的一个取景框：中心 + **实部跨度**。

    ``span`` 是实方向的长度；虚方向的长度由像素尺寸推出（:meth:`height`），
    于是"像素是正方形"这件事由几何本身保证，切换分辨率 / 缩放都不会变形。
    """

    center_x: float = DEFAULT_CENTER_X
    center_y: float = DEFAULT_CENTER_Y
    span: float = DEFAULT_SPAN

    # ---------------- 几何 ----------------
    def xlim(self) -> Tuple[float, float]:
        """实部区间 ``(左, 右)``（按像素中心采样，实际采样范围略窄半个像素）。"""
        half = self.span / 2.0
        return self.center_x - half, self.center_x + half

    def height(self, rows: int, cols: int) -> float:
        """虚部跨度 = ``span · rows / cols``（保证像素为正方形）。"""
        rows, cols = max(1, int(rows)), max(1, int(cols))
        return self.span * rows / cols

    def ylim(self, rows: int, cols: int) -> Tuple[float, float]:
        half = self.height(rows, cols) / 2.0
        return self.center_y - half, self.center_y + half

    def area(self, rows: int, cols: int) -> float:
        """取景框在复平面上的面积（像素计数乘上它就是"集合面积"的估计）。"""
        return self.span * self.height(rows, cols)

    def pixel(self, row: int, col: int, rows: int, cols: int) -> complex:
        """**屏幕坐标** ``(row, col)``（第 0 行在顶部）→ 该像素中心的复数 ``c``。

        与 :func:`complex_grid` 严格同式（自检里逐点比对过），因此界面上点到哪一格、
        模型算的是哪一格，不会有半个像素的偏差。
        """
        rows, cols = max(1, int(rows)), max(1, int(cols))
        dx = self.span / cols
        dy = self.height(rows, cols) / rows
        x = self.center_x + (int(col) - (cols - 1) / 2.0) * dx
        y = self.center_y + ((rows - 1 - int(row)) - (rows - 1) / 2.0) * dy
        return complex(x, y)

    @property
    def magnification(self) -> float:
        """放大倍率的对数：``span = DEFAULT_SPAN / 2**mag``（负值 = 比默认取景更宽）。"""
        return math.log2(DEFAULT_SPAN / self.span)

    def label(self) -> str:
        """一行人类可读的取景描述。"""
        return (f"中心 {self.center_x:+.6f} {self.center_y:+.6f}i · "
                f"宽 {self.span:.6g} · 放大 ×{2.0 ** self.magnification:.4g}")

    # ---------------- 变换 ----------------
    def zoomed(self, factor: float, anchor: Optional[complex] = None) -> "Viewport":
        """以 ``anchor``（缺省为视窗中心）为不动点缩放：``factor > 1`` 是放大。

        锚点在**复数平面上**保持不动，所以"点哪放大哪"。缩放被 :data:`MIN_SPAN`
        截断时，中心的位移也按**实际生效**的比例算 —— 否则贴到下限继续点会慢慢漂走。
        """
        factor = float(factor)
        if not math.isfinite(factor) or factor <= 0.0:
            factor = 1.0
        ax, ay = (self.center_x, self.center_y) if anchor is None else (anchor.real, anchor.imag)
        target = _clamp(self.span / factor, MIN_SPAN, MAX_SPAN)
        scale = target / self.span if self.span else 1.0
        return Viewport(
            center_x=ax + (self.center_x - ax) * scale,
            center_y=ay + (self.center_y - ay) * scale,
            span=target,
        )

    def moved(self, dx: float, dy: float) -> "Viewport":
        """平移：把中心挪到复数平面上的相对位移 ``(dx, dy)``。"""
        return Viewport(self.center_x + float(dx), self.center_y + float(dy), self.span)


def make_viewport(center_x: Any = DEFAULT_CENTER_X, center_y: Any = DEFAULT_CENTER_Y,
                  span: Any = DEFAULT_SPAN) -> Viewport:
    """按原始输入（可能是字符串 / None）造一个合法的 :class:`Viewport`。"""
    def _num(value: Any, fallback: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return fallback
        return number if math.isfinite(number) else fallback

    return Viewport(
        center_x=_num(center_x, DEFAULT_CENTER_X),
        center_y=_num(center_y, DEFAULT_CENTER_Y),
        span=_clamp(_num(span, DEFAULT_SPAN), MIN_SPAN, MAX_SPAN),
    )


# ----------------------------------------------------------------------
# 像素网格与逃逸时间
# ----------------------------------------------------------------------
def complex_grid(viewport: Viewport, rows: int, cols: int) -> np.ndarray:
    """``(rows, cols)`` 的复数网格，第 0 行 = **最小虚部**（数学序，出图前要翻转）。

    以 "(下标 − (n−1)/2) · step" 构造，因此关于中心严格镜像（奇数列/行时是精确相反数）。
    """
    rows, cols = max(1, int(rows)), max(1, int(cols))
    xs = viewport.center_x + (np.arange(cols) - (cols - 1) / 2.0) * (viewport.span / cols)
    ys = viewport.center_y + (np.arange(rows) - (rows - 1) / 2.0) * (
        viewport.height(rows, cols) / rows)
    grid = np.empty((rows, cols), dtype=np.complex128)
    grid.real = xs[None, :]
    grid.imag = ys[:, None]
    return grid


def escape_counts(points: Union[np.ndarray, complex],
                  max_iter: int = DEFAULT_ITERATIONS,
                  bailout: float = ESCAPE_RADIUS,
                  skip_interior: bool = True
                  ) -> Tuple[np.ndarray, np.ndarray]:
    """对 ``points``（复数数组）做逃逸时间迭代，返回 ``(整数迭代数, 平滑迭代数)``。

    * 整数迭代数 ``counts``：逃逸的记 ``n ≥ 1``（第 n 次迭代后 ``|z| > R``），
      一直有界的记 ``0``（即"属于 M"，上限是 ``max_iter``）；
    * 平滑迭代数 ``smooth``：逃逸点用 ``μ = n + 1 − log₂(ln|zₙ| / ln R)`` 抹平台阶值，
      未逃逸点固定为 ``max_iter``。

    实现要点（三条都是实测选出来的）：

    1. **先判内部**：``skip_interior=True`` 时先用 :func:`interior_mask` 剔掉"不用算也知道
       在集合内"的点 —— 默认取景能占内部像素的 94%，海马谷浅放大 85%，这批像素一次迭代
       都不做（默认取景实测 1.5×、海马谷 2.4×）；
    2. **紧凑活动集**（而不是"下标数组 + gather/scatter"）：后者每轮要做三次随机访问，
       在"一大半像素都属于集合"的深放大视图里反而慢一倍（实测），紧凑数组则是连续内存；
    3. **懒压缩**：深放大视图里每轮只逃逸几个点，而"剔除 + 复制五个数组"是 O(活动集) ——
       每轮都做一次纯属浪费。让死点在数组里多躺几轮（多算的那点像素比复制的代价便宜），
       实测深放大视图快 10~15%。

    代价是已逃逸的点还会被算几轮、``|z|`` 会溢出成 ``inf/nan`` —— 用 ``errstate`` 静音，
    而且它们已被 ``alive`` 排除，不会再被采信。
    """
    c = np.asarray(points, dtype=np.complex128)
    shape = c.shape
    total = c.size
    max_iter = max(1, int(max_iter))
    bailout = float(bailout) if float(bailout) > 1.0 else ESCAPE_RADIUS
    bailout2 = bailout * bailout
    log_bailout = math.log(bailout)
    inv_log2 = 1.0 / math.log(2.0)

    counts = np.zeros(total, dtype=np.int32)
    smooth = np.full(total, float(max_iter), dtype=float)
    if total == 0:
        return counts.reshape(shape), smooth.reshape(shape)

    real_all = np.ascontiguousarray(c.real.reshape(-1))
    imag_all = np.ascontiguousarray(c.imag.reshape(-1))
    #: 解析判据先剔掉"不用算也知道在集合内"的点（默认取景能占内部像素的九成以上）
    if skip_interior:
        index = np.flatnonzero(~interior_mask(c).reshape(-1))
    else:
        index = np.arange(total)
    #: 活动集：原始下标 + 它的 c 与 z（逃逸的点标成 dead，**攒够了才**真的剔出去）
    if index.size == total:
        real_c, imag_c = real_all, imag_all          # 一个都没命中：别白复制一遍
    else:
        real_c, imag_c = real_all[index], imag_all[index]
    real_z = np.zeros(index.size, dtype=float)
    imag_z = np.zeros(index.size, dtype=float)
    alive = np.ones(index.size, dtype=bool)
    dead = 0
    with np.errstate(over="ignore", invalid="ignore"):     # 已逃逸的点会溢出，反正不再采信
        for n in range(1, max_iter + 1):
            real2 = real_z * real_z
            imag2 = imag_z * imag_z
            imag_z = 2.0 * real_z * imag_z + imag_c
            real_z = real2 - imag2 + real_c
            mag2 = real_z * real_z + imag_z * imag_z
            escaped = alive & (mag2 > bailout2)
            if escaped.any():
                done = index[escaped]
                counts[done] = n
                mag = np.sqrt(mag2[escaped])
                smooth[done] = (n + 1) - np.log(np.log(mag) / log_bailout) * inv_log2
                alive &= ~escaped
                dead += int(np.count_nonzero(escaped))
                # 每轮都做一次"剔除 + 复制五个数组"在深放大视图里是纯浪费：那时每一轮只逃逸
                # 几个点，而复制是 O(活动集)。攒到 5% 再压缩，多算的那点已逃逸像素比复制的
                # 代价便宜得多（实测深放大视图快约 2 倍）。
                if dead * 20 >= alive.size or not alive.any():
                    if not alive.any():
                        index = index[:0]
                        break
                    index, real_c, imag_c = index[alive], real_c[alive], imag_c[alive]
                    real_z, imag_z = real_z[alive], imag_z[alive]
                    alive = np.ones(index.size, dtype=bool)
                    dead = 0
    return counts.reshape(shape), smooth.reshape(shape)


def mandelbrot_levels(smooth: np.ndarray, max_iter: int, escaped: Optional[np.ndarray] = None
                      ) -> np.ndarray:
    """平滑逃逸时间 → ``0..LEVELS-1`` 的色带下标（**集合内部固定为 0**）。

    ``level = round(sqrt(μ / max_iter) · (LEVELS − 1))``：逃逸越慢（越贴近集合边界）
    越亮，逃逸越快（离得越远）越暗，集合内部最暗 —— 于是集合是一块暗色剪影，
    边界上的细节被亮色描出来。
    """
    max_iter = max(1, int(max_iter))
    ratio = np.clip(np.asarray(smooth, dtype=float) / max_iter, 0.0, 1.0)
    levels = np.rint(np.sqrt(ratio) * (LEVELS - 1)).astype(np.int32)
    if escaped is None:
        escaped = np.asarray(smooth, dtype=float) < max_iter
    levels[~escaped] = 0
    return levels


def resample_to(levels: np.ndarray, source: Viewport, target: Viewport,
                rows: int, cols: int) -> np.ndarray:
    """把一张**屏幕序**的色带下标图从 ``source`` 取景最近邻重采样到 ``target`` 取景。

    用于缩放时的"即时预览"：手感上先让画面按新取景拉一下（几毫秒），清晰的那张随后由
    内核慢慢算 —— 否则每点一下都要干等一整轮渲染（几百毫秒），"放缩"就成了"卡一下"。

    两个取景用的是同一套"像素中心"约定（:meth:`Viewport.pixel`），所以预览与随后那张
    清晰图在几何上严格对齐，不会先"跳"一下再对齐。
    """
    levels = np.asarray(levels)
    if levels.ndim != 2 or levels.shape != (int(rows), int(cols)):
        raise ValueError("重采样需要 (rows, cols) 的屏幕序下标图")
    rows, cols = int(rows), int(cols)
    dx = target.span / cols
    dy = target.height(rows, cols) / rows
    xs = target.center_x + (np.arange(cols) - (cols - 1) / 2.0) * dx
    # 屏幕序：第 0 行在顶部（虚部最大），与 Viewport.pixel 的写法一致
    ys = target.center_y - (np.arange(rows) - (rows - 1) / 2.0) * dy
    dx_source = source.span / cols
    dy_source = source.height(rows, cols) / rows
    col_source = (xs - source.center_x) / dx_source + (cols - 1) / 2.0
    row_source = (source.center_y - ys) / dy_source + (rows - 1) / 2.0
    cols_index = np.clip(np.rint(col_source).astype(np.int64), 0, cols - 1)
    rows_index = np.clip(np.rint(row_source).astype(np.int64), 0, rows - 1)
    return levels[rows_index[:, None], cols_index[None, :]]


def in_main_bulb(points: Union[np.ndarray, complex]) -> np.ndarray:
    """``points`` 是否落在**主心形**（周期 1）或**周期 2 圆盘**里（解析判据，闭式）。

    这两个区域整体属于 ``M``，所以它们可以当"逃逸判据有没有漏判"的护栏：
    解析说在里面、逃逸迭代却说跑了，那就是内核写错了。
    """
    c = np.asarray(points, dtype=np.complex128)
    x, y = c.real, c.imag
    q = (x - 0.25) ** 2 + y * y
    cardioid = q * (q + (x - 0.25)) <= 0.25 * y * y
    period2 = (x + 1.0) ** 2 + y * y <= 0.0625      # 半径 1/4 的圆盘
    return cardioid | period2


def interior_mask(points: Union[np.ndarray, complex], disks: bool = True) -> np.ndarray:
    """``points`` 中"**不用迭代就能确定在集合内**"的点（解析判据的并集）。

    包含 :func:`in_main_bulb` 与 :data:`INTERIOR_DISKS` 里那些实测验证过的内切圆盘。
    它对**准确性零风险**（这些区域数学上整体属于 M），换来的是这批像素一次迭代都不做。

    实测覆盖面（与被判为"集合内"的像素总数之比）：
    默认取景 **94%**、海马谷浅放大 **85%** —— 也就是说"内部像素要迭代到上限"这件事
    基本被消掉了；代价只有几个向量化的圆盘比较（十万像素约 1 ms）。
    """
    c = np.asarray(points, dtype=np.complex128)
    x, y = c.real, c.imag
    mask = in_main_bulb(c)
    if not disks:
        return mask
    for cx, cy, radius in INTERIOR_DISKS:
        mask = mask | ((x - cx) ** 2 + (y - cy) ** 2 <= radius * radius)
    big_x, big_y, big_r = INTERIOR_BIG_DISK
    mask = mask | (((x - big_x) ** 2 + (y - big_y) ** 2 <= big_r * big_r)
                   & (x <= INTERIOR_BIG_DISK_MAX_X))
    return mask


def iterations_for(span: float) -> int:
    """按视窗宽度给一个"够用"的迭代上限（放大得越深越要加，否则形状发胖）。

    ``max_iter ≈ 200 · 2**(0.5 · 放大倍率)``：每放大 4 倍，上限翻一倍。标定方式与数据见
    模块说明末尾 —— 取的是"集合内占比不再明显变化"的那个值再留一点余量。
    """
    span = max(float(span), MIN_SPAN)
    mag = max(math.log2(DEFAULT_SPAN / span), 0.0)
    value = AUTO_ITERATIONS_BASE * (2.0 ** (AUTO_ITERATIONS_SLOPE * mag))
    return int(min(MAX_ITERATIONS, max(MIN_ITERATIONS, round(value))))


# ----------------------------------------------------------------------
# 一次渲染的结果
# ----------------------------------------------------------------------
@dataclass
class MandelbrotField:
    """一次渲染：迭代数场 + 统计量（数组是**数学序**，第 0 行 = 最小虚部）。"""

    viewport: Viewport
    rows: int
    cols: int
    max_iter: int
    counts: np.ndarray                  # 整数迭代数（0 = 未逃逸）
    smooth: np.ndarray                  # 平滑迭代数
    #: 其中有多少像素是**解析判据直接判内部**的（一次迭代都没做）—— 界面与文档里的"省了多少"
    analytic_inside: int = 0
    elapsed: float = 0.0
    _levels: Optional[np.ndarray] = field(default=None, repr=False, compare=False)

    # ---------------- 判定与统计 ----------------
    @property
    def escaped(self) -> np.ndarray:
        """逃逸掩码（``counts > 0``）。"""
        return self.counts > 0

    @property
    def inside(self) -> np.ndarray:
        """"属于 M" 的掩码（``max_iter`` 次迭代后仍未逃逸）。"""
        return self.counts == 0

    @property
    def inside_count(self) -> int:
        return int(np.count_nonzero(self.counts == 0))

    @property
    def escaped_count(self) -> int:
        return int(self.rows) * int(self.cols) - self.inside_count

    @property
    def inside_ratio(self) -> float:
        """集合内像素占取景框的比例。"""
        total = max(1, int(self.rows) * int(self.cols))
        return self.inside_count / total

    @property
    def area(self) -> float:
        """集合面积的像素计数估计：``占比 × 取景框面积``。

        它当然依赖分辨率与 ``max_iter``（像素越细、迭代越深，越接近真值
        :data:`AREA_REFERENCE` ≈ 1.5066），所以这个数字要连着采样尺寸一起报。
        """
        return self.inside_ratio * self.viewport.area(self.rows, self.cols)

    @property
    def mean_escape(self) -> Optional[float]:
        """逃逸点的平均迭代数（没有逃逸点时返回 ``None``）。"""
        mask = self.counts > 0
        if not mask.any():
            return None
        return float(self.counts[mask].mean())

    @property
    def levels(self) -> np.ndarray:
        """色带下标（``0..LEVELS-1``），按需计算并缓存。"""
        if self._levels is None:
            self._levels = mandelbrot_levels(self.smooth, self.max_iter, self.escaped)
        return self._levels

    def level_values(self) -> List[int]:
        """**屏幕序**的色带下标（第 0 行 = 顶部）的扁平列表，供画布的连续场直接吃。"""
        return np.flipud(self.levels).reshape(-1).tolist()

    def level_array(self) -> np.ndarray:
        """**屏幕序**的色带下标数组（与 :meth:`level_values` 同一份数据，但是 numpy 数组）。

        桌面视图用它：几百 k 像素的图转成 Python 列表（为了能 JSON 序列化）本身就要几十
        毫秒，而同一个进程里没必要来回转 —— 数据级契约（``payload_for`` 默认那一支）仍然
        给列表，两条路各自付该付的成本。
        """
        return np.ascontiguousarray(self.levels[::-1, :])

    # ---------------- 文案 ----------------
    @property
    def size_text(self) -> str:
        return f"{self.cols}×{self.rows}"

    @property
    def view_text(self) -> str:
        """一行说清"现在看的是哪儿"，界面标题直接用。"""
        return (f"{self.viewport.label()} · 最多 {self.max_iter} 次迭代 · {self.size_text}"
                f" · 集合占 {self.inside_ratio:.1%}")

    def as_dict(self) -> Dict[str, Any]:
        """除像素数据之外的统计量（转 JSON / 打表格都用它）。"""
        return {
            "rows": self.rows,
            "cols": self.cols,
            "maxIter": self.max_iter,
            "centerX": self.viewport.center_x,
            "centerY": self.viewport.center_y,
            "span": self.viewport.span,
            "magnification": self.viewport.magnification,
            "inside": self.inside_count,
            "escaped": self.escaped_count,
            "insideRatio": self.inside_ratio,
            "analyticInside": self.analytic_inside,
            "area": self.area,
            "meanEscape": self.mean_escape,
            "sizeText": self.size_text,
            "viewText": self.view_text,
        }


# ----------------------------------------------------------------------
# 模型（由参数造，按参数渲染）
# ----------------------------------------------------------------------
class Mandelbrot:
    """Mandelbrot 集模型（纯计算）。

    参数
    ----
    center_x / center_y : float
        视窗中心（复平面坐标）。
    span : float
        实部跨度，会被夹到 ``[MIN_SPAN, DEFAULT_SPAN · 2**MAX_MAGNIFICATION]``。
    max_iter : int
        判"属于 M"的迭代上限；**给 0（或负数）表示"自动"** —— 按放大倍率取
        :func:`iterations_for`（放大越深越要加，否则边界附近"其实会逃逸"的点被算成集合内，
        形状发胖）。
    pixels : int
        图像宽度（像素），高度 = ``round(pixels · aspect)``。
    aspect : float
        高 / 宽，默认 3:4。
    """

    def __init__(self, center_x: float = DEFAULT_CENTER_X, center_y: float = DEFAULT_CENTER_Y,
                 span: float = DEFAULT_SPAN, max_iter: int = DEFAULT_ITERATIONS,
                 pixels: int = DEFAULT_PIXELS, aspect: float = DEFAULT_ASPECT) -> None:
        self.viewport = make_viewport(center_x, center_y, span)
        if int(max_iter) <= 0:                      # 0 = 自动：按放大倍率给
            max_iter = iterations_for(self.viewport.span)
        self.max_iter = _clamp_int(max_iter, MIN_ITERATIONS, MAX_ITERATIONS, DEFAULT_ITERATIONS)
        self.cols = _clamp_int(pixels, MIN_PIXELS, MAX_PIXELS, DEFAULT_PIXELS)
        try:
            ratio = float(aspect)
        except (TypeError, ValueError):
            ratio = DEFAULT_ASPECT
        self.rows = _clamp_int(round(self.cols * ratio), 2, MAX_PIXELS, DEFAULT_ROWS)

    # ---------------- 便捷属性 ----------------
    @property
    def magnification(self) -> float:
        return self.viewport.magnification

    @property
    def size_text(self) -> str:
        return f"{self.cols}×{self.rows}"

    # ---------------- 渲染 ----------------
    def points(self) -> np.ndarray:
        """本视图的复数网格（数学序）。"""
        return complex_grid(self.viewport, self.rows, self.cols)

    def render(self) -> MandelbrotField:
        """算一次完整渲染（含逃逸时间迭代与统计）。"""
        started = time.perf_counter()
        points = self.points()
        counts, smooth = escape_counts(points, self.max_iter)
        return MandelbrotField(
            viewport=self.viewport, rows=self.rows, cols=self.cols, max_iter=self.max_iter,
            counts=counts, smooth=smooth,
            # 顺手数一下有多少像素是解析判据直接判的（界面与文档里的"省了多少"）
            analytic_inside=int(np.count_nonzero(interior_mask(points))),
            elapsed=time.perf_counter() - started,
        )

    # ---------------- 视图变换 ----------------
    def zoomed(self, factor: float, anchor: Optional[complex] = None) -> "Mandelbrot":
        """按同样的分辨率 / 迭代上限，换一个取景框（返回**新实例**，不修改自己）。"""
        return self.with_view(self.viewport.zoomed(factor, anchor))

    def with_view(self, viewport: Viewport) -> "Mandelbrot":
        """换一个取景框（其余参数不变）。"""
        return Mandelbrot(center_x=viewport.center_x, center_y=viewport.center_y,
                          span=viewport.span, max_iter=self.max_iter, pixels=self.cols,
                          aspect=self.rows / self.cols)


# ----------------------------------------------------------------------
# 扫描：迭代上限 -> 面积估计（"再多算几次还准不准"的量尺）
# ----------------------------------------------------------------------
def scan_iterations(iterations: List[int], center_x: float = DEFAULT_CENTER_X,
                    center_y: float = DEFAULT_CENTER_Y, span: float = DEFAULT_SPAN,
                    pixels: int = 240,
                    aspect: float = DEFAULT_ASPECT) -> List[Tuple[int, MandelbrotField]]:
    """对每个迭代上限各渲染一次（同一取景框、同一分辨率），返回 ``[(上限, 结果)]``。

    同一台机器上每次渲染只差一个"迭代上限"，所以这张表干净地回答一个问题：
    **把上限调高，形状还会不会变**（像素计数收敛到面积真值的那条曲线）。
    """
    model = Mandelbrot(center_x=center_x, center_y=center_y, span=span,
                       max_iter=max(iterations) if iterations else DEFAULT_ITERATIONS,
                       pixels=pixels, aspect=aspect)
    out: List[Tuple[int, MandelbrotField]] = []
    for value in iterations:
        model.max_iter = _clamp_int(value, MIN_ITERATIONS, MAX_ITERATIONS, DEFAULT_ITERATIONS)
        out.append((model.max_iter, model.render()))
    return out


# ----------------------------------------------------------------------
# 直接运行本文件时的自检：全是确定性结论（没有随机数，也没有计时）
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    try:  # Windows 控制台默认 GBK，需要切到 UTF-8 才能正常输出中文
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    print("=" * 70)
    print("Mandelbrot 集自检：逃逸时间、对称性与解析子集")
    print("=" * 70)

    # ---------------- 1. 已知点 ----------------
    print("1. 已知点的归属（max_iter = 200，|z| > 2 即逃逸）")
    known = (
        (0.0, 0.0, True, "z 恒为 0"),
        (-1.0, 0.0, True, "0 → -1 → 0 → …（周期 2）"),
        (-0.5, 0.5, True, "经典内点"),
        (0.25, 0.0, True, "主心形的尖点（边界上）"),
        (-2.0, 0.0, True, "集合最左端（2 → 2 → …）"),
        (1.0, 0.0, False, "0 → 1 → 2 → 5 → … 很快发散"),
        (0.5, 0.0, False, "0 → 0.5 → 0.75 → 1.06 → …"),
    )
    for real, imag, inside_expected, note in known:
        count, _smooth = escape_counts(np.array([complex(real, imag)]), 200)
        is_inside = int(count[0]) == 0
        shown = "未逃逸（属于 M）" if is_inside else f"第 {int(count[0])} 步逃逸"
        mark = "✔" if is_inside == inside_expected else "✘"
        print(f"   c = {real:+.2f} {imag:+.2f}i : {shown:<16} {mark} {note}")
        assert is_inside == inside_expected, f"c = {real}{imag:+}i 的归属判错了"

    # ---------------- 2. 实轴对称（逐位精确） ----------------
    # 行数为奇数时，"以中心对称"的构造让镜像坐标严格互为相反数，共轭轨道逐位相同
    view = Viewport(center_x=0.0, center_y=0.0, span=2.4)
    rows, cols = 301, 240
    counts, smooth = escape_counts(complex_grid(view, rows, cols), 200)
    flipped_counts = counts[::-1, :]
    mismatch = int(np.count_nonzero(counts != flipped_counts))
    print()
    print(f"2. 实轴对称（共轭对称）：{cols}×{rows} 网格逐点比对整数迭代数")
    print(f"   不相同的点：{mismatch} 个（共轭轨道逐位镜像，所以要求严格相等）")
    assert mismatch == 0, f"共轭对称被破坏：{mismatch} 个点的迭代数不一致"
    assert np.array_equal(smooth, smooth[::-1, :]), "平滑迭代数也应当逐位镜像"

    # ---------------- 3. 解析子集 ⊆ M + 覆盖面 ----------------
    grid = complex_grid(Viewport(center_x=-0.6, center_y=0.0, span=3.2), 240, 320)
    naive_counts = escape_counts(grid, 200, skip_interior=False)[0]
    analytic = interior_mask(grid)                    # 主心形 + 周期 2 + 6 个内切圆盘
    analytic_count = int(np.count_nonzero(analytic))
    missed = int(np.count_nonzero(analytic & (naive_counts > 0)))
    inside_total = int(np.count_nonzero(naive_counts == 0))
    covered = int(np.count_nonzero(analytic & (naive_counts == 0)))
    print()
    print("3. 解析判据 ⊆ 逃逸判据：主心形 + 周期 2 圆盘 + 6 个内切圆盘")
    print(f"   解析判为在 M 内的像素：{analytic_count} 个；"
          f"其中被逃逸判据误判为发散的：{missed} 个")
    print(f"   同一网格上被判「集合内」的 {inside_total} 个像素里，"
          f"判据直接判出 {covered} 个（{covered / inside_total:.1%}）—— 这批像素一次迭代都不做")
    assert analytic_count > 0, "解析判据一个点都没判出来（公式写错了？）"
    assert missed == 0, f"有 {missed} 个解析内点被判成逃逸"
    assert covered / inside_total > 0.85, "解析判据的覆盖面明显缩水（圆盘列表被改坏了？）"

    # ---------------- 4. |c| > 2 必逃逸 ----------------
    outside = grid[np.abs(grid) > 2.0]
    escaped_outside = int(np.count_nonzero(escape_counts(outside, 200)[0] > 0))
    print()
    print("4. |c| > 2 的点一定逃逸（因为 c ∈ M ⇒ |c| ≤ 2）")
    print(f"   网格里 |c| > 2 的点：{outside.size} 个；其中逃逸的：{escaped_outside} 个")
    assert outside.size > 0 and escaped_outside == outside.size, "|c| > 2 的点竟然没全部逃逸"

    # ---------------- 5. 主视图统计与像素坐标 ----------------
    model = Mandelbrot(max_iter=200)
    field = model.render()
    print()
    print("5. 主视图（默认取景）")
    print(f"   {field.view_text}")
    print(f"   集合内像素 {field.inside_count} / {field.rows * field.cols}"
          f"（{field.inside_ratio:.4f}），面积估计 ≈ {field.area:.6f}"
          f"（数值真值 ≈ {AREA_REFERENCE:.6f}）")
    assert abs(field.area - AREA_REFERENCE) < 0.05, "面积估计偏离真值太远（取景或判据错了）"
    assert field.levels.min() >= 0 and field.levels.max() < LEVELS, "色带下标越界"
    assert int(np.count_nonzero(field.levels[field.inside] != 0)) == 0, "集合内的色带下标应为 0"
    assert len(field.level_values()) == field.rows * field.cols, "屏幕序像素数与分辨率不符"

    grid_math = model.points()
    pixel_ok = all(
        grid_math[model.rows - 1 - row, col] == model.viewport.pixel(row, col, model.rows, model.cols)
        for row, col in ((0, 0), (model.rows - 1, model.cols - 1),
                         (model.rows // 3, model.cols // 4))
    )
    print(f"   屏幕坐标 ↔ 数学序网格逐点一致：{'是' if pixel_ok else '否'}")
    assert pixel_ok, "屏幕像素反查与网格构造不一致（点击放大就会偏）"

    anchor = complex(-0.743643887, 0.131825904)      # 海马谷里的一个点
    before = model.viewport
    zoomed = before.zoomed(4.0, anchor)
    print(f"   以 {anchor} 为锚放大 4 倍后：{zoomed.label()}")
    # "点哪放大哪"的严格说法：锚点在视窗里的**相对位置**不变（于是它看上去没动）
    for name, old, new in (("实部", before.center_x, zoomed.center_x),
                           ("虚部", before.center_y, zoomed.center_y)):
        was = (getattr(anchor, "real" if name == "实部" else "imag") - old) / before.span
        now = (getattr(anchor, "real" if name == "实部" else "imag") - new) / zoomed.span
        print(f"   锚点的{name}相对位置：{was:+.6f} -> {now:+.6f}（应保持不变）")
        assert abs(was - now) < 1e-12, f"锚点的{name}相对位置变了"
    assert abs(zoomed.span - before.span / 4.0) < 1e-12, "跨度没有按倍率缩小"
    assert before.zoomed(1.0).span == before.span, "倍率为 1 时不应改变取景"

    # ---------------- 6. 迭代上限 -> 面积估计 ----------------
    print()
    print("6. 迭代上限 -> 面积估计（160×120 采样，视图宽 3.2）")
    print(f"   {'迭代上限':>8} | {'集合内像素':>10} | {'集合内占比':>10} | {'面积估计':>10}")
    print("-" * 70)
    for limit, result in scan_iterations([20, 50, 100, 200, 500, 1000], pixels=160):
        print(f"   {limit:>8} | {result.inside_count:>10} | "
              f"{result.inside_ratio:>10.4f} | {result.area:>10.6f}")
    print("-" * 70)
    print("提示：像素是有限网格、迭代也有上限，所以面积估计随迭代上限单调下降并趋于")
    print(f"      数值真值 ≈ {AREA_REFERENCE:.4f}；分辨率越细、上限越高，估计越接近它。")

    # ---------------- 7. 迭代上限随放大自适应 ----------------
    print()
    print(f"7. 自动迭代上限（max_iter = 0）：≈ {AUTO_ITERATIONS_BASE:.0f} · "
          f"2^({AUTO_ITERATIONS_SLOPE:g} · 放大倍率)，上限 {MAX_ITERATIONS}")
    print(f"   {'放大倍率':>8} | {'视窗宽度':>12} | {'自动给的迭代上限':>16}")
    print("-" * 70)
    for mag in (0, 3, 6, 9, 12, 24):
        span = DEFAULT_SPAN / (2.0 ** mag)
        print(f"   {mag:>8} | {span:>12.6g} | {iterations_for(span):>16}")
    print("-" * 70)
    print("   放大越深给得越多：上限太小会把「其实会逃逸」的点算成集合内（形状发胖、一片暗）。")
    assert iterations_for(DEFAULT_SPAN) == DEFAULT_ITERATIONS, "默认取景的自动上限应当是基准值"
    assert (iterations_for(DEFAULT_SPAN / 4.0)
            > iterations_for(DEFAULT_SPAN)), "放大之后自动上限应当变大"

    print()
    print("全部自检通过 ✔")
