# -*- coding: utf-8 -*-
"""
通用图表骨架：参数表单 + 声明式图表
=====================================

为什么需要这一层
----------------
:class:`~prismath.ui.tk.kit.base.ModelViewBase` 是「什么都自己写」的万能骨架，
``PercolationViewBase`` 又和渗流语义（概率 p、格子、判据、逐层蔓延）强绑定。非渗流模型
夹在中间很尴尬：要么落回「只看 JSON」的通用视图，要么整份界面都自己写。

:class:`ChartViewBase` 补上这一层：在「参数表单 + 动作按钮」（沿用 ``ModelViewBase``）之外，
再给出一个**声明式的通用图表**——模型只要说清「动作返回的 JSON 里哪些字段怎么画」，
画布、坐标轴、网格、参考线、逐帧动画与右侧指标行都由工具箱负责，视图里可以一行 Tk 代码都不写。

声明几样东西即可
----------------
* :attr:`ChartViewBase.CHART_SPECS`：``payload["view"] -> ChartSpec``，每种返回结构怎么画；
* :attr:`ChartViewBase.RESULT_ROWS` / ``ROW_SOURCES`` / ``RESULT_FORMATS``：右侧指标行；
* :attr:`ChartViewBase.EXPLAIN`：面板底部的说明段落；
* 可选钩子：``_badge_for(payload, values)``（结论徽章）、``_partial_rows(payload, drawn)``
  （动画进行中按"已画出的前 drawn 个样本"给实时指标）、``_status_for(payload, values)``。

支持五种图（:attr:`ChartSpec.kind`）
-----------------------------------
============  ==========================================================
``segments``  线段云：由「中心 + 夹角 + 长度」描述，可按 0/1 掩码着色（投针、键……）
``series``    曲线族：横轴 + 若干纵轴序列，可选水平参考线（收敛过程、直方趋势……）
``bars``      柱状：一组数值（可带标签）
``grid``      栅格 / 像素场：离散态（0/1 掩码，可多帧）或连续场（数值 + 色带）
``text``      只出文字（无法作图时的兜底）
============  ==========================================================

带 ``animate=True`` 的图会**从零开始逐个出现**（左上侧栏自动多出「动画间隔」卡片），
让「样本越来越多」这件事在画布上看得见；``_partial_rows`` 还能让指标随样本实时刷新。

栅格图（``kind="grid"``）的两条渲染路径与两种时间轴
--------------------------------------------------
* **离散态**（``frames`` / ``cells``，每帧一个 0/1 字符串）用「预建矩形 + 差分刷新」：
  每帧只对"新活 / 刚死"的格子做一次 ``create_rectangle`` / ``delete``，因此一帧的开销
  与**变化量**成正比，而不是与格子总数成正比；
* **连续场**（``values`` + ``vmin``/``vmax``/``cmap``）走**整块位图**：数值 → 64 档色带
  （numpy 查表）→ 最近邻重采样到目标尺寸 → 一份 PPM → 一张 :class:`tkinter.PhotoImage`。
  一次 ``PhotoImage`` 构造就是全部开销，没有逐图元、也没有逐像素的 Python 循环
  （Mandelbrot、热力图）。**连续场铺满画布，不受"整数倍格子"的限制** ——
  离散态必须整数倍（矩形不能糊边、差分刷新要按格对齐），而连续场每个像素本来就是一次
  数值采样，重采样到任意尺寸是它天然该有的能力；
* 多帧（``frames``）表示**时间轴**：``animate=True`` 时**每帧前进恰好一帧**（不是把
  总时长摊成固定帧数），于是「动画间隔」滑块就是"每一代/每一帧的间隔"——
  元胞自动机必须逐代显示，摊薄会把滑翔机跳过去；
* ``clickable=True`` 时画布会把点击 / 拖拽反查成 ``(行, 列)`` 交给
  :meth:`ChartViewBase._on_cell_click`（默认不处理，于是既有模型的行为完全不变）。

实测（Windows / Python 3.13，画布 900×700，``cell`` 为整数倍格子边长）
----------------------------------------------------------------------
============  ======  ================  ==========================  ==========
棋盘          格边长  全量重建一帧      差分刷新（变化 10%）        图像缓冲
============  ======  ================  ==========================  ==========
30×30          22     5.8 ms            0.6 ms（90 格）             10.4 ms
50×50          13     47.9 ms           3.7 ms（250 格）            18.5 ms
80×80           8     29.2 ms           2.8 ms（640 格）             7.2 ms
120×120         5     55.6 ms           6.7 ms（1440 格）          10.7 ms
============  ======  ================  ==========================  ==========

* 差分刷新约 **0.012 ms / 变化格**（与棋盘大小无关），而**全量重建是 30–56 ms/帧** ——
  所以"每帧只改动变化的格子"不是微优化，而是逐代播放能不能流畅的分水岭；
* 全量重建只在窗口缩放 / 换一种图时发生（走一次即可）；
* 连续场的整块位图是**按像素计价**的（见下表），棋盘越大越不划算 —— 所以
  **连续场**（Mandelbrot、热力图）走它，**离散场**（元胞自动机、沙堆）走矩形差分。

实测（Windows / Python 3.13，画布 868×708；一栏 = "数值 → 色带 → PPM → PhotoImage"）
------------------------------------------------------------------------------
==========  =========  ====================  ==================  ==================
数值网格     像素数      旧：逐像素拼字符串      新：整块位图（同尺寸）  新：整块位图（铺满）
==========  =========  ====================  ==================  ==================
360×270      97k       109 ms（放大到 720×540）  10.0 ms（360×270）    58.8 ms（828×621）
640×480      307k      768 ms（640×480）          50.6 ms（640×480）    78.4 ms（828×621）
==========  =========  ====================  ==================  ==================

* 同样尺寸下整块位图便宜**一个数量级**（109 → 10 ms、768 → 51 ms）：旧实现的开销几乎
  全在"每像素一个 ``"#rrggbb"`` 字符串交给 Tcl 逐个解析"上，新的只让 Tcl 解析一次二进制；
* 旧的连续场**铺不满画布**，不是不想，而是 ``PhotoImage.zoom`` 只支持整数倍：360 宽的图
  放进 868 宽的画布，2 倍放不下、1 倍又只剩一半。整块位图可以直接重采样到任意尺寸，
  所以"铺满"这一档（828×621，像素数是旧的小图的 5 倍）也只花 **59 ms**。
"""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..theme import BORDER, DIM, FAINT, FONT_BOLD, FONT_SM, PANEL_2, lerp_color
from .base import ModelViewBase
from .common import (
    BADGE_BAD_BG,
    BADGE_BAD_FG,
    BADGE_NO_BG,
    BADGE_NO_FG,
    BADGE_OK_BG,
    BADGE_OK_FG,
    BG_CANVAS,
)
from .criteria import BAD, NO, OK

__all__ = ["CMAPS", "FIELD_LEVELS", "FIELD_PAD", "ChartSpec", "ChartViewBase"]

#: 徽章等级 -> (底色, 字色)
_BADGE_COLORS = {
    OK: (BADGE_OK_BG, BADGE_OK_FG),
    NO: (BADGE_NO_BG, BADGE_NO_FG),
    BAD: (BADGE_BAD_BG, BADGE_BAD_FG),
}

#: 连续场的内置色带：名字 -> ``(低端 RGB, 高端 RGB)``，中间由 :func:`theme.lerp_color`
#: 插值（它收的是 RGB 元组，与渗流视图的 ``COL_WET_FROM`` 同一约定，不是十六进制串）。
#: 只放少量常用的几条 —— 够用即可，避免把"配色"变成需要维护的目录。
CMAPS: Mapping[str, Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = {
    "viridis": ((68, 1, 84), (253, 231, 37)),      # #440154 -> #fde725（深紫 -> 亮黄）
    "magma": ((0, 0, 4), (252, 253, 191)),         # #000004 -> #fcfdbf（黑 -> 暖白）
    "ice": ((226, 242, 254), (14, 165, 233)),      # 浅蓝底 -> 冰蓝
    "heat": ((26, 11, 11), (255, 209, 102)),       # #1a0b0b -> #ffd166（暗红 -> 亮黄）
}

#: 栅格图细格线（``ChartSpec.grid_lines``）的颜色：比画布底色略亮，只用于读坐标
GRID_LINE_COLOR = "#cbd5e1"

#: 连续场的色带档数：数值先量化成这么多档再查色带（与旧的逐像素实现一致）
FIELD_LEVELS = 64
#: 连续场四周留的边距（像素）：图像按"铺满画布"取最大尺寸时用
FIELD_PAD = 18

#: 色带名 -> ``(FIELD_LEVELS, 3)`` 的 uint8 查找表（算一次缓存，省得每次渲染重算 64 次插值）
_PALETTE_CACHE: Dict[str, np.ndarray] = {}


def field_palette(name: str) -> np.ndarray:
    """取某条色带的查表数组：``(FIELD_LEVELS, 3)`` 的 uint8，下标即"第几档"。"""
    table = _PALETTE_CACHE.get(name)
    if table is None:
        low, high = CMAPS.get(name, CMAPS["viridis"])
        ramp = np.empty((FIELD_LEVELS, 3), dtype=np.uint8)
        for level in range(FIELD_LEVELS):
            color = lerp_color(low, high, level / (FIELD_LEVELS - 1))
            ramp[level] = (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))
        _PALETTE_CACHE[name] = table = ramp
    return table


def _resample_index(source: int, target: int) -> np.ndarray:
    """最近邻重采样用的下标：把 ``target`` 个显示像素映射回 ``source`` 个采样点。

    连续场铺满画布靠的就是它 —— 离散态必须整数倍放大（矩形不能糊边），而连续场每个像素
    本来就是一次数值采样，重采样到任意尺寸都成立。源更大时它是等距抽样（下采样），
    源更小时它是重复（上采样），两种情形共用一条式子。
    """
    source, target = max(int(source), 1), max(int(target), 1)
    if source == target:
        return np.arange(source)
    return np.minimum((np.arange(target) * source) // target, source - 1)


@dataclass(frozen=True)
class ChartSpec:
    """把一个动作返回的 JSON 画成图的**声明**（构造后只读）。

    字段按图种取用，没用到的留默认值即可。``kind`` 决定读哪些字段：

    * ``segments``：``x`` / ``y`` / ``theta`` / ``length`` / ``flag``（平行数组 + 0/1 掩码）；
    * ``series``：``records`` + ``x_field`` + ``y_fields``，或用 ``x`` + ``y_fields`` 平行数组；
    * ``bars``：``values``（或 ``y``）+ ``labels``；
    * ``text``：只画 ``title`` / ``caption``。
    """

    kind: str
    title: str = ""
    #: 画布左上角说明，可用 ``{字段名}`` 从 payload 里插值（如 ``"L/d = {ratio:.2f}"``）
    caption: str = ""
    # ---- segments：平行数组 + 掩码 ----
    x: str = "xs"
    y: str = "ys"
    theta: str = "thetas"
    length: str = "length"
    flag: str = "flags"
    # ---- series：记录数组（与平行数组二选一）----
    records: str = ""
    x_field: str = "x"
    y_fields: Tuple[str, ...] = ()
    # ---- bars ----
    labels: str = "labels"
    values: str = "values"
    # ---- grid：离散态（多帧 0/1 掩码；``cells`` 是单帧简写）----
    # 注意：字段名不能叫 ``rows`` —— 本 dataclass 末尾已有一个 ``rows``（"这张图的指标行
    # 取值来源"，覆盖视图级的 ROW_SOURCES）。同名会静默覆盖那一个，连带弄坏既有视图。
    row_field: str = "rows"
    col_field: str = "cols"
    frames: str = "frames"
    cells: str = "cells"
    #: 状态 -> 颜色（下标即取值；缺省时用 ``color`` / ``flag_color``）
    colors: Tuple[str, ...] = ()
    #: 格子之间的像素间隙（0 = 紧贴；差分刷新不受它影响）
    gap: int = 1
    #: 是否画细格线（格子很少时有助于读坐标；格子多时反而糊成一片）
    grid_lines: bool = False
    # ---- grid：连续场（与 frames/cells 二选一）----
    vmin: float = 0.0
    vmax: float = 1.0
    #: 色带名，见 :data:`CMAPS`（由 ``theme.lerp_color`` 生成的少量内置色带）
    cmap: str = "viridis"
    # ---- 交互 ----
    #: 绑定点击 / 拖拽并把 ``(行, 列)`` 交给 :meth:`ChartViewBase._on_cell_click`
    clickable: bool = False
    # ---- 坐标轴 ----
    ref: Optional[float] = None
    ref_label: str = ""
    x_label: str = ""
    y_label: str = ""
    xlim: Optional[Tuple[float, float]] = None
    ylim: Optional[Tuple[float, float]] = None
    grid: Optional[float] = None
    # ---- 外观 ----
    color: str = "#64748b"
    flag_color: Optional[str] = None
    ref_color: str = "#15803d"
    grid_color: str = "#cbd5e1"
    limit: int = 3000
    animate: bool = False
    #: 这张图的指标行取值来源（覆盖视图级的 ``ROW_SOURCES``）
    rows: Mapping[str, str] = field(default_factory=dict)


class ChartViewBase(ModelViewBase):
    """「参数表单 + 通用图表」骨架：非渗流模型的默认选择。"""

    #: ``payload["view"] -> ChartSpec``：每种动作返回结构怎么画
    CHART_SPECS: Mapping[str, ChartSpec] = {}
    #: 右侧指标行：``((标题, vals 键), ...)``
    RESULT_ROWS: Sequence[Tuple[str, str]] = ()
    #: 指标行取值来自 payload 的哪个键（缺省与 vals 键同名）
    ROW_SOURCES: Mapping[str, str] = {}
    #: 指标行的格式化模板，如 ``{"pi": "{:.5f}", "cost": "{:.1f} ms"}``
    RESULT_FORMATS: Mapping[str, str] = {}
    #: 面板底部说明
    EXPLAIN: str = ""
    #: 允许动画（图自身的 ``animate`` 也需要为 True）
    ANIMATED: bool = True
    #: 动画固定帧数（帧数固定，于是"动画间隔"滑块调的就是快慢）
    ANIM_STEPS: int = 48
    SPEED_MIN, SPEED_MAX, SPEED_DEFAULT = 1, 200, 25
    #: 某些高采样动画允许 ``after(0, ...)`` 尽快刷新；默认模型仍保留 1 ms 下限。
    ALLOW_ZERO_ANIM_DELAY: bool = False
    #: 是否在播放完时间轴后自动从第 1 帧重新开始。
    LOOP_ANIMATION: bool = False

    # ==================================================================
    # 状态
    # ==================================================================
    def _setup_state(self) -> None:
        self._last: Optional[Dict[str, Any]] = None
        self._chart: Optional[ChartSpec] = None
        self._reveal = 0
        self._anim_target = 0
        self._scale = 1.0
        self._origin: Tuple[float, float] = (0.0, 0.0)
        #: 栅格图当前画到第几帧（0 基）与总帧数；非栅格图不用
        self._frame_index = 0
        self._frame_count = 0
        #: 栅格图"上一帧画了什么"（用于差分刷新）与反查几何 ``(cell, ox, oy, rows, cols)``；
        #: 连续场的 ``cell`` 是浮点（图像铺满画布，格子边长不必是整数）
        self._grid_state: Optional[str] = None
        self._grid_geom: Optional[Tuple[float, int, int, int, int]] = None
        #: 画布上的格子矩形（``index -> item id``），差分刷新时按需增删
        self._grid_cells: Dict[int, int] = {}
        #: 连续场用的图像缓冲（必须持引用，否则被 GC 后画布变空白）
        self._grid_image: Optional[tk.PhotoImage] = None
        self.var_speed = tk.IntVar(value=self.SPEED_DEFAULT)
        #: 时间轴是否正在自动前进（"暂停/继续"按钮的状态）
        self.var_playing = tk.BooleanVar(value=False)
        self.vals: Dict[str, tk.StringVar] = {
            key: tk.StringVar(value="-") for _label, key in self.RESULT_ROWS
        }
        self.var_badge = tk.StringVar(value="")
        self.var_caption = tk.StringVar(value="")

    def _after_build(self) -> None:
        self._draw_message("点左侧动作按钮开始")

    # ------------------------------------------------------------------
    # 中央画布
    # ------------------------------------------------------------------
    def _build_center(self) -> None:
        center = ttk.Frame(self.host, style="Panel.TFrame", padding=12)
        center.grid(row=0, column=1, sticky="nsew", pady=12)
        center.columnconfigure(0, weight=1)
        center.rowconfigure(1, weight=1)

        ttk.Label(center, textvariable=self.var_caption, style="Card.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8))
        self.canvas = tk.Canvas(
            center, bg=BG_CANVAS, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,
        )
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._on_resize)
        # 点击 / 拖拽只在图的 ``clickable`` 为真时才起作用（默认不处理，既有模型行为不变）
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)

    def _on_resize(self, _event=None) -> None:
        if self._redraw_job is not None:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(120, self._redraw)

    def _redraw(self) -> None:
        self._redraw_job = None
        if not (self._alive and self.canvas.winfo_exists()):
            return
        if self._last is None or self._chart is None:
            self._draw_message("点左侧动作按钮开始")
            return
        self._draw(self._chart, self._last, self._current_reveal())

    def _current_reveal(self) -> Optional[int]:
        """当前该显示到第几个图元 / 第几帧；``None`` 表示"全部显示"（不处于中途）。

        用它而不是 ``_anim_job`` 判断：**暂停**之后 ``_anim_job`` 是空的，但画面应当停在
        暂停的那一帧（窗口缩放触发的重绘必须画出同一帧，而不是跳到末帧）。
        """
        if 0 < self._reveal < self._anim_target:
            return self._reveal
        return None

    # ------------------------------------------------------------------
    # 右侧指标面板
    # ------------------------------------------------------------------
    def _build_right(self) -> None:
        panel = ttk.Frame(self.host, style="Panel.TFrame", padding=14)
        panel.grid(row=0, column=2, sticky="nsew", padx=(7, 14), pady=12)
        panel.columnconfigure(1, weight=1)

        self.badge = tk.Label(
            panel, textvariable=self.var_badge, bg=PANEL_2, fg=FAINT,
            font=FONT_BOLD, pady=12, wraplength=300, justify="center",
        )
        self.badge.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        for i, (label, key) in enumerate(self.RESULT_ROWS, start=1):
            ttk.Label(panel, text=label, style="CardDim.TLabel",
                      width=16, anchor="w").grid(row=i, column=0, sticky="w", pady=4)
            ttk.Label(panel, textvariable=self.vals[key], style="Mono.TLabel",
                      anchor="w").grid(row=i, column=1, sticky="w", pady=4)

        row = self._build_right_extra(panel, len(self.RESULT_ROWS) + 1)
        if self.EXPLAIN:
            ttk.Separator(panel, orient="horizontal").grid(
                row=row, column=0, columnspan=2, sticky="ew", pady=10)
            ttk.Label(panel, text=self.EXPLAIN, style="CardDim.TLabel", wraplength=300,
                      justify="left", font=FONT_SM).grid(
                row=row + 1, column=0, columnspan=2, sticky="w")

    def _build_right_extra(self, panel: tk.Widget, row: int) -> int:
        """在右侧面板的指标行**下方**追加自定义内容（默认没有），返回下一个可用行号。

        模型可以用它在指标旁边放自己的小图 —— 例如生命游戏的实时人口曲线。
        """
        return row

    # ------------------------------------------------------------------
    # 侧栏**顶部**的「动画 / 播放」卡片（只有存在可动画的图时才加）
    #
    # 放在最上面而不是最下面：播放是最常用的控件，不该让人先滚过一堆参数才看得见。
    # ------------------------------------------------------------------
    def _animated(self) -> bool:
        return self.ANIMATED and any(s.animate for s in self.CHART_SPECS.values())

    def _build_top_cards(self, parent: tk.Widget) -> None:
        if not self._animated():
            return
        card = self._card(parent, "动画")

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 6))
        self.btn_pause = ttk.Button(row, text="▶ 播放", command=self._toggle_pause)
        self.btn_pause.pack(side="left", expand=True, fill="x")
        self.btn_step = ttk.Button(row, text="⏭ 下一帧", command=self._next_frame)
        self.btn_step.pack(side="left", expand=True, fill="x", padx=(6, 0))
        self._action_buttons.extend([self.btn_pause, self.btn_step])

        self._build_player_extra(card)     # 子类可在此追加按钮（例如「清空」）

        speed = ttk.Frame(card, style="Card.TFrame")
        speed.pack(fill="x")
        ttk.Label(speed, text="动画间隔（毫秒）", style="Card.TLabel").pack(side="left")
        self.scale_speed = ttk.Scale(
            speed, from_=self.SPEED_MIN, to=self.SPEED_MAX, length=118,
            command=self._on_speed_change,
        )
        self.scale_speed.set(self.var_speed.get())
        self.scale_speed.pack(side="right", pady=(0, 2))
        ttk.Label(card, text=self._speed_hint(), style="CardDim.TLabel", font=FONT_SM,
                  wraplength=252, justify="left").pack(anchor="w", pady=(2, 0))
        self._sync_player_buttons()

    def _build_player_extra(self, parent: tk.Widget) -> None:
        """播放卡片里的附加按钮（默认没有）。

        模型可以在这里放自己的"播放相关"操作 —— 例如生命游戏的「清空」：它属于棋盘编辑，
        和播放按钮是同一套操作节奏，放在一起最顺手。
        """
        return None

    def _on_speed_change(self, value: str) -> None:
        try:
            speed = int(round(float(value)))
        except (TypeError, ValueError):
            return
        self.var_speed.set(max(self.SPEED_MIN, min(self.SPEED_MAX, speed)))

    def _last_is_animated(self) -> bool:
        return bool(self._last) and bool(self._chart and self._chart.animate)

    # ------------------------------------------------------------------
    # 播放器：暂停 / 继续 / 单步（对"多帧"与"逐图元"两种动画都成立）
    # ------------------------------------------------------------------
    def _speed_hint(self) -> str:
        """「动画间隔」滑块的说明文案（栅格图是时间轴，语义与"逐样本出现"不同）。"""
        if any(spec.animate and spec.kind == "grid" for spec in self.CHART_SPECS.values()):
            return ("越小越快：每一帧前进一代（或一个采样点），间隔即相邻两帧之间的停顿。"
                    "想细看某一步，用「⏸ 暂停」+「⏭ 下一帧」。")
        return "越小越快：每帧新增的图元数固定，间隔越小整段动画越短。"

    def _sync_player_buttons(self) -> None:
        """按当前播放状态刷新「暂停 / 继续 / 播放」按钮的文字。"""
        btn = getattr(self, "btn_pause", None)
        if btn is None:
            return
        if self._anim_target <= 0 or self._reveal >= self._anim_target:
            text = "▶ 播放"          # 还没播过 / 已经播到末帧：再点是（重新）播放
        else:
            text = "⏸ 暂停" if self.var_playing.get() else "▶ 继续"
        btn.configure(text=text)

    def _toggle_pause(self) -> None:
        """「暂停 / 继续 / 播放」按钮。"""
        if self._last is None or self._chart is None or not self._last_is_animated():
            self.var_status.set("还没有可播放的动画，先运行一次左侧动作。")
            return
        if self._anim_job is not None:
            self._pause()
        else:
            self._resume()

    def _pause(self) -> None:
        """停在当前帧（画面保持不动，指标也保持这一帧的值）。"""
        if self._anim_job is None:
            return
        self._cancel_animation()
        self.var_playing.set(False)
        self._sync_player_buttons()
        self.var_status.set(
            f"已暂停在第 {max(self._reveal, 1)}/{self._anim_target} 帧 —— "
            "「继续」接着播，或「下一帧」逐步细看。"
        )

    def _resume(self) -> None:
        """从当前帧继续；已经播完则从头再播。"""
        if self._last is None or self._chart is None:
            return
        if self._anim_target <= 0:
            return
        if self._reveal >= self._anim_target:
            self._reveal = 0
        self.var_playing.set(True)
        self._sync_player_buttons()
        self._step_animation()

    def _next_frame(self) -> None:
        """单步：只前进一帧（暂停状态下逐代细看）。"""
        if self._last is None or self._chart is None or self._anim_target <= 0:
            self.var_status.set("还没有可播放的动画，先运行一次左侧动作。")
            return
        self._cancel_animation()
        self.var_playing.set(False)
        if self._reveal < self._anim_target:
            self._reveal += 1
        self._frame_index, self._frame_count = self._reveal - 1, self._anim_target
        self._draw(self._chart, self._last, self._reveal)
        self._fill_rows(self._last, drawn=self._reveal)
        self._sync_player_buttons()

    def _redraw_payload(self, payload: Mapping[str, Any]) -> None:
        """用一份新 payload **原地**重绘（不播放动画）：供交互式图表（如点击编辑）刷新用。"""
        key = str(payload.get("view") or "")
        spec = self.CHART_SPECS.get(key)
        if spec is None:
            return
        self._cancel_animation()
        self.var_playing.set(False)
        self._last = dict(payload)
        self._chart = spec
        self._anim_target = min(self._primitive_count(spec, self._last), spec.limit)
        self._reveal = self._anim_target
        self.var_caption.set(spec.title)
        self._draw(spec, self._last)
        self._fill_rows(self._last)
        self._sync_player_buttons()

    # ==================================================================
    # 动作结果 -> 图表
    # ==================================================================
    def _render_result(self, payload: Any) -> None:
        """把动作返回的字典按 :attr:`CHART_SPECS` 的声明画出来。"""
        if not isinstance(payload, dict):
            return
        if "error" in payload:
            message = str(payload["error"])
            self._cancel_animation()
            self._draw_message(f"× {message}")
            self.var_status.set(f"运行失败：{message}")
            self.var_badge.set("运行失败")
            self.badge.configure(bg=BADGE_BAD_BG, fg=BADGE_BAD_FG)
            return

        self._last = payload
        key = str(payload.get("view") or "")
        spec = self.CHART_SPECS.get(key)
        if spec is None:
            self._cancel_animation()
            self._chart = None
            self.var_caption.set(f"未声明图表：{key or '(缺少 view 字段)'}")
            self._draw_message(f"没有为 view={key!r} 声明图表（见 CHART_SPECS）")
            self._fill_rows(payload)
            self.var_status.set(f"未声明图表：view={key!r}（请在 CHART_SPECS 里登记）")
            return

        self._chart = spec
        self.var_caption.set(spec.title)
        if spec.animate and self._animated():
            self._start_animation(spec, payload)
        else:
            self._cancel_animation()
            self._draw(spec, payload)
            self._fill_rows(payload)

    # ------------------------------------------------------------------
    # 逐帧动画
    # ------------------------------------------------------------------
    def _primitive_count(self, spec: ChartSpec, payload: Mapping[str, Any]) -> int:
        """这张图一共有多少个"可以逐个出现"的图元（栅格图里 = 帧数）。"""
        if spec.kind == "segments":
            return len(payload.get(spec.x) or [])
        if spec.kind == "series":
            xs, _series = self._series_data(spec, payload)
            return len(xs)
        if spec.kind == "bars":
            return len(payload.get(spec.values) or payload.get(spec.y) or [])
        if spec.kind == "grid":
            return len(self._grid_frames(spec, payload))
        return 0

    def _start_animation(self, spec: ChartSpec, payload: Mapping[str, Any]) -> None:
        self._cancel_animation()
        self._chart = spec
        self._anim_target = min(self._primitive_count(spec, payload), spec.limit)
        self._reveal = 0
        self._draw(spec, payload, 0)
        self._fill_rows(payload, drawn=0)
        if self._anim_target <= 0:
            self._finish_animation()
            return
        self.var_playing.set(True)
        self._sync_player_buttons()
        self._step_animation()

    def _step_animation(self) -> None:
        self._anim_job = None
        if not self._alive or self._last is None or self._chart is None:
            return
        target = self._anim_target
        if self._reveal >= target:
            self._finish_animation()
            return

        # 栅格图是"时间轴"：每步**恰好前进一帧**（"动画间隔"即相邻两帧的间隔）。
        # 若沿用"总时长 48 帧"的节奏，300 代会变成每帧 6 代 —— 滑翔机直接被跳过去。
        per_frame = 1 if self._chart.kind == "grid" else max(1, math.ceil(target / self.ANIM_STEPS))
        self._reveal = min(target, self._reveal + per_frame)
        self._frame_index, self._frame_count = self._reveal - 1, target
        self._draw(self._chart, self._last, self._reveal)
        self._fill_rows(self._last, drawn=self._reveal)
        floor = 0 if self.ALLOW_ZERO_ANIM_DELAY else 1
        delay = max(floor, min(self.SPEED_MAX, int(self.var_speed.get())))
        self._anim_job = self.root.after(delay, self._step_animation)

    def _finish_animation(self) -> None:
        self._cancel_animation()
        if self._last is None:
            self.var_playing.set(False)
            self._sync_player_buttons()
            return
        if self._chart is not None:
            self._draw(self._chart, self._last)
        self._fill_rows(self._last)
        if (self.LOOP_ANIMATION and self._chart is not None
                and self._chart.animate and self._anim_target > 0 and self._alive):
            # 保留完整末帧一小段事件循环后再回到起点，避免视觉上出现半帧残留。
            self._reveal = 0
            self._frame_index, self._frame_count = -1, self._anim_target
            self.var_playing.set(True)
            self._sync_player_buttons()
            floor = 0 if self.ALLOW_ZERO_ANIM_DELAY else 1
            delay = max(floor, min(self.SPEED_MAX, int(self.var_speed.get())))
            self._anim_job = self.root.after(delay, self._step_animation)
            return
        self.var_playing.set(False)
        self._sync_player_buttons()

    def _cancel_animation(self) -> None:
        if self._anim_job is not None:
            try:
                self.root.after_cancel(self._anim_job)
            except tk.TclError:
                pass
            self._anim_job = None

    # ==================================================================
    # 画图
    # ==================================================================
    def _draw_message(self, text: str) -> None:
        cv = self.canvas
        cv.delete("all")
        self._forget_grid()          # 画布已被清空，栅格的差分缓存作废
        cv.create_text(
            max(cv.winfo_width(), 60) // 2, max(cv.winfo_height(), 60) // 2,
            text=text, fill=FAINT, font=FONT_BOLD, justify="center",
            width=max(120, cv.winfo_width() - 40),
        )

    def _forget_grid(self) -> None:
        """丢弃栅格的差分缓存（画布被清空 / 换成别的图种时调用）。"""
        self._grid_state = None
        self._grid_cells = {}
        self._grid_geom = None

    def _draw(self, spec: ChartSpec, payload: Mapping[str, Any],
              reveal: Optional[int] = None) -> None:
        caption = self._caption(spec, payload)
        if spec.kind == "grid":
            # 栅格自己管理画布内容：帧与帧之间只改变化的格子（差分刷新）
            self._draw_grid(spec, payload, reveal)
        else:
            self.canvas.delete("all")
            self._forget_grid()
            if spec.kind == "series":
                self._draw_series(spec, payload, reveal)
            elif spec.kind == "bars":
                self._draw_bars(spec, payload, reveal)
            elif spec.kind == "text":
                self._draw_message(caption or "（无图）")
                return
            else:
                self._draw_segments(spec, payload, reveal)
        self._draw_overlay(spec, reveal, caption)

    def _caption(self, spec: ChartSpec, payload: Mapping[str, Any]) -> str:
        """把 ``caption`` 模板里 ``{字段}`` 用 payload 的标量字段填好。"""
        if not spec.caption:
            return spec.title
        flat = {k: v for k, v in payload.items() if isinstance(v, (int, float, str))}
        try:
            return spec.caption.format(**flat)
        except (KeyError, IndexError, ValueError, TypeError):
            return spec.caption

    def _draw_overlay(self, spec: ChartSpec, reveal: Optional[int], caption: str) -> None:
        """画布左上角的说明与（动画中）右下角的进度。

        用 ``overlay`` 标签管理：栅格图逐帧只做差分刷新、不会 ``delete("all")``，
        因此叠加文字必须自己先清掉，否则每一帧都会叠一层。
        """
        self.canvas.delete("overlay")
        if caption:
            self.canvas.create_text(10, 8, anchor="nw", text=caption,
                                    fill=DIM, font=FONT_SM, tags="overlay")
        if spec.animate and reveal is not None:
            total = self._anim_target
            self.canvas.create_text(
                max(self.canvas.winfo_width(), 60) - 10,
                max(self.canvas.winfo_height(), 60) - 8,
                anchor="se", text=f"{min(reveal, total)}/{total}",
                fill=DIM, font=FONT_SM, tags="overlay",
            )

    # ------------------------------------------------------------------
    # segments
    # ------------------------------------------------------------------
    @staticmethod
    def _flag_list(raw: Any, count: int) -> List[bool]:
        """把 ``"0101"`` 这样的掩码（或布尔数组）转成 ``List[bool]``。"""
        if raw is None:
            return [False] * count
        if isinstance(raw, str):
            flags = [ch == "1" for ch in raw[:count]]
            return flags + [False] * (count - len(flags))
        return [bool(v) for v in list(raw)[:count]]

    def _fit(self, xlim: Tuple[float, float],
             ylim: Tuple[float, float]) -> Tuple[float, float, float]:
        """等比缩放到画布（返回 ``(scale, ox, oy)``；屏幕坐标 = 值·scale + o）。"""
        width = max(self.canvas.winfo_width(), 80)
        height = max(self.canvas.winfo_height(), 80)
        pad = 20.0
        span_x = max(xlim[1] - xlim[0], 1e-9)
        span_y = max(ylim[1] - ylim[0], 1e-9)
        scale = min((width - 2 * pad) / span_x, (height - 2 * pad) / span_y)
        if scale <= 0:
            return 1.0, 0.0, 0.0
        ox = (width - scale * span_x) / 2.0 - xlim[0] * scale
        oy = (height - scale * span_y) / 2.0 - ylim[0] * scale
        return scale, ox, oy

    def _draw_segments(self, spec: ChartSpec, payload: Mapping[str, Any],
                       reveal: Optional[int]) -> None:
        xs = list(payload.get(spec.x) or [])
        ys = list(payload.get(spec.y) or [])
        thetas = list(payload.get(spec.theta) or [])
        length = float(payload.get(spec.length) or 0.0)
        count = min(len(xs), len(ys), len(thetas), spec.limit)
        if count == 0:
            self._draw_message("没有可画的图元（数据为空）")
            return
        flags = self._flag_list(payload.get(spec.flag), len(xs))

        half = length / 2.0
        xlim, ylim = spec.xlim, spec.ylim
        if xlim is None or ylim is None:
            xs_lo = min(xs[:count]) - half
            xs_hi = max(xs[:count]) + half
            ys_lo = min(ys[:count]) - half
            ys_hi = max(ys[:count]) + half
            xlim = xlim or (xs_lo, xs_hi)
            ylim = ylim or (ys_lo, ys_hi)

        scale, ox, oy = self._fit(xlim, ylim)
        self._scale, self._origin = scale, (ox, oy)

        # 线段图原本只画图元，没有使用 ChartSpec 里已经声明的轴标题，导致
        # 分岔图这类“坐标本身就是含义”的图很难读。边框和标题不改变图元
        # 坐标，只补充方向感；自由布局类线段图（如投针）也能直接受益。
        plot_left = ox + xlim[0] * scale
        plot_right = ox + xlim[1] * scale
        plot_top = oy + ylim[0] * scale
        plot_bottom = oy + ylim[1] * scale
        self.canvas.create_rectangle(plot_left, plot_top, plot_right, plot_bottom,
                                     outline=spec.grid_color)
        if spec.y_label:
            self.canvas.create_text(plot_left + 4, plot_top + 4, anchor="nw",
                                    text=spec.y_label, fill=FAINT, font=FONT_SM)
        if spec.x_label:
            self.canvas.create_text((plot_left + plot_right) / 2.0,
                                    plot_bottom + 2, anchor="n",
                                    text=spec.x_label, fill=FAINT, font=FONT_SM)
        # 端点刻度让自动范围的图也能读出数值（尤其是分岔图的 r 区间）。
        self.canvas.create_text(plot_left, plot_bottom + 2, anchor="sw",
                                text=f"{xlim[0]:g}", fill=DIM, font=FONT_SM)
        self.canvas.create_text(plot_right, plot_bottom + 2, anchor="se",
                                text=f"{xlim[1]:g}", fill=DIM, font=FONT_SM)
        self.canvas.create_text(plot_left - 4, plot_top, anchor="e",
                                text=f"{ylim[0]:g}", fill=DIM, font=FONT_SM)
        self.canvas.create_text(plot_left - 4, plot_bottom, anchor="e",
                                text=f"{ylim[1]:g}", fill=DIM, font=FONT_SM)

        if spec.grid:
            step = float(spec.grid)
            k = math.ceil(ylim[0] / step)
            while k * step <= ylim[1] + 1e-9:
                y = oy + k * step * scale
                self.canvas.create_line(0.0, y, self.canvas.winfo_width(), y,
                                        fill=spec.grid_color)
                k += 1

        shown = count if reveal is None else min(reveal, count)
        for i in range(shown):
            cx = ox + xs[i] * scale
            cy = oy + ys[i] * scale
            theta = thetas[i]
            dx = half * math.cos(theta) * scale
            dy = half * math.sin(theta) * scale
            color = spec.color
            if spec.flag_color is not None and i < len(flags) and flags[i]:
                color = spec.flag_color
            self.canvas.create_line(cx - dx, cy - dy, cx + dx, cy + dy, fill=color,
                                    width=2 if color == spec.flag_color else 1)

    # ------------------------------------------------------------------
    # grid（栅格 / 像素场）
    # ------------------------------------------------------------------
    @staticmethod
    def _grid_frames(spec: ChartSpec, payload: Mapping[str, Any]) -> List[str]:
        """取出栅格图的帧序列：``frames`` 优先，否则把 ``cells`` 当作唯一一帧。"""
        raw = payload.get(spec.frames)
        if raw:
            return [str(frame) for frame in raw]
        single = payload.get(spec.cells)
        return [str(single)] if single else []

    def _grid_layout(self, rows: int, cols: int) -> Tuple[int, int, int]:
        """栅格几何：格子边长取**整数**（最近邻放大，边缘不糊），整体居中。"""
        width = max(self.canvas.winfo_width(), 80)
        height = max(self.canvas.winfo_height(), 80)
        cell = int(max(1, min((width - 2 * FIELD_PAD) / max(cols, 1),
                              (height - 2 * FIELD_PAD) / max(rows, 1))))
        ox = int((width - cell * cols) / 2)
        oy = int((height - cell * rows) / 2)
        return cell, ox, oy

    def _field_layout(self, rows: int, cols: int) -> Tuple[float, int, int, int, int]:
        """连续场的几何：等比**铺满**画布（**非整数倍**），返回 ``(scale, ox, oy, tw, th)``。

        离散态由 :meth:`_grid_layout` 取整数格边长（矩形不能糊边、差分刷新要按格对齐），
        但那条约束套在连续场上会让图像白白缩水：360 宽的图放进 700 宽的画布，
        2 倍放不下、1 倍又只剩一半 —— 于是四周一片空白。连续场每个像素本来就是一次数值
        采样，重采样到任意尺寸都成立，所以这里直接取"能铺满的最大尺寸"。

        ``scale`` 返回的是**有效**格子边长 ``tw / cols``（而不是取尺寸用的那个浮点比例）：
        :meth:`_hit_cell` 用它把画布坐标反查回源网格，用有效值才不会偏。
        """
        width = max(self.canvas.winfo_width(), 80)
        height = max(self.canvas.winfo_height(), 80)
        scale = min((width - 2 * FIELD_PAD) / max(cols, 1),
                    (height - 2 * FIELD_PAD) / max(rows, 1))
        scale = max(scale, 1e-3)
        tw = max(1, int(round(cols * scale)))
        th = max(1, int(round(rows * scale)))
        return tw / cols, int((width - tw) // 2), int((height - th) // 2), tw, th

    def _grid_color(self, spec: ChartSpec, value: int) -> Optional[str]:
        """离散态的取值 -> 颜色；返回 ``None`` 表示这一格不画（留画布底色）。

        没给 ``colors`` 色表时的约定与 ``segments`` 一致：``0`` 不画、非 ``0`` 用
        ``flag_color``（缺省回退到 ``color``）。
        """
        if spec.colors:
            index = min(max(int(value), 0), len(spec.colors) - 1)
            return spec.colors[index] or None
        return None if not value else (spec.flag_color or spec.color)

    def _draw_grid(self, spec: ChartSpec, payload: Mapping[str, Any],
                   reveal: Optional[int]) -> None:
        frames = self._grid_frames(spec, payload)
        values = payload.get(spec.values)
        if not frames and (values is None or len(values) == 0):
            self._draw_message("没有可画的格子（数据为空）")
            return
        rows = max(1, int(payload.get(spec.row_field) or 1))
        cols = max(1, int(payload.get(spec.col_field) or 1))
        if not frames:                       # 连续场：整块位图，等比铺满画布
            scale, ox, oy, tw, th = self._field_layout(rows, cols)
            self._draw_field(spec, values, rows, cols, scale, ox, oy, tw, th)
            return
        cell, ox, oy = self._grid_layout(rows, cols)
        if reveal is None:
            state = frames[-1]
        elif reveal <= 0:
            state = ""                       # 动画起点：一帧都还没显示
        else:
            state = frames[min(reveal, len(frames)) - 1]
        self._paint_cells(spec, state, rows, cols, cell, ox, oy)

    def _paint_cells(self, spec: ChartSpec, state: str, rows: int, cols: int,
                     cell: int, ox: int, oy: int) -> None:
        """把一帧离散状态画到画布上：**只改动与上一帧不同的格子**。

        差分刷新是栅格图能逐帧播放的关键：一帧的开销与"变化的格子数"成正比，
        而不是与格子总数成正比（暂停后单步、点击编辑后的重绘也走同一条路径）。
        """
        cv = self.canvas
        geom = (cell, ox, oy, rows, cols)
        previous = self._grid_state
        # ``not state`` = 动画起点（一帧还没显示）：直接清空重建，别指望"下一帧的差分顺手
        # 把旧图元删掉"—— 那种隐式依赖读代码的人看不出来。
        rebuild = (previous is None or not state or len(previous) != len(state)
                   or self._grid_geom != geom)
        if rebuild:
            cv.delete("all")
            self._grid_cells = {}
            previous = "\0" * len(state)     # 全空基线：这一帧的活细胞全部要新建
        gap = max(0, int(spec.gap))

        for index, char in enumerate(state):
            before = previous[index] if index < len(previous) else "\0"
            if char == before:
                continue
            item = self._grid_cells.pop(index, None)
            if item is not None:
                cv.delete(item)              # 这一格要变色 / 变空，先撤掉旧矩形
            color = self._grid_color(spec, int(char) if char.isdigit() else 1)
            if color is None:
                continue
            row, col = divmod(index, cols)
            x0, y0 = ox + col * cell, oy + row * cell
            self._grid_cells[index] = cv.create_rectangle(
                x0, y0, x0 + cell - gap, y0 + cell - gap,
                fill=color, outline="", tags="cell",
            )

        self._grid_state = state
        self._grid_geom = geom
        if rebuild and spec.grid_lines and cell >= 6:
            self._draw_grid_lines(rows, cols, cell, ox, oy)

    def _draw_grid_lines(self, rows: int, cols: int, cell: int,
                         ox: int, oy: int) -> None:
        """细格线（只在重建底图时画一次，之后差分刷新不动它）。"""
        for row in range(rows + 1):
            y = oy + row * cell
            self.canvas.create_line(ox, y, ox + cols * cell, y, fill=GRID_LINE_COLOR)
        for col in range(cols + 1):
            x = ox + col * cell
            self.canvas.create_line(x, oy, x, oy + rows * cell, fill=GRID_LINE_COLOR)

    def _draw_field(self, spec: ChartSpec, values: Any, rows: int, cols: int,
                    scale: float, ox: int, oy: int, tw: int, th: int) -> None:
        """连续场：数值 -> 色带 -> 一张 ``PhotoImage``（整块位图，铺满画布）。

        三步，全是整块操作，**没有逐像素的 Python 循环**：

        1. 数值按 ``vmin``/``vmax`` 量化成 :data:`FIELD_LEVELS` 档，再用色带查表成 RGB
           （``(rows, cols, 3)`` 的 uint8 数组）；
        2. 最近邻重采样到目标显示尺寸（:func:`_resample_index`）—— 这是"铺满画布"的实现，
           而不是 ``PhotoImage.zoom``（那个只能整数倍）；
        3. 拼成一份 PPM（``P6`` 头 + RGB 字节）交给 ``PhotoImage``：Tk 一次解码到位，
           比"每像素一个 ``"#rrggbb"`` 字符串交给 Tcl 逐个解析"快两个数量级。
        """
        grid = self._field_grid(values, rows, cols)
        rgb = field_palette(spec.cmap)[self._field_levels(spec, grid)]
        if (th, tw) != (rows, cols):
            rgb = rgb[_resample_index(rows, th)[:, None],
                      _resample_index(cols, tw)[None, :]]

        ppm = b"P6 %d %d 255\n" % (tw, th) + np.ascontiguousarray(rgb).tobytes()
        image = tk.PhotoImage(data=ppm, format="PPM")
        self.canvas.delete("all")
        self._grid_cells = {}
        self._grid_state = None
        # 几何要记下来：连续场同样支持 ``clickable``（例如 Mandelbrot 的"点击放大"）
        self._grid_geom = (scale, ox, oy, rows, cols)
        self._grid_image = image       # 必须持引用：否则被 GC 后画布上会变空白
        self.canvas.create_image(ox, oy, image=image, anchor="nw")

    @staticmethod
    def _field_grid(values: Any, rows: int, cols: int) -> np.ndarray:
        """把 payload 的 ``values`` 统一成 ``(rows, cols)`` 数组（第 0 行 = 顶部）。

        ``values`` 可以是"屏幕序的扁平序列"（payload 里那个可 JSON 序列化的列表），
        也可以是模型自己递进来的 ``(rows, cols)`` 数组（原地重绘时省一次转换）——
        两种都收，少一项就当成 ``vmin`` 补齐。
        """
        total = rows * cols
        flat = np.asarray(values).reshape(-1)
        if flat.size < total:
            flat = np.concatenate([flat, np.full(total - flat.size, 0, dtype=flat.dtype)])
        return flat[:total].reshape(rows, cols)

    @staticmethod
    def _field_levels(spec: ChartSpec, grid: np.ndarray) -> np.ndarray:
        """数值 -> 色带档号 ``0..FIELD_LEVELS-1``（先夹取再截断，与旧的逐像素实现一致）。"""
        span = (float(spec.vmax) - float(spec.vmin)) or 1.0
        ratio = (grid.astype(np.float64) - float(spec.vmin)) / span
        return np.clip((ratio * (FIELD_LEVELS - 1)).astype(np.int32),
                       0, FIELD_LEVELS - 1)

    # ------------------------------------------------------------------
    # series
    # ------------------------------------------------------------------
    def _series_data(self, spec: ChartSpec,
                     payload: Mapping[str, Any]) -> Tuple[List[float], List[List[Optional[float]]]]:
        """取出 ``(横轴, [各序列])``，统一成平行数组。"""
        if spec.records:
            records = [r for r in (payload.get(spec.records) or [])
                       if isinstance(r, Mapping) and r.get(spec.x_field) is not None]
            xs = [float(r[spec.x_field]) for r in records]
            series: List[List[Optional[float]]] = []
            for field in spec.y_fields:
                series.append([
                    (float(r[field]) if r.get(field) is not None else None)
                    for r in records
                ])
            return xs, series

        xs = [float(v) for v in (payload.get(spec.x) or [])]
        fields = spec.y_fields or ((spec.y,) if spec.y else ())
        series = [[float(v) for v in (payload.get(f) or [])] for f in fields]
        return xs, series

    def _draw_series(self, spec: ChartSpec, payload: Mapping[str, Any],
                     reveal: Optional[int]) -> None:
        xs, series = self._series_data(spec, payload)
        length = min([len(xs)] + [len(s) for s in series]) if series else len(xs)
        if length < 2:
            self._draw_message("样本太少，画不出曲线（可增大次数）")
            return
        shown = length if reveal is None else max(2, min(reveal, length))

        left, right, top, bottom = 66.0, 24.0, 26.0, 46.0
        width = max(self.canvas.winfo_width(), 160)
        height = max(self.canvas.winfo_height(), 160)
        plot_w = max(width - left - right, 10.0)
        plot_h = max(height - top - bottom, 10.0)

        x_max = max(xs[:shown]) or 1.0
        values = [v for s in series for v in s[:shown] if v is not None]
        if spec.ref is not None:
            values.append(spec.ref)
        if not values:
            self._draw_message("没有可画的数值（数据为空）")
            return
        y_lo = min(values) if spec.ylim is None else spec.ylim[0]
        y_hi = max(values) if spec.ylim is None else spec.ylim[1]
        margin = (y_hi - y_lo) * 0.12 or 0.15
        if spec.ylim is None:
            y_lo -= margin
            y_hi += margin
        if y_hi - y_lo < 1e-9:
            y_lo, y_hi = y_lo - 0.5, y_hi + 0.5

        def sx(x: float) -> float:
            return left + (x / x_max) * plot_w

        def sy(y: float) -> float:
            return top + (y_hi - y) / (y_hi - y_lo) * plot_h

        self.canvas.create_line(left, top, left, top + plot_h, fill=spec.grid_color)
        self.canvas.create_line(left, top + plot_h, left + plot_w, top + plot_h,
                                fill=spec.grid_color)
        for k in range(1, 4):                       # 横向网格
            y = top + plot_h * k / 4.0
            value = y_hi - (y_hi - y_lo) * k / 4.0
            self.canvas.create_line(left, y, left + plot_w, y,
                                    fill=spec.grid_color, dash=(1, 3))
            self.canvas.create_text(left - 6, y, anchor="e", text=f"{value:.2f}",
                                    fill=DIM, font=FONT_SM)

        if spec.ref is not None:                    # 参考线
            ref_y = sy(spec.ref)
            self.canvas.create_line(left, ref_y, left + plot_w, ref_y,
                                    fill=spec.ref_color, dash=(4, 3))
            label = spec.ref_label or f"{spec.ref:.4f}"
            self.canvas.create_text(left + plot_w - 4, ref_y - 10, anchor="e",
                                    text=label, fill=spec.ref_color, font=FONT_SM)

        for column in series:                       # 曲线族
            points = [(sx(xs[i]), sy(column[i]))
                      for i in range(shown) if column[i] is not None]
            if len(points) < 2:
                continue
            coords: List[float] = []
            for px, py in points:
                coords.extend((px, py))
            self.canvas.create_line(*coords, fill=spec.color, width=2)
            for px, py in points:
                self.canvas.create_oval(px - 2.5, py - 2.5, px + 2.5, py + 2.5,
                                        fill=spec.color, outline="")

        if spec.y_label:
            self.canvas.create_text(left + 4, top + 2, anchor="nw",
                                    text=spec.y_label, fill=FAINT, font=FONT_SM)
        if spec.x_label:
            self.canvas.create_text(left + plot_w / 2, top + plot_h + 30, anchor="n",
                                    text=spec.x_label, fill=FAINT, font=FONT_SM)
        self.canvas.create_text(left, top + plot_h + 12, anchor="w", text="0",
                                fill=DIM, font=FONT_SM)
        self.canvas.create_text(left + plot_w, top + plot_h + 12, anchor="e",
                                text=f"{x_max:g}", fill=DIM, font=FONT_SM)

    # ------------------------------------------------------------------
    # bars
    # ------------------------------------------------------------------
    def _draw_bars(self, spec: ChartSpec, payload: Mapping[str, Any],
                   reveal: Optional[int]) -> None:
        raw = payload.get(spec.values)
        if raw is None:
            raw = payload.get(spec.y)
        values = [float(v) for v in (raw or [])]
        if not values:
            self._draw_message("没有可画的数值（数据为空）")
            return
        labels = list(payload.get(spec.labels) or [])
        width = max(self.canvas.winfo_width(), 160)
        height = max(self.canvas.winfo_height(), 160)
        left, right, top, bottom = 46.0, 20.0, 26.0, 42.0
        plot_w = max(width - left - right, 10.0)
        plot_h = max(height - top - bottom, 10.0)
        y_hi = max(max(values), 1e-9)

        shown = len(values) if reveal is None else min(reveal, len(values))
        step = plot_w / max(len(values), 1)
        bar_w = max(step * 0.6, 2.0)
        self.canvas.create_line(left, top + plot_h, left + plot_w, top + plot_h,
                                fill=spec.grid_color)
        for i in range(shown):
            x = left + step * (i + 0.5)
            bar_h = plot_h * (values[i] / y_hi)
            self.canvas.create_rectangle(x - bar_w / 2, top + plot_h - bar_h,
                                        x + bar_w / 2, top + plot_h,
                                        fill=spec.color, outline="")
            if labels and len(labels) == len(values) and len(values) <= 24:
                self.canvas.create_text(x, top + plot_h + 8, anchor="n",
                                        text=str(labels[i]), fill=DIM, font=FONT_SM)
        if spec.y_label:
            self.canvas.create_text(left + 4, top + 2, anchor="nw",
                                    text=spec.y_label, fill=FAINT, font=FONT_SM)

    # ==================================================================
    # 指标行与徽章
    # ==================================================================
    def _format_row(self, key: str, value: Any) -> str:
        if value is None:
            return "—"
        template = self.RESULT_FORMATS.get(key)
        if template:
            try:
                return template.format(value)
            except (ValueError, TypeError):
                return str(value)
        if isinstance(value, float):
            return f"{value:g}"
        return str(value)

    def _row_values(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        per_chart = getattr(self._chart, "rows", None) or {}
        values: Dict[str, Any] = {}
        for _label, key in self.RESULT_ROWS:
            source = per_chart.get(key) or self.ROW_SOURCES.get(key, key)
            values[key] = payload.get(source)
        return values

    def _fill_rows(self, payload: Mapping[str, Any],
                   drawn: Optional[int] = None) -> None:
        """刷新指标行、徽章与状态栏（动画中 ``drawn`` 非空时走 ``_partial_rows``）。"""
        values = None if drawn is None else self._partial_rows(payload, drawn)
        partial = values is not None
        if values is None:
            values = self._row_values(payload)

        for _label, key in self.RESULT_ROWS:
            self.vals[key].set(self._format_row(key, values.get(key)))

        badge = self._badge_for(payload, values)
        if badge is not None:
            text, level = badge
            bg, fg = _BADGE_COLORS.get(level, _BADGE_COLORS[NO])
            self.var_badge.set(text)
            self.badge.configure(bg=bg, fg=fg)

        status = self._status_for(payload, values, partial)
        if status:
            self.var_status.set(status)

    # ------------------------------------------------------------------
    # 交给子类的可选钩子
    # ------------------------------------------------------------------
    def _badge_for(self, payload: Mapping[str, Any],
                   values: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
        """结论徽章：``(文案, 等级)``；等级取 ``"ok"`` / ``"no"`` / ``"bad"``。"""
        return None

    def _partial_rows(self, payload: Mapping[str, Any],
                      drawn: int) -> Optional[Mapping[str, Any]]:
        """动画进行中按「已画出的前 ``drawn`` 个样本」给出实时指标（返回 None 就不刷新）。"""
        return None

    def _status_for(self, payload: Mapping[str, Any], values: Mapping[str, Any],
                    partial: bool) -> Optional[str]:
        """状态栏文案（返回 None 表示不改动）。"""
        return None

    # ==================================================================
    # 交互与生命周期
    # ==================================================================
    def _hit_cell(self, x: int, y: int, start: bool) -> None:
        """把画布坐标反查成 ``(行, 列)`` 并交给 :meth:`_on_cell_click`。

        ``start=True`` 表示这一次是"按下"（一次拖画动作的起点），``False`` 表示拖动途中；
        视图据此把**一次按下-拖动**当成同一笔来涂（而不是每经过一格就翻转一次 ——
        那样按住不动或来回蹭同一格会反复翻转，画面乱跳）。
        """
        spec = self._chart
        if spec is None or not spec.clickable or self._grid_geom is None:
            return
        cell, ox, oy, rows, cols = self._grid_geom
        if cell <= 0:
            return
        col, row = int((x - ox) // cell), int((y - oy) // cell)
        if not (0 <= row < rows and 0 <= col < cols):
            return
        try:
            payload = self._on_cell_click(row, col, start)
        except Exception as exc:            # 编辑出错不该把整个界面带崩
            self.var_status.set(f"编辑失败：{type(exc).__name__}: {exc}")
            return
        if payload:
            self._redraw_payload(payload)

    def _on_canvas_click(self, event) -> None:
        self._hit_cell(event.x, event.y, start=True)

    def _on_canvas_drag(self, event) -> None:
        self._hit_cell(event.x, event.y, start=False)

    def _on_cell_click(self, row: int, col: int, start: bool) -> Optional[Mapping[str, Any]]:
        """点到某个格子时的**可选钩子**（只有 ``ChartSpec.clickable=True`` 才会被调用）。

        ``start`` 为真表示"按下的第一格"，为假表示"拖动途中经过的格子"。
        返回一份**新的 payload** 表示"状态已被修改，请原地重绘"；返回 ``None`` 表示不处理
        （默认实现）。因此既有模型即使不关心它，行为也完全不变。
        """
        return None

    def on_key(self, key: str) -> None:
        """空格 = 播放 / 暂停；有多个动作时 ``1``..``9`` 触发第 n 个。"""
        k = key.lower()
        if k in (" ", "space"):
            self._toggle_pause()
            return
        actions = tuple(getattr(self.spec, "actions", ()) or ())
        if k.isdigit() and 1 <= int(k) <= len(actions):
            self.run_action(actions[int(k) - 1].key)

    def shutdown(self) -> None:
        self._cancel_animation()
        super().shutdown()
