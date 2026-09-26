# -*- coding: utf-8 -*-
"""
Mandelbrot 集模型 · 桌面视图（Tkinter）
========================================

本视图继承**通用图表骨架** :class:`~prismath.ui.tk.kit.chart.ChartViewBase`，用到的图种是
``ChartSpec(kind="grid")`` 的**连续场**路径（数值 → 色带 → 整块位图，见 ``chart.py``）：
参数表单、动作按钮、画布、叠加文字、指标行、徽章、状态栏都由基类负责，本文件写**声明**
（每种色带一张图怎么画 :attr:`MandelbrotView.CHART_SPECS`、指标行怎么取
:attr:`MandelbrotView.RESULT_ROWS`）外加几件"声明表达不了的事"：

1. **布局可切换**（:meth:`_toggle_layout`）：默认**沉浸模式**——两侧栏 ``grid_remove``、
   画布跨满三列，关键数字与手势提示改成画在画布上的 HUD；按 ``I`` 切回仪器台。
   刻意**不重建控件**（只是改 grid），所以来回切换不丢状态、也不会出现两份绑同一批
   Tk 变量的控件；
2. **按窗口大小渲染**（:meth:`_render_size`）：分辨率不写死在参数里，而是取画布可用区域，
   于是图像正好**铺满**窗口、像素一格对一格（"整数倍放大"那套做不到：360 宽的图放进
   700 宽的画布只能铺 1 倍，四周一片空白）。窗口一改就重新渲染一次；
3. **手势**：左键拖动 = 平移（直接挪画布上的图像图元，0 ms 响应，松手后才重算）；
   滚轮 = 以光标为锚细步缩放（一格 1.25 倍）；点击 = 放大、右键 = 缩小；
   退格 = 退回上一步（取景栈）、``0`` = 重置；
4. **先预览、再细化**：换取景时立刻把上一张按新取景**重采样**拉过去（几十毫秒，画面马上
   跟上手势），清晰的那张丢到**后台线程**算，算完再换上 —— 一屏像素的内核开销是几百毫秒，
   同步做的话窗口会冻住。连点几下时只有最后一次的结果会被采用（代号作废旧结果）；
   预览的**源取景**取自 `_values_view`（那张清晰图自己的取景），不是"当前 payload" ——
   否则连点两下之后会把老图错位地映射一遍（预览"飞"到别处，清晰图到了再跳回来）；
5. **取景与表单联动**：取景写回参数变量（否则点了十下放大、滑块还停在 ×1），
   参数一改又反过来触发一次（延迟）重渲染。

色带为什么是"一张色带一份声明"
------------------------------
连续场的色带（``ChartSpec.cmap``）来自**声明**而不是 payload，所以四种色带就声明四张图；
payload 里的 ``view`` 字段（``mandelbrot-magma`` / ``-viridis`` / …）负责选中对应那一张。
这样"换色带"仍然是纯声明，视图里不必覆盖任何绘制方法。
"""

from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np

from prismath.ui.tk.kit import (
    BG_CANVAS,
    FIELD_PAD,
    NO,
    OK,
    ChartSpec,
    ChartViewBase,
    register_view,
)
from prismath.ui.tk.theme import DIM, FAINT, FONT_SM, WARN

from ..model import (
    AREA_REFERENCE,
    DEFAULT_COLS,
    DEFAULT_ROWS,
    LEVELS,
    MAX_PIXELS,
    MIN_PIXELS,
    PALETTES,
    Viewport,
    make_viewport,
    resample_to,
)
from ..spec import (
    PALETTE_LABELS,
    build_mandelbrot,
    options_from_ui,
    payload_for,
    target_view,
)

#: 强调色（与 ``spec.accent`` 一致）
COL_ACCENT = "#f472b6"

#: 单张图的渲染像素总数上限：内核开销与像素数成正比，超大窗口按比例缩小渲染再拉满。
#: 它是 :attr:`MandelbrotView.MAX_RENDER_PIXELS` 的默认值（测试会把它压小）。
DEFAULT_MAX_RENDER_PIXELS = 1_100_000

#: 参数改动后的（延迟）重渲染间隔：连拖滑块时只渲染最后停下的那一处
DEFAULT_RENDER_DELAY = 320

#: 滚轮一格（Windows 的 delta=120）缩放多少倍。**细步**是有意的：一档 2 倍会让人
#: "一格飞出去"，而分形浏览器的标准手感是每格 1.1~1.3 倍。
WHEEL_STEP = 1.25
#: 左键点一下放大多少倍（拖动 = 平移，不缩放）
CLICK_ZOOM = 1.5
#: 拖动多少像素才算"拖动"（小于它当成点击，避免手抖导致点不动）
DRAG_SLOP = 3
#: 退回上一步最多记几步取景
UNDO_DEPTH = 32
#: 两次预览之间至少隔多久（毫秒）：滚轮连滚时不至于把事件队列堵住
PREVIEW_MIN_INTERVAL_MS = 60
#: 进来时默认是沉浸式布局（这个模型的图像本身就是产品；按 I / 点右上角提示切回参数面板）
DEFAULT_IMMERSIVE = True

EXPLAIN = (
    "说明：\n"
    "· 每个像素 c 迭代 z → z² + c：跑到 |z| > 2 就记下第几步逃逸，"
    "迭代到上限仍未逃逸的算作集合内；\n"
    "· 上色用**平滑逃逸时间** μ = n + 1 − log₂(ln|zₙ| / ln 2)，再压成 64 档："
    "集合内部最暗，越贴近边界（逃逸越慢）越亮，于是细节全在剪影边缘上；\n"
    "· 集合关于实轴对称，所以画面上半张与下半张是严格镜像；\n"
    "· **左键拖动 = 平移**（整幅图跟着手走）；**滚轮 = 以光标为锚缩放**（一格 1.25 倍，"
    "细步是为了好停在想看的位置）；**左键点击 = 放大**（点哪放大哪）、**右键 = 缩小**；"
    "**退格 = 退回上一步**、**0 = 重置视图**；\n"
    "· 每次换取景都是**先出预览再细化**：画面立刻按新取景拉过去（不失真、只是暂时糊一点），"
    "清晰的一张在后台算完自动换上 —— HUD / 状态栏 / 徽章上会写着「正在细化」；\n"
    "· **布局可切换**（`I` 键，或点画布右上角的提示）：默认**沉浸模式** —— 画布铺满窗口，"
    "参数与指标收起来只留 HUD；按一下切回仪器台（参数表单 + 指标 + 说明都在）。\n"
    "· 迭代上限默认是**自动**：「最大迭代次数」给 0 就按放大倍率取（≈ 200·2^(倍率/2)）。"
    "放大得越深越需要迭代，上限太小会把边界附近「其实会逃逸」的点算成集合内"
    "（形状发胖、一片暗）；\n"
    "· 集合内有一大批像素是**解析判据直接判出来的**（主心形、周期 2 圆盘与几个内切圆盘），"
    "它们一次迭代都不做 —— 所以「集合内像素」里那部分再放大也不花时间；\n"
    "· 图像按窗口大小渲染（窗口越大算得越久，像素总数有上限）；"
    "面积估计是**像素计数**（集合内占比 × 取景框面积）：默认取景下它约等于整个集合"
    f"的面积（数值真值 ≈ {AREA_REFERENCE:.4f}），放大之后它只代表**当前视窗内**那一部分。"
)


def _field_spec(palette: str) -> ChartSpec:
    """一种色带对应一张连续场图的声明（数据都来自 payload）。"""
    label = PALETTE_LABELS.get(palette, palette)
    return ChartSpec(
        kind="grid",
        title=f"Mandelbrot 集（{label}）",
        caption="{viewText} · 色带 {paletteName}",
        row_field="rows", col_field="cols",
        vmin=0.0, vmax=float(LEVELS - 1),   # payload 里的 values 是 0..63 的色带下标
        cmap=palette,
        clickable=True,                     # 允许点击 / 拖动反查成 (行, 列)
        color=COL_ACCENT,
    )


@register_view("mandelbrot")
class MandelbrotView(ChartViewBase):
    """Mandelbrot 集的可视化视图（通用图表骨架 + 连续场 + 点哪放大哪）。"""

    HINTS = ("左键拖动 平移   滚轮 缩放   左键点击 放大   右键 缩小   退格 退回   "
             "I 沉浸/面板   0 重置   R 重渲")
    INTRO_STATUS = "就绪：正在按窗口大小渲染第一张（拖动平移、滚轮缩放、点哪放大哪）。"
    FALLBACK_ACCENT = COL_ACCENT
    EXPLAIN = EXPLAIN

    # ---------------- 右侧指标行（声明即可，不必写刷新代码） ----------------
    RESULT_ROWS: Tuple[Tuple[str, str], ...] = (
        ("分辨率", "size"),
        ("最大迭代", "iter"),
        ("集合内像素", "inside"),
        ("集合内占比", "ratio"),
        ("面积估计", "area"),
        ("逃逸点均步数", "mean"),
        ("放大倍率", "mag"),
        ("视窗宽度", "span"),
        ("渲染耗时", "cost"),
    )
    #: 指标行取值来自 payload 的哪个键
    ROW_SOURCES: Mapping[str, str] = {
        "size": "sizeText", "iter": "maxIter", "inside": "inside",
        "ratio": "insideRatio", "area": "area", "mean": "meanEscape",
        "mag": "zoomFactor", "span": "span", "cost": "elapsedMs",
    }
    #: 指标行的格式化模板
    RESULT_FORMATS: Mapping[str, str] = {
        "ratio": "{:.2%}", "area": "{:.4f}", "mean": "{:.1f}",
        "mag": "×{:g}", "span": "{:.6g}", "cost": "{:.1f} ms",
    }

    # ---------------- 图表声明：payload["view"] -> 怎么画 ----------------
    CHART_SPECS: Mapping[str, ChartSpec] = {
        f"mandelbrot-{name}": _field_spec(name) for name in PALETTES
    }

    #: 走"渲染"这条路线的动作（其余动作交给基类）
    VIEW_ACTIONS: Tuple[str, ...] = ("render", "zoom_in", "zoom_out", "reset_view")
    #: 这些参数一改就（延迟）重新渲染；连拖滑块时只渲染最后停下的那一处
    AUTO_RENDER_KEYS: Tuple[str, ...] = (
        "iterations", "palette", "center_x", "center_y", "magnification",
    )
    #: 单张图的渲染像素总数上限（"越大越清晰、也越慢"的那个旋钮）
    MAX_RENDER_PIXELS: int = DEFAULT_MAX_RENDER_PIXELS
    #: 参数改动后延迟多久才真的重渲染（毫秒）
    RENDER_DELAY: int = DEFAULT_RENDER_DELAY

    # ==================================================================
    # 状态与首屏
    # ==================================================================
    def _setup_state(self) -> None:
        super()._setup_state()
        self._render_job: Optional[str] = None
        #: 正在把取景写回表单：此时参数回调不该再触发一次渲染
        self._syncing = False
        #: 渲染代号：只采用最新一次的结果（连点几下时中间那些作废）
        self._generation = 0
        #: 最近一次**清晰**渲染的色带下标（屏幕序，numpy 数组）**以及它对应的取景**。
        #: 两者必须成对记住：预览是"把这份 values 从它的取景重采样到新取景"，
        #: 只记 values 不记取景，连点两下之后就会拿"老图"当"新取景下的图"来映射（曾经真的错过）。
        self._values: Optional[np.ndarray] = None
        self._values_view: Optional[Viewport] = None
        #: 当前屏幕上那张图是**按多大尺寸**渲染的；窗口尺寸变了才值得重渲染
        self._rendered_size: Optional[Tuple[int, int]] = None
        #: 沉浸式布局（画布铺满，参数面板收起来）—— 可切换，见 DEFAULT_IMMERSIVE
        self._immersive: bool = DEFAULT_IMMERSIVE
        #: 三栏各自是哪些控件（界面搭好后由 :meth:`_collect_panels` 填；切布局只改它们的 grid）
        self._panels_left: List[tk.Widget] = []
        self._panels_center: List[tk.Widget] = []
        self._panels_right: List[tk.Widget] = []
        #: 左键拖动的起点、"这一按有没有变成拖动"、以及拖动前的取景（松开时压进退回栈）
        self._drag_from: Optional[Tuple[int, int]] = None
        self._drag_view: Optional[Viewport] = None
        self._drag_moved: bool = False
        #: 退回上一步的取景栈（每次改取景前压栈）
        self._undo: List[Viewport] = []
        #: 上次画预览的时刻（毫秒级时钟）：滚轮连滚时少画几次
        self._preview_at: float = 0.0

    def _after_build(self) -> None:
        self._bind_zoom_events()
        self._collect_panels()      # 先记下三栏控件（之后再 grid_remove，就查不到它们了）
        self._apply_layout()
        self._draw_message("正在按窗口大小渲染…")
        # 画布此刻多半还没拿到真实尺寸（窗口还没布局出来）。等它一下再渲染第一张，
        # 免得先按"默认尺寸"渲一张、再按真实尺寸重渲一张。
        self._first_job = self.root.after(30, self._render_when_ready)

    def _render_when_ready(self) -> None:
        """画布拿到可用尺寸后才渲染第一张；还没拿到就过一会儿再问。"""
        self._first_job = None
        if not self._alive:
            return
        if self.canvas.winfo_width() < MIN_PIXELS:
            self._first_job = self.root.after(30, self._render_when_ready)
            return
        self.run_action("render")

    def _bind_zoom_events(self) -> None:
        """补上基类没绑的鼠标交互：右键缩小、滚轮缩放、松开左键收尾。

        左键的**按下 / 拖动**由基类绑到 :meth:`_on_canvas_click` / :meth:`_on_canvas_drag`
        （本视图覆盖了那两个方法）：拖动 = 平移，没拖动 = 点哪放大哪。
        """
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        # HUD 上"点一下切回参数面板"的提示（绑定在 tag 上，画一次就长期有效）
        self.canvas.tag_bind("hud-toggle", "<Button-1>", lambda _e: self._toggle_layout())

    # ==================================================================
    # 布局：沉浸式（画布铺满） <-> 仪器台（参数 / 指标两栏）
    # ==================================================================
    def _toggle_layout(self) -> None:
        self._immersive = not self._immersive
        self._apply_layout()
        if self._immersive:
            self.var_status.set("已切到沉浸模式（按 I 或点右上角提示切回参数面板）。")
        else:
            self.var_status.set("已切回仪器台模式（按 I 切到沉浸模式）。")
        # 画布尺寸变了：先按新尺寸**重采样出预览**（立刻铺满，不再"缩在中间"），
        # 再把清晰的一张丢到后台
        view = self._current_view()
        if view is None:
            self._schedule_render(delay=0)
        else:
            self._start_render(dict(self.current_params()), view, "zoom")

    def _collect_panels(self) -> None:
        """记下三栏各自是哪些控件（只在界面刚搭好时调一次）。

        **不能每次切换时现查 ``host.grid_slaves``**：``grid_remove`` 之后那些控件就不在
        ``grid_slaves`` 的返回里了，于是"切回仪器台"会找不到该恢复谁 —— 参数栏再也回不来。
        """
        self._panels_left = list(self.host.grid_slaves(row=0, column=0))
        self._panels_center = list(self.host.grid_slaves(row=0, column=1))
        self._panels_right = list(self.host.grid_slaves(row=0, column=2))

    def _apply_layout(self) -> None:
        """按 :attr:`_immersive` 显隐两侧栏：沉浸模式下画布**跨满三列**。

        刻意不重建控件（不用"拆了重搭"那套）：参数表单、指标行、状态栏全部原地复用，
        显隐只是改 grid —— 于是来回切换**不丢任何状态**（取景、色带、迭代上限都还在），
        也不会多出一份绑定同一批 Tk 变量的控件。
        """
        side = self._panels_left + self._panels_right
        center = self._panels_center
        for widget in side:
            if self._immersive:
                widget.grid_remove()
            else:
                widget.grid()
        for widget in center:
            widget.grid_configure(columnspan=3 if self._immersive else 1)
        self.host.update_idletasks()

    def shutdown(self) -> None:
        self._cancel_render_job()
        super().shutdown()

    # ==================================================================
    # 画布尺寸 -> 渲染分辨率
    # ==================================================================
    def _render_size(self) -> Tuple[int, int]:
        """按画布可用区域定渲染分辨率（连续场会把它等比铺满，留白见 ``FIELD_PAD``）。

        两道上限：单边不超过 ``MAX_PIXELS``、总数不超过 :attr:`MAX_RENDER_PIXELS`
        —— 内核开销与像素数成正比，超大窗口得按比例缩着渲染（再拉满显示）。
        画布还没布局出来（宽高是 1）时退回默认尺寸。
        """
        width = self.canvas.winfo_width() - 2 * FIELD_PAD
        height = self.canvas.winfo_height() - 2 * FIELD_PAD
        if width < MIN_PIXELS or height < 2:
            return DEFAULT_COLS, DEFAULT_ROWS
        cols = min(float(width), float(MAX_PIXELS),
                   math.sqrt(self.MAX_RENDER_PIXELS * width / height))
        cols = max(cols, float(MIN_PIXELS))
        return int(round(cols)), max(2, int(round(cols * height / width)))

    # ==================================================================
    # 渲染：先预览（可选），再后台算清晰的一张
    # ==================================================================
    @staticmethod
    def _render_payload(params: Mapping[str, Any], view: Viewport,
                        size: Tuple[int, int]) -> Dict[str, Any]:
        """造模型 → 渲染 → payload（走对象级契约；``values`` 直接给 numpy 数组）。

        **故意是 staticmethod**：它要在后台线程里跑，而线程闭包一旦抓住 ``self``，
        这个视图（连同它那一堆 tkinter 对象）就可能被后台线程释放 —— Tk 对象在非主线程里
        析构会抛 "main thread is not in main loop"（后台线程里触发一次 GC 就会撞上）。
        只把纯数据（参数 / 取景 / 尺寸）交给线程。
        """
        opts = options_from_ui(dict(params))
        cols, rows = size
        model = build_mandelbrot({
            **opts,
            "center_x": view.center_x, "center_y": view.center_y, "span": view.span,
            "pixels": cols, "aspect": rows / cols,
        })
        return payload_for(model.render(), opts["palette"], as_array=True)

    def _start_render(self, params: Mapping[str, Any], view: Viewport,
                      action: str = "render", throttle: bool = False) -> None:
        """换一个取景去渲染：能预览就先预览（几毫秒），清晰的那张丢到后台算。

        **为什么放后台**：一屏像素的内核开销是几百毫秒，同步渲染会让窗口冻住（连"正在
        细化"都画不出来）。代号（``_generation``）负责作废过期结果 —— 连点几下放大时，
        只有最后一次会被采用。``throttle`` 给滚轮用：连滚时少画几次预览。
        """
        self._apply_view_params(view)
        request = {**params, "center_x": view.center_x, "center_y": view.center_y,
                   "magnification": view.magnification}
        preview = (None if action == "render"
                   else self._preview_payload(view, throttle=throttle))
        if preview is not None:
            self._redraw_payload(preview)
            self.var_status.set("正在细化…（画面已按新取景拉过去，清晰的一张随后换上）")
        else:
            self.var_status.set("正在渲染…")

        self._generation += 1
        generation = self._generation
        size = self._render_size()          # 画布尺寸只能在主线程问
        #: 线程闭包只抓这些**纯数据**（连 self 都别抓：见 _render_payload 的说明）
        render, queue = self._render_payload, self._queue

        def job() -> None:
            try:
                result = render(request, view, size)
            except Exception as exc:        # 后台线程里出错也要报出来，而不是静悄悄
                queue.put(("render-error", f"{type(exc).__name__}: {exc}"))
                return
            queue.put(("render-done", (generation, result)))

        self._submit(job)

    def _preview_payload(self, view: Viewport,
                         throttle: bool = False) -> Optional[Dict[str, Any]]:
        """按新取景把上一张**拉**一下：几何立刻跟上手势，数字等清晰那张再报。

        用 :func:`~prismath.models.mandelbrot.model.resample_to`（与内核同一套像素约定），
        所以预览和随后的清晰图在几何上严格对齐，不会先"跳"一下再对齐。统计量先留空
        —— 显示的图还没有重算过，报出来的数字就是假的（界面上会显示 "—"）。

        **源取景取自已记住的 ``_values_view``（那张清晰图的取景），而不是"当前 payload"**：
        连点几下时 payload 已经变成上一张预览的取景了，用它当源就会把老图错位地映射一遍
        （预览会"飞"到别处，等清晰图到了再跳回来）。
        """
        payload = self._last
        values, source = self._values, self._values_view
        if values is None or source is None or not isinstance(payload, Mapping):
            return None
        if "error" in payload:
            return None
        if throttle:
            now = time.perf_counter() * 1000.0
            if now - self._preview_at < PREVIEW_MIN_INTERVAL_MS:
                return None
            self._preview_at = now
        rows, cols = values.shape
        preview = dict(payload)
        preview.update({
            "centerX": view.center_x,
            "centerY": view.center_y,
            "span": view.span,
            "magnification": view.magnification,
            "zoomFactor": 2.0 ** view.magnification,
            "values": resample_to(values, source, view, rows, cols),
            "preview": True,
            "viewText": f"{view.label()} · 正在细化…",
            "inside": None, "escaped": None, "insideRatio": None,
            "area": None, "meanEscape": None, "elapsedMs": None,
        })
        return preview

    def _handle_message(self, kind: str, payload: Any) -> None:
        """后台渲染的结果：只采用最新那一次。"""
        if kind == "render-done":
            generation, result = payload
            if not self._alive or generation != self._generation:
                return                      # 视图已关 / 已经有更新的请求：这一张作废
            self._adopt(result)
            return
        if kind == "render-error":
            self._draw_message(f"× 渲染失败：{payload}")
            self.var_status.set(f"渲染失败：{payload}")
            return
        super()._handle_message(kind, payload)

    def _adopt(self, result: Mapping[str, Any]) -> None:
        """采用一份新算好的 payload：记住色带下标**与它的取景**（下次预览用它）→ 原地重绘。"""
        values = result.get("values")
        if isinstance(values, np.ndarray):
            self._values = values.reshape(int(result["rows"]), int(result["cols"]))
            self._values_view = make_viewport(result.get("centerX"), result.get("centerY"),
                                              result.get("span"))
        self._rendered_size = (int(result["cols"]), int(result["rows"]))
        self._redraw_payload(result)

    # ==================================================================
    # 参数联动：改了参数就延迟重渲染；取景变化写回表单
    # ==================================================================
    def _on_param_change(self, key: str) -> None:
        super()._on_param_change(key)
        if self._syncing:
            return
        if key in self.AUTO_RENDER_KEYS:
            self._schedule_render()

    def _schedule_render(self, delay: Optional[int] = None) -> None:
        self._cancel_render_job()
        wait = self.RENDER_DELAY if delay is None else max(0, int(delay))
        self._render_job = self.root.after(wait, self._render_now)

    def _cancel_render_job(self) -> None:
        if self._render_job is None:
            return
        try:
            self.root.after_cancel(self._render_job)
        except tk.TclError:
            pass
        self._render_job = None

    def _render_now(self) -> None:
        self._render_job = None
        if self._alive:
            self.run_action("render")

    def _on_resize(self, _event=None) -> None:
        """画布尺寸变了 = 可用像素变了：先按旧数值重绘（基类），**真的变了**才重渲染。"""
        super()._on_resize()
        if self._render_size() != self._rendered_size:
            self._schedule_render()

    def _apply_view_params(self, view: Viewport) -> None:
        """把取景写回参数表单（**立刻**生效：连点几下才能逐级叠加、滑块跟着走）。"""
        values = (("center_x", view.center_x), ("center_y", view.center_y),
                  ("magnification", view.magnification))
        self._syncing = True
        try:
            for key, value in values:
                var = getattr(self, "param_vars", {}).get(key)
                if var is None:
                    continue
                try:
                    var.set(float(value))
                except (tk.TclError, TypeError, ValueError):
                    continue
                self._refresh_param_label(key)
        finally:
            self._syncing = False

    # ==================================================================
    # 动作：渲染类走"后台 + 预览"，其余交给基类
    # ==================================================================
    def run_action(self, key: str) -> None:
        if key not in self.VIEW_ACTIONS:
            super().run_action(key)
            return
        params = dict(self.current_params())
        if key != "render":                 # 换了取景才值得记一步，方便退回
            self._push_undo(self._current_view())
        self._start_render(params, target_view(params, key), key)

    # ==================================================================
    # 侧栏：仪器台模式下放一个「沉浸模式」按钮
    # ==================================================================
    def _build_extra_cards(self, parent: tk.Widget) -> None:
        card = self._card(parent, "布局")
        ttk.Button(card, text="⛶ 沉浸模式（I）", command=self._toggle_layout).pack(fill="x")
        ttk.Label(card, text="沉浸模式下画布铺满窗口、参数与指标收起来；再按一次 I"
                            "（或点画布右上角的提示）切回。",
                  style="CardDim.TLabel", font=FONT_SM, wraplength=252,
                  justify="left").pack(anchor="w", pady=(4, 0))

    # ==================================================================
    # 手势：拖动平移 / 点哪放大哪 / 滚轮细步 / 右键缩小 / 退回上一步
    # ==================================================================
    def _on_canvas_click(self, event) -> None:
        """左键按下：先只记住起点 —— 这一按到底是"点击"还是"拖动"，等松开时才知道。"""
        self._drag_from = (event.x, event.y)
        self._drag_view = self._current_view()
        self._drag_moved = False

    def _on_canvas_drag(self, event) -> None:
        """左键拖动 = **平移**：直接把画布上的图像挪走（0 ms 响应），松手后再重算清晰图。"""
        if self._drag_from is None:
            return
        dx = event.x - self._drag_from[0]
        dy = event.y - self._drag_from[1]
        if not self._drag_moved and abs(dx) < DRAG_SLOP and abs(dy) < DRAG_SLOP:
            return                        # 还没超过抖动阈值：当成点击，先不动
        if not self._drag_moved:
            self._drag_moved = True
            # 拖动开始了：把之前排队的渲染结果作废 —— 否则它按"拖动前的取景"算完换上来，
            # 画面会在你手底下跳回去
            self._generation += 1
        self._drag_from = (event.x, event.y)
        self._shift_image(dx, dy)

    def _on_canvas_release(self, event) -> None:
        self._drag_from = None
        if self._drag_moved:
            self._drag_moved = False
            self._push_undo(self._drag_view)        # 整段拖动算一步，可退回
            self._drag_view = None
            self._schedule_render(delay=0)          # 拖动结束：按新取景算一张清晰的
            return
        self._drag_view = None
        self._zoom_at(event.x, event.y, CLICK_ZOOM)

    def _shift_image(self, dx: int, dy: int) -> None:
        """把画布上的图像平移 ``(dx, dy)`` 显示像素，并把取景同步挪过去。

        平移**只动图像图元**：说明文字与 HUD 是屏幕空间的叠加层，跟着鼠标跑才怪。
        取景写回 ``_last`` 与参数表单，于是随后那次重渲染就是在"挪过之后的取景"上算的。
        """
        geom = self._grid_geom
        view = self._current_view()
        if geom is None or view is None:
            return
        scale, ox, oy, rows, cols = geom
        if scale <= 0:
            return
        for item in self.canvas.find_all():
            if self.canvas.type(item) == "image":
                self.canvas.move(item, dx, dy)
        self._grid_geom = (scale, ox + dx, oy + dy, rows, cols)
        per_pixel = view.span / max(cols * scale, 1.0)      # 显示像素 -> 复数单位
        self._remember(view.moved(-dx * per_pixel, dy * per_pixel))

    def _remember(self, view: Viewport) -> None:
        """把取景同步到"当前 payload + 参数表单"（不触发渲染、不压栈）。"""
        self._apply_view_params(view)
        payload = self._last
        if isinstance(payload, dict):
            payload.update({"centerX": view.center_x, "centerY": view.center_y,
                            "span": view.span, "magnification": view.magnification,
                            "zoomFactor": 2.0 ** view.magnification,
                            "viewText": view.label()})
            if self._chart is not None:
                self._draw_overlay(self._chart, None, self._caption(self._chart, payload))

    def _current_view(self) -> Optional[Viewport]:
        """当前画面正在看哪一块（取自 payload；不是连续场时返回 ``None``）。"""
        payload = self._last
        if not isinstance(payload, Mapping) or "error" in payload:
            return None
        if not str(payload.get("view") or "").startswith("mandelbrot"):
            return None
        return make_viewport(payload.get("centerX"), payload.get("centerY"),
                             payload.get("span"))

    def _push_undo(self, view: Optional[Viewport]) -> None:
        if view is None:
            return
        self._undo.append(view)
        del self._undo[:-UNDO_DEPTH]

    def _undo_step(self) -> None:
        """退回上一步取景（拖动整段算一步 —— 只有缩放 / 重置 / 松开时才压栈）。"""
        if not self._undo:
            self.var_status.set("没有可退回的取景了。")
            return
        target = self._undo.pop()
        self._start_render(dict(self.current_params()), target, "zoom")

    def _on_cell_click(self, row: int, col: int, start: bool) -> Optional[Mapping[str, Any]]:
        """兼容入口（基类的点击反查会调它）：按下那一格就以它为锚放大。

        真正走鼠标的路径是 :meth:`_on_canvas_click` / :meth:`_on_canvas_release`
        （要先区分"点击"与"拖动"），这里保留给"按格子驱动"的调用方（测试也是）。
        """
        if start:
            self._zoom(row, col, CLICK_ZOOM)
        return None

    def _on_right_click(self, event) -> None:
        self._zoom_at(event.x, event.y, 1.0 / CLICK_ZOOM)

    def _on_wheel(self, event) -> None:
        """滚轮：**细步**缩放（一格 1.25 倍），以光标位置为锚。"""
        delta = getattr(event, "delta", 0)
        if not delta:
            return
        notches = max(1, abs(int(delta)) // 120)
        factor = (WHEEL_STEP ** notches) if delta > 0 else (WHEEL_STEP ** -notches)
        self._zoom_at(event.x, event.y, factor, throttle=True)

    def _zoom_at(self, x: int, y: int, factor: float, throttle: bool = False) -> None:
        hit = self._cell_at(x, y)
        if hit is not None:
            self._zoom(hit[0], hit[1], factor, throttle=throttle)

    def _cell_at(self, x: int, y: int) -> Optional[Tuple[int, int]]:
        """画布坐标 -> ``(行, 列)``（拿连续场记下的几何反查；越界返回 ``None``）。"""
        geom = self._grid_geom
        if geom is None:
            return None
        cell, ox, oy, rows, cols = geom
        if cell <= 0:
            return None
        col, row = int((x - ox) // cell), int((y - oy) // cell)
        if 0 <= row < rows and 0 <= col < cols:
            return row, col
        return None

    def _zoom(self, row: int, col: int, factor: float, throttle: bool = False) -> None:
        """以第 ``(row, col)`` 格为锚缩放：锚点由 :meth:`Viewport.pixel` 换算。

        取景来自**当前 payload**（而不是表单）：表单里的滑块分辨率有限，连续点几下之后
        以 payload 为准才不会丢精度。迭代上限 / 色带则来自表单。
        """
        payload = self._last
        if not isinstance(payload, Mapping) or "error" in payload:
            return
        rows = int(payload.get("rows") or 0)
        cols = int(payload.get("cols") or 0)
        if rows <= 0 or cols <= 0:
            return
        view = self._current_view()
        if view is None:
            return
        self._push_undo(view)
        anchor = view.pixel(row, col, rows, cols)        # 这一格对应的复数
        self._start_render(dict(self.current_params()), view.zoomed(factor, anchor), "zoom",
                           throttle=throttle)

    # ==================================================================
    # 沉浸式 HUD：右栏收起来之后，关键数字与手势提示得贴到画布上
    # ==================================================================
    def _draw_overlay(self, spec: ChartSpec, reveal: Optional[int], caption: str) -> None:
        """在基类的叠加文字（左上角说明 / 右下角进度）之外，沉浸模式下再画一层 HUD。"""
        super()._draw_overlay(spec, reveal, caption)
        if not self._immersive:
            return
        canvas = self.canvas
        width = max(canvas.winfo_width(), 80)
        height = max(canvas.winfo_height(), 80)
        payload = self._last if isinstance(self._last, Mapping) else {}
        refining = bool(payload.get("preview"))

        stats = (f"{self.vals['size'].get()} · {self.vals['iter'].get()} 次迭代上限 · "
                 f"色带 {payload.get('paletteName', '—')}")
        numbers = (f"集合占 {self.vals['ratio'].get()} · 面积 {self.vals['area'].get()} · "
                   f"耗时 {self.vals['cost'].get()}")
        analytic = payload.get("analyticInside")
        if isinstance(analytic, int):
            numbers += f" · 判据直接判 {analytic} 像素"
        lines = [stats, numbers]
        if refining:
            lines.append("正在细化…（画面已按新取景拉过去，清晰的一张随后换上）")

        # 左下角：两三行小字（带半透明底色，压在亮色带上也看得清）
        self._hud_text(12, height - 10, "sw", "\n".join(lines),
                       fill=WARN if refining else DIM)
        # 右上角：一行可点的提示（点一下切回参数面板）
        self._hud_text(width - 12, 10, "ne", "I = 参数面板（点这里）", fill=FAINT,
                       tag="overlay hud-toggle")
        # 正下方：手势提示
        self._hud_text(width // 2, height - 10, "s",
                       "拖动 平移 · 滚轮 缩放 · 点击 放大 · 右键 缩小 · "
                       "退格 退回 · 0 重置 · R 重渲", fill=FAINT)

    def _hud_text(self, x: float, y: float, anchor: str, text: str,
                  fill: str = DIM, tag: str = "overlay") -> None:
        """画一条 HUD 文字，并在它下面垫一块"半透明"底色（Tk 没有 alpha，用点阵网格凑）。"""
        item = self.canvas.create_text(x, y, anchor=anchor, text=text, fill=fill,
                                       font=FONT_SM, justify="left", tags=tag)
        box = self.canvas.bbox(item)
        if box:
            backdrop = self.canvas.create_rectangle(
                box[0] - 5, box[1] - 3, box[2] + 5, box[3] + 3,
                fill=BG_CANVAS, outline="", stipple="gray75", tags=tag)
            self.canvas.tag_lower(backdrop, item)

    # ==================================================================
    # 快捷键：I 切布局、0 重置、退格退回、R 重渲（数字键 1-4 仍触发动作用）
    # ==================================================================
    def on_key(self, key: str) -> None:
        text = str(key).lower()
        if text == "i":
            self._toggle_layout()
            return
        if text == "r":
            self._schedule_render(delay=0)
            return
        if text in ("0", "home"):
            self.run_action("reset_view")
            return
        if text in ("backspace", "delete"):
            self._undo_step()
            return
        super().on_key(key)

    # ==================================================================
    # 钩子：徽章与状态栏
    # ==================================================================
    def _badge_for(self, payload: Mapping[str, Any],
                   values: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
        """徽章：细化中说细化，默认取景报"面积 ≈ 1.5066"，放大之后报倍率。

        放大之后面积只是"当前视窗内那一块"的面积，再和整个集合的真值比就没有意义了，
        所以到那时把主角换成放大倍率 —— 判据不一样，不硬凑一个 OK / NO 出来。
        """
        ratio = values.get("ratio")
        share = f"{float(ratio):.1%}" if isinstance(ratio, (int, float)) else "—"
        mag = values.get("mag")
        text = f"×{float(mag):g}" if isinstance(mag, (int, float)) else "—"
        if payload.get("preview"):
            return f"正在细化 {text}\n（先按上一张拉过去，清晰的一张随后换上）", NO
        if isinstance(mag, (int, float)) and float(mag) <= 1.001:
            area = values.get("area")
            if isinstance(area, (int, float)):
                return (f"M 面积 ≈ {float(area):.4f}（数值真值 {AREA_REFERENCE:.4f}）\n"
                        f"集合占 {share}", OK)
        if isinstance(mag, (int, float)):
            return f"放大 {text}\n集合占 {share}", OK
        return None

    def _status_for(self, payload: Mapping[str, Any], values: Mapping[str, Any],
                    partial: bool) -> Optional[str]:
        if not str(payload.get("view") or "").startswith("mandelbrot"):
            return None
        if payload.get("preview"):
            return "正在细化…（画面已按新取景拉过去，清晰的一张随后换上）"
        return (f"渲染完成：{self.vals['size'].get()} 像素、"
                f"{self.vals['iter'].get()} 次迭代上限，集合占 {self.vals['ratio'].get()}"
                f"；拖动 = 平移，滚轮 = 缩放，点击 = 放大，退格 = 退回上一步。")
