# -*- coding: utf-8 -*-
"""
Mandelbrot 集模型 —— 界面元数据与动作处理器
============================================

本文件是「模型」与「界面」之间的唯一桥梁：

* :data:`PARAMS` 描述可调参数（迭代上限、色带、视窗中心、放大倍率），
  桌面 / 网页 / 终端三种界面都据此生成控件（分辨率不在这里：桌面视图按画布大小渲染，
  终端 / 网页用 ``--pixels`` / 默认值）；
* :func:`handle` 处理界面发来的动作请求（渲染视图、放大、缩小、重置视图），
  返回 JSON 可序列化的 payload（其中 ``values`` 是**屏幕序**的 0..63 色带下标）；
* :func:`build_mandelbrot` 是**对象级契约**里的 ``factory``：由（内部取值的）参数造模型，
  桌面视图"点击放大"时也走它，于是"参数 → 模型"的换算只有一份；
* :func:`_cli` 是终端模式的入口：出统计 + 一张字符画，``--scan`` 扫「迭代上限 → 面积估计」。

算法本身在 :mod:`~prismath.models.mandelbrot.model` 中，与本文件完全解耦。

**放大倍率为什么用对数**：视窗宽度 ``span`` 从 3.2 一直缩到 2⁻²⁴ × 3.2，线性滑块在这段
跨度上没法用（前 99% 的行程都挤在"几乎没放大"里）。所以界面上的缩放参数是
``magnification = log₂(3.2 / span)`` —— 滑块线性拖动 = 等比放大，点一下放大 = +1。
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ...spec import ActionSpec, CliArgs, CliOption, ModelSpec, ParamSpec
from .model import (
    AREA_REFERENCE,
    BACKENDS,
    DEFAULT_ASPECT,
    DEFAULT_CENTER_X,
    DEFAULT_CENTER_Y,
    DEFAULT_ITERATIONS,
    DEFAULT_PALETTE,
    DEFAULT_PIXELS,
    DEFAULT_SPAN,
    LEVELS,
    MAX_ITERATIONS,
    MAX_MAGNIFICATION,
    MAX_PIXELS,
    MAX_SPAN,
    MIN_ITERATIONS,
    MIN_MAGNIFICATION,
    MIN_PIXELS,
    MIN_SPAN,
    PALETTES,
    Mandelbrot,
    MandelbrotField,
    Viewport,
    scan_iterations,
)

# ----------------------------------------------------------------------
# 界面选项词表（中文标签 -> 内部取值）
# ----------------------------------------------------------------------
#: 色带：内部名与 ``ui/tk/kit/chart.py`` 的 ``CMAPS`` 一致
PALETTE_LABELS: Dict[str, str] = {
    "magma": "岩浆（暗 → 暖白）",
    "viridis": "翠绿（紫 → 黄）",
    "ice": "冰蓝（暗 → 亮蓝）",
    "heat": "暖黄（暗红 → 亮黄）",
}

#: 视窗中心的允许范围：集合整体落在 [-2, 0.25] × [-1.1, 1.1] 里，这里留足余量。
#: 它同时是参数滑块的范围与内核的夹取范围 —— 两者必须是同一份，否则界面显示的位置
#: 与真正渲染的位置会不一致。
CENTER_X_RANGE: Tuple[float, float] = (-3.0, 2.0)
CENTER_Y_RANGE: Tuple[float, float] = (-2.0, 2.0)

# ----------------------------------------------------------------------
# 可调参数（桌面侧栏按 group 自动分组生成控件）
# ----------------------------------------------------------------------
PARAMS = (
    ParamSpec(
        key="iterations", label="最大迭代次数（0 = 自动）", kind="int", default=0,
        min=0, max=MAX_ITERATIONS, step=10, group="渲染",
        hint="迭代多少次仍未逃逸就认为该点属于 M。**0 = 按放大倍率自动**"
             "（≈ 200·2^(倍率/2)，每放大 4 倍翻一倍）—— 放大得越深越需要迭代，"
             "上限太小会把「其实会逃逸」的点算成集合内（形状发胖、一片暗）。",
    ),
    ParamSpec(
        key="palette", label="色带", kind="choice", default=PALETTE_LABELS[DEFAULT_PALETTE],
        choices=tuple(PALETTE_LABELS.values()), group="渲染",
        hint="集合内部固定为最暗的一档；逃逸越慢（越贴近边界）越亮。",
    ),
    ParamSpec(
        key="center_x", label="视窗中心（实部）", kind="float", default=DEFAULT_CENTER_X,
        min=CENTER_X_RANGE[0], max=CENTER_X_RANGE[1], step=0.005, group="视图",
        hint="集合整体在实部 [-2, 0.25] 之间。",
    ),
    ParamSpec(
        key="center_y", label="视窗中心（虚部）", kind="float", default=DEFAULT_CENTER_Y,
        min=CENTER_Y_RANGE[0], max=CENTER_Y_RANGE[1], step=0.005, group="视图",
        hint="集合关于实轴对称：虚部 ± 的图案互为镜像。",
    ),
    ParamSpec(
        key="magnification", label="放大倍率 log₂", kind="float", default=0.0,
        min=MIN_MAGNIFICATION, max=MAX_MAGNIFICATION, step=0.25, group="视图",
        hint="视窗宽度 = 3.2 / 2^倍率，**负值即缩小**（-1 = 比默认取景宽一倍）。"
             "用对数是因为跨度从 2²⁴ × 3.2 一直到 2⁻²⁴ × 3.2：线性滑块在那段范围里没法用。"
             "画布上左键点哪放哪、右键缩小，都会改写它。",
    ),
)

# ----------------------------------------------------------------------
# 动作
# ----------------------------------------------------------------------
ACTIONS = (
    ActionSpec("render", "渲染视图", mode="once", kind="primary",
               hint="按当前取景、迭代上限与色带算出整幅图像"),
    ActionSpec("zoom_in", "放大 ×2", mode="once", kind="default",
               hint="以视窗中心为锚放大 2 倍；在画布上左键点哪就以哪为锚（右键缩小）"),
    ActionSpec("zoom_out", "缩小 ×2", mode="once", kind="default",
               hint="以视窗中心为锚缩小 2 倍（最多退到默认取景的 2²⁴ 倍宽）"),
    ActionSpec("reset_view", "⌖ 重置视图", mode="once", kind="ghost",
               hint="回到默认取景：中心 -0.6 + 0i，视窗宽 3.2（放大倍率 0）"),
)

# ----------------------------------------------------------------------
# 终端命令行参数（自己的名字：--iterations / --pixels / --span / --zoom / --center / --palette）
# ----------------------------------------------------------------------
CLI_OPTIONS = (
    CliOption(
        ("--iterations",), kind="int", default=0,
        help="最大迭代次数；0（默认）= 按放大倍率自动给，放大越深给的越多",
    ),
    CliOption(
        ("--pixels",), kind="int", default=DEFAULT_PIXELS,
        help=f"图像宽度（像素，高度 = 宽 × 3/4），默认 {DEFAULT_PIXELS}",
    ),
    CliOption(
        ("--span",), kind="float",
        help="视窗的实部跨度（如 --span 0.001）；省略则按 --zoom 推",
    ),
    CliOption(
        ("--zoom",), kind="float", default=0.0,
        help="放大倍率的对数 log₂（视窗宽 = 3.2 / 2^zoom），默认 0",
    ),
    CliOption(
        ("--center-x",), kind="float",
        help="视窗中心的实部（如 --center-x -0.7436439），默认 -0.6",
    ),
    CliOption(
        ("--center-y",), kind="float",
        help="视窗中心的虚部（如 --center-y 0.1318259），默认 0",
    ),
    CliOption(
        ("--palette",), kind="choice", choices=tuple(PALETTES),
        help="色带：" + " / ".join(PALETTES),
    ),
    CliOption(
        ("--backend",), kind="choice", choices=BACKENDS,
        help="计算后端：numpy（默认）/ numba（可选依赖）/ auto（大图自动选择）",
    ),
    CliOption(
        ("--scan",), kind="flag",
        help="扫描：逐级调高迭代上限，看集合面积估计怎么收敛（不开窗口）",
    ),
)


# ----------------------------------------------------------------------
# 参数校正（界面取值 -> 内核取值）
# ----------------------------------------------------------------------
def _num(value: Any, fallback: Optional[float]) -> Optional[float]:
    """把可能是字符串 / None 的输入转成 float（非法时返回 ``fallback``）。"""
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


def _clamp_int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def _pick_palette(value: Any) -> str:
    """色带：界面上给的是中文标签，终端里给的是内部名，两者都认。"""
    text = str(value or "")
    if text in PALETTE_LABELS:
        return text
    for name, label in PALETTE_LABELS.items():
        if text == label:
            return name
    return DEFAULT_PALETTE


def _pick_backend(value: Any) -> str:
    """显式参数优先，其次环境变量；未配置时保持 NumPy。"""
    name = str(value or os.environ.get("PRISMATH_MANDELBROT_BACKEND") or "numpy").strip().lower()
    if name not in BACKENDS:
        raise ValueError(f"未知的 Mandelbrot 计算后端：{name!r}（可选：{' / '.join(BACKENDS)}）")
    return name


def _resolve_magnification(value: Any) -> float:
    """放大倍率的对数：负值表示比默认取景更宽（缩小），两端都夹在允许区间里。"""
    return _clamp(_num(value, 0.0) or 0.0, MIN_MAGNIFICATION, MAX_MAGNIFICATION)


def _resolve_span(span: Any, zoom: Any) -> float:
    """视窗实部跨度：显式给了 ``--span`` 就用它，否则按 ``--zoom``（log₂ 倍率）推。"""
    explicit = _num(span, None)
    if explicit is not None:
        return _clamp(explicit, MIN_SPAN, MAX_SPAN)
    return _clamp(DEFAULT_SPAN / (2.0 ** _resolve_magnification(zoom)), MIN_SPAN, MAX_SPAN)


def _resolve_center(value: Any, fallback: float, bounds: Tuple[float, float]) -> float:
    """视窗中心的一个分量：非法输入退回默认值，合法输入夹到允许范围内。"""
    return _clamp(_num(value, fallback) or fallback, *bounds)


def options_from_ui(params: Dict[str, Any]) -> Dict[str, Any]:
    """把界面参数翻成**内部取值**（只认内部取值的内核才吃得下）。

    返回的键就是 :func:`build_mandelbrot` 需要的那些（外加渲染用的 ``palette``）。
    """
    return {
        "center_x": _clamp(_num(params.get("center_x"), DEFAULT_CENTER_X) or 0.0,
                           *CENTER_X_RANGE),
        "center_y": _clamp(_num(params.get("center_y"), DEFAULT_CENTER_Y) or 0.0,
                           *CENTER_Y_RANGE),
        "span": _resolve_span(None, params.get("magnification")),
        # 0 是合法值：内核按放大倍率自动给（见 model.iterations_for）
        "iterations": _clamp_int(params.get("iterations"), 0, MAX_ITERATIONS, 0),
        "pixels": _clamp_int(params.get("pixels"), MIN_PIXELS, MAX_PIXELS, DEFAULT_PIXELS),
        "palette": _pick_palette(params.get("palette")),
        # Tk 不增加控件；可以通过环境变量或调用参数显式启用加速。
        "backend": _pick_backend(params.get("backend")),
    }


# ----------------------------------------------------------------------
# 模型构造与 payload（对象级契约）
# ----------------------------------------------------------------------
def build_mandelbrot(params: Dict[str, Any]) -> Mandelbrot:
    """由**内部取值**的参数造模型（``spec.factory``；桌面视图与 :func:`handle` 共用）。

    ``aspect``（高 / 宽）可选：桌面视图按画布的形状传进来，于是图像能**铺满**窗口；
    不传时用 4:3 —— 终端 / 网页这些没有画布的后端用默认值就够了。
    """
    view = Viewport(
        center_x=_num(params.get("center_x"), DEFAULT_CENTER_X) or 0.0,
        center_y=_num(params.get("center_y"), DEFAULT_CENTER_Y) or 0.0,
        span=_clamp(_num(params.get("span"), DEFAULT_SPAN) or DEFAULT_SPAN, MIN_SPAN, MAX_SPAN),
    )
    return Mandelbrot(
        center_x=view.center_x,
        center_y=view.center_y,
        span=view.span,
        # 0 = 自动（内核按 span 推），所以下界从 0 起
        max_iter=_clamp_int(params.get("iterations"), 0, MAX_ITERATIONS, 0),
        pixels=_clamp_int(params.get("pixels"), MIN_PIXELS, MAX_PIXELS, DEFAULT_PIXELS),
        aspect=_num(params.get("aspect"), DEFAULT_ASPECT) or DEFAULT_ASPECT,
        backend=_pick_backend(params.get("backend")),
    )


def target_view(params: Dict[str, Any], action: str = "render") -> Viewport:
    """动作 -> **目标取景**（``handle`` 与桌面视图共用这一处换算）。

    桌面视图的"即时预览"也要知道目标取景（不然预览和随后那张清晰图会对不上），
    所以这个换算只写一份：模型侧、视图侧都调它。
    """
    if action == "reset_view":
        return Viewport(DEFAULT_CENTER_X, DEFAULT_CENTER_Y, DEFAULT_SPAN)
    opts = options_from_ui(params)
    view = Viewport(opts["center_x"], opts["center_y"], opts["span"])
    factor = {"zoom_in": 2.0, "zoom_out": 0.5}.get(action, 1.0)
    return view.zoomed(factor)


def payload_for(field: MandelbrotField, palette: str = DEFAULT_PALETTE,
                cost_ms: float = 0.0, as_array: bool = False) -> Dict[str, Any]:
    """把一次渲染包成界面用的 payload（唯一的返回结构：``mandelbrot-<色带>``）。

    ``values`` 是**屏幕序**（第 0 行 = 顶部）的色带下标：与
    :class:`~prismath.ui.tk.kit.chart.ChartSpec` 里的 ``vmin=0 / vmax=63`` 一一对应，
    画布把它当"连续场"直接拼成一张 ``PhotoImage``。

    ``as_array=True`` 时 ``values`` 给 **numpy 数组**（桌面视图用：几百 k 像素转成 Python
    列表本身就要几十毫秒）；默认给列表，因为数据级契约要能 JSON 序列化（网页 / 通用视图）。
    """
    palette = _pick_palette(palette)
    data = field.as_dict()
    return {
        "view": f"mandelbrot-{palette}",
        "palette": palette,
        "paletteName": PALETTE_LABELS.get(palette, palette),
        **data,
        "zoomFactor": 2.0 ** float(data["magnification"]),
        "areaReference": AREA_REFERENCE,
        "levels": LEVELS,
        "values": field.level_array() if as_array else field.level_values(),
        "elapsedMs": (field.elapsed * 1000.0) if not cost_ms else cost_ms,
    }


# ----------------------------------------------------------------------
# 动作处理器
# ----------------------------------------------------------------------
def _render(params: Dict[str, Any], action: str = "render") -> Dict[str, Any]:
    """按动作渲染一次（取景由 :func:`target_view` 换算，与桌面视图共用）。"""
    opts = options_from_ui(params)
    view = target_view(params, action)
    model = build_mandelbrot({**opts, "center_x": view.center_x,
                              "center_y": view.center_y, "span": view.span})
    return payload_for(model.render(), opts["palette"])


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """动作分发入口，由 :class:`~prismath.spec.ModelSpec` 调用。

    ``payload`` 目前用不上（"点击放大"需要点在哪一格的**像素坐标**，那是纯界面信息，
    由桌面视图自己换算后改一组参数再调 :func:`handle`），保留它是为了与统一签名一致。
    """
    if action in ("render", "zoom_in", "zoom_out", "reset_view"):
        return _render(params, action)
    raise ValueError(f"Mandelbrot 集模型不支持的动作：{action}")


# ----------------------------------------------------------------------
# 终端模式
# ----------------------------------------------------------------------
#: 字符画的宽度（列）与高宽比：终端字符是"高 ≈ 2 × 宽"，所以纵向按一半采样
ASCII_COLS = 100
ASCII_ASPECT = 0.38
#: 逃逸速度 -> 字符（越亮 = 逃逸越慢，越贴近集合边界）
ASCII_RAMP = " .:-=+*#%@"
#: ``--scan`` 逐级调高的迭代上限
_SCAN_LIMITS = (10, 20, 50, 100, 200, 500, 1000, 2000)
#: ``--scan`` 用的采样分辨率（扫 8 档，分辨率不能跟着 --pixels 一起放大）
_SCAN_PIXELS = 160


def _ascii_field(field: MandelbrotField) -> List[str]:
    """把色带下标画成字符画：集合内为实心 ``█``，其余按逃逸速度由疏到密。

    字符画是**独立渲染**的一张小图（``ASCII_COLS × ASCII_COLS·ASCII_ASPECT``），
    不是对那张大图的抽样 —— 抽样会把边界上最细的结构整个丢掉。
    """
    levels = np.flipud(field.levels)
    ramp = ASCII_RAMP
    last = len(ramp) - 1
    lines: List[str] = []
    for row in range(field.rows):
        chars: List[str] = []
        for col in range(field.cols):
            level = int(levels[row, col])
            if level <= 0:
                chars.append("█")
            else:
                chars.append(ramp[level * last // (LEVELS - 1)])
        lines.append("".join(chars))
    return lines


def _cli(raw_args) -> int:
    """终端模式：出一次统计 + 字符画，或（``--scan``）扫描迭代上限对面积估计的影响。

    取值统一走 :class:`~prismath.spec.CliArgs`：名字与默认值都来自 :data:`CLI_OPTIONS`
    的声明，不手写魔法字符串。
    """
    args = CliArgs(raw_args, CLI_OPTIONS)
    iterations = _clamp_int(args.iterations, 0, MAX_ITERATIONS, 0)      # 0 = 自动
    pixels = _clamp_int(args.pixels, MIN_PIXELS, MAX_PIXELS, DEFAULT_PIXELS)
    palette = _pick_palette(args.palette)
    backend = _pick_backend(args.backend)
    center_x = _resolve_center(getattr(args, "center_x", None), DEFAULT_CENTER_X, CENTER_X_RANGE)
    center_y = _resolve_center(getattr(args, "center_y", None), DEFAULT_CENTER_Y, CENTER_Y_RANGE)
    span = _resolve_span(getattr(args, "span", None), getattr(args, "zoom", 0.0))
    view = Viewport(center_x, center_y, span)

    if args.scan:
        print("=" * 78)
        print(f"Mandelbrot 集 · 迭代上限扫描 | {view.label()} | "
              f"{_SCAN_PIXELS}×{int(round(_SCAN_PIXELS * DEFAULT_ASPECT))} 采样")
        print("=" * 78)
        print(f"{'迭代上限':>10} | {'集合内像素':>10} | {'集合内占比':>10} | "
              f"{'面积估计':>10} | {'耗时':>10}")
        print("-" * 78)
        for limit, result in scan_iterations(list(_SCAN_LIMITS), center_x=center_x,
                                             center_y=center_y, span=span,
                                             pixels=_SCAN_PIXELS, backend=backend):
            print(f"{limit:>10} | {result.inside_count:>10} | "
                  f"{result.inside_ratio:>10.4f} | {result.area:>10.6f} | "
                  f"{result.elapsed * 1000:>7.1f} ms")
        print("-" * 78)
        print(f"提示：像素是有限网格、迭代也有上限，所以面积估计随上限单调下降并趋于数值真值 "
              f"≈ {AREA_REFERENCE:.4f}；")
        print("      上限太小会把「其实会逃逸」的点算成集合内，于是面积偏大、形状发胖 ——")
        print("      放大得越深，越要把「最大迭代次数」一起调大。")
        return 0

    model = build_mandelbrot({"center_x": center_x, "center_y": center_y, "span": span,
                              "iterations": iterations, "pixels": pixels, "backend": backend})
    field = model.render()
    print("=" * 78)
    print(f"Mandelbrot 集 | {field.view_text} | 色带：{PALETTE_LABELS[palette]}")
    print("=" * 78)
    print(f"集合内像素 {field.inside_count} / {field.rows * field.cols}"
          f"（{field.inside_ratio:.4f}），视窗内 M 的面积估计 ≈ {field.area:.6f}"
          f"（整个集合的真值 ≈ {AREA_REFERENCE:.6f}，放大后这个数只代表当前视窗内的部分）")
    mean_escape = field.mean_escape
    print(f"逃逸点平均迭代数 {mean_escape:.1f}" if mean_escape is not None
          else "所有像素都没逃逸（迭代上限太小？）",
          end="")
    print(f" | 渲染耗时 {field.elapsed * 1000:.1f} ms")

    art_model = build_mandelbrot({"center_x": center_x, "center_y": center_y, "span": span,
                                  "iterations": iterations, "pixels": ASCII_COLS,
                                  "backend": backend})
    art_model.rows = int(round(ASCII_COLS * ASCII_ASPECT))     # 终端字符 ≈ 2:1 的高宽比
    art = _ascii_field(art_model.render())
    print()
    print(f"字符画（{ASCII_COLS}×{len(art)} 采样；█ = 集合内，其余按逃逸速度由疏到密）")
    for line in art:
        print("  " + line)
    print("=" * 78)
    print("提示：左键点画布 = 以该点为锚放大，右键 = 缩小（桌面窗口里）；"
          "终端里用 --zoom / --center 指定要看的区域。")
    return 0


def build_spec() -> ModelSpec:
    """构造并返回 Mandelbrot 集模型的元数据。"""
    return ModelSpec(
        key="mandelbrot",
        name="Mandelbrot 集模型",
        topic="分形与自相似",
        summary="把 z → z² + c 迭代到发散，记下每个 c 的逃逸时间就得到 Mandelbrot 集："
                "边界处处自相似，面积有限（≈ 1.5066）却怎么放大都有新结构。",
        description=(
            "对复平面上的每个点 c 迭代 z₀ = 0、z_{n+1} = z_n² + c：\n\n"
            "    **轨道有界**的点（迭代多少次都不跑掉）组成 Mandelbrot 集 M，\n"
            "    轨道发散的点则记下它**第几步**跑出半径 2 的圆 —— 这个「逃逸时间」就是上色的依据。\n\n"
            "三条一眼能看懂、又完全确定的结论：\n\n"
            "1. **|c| > 2 的点一定逃逸**（因为 c ∈ M ⇒ |c| ≤ 2），所以视窗取实部 [-2.2, 1.0] "
            "就装得下整个集合；\n"
            "2. **关于实轴对称**：c 与它的共轭要么同属 M、要么同时逃逸，而且逃逸步数完全相同 ——"
            "画面上半张和下半张是严格镜像；\n"
            "3. **主心形与周期 2 圆盘**（周期 1、2 的吸引域）有闭式判据，它们整体落在 M 里，"
            "内核就用它当「逃逸判据有没有漏判」的护栏。\n\n"
            "**为什么它值得看**：集合边界是**分形** —— 面积有限（数值估计 ≈ 1.5066），"
            "但怎么放大都长出新结构，而且到处都能找到和整体相似的小小 M（自相似）。"
            "主视图之外的经典去处：海马谷（-0.75 + 0.1i 附近）、象谷、以及各处的迷你 M。\n\n"
            "**怎么玩**：\n\n"
            "1. **渲染视图**：按当前取景、迭代上限与色带算出整幅图像（集合内部最暗，"
            "越贴近边界逃逸越慢、越亮）；\n"
            "2. **点哪放大哪**：画布上**左键**点一下就以该点为锚放大 2 倍，"
            "**右键**缩小，**滚轮**也行；左侧「放大 / 缩小 / 重置视图」按钮作用在视窗中心上。"
            "每一下都是**先出预览再细化**：画面立刻按新取景拉过去，清晰的一张随后换上 ——"
            "不用干等一整轮渲染；\n"
            "3. **缩放用对数**：视窗宽度从 3.2 一直缩到 2⁻²⁴ × 3.2，「放大倍率 log₂」"
            "这个滑块线性拖动就是等比放大（点一下 = +1）；\n"
            "4. **越深越要加迭代**：迭代上限太小时，边界附近「其实会逃逸」的点被算成集合内，"
            "形状会发胖、细节会糊 —— 放大之后把「最大迭代次数」一起调大。\n\n"
            "**两个容易误解的地方**：\n\n"
            "1. **面积是像素计数**：「集合内像素占比 × 取景框面积」，所以它依赖分辨率与迭代"
            "上限（终端里的 ``--scan`` 扫的就是这条收敛曲线）。低分辨率下会有几个百分点的偏差，\n"
            "   这不是 bug，而是「用有限网格量一个分形」的代价；\n"
            "2. **颜色不代表数学上有分界**：色带下标是逃逸时间压成的 64 档，相邻两档之间"
            "在数学上没有界线 —— 那只是把连续量离散化的结果（同心色带正是等势线的模样）。"
        ),
        params=PARAMS,
        actions=ACTIONS,
        view="mandelbrot",
        accent="#f472b6",
        icon="❋",
        handler=handle,
        cli=_cli,
        cli_options=CLI_OPTIONS,
        # 对象级契约：桌面视图在「点击放大」时要自己造模型 → 渲染 → 原地重绘
        factory=build_mandelbrot,
        highlights=("z → z² + c：逃逸时间画出集合 M",
                    "边界处处自相似，面积却只有 ≈ 1.5066",
                    "点哪放大哪；越深越要加迭代上限"),
        order=10,
    )
