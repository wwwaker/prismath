# -*- coding: utf-8 -*-
"""
方格网渗流模型 · 桌面窗口界面（Tkinter 后端）
==============================================

这是网页界面之外的第二套实现，两者共用同一份模型代码
（:mod:`awe_math.models.percolation.model`），只是渲染方式不同：

* :mod:`awe_math.ui.web` —— 现代网页界面
* :mod:`awe_math.ui.tk`  —— 本文件，传统桌面窗口，无需浏览器

界面构成
--------
* 控制面板：流通概率 p 滑块、网格尺寸、动画速度、单次/批量统计次数、各类按钮。
* 网格画布：实时绘制流通边（青色实线）与阻断边（灰色虚线），
  并以逐层动画展示水从顶端向下渗透的过程（浸润节点按渗透层数着色）。
* 右侧面板（三个标签页）：
  1. 「本次模拟」——当前 p、网格规模、浸润节点数、是否贯通等指标；
  2. 「批量统计」——多次独立重复实验的历史记录表；
  3. 「P(p) 曲线」——渗流概率随 p 变化的曲线（含理论阈值 p_c = 0.5）。

性能与线程
----------
批量统计与曲线扫描都在后台线程执行，进度通过 ``queue`` 回传主线程刷新界面，
因此界面在数千次模拟期间依然可以响应「停止」。

若环境中没有 matplotlib，界面仍可正常使用，只是曲线页显示提示文字。
"""

from __future__ import annotations

import math
import os
import queue
import random
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Sequence, Tuple

try:  # 作为包的一部分导入
    from ...models.percolation.model import (
        THEORETICAL_PC,
        BatchResult,
        PercolationGrid,
        SimResult,
        batch_percolation_probability,
        scan_curve,
    )
except ImportError:  # 允许直接运行本文件（把项目根目录加入 import 路径）
    from pathlib import Path

    _ROOT = Path(__file__).resolve().parents[3]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from awe_math.models.percolation.model import (  # type: ignore
        THEORETICAL_PC,
        BatchResult,
        PercolationGrid,
        SimResult,
        batch_percolation_probability,
        scan_curve,
    )

# ----------------------------------------------------------------------
# 界面配色与字体（深色扁平风：近黑底 + 细边框 + 单一强调色）
# ----------------------------------------------------------------------
BG = "#0f141b"          # 窗口底色
PANEL = "#151c26"       # 卡片 / 面板底
PANEL_2 = "#1d2634"     # 输入框 / 按钮底
BORDER = "#26313f"      # 细边框
BORDER_2 = "#35455c"    # 悬停边框
TEXT = "#e6edf6"        # 主文字
DIM = "#93a1b5"         # 次要文字
FAINT = "#66748f"       # 弱化文字
ACCENT = "#38bdf8"      # 主题强调色
ACCENT_TEXT = "#06283a"  # 强调色按钮上的深色文字
SEL_BG = "#1d3a52"      # 列表 / 表格选中行
BTN_HOVER = "#273242"
BTN_ACTIVE = "#2f3c50"
OK = "#34d399"
WARN = "#fbbf24"
DANGER = "#fb7185"

FONT = ("Microsoft YaHei UI", 10)
FONT_SM = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 14, "bold")
FONT_MONO = ("Consolas", 10)
FONT_MONO_B = ("Consolas", 10, "bold")

# 画布配色
BG_CANVAS = "#0c1118"       # 画布背景
COL_BLOCKED = "#333f4f"     # 阻断边
COL_OPEN = "#2fa9c9"        # 流通边
COL_WET_EDGE = "#ffb703"    # 已被水浸透的流通边
COL_NODE = "#5b6878"        # 未浸润节点
COL_NODE_EDGE = "#0a0e13"   # 节点描边
COL_TOP = "#4dabf7"         # 顶端水源
COL_BOTTOM = "#51cf66"      # 底端出口
COL_WET_FROM = (255, 222, 118)   # 早层浸润色（黄）
COL_WET_TO = (255, 74, 92)       # 深层浸润色（红）

#: 节点数上限提示：方格尺寸上限
MAX_SIZE = 60


def _lerp_color(start: Tuple[int, int, int], end: Tuple[int, int, int], t: float) -> str:
    """在两个 RGB 颜色之间线性插值，返回 ``#rrggbb``。"""
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    r = int(start[0] + (end[0] - start[0]) * t)
    g = int(start[1] + (end[1] - start[1]) * t)
    b = int(start[2] + (end[2] - start[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _install_theme(root: tk.Tk) -> None:
    """在 clam 主题上定制一套深色扁平样式（所有控件共用同一调色板）。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=BG)
    root.option_add("*TCombobox*Listbox.background", PANEL_2)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", SEL_BG)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT)

    def cfg(name: str, **kw) -> None:
        # 个别样式选项在旧版本 Tk 上可能不存在，逐条忽略以保证整体可用
        try:
            style.configure(name, **kw)
        except tk.TclError:
            pass

    def smap(name: str, **kw) -> None:
        try:
            style.map(name, **kw)
        except tk.TclError:
            pass

    cfg(".", background=BG, foreground=TEXT, font=FONT)
    cfg("TFrame", background=BG)
    cfg("Side.TFrame", background=BG)
    cfg("Panel.TFrame", background=PANEL)
    cfg("Card.TFrame", background=PANEL)

    cfg("TLabel", background=BG, foreground=TEXT)
    cfg("Dim.TLabel", background=BG, foreground=DIM)
    cfg("Card.TLabel", background=PANEL, foreground=TEXT)
    cfg("CardDim.TLabel", background=PANEL, foreground=DIM)
    cfg("Mono.TLabel", background=PANEL, foreground=TEXT, font=FONT_MONO)
    cfg("MonoAccent.TLabel", background=PANEL, foreground=ACCENT, font=FONT_MONO_B)
    cfg("Danger.TLabel", background=PANEL, foreground=DANGER)

    cfg("Card.TLabelframe", background=PANEL, bordercolor=BORDER,
        relief="solid", borderwidth=1)
    cfg("Card.TLabelframe.Label", background=PANEL, foreground=FAINT,
        font=("Microsoft YaHei UI", 9, "bold"))

    cfg("TButton", background=PANEL_2, foreground=TEXT, bordercolor=BORDER,
        focusthickness=1, focuscolor=BORDER_2, padding=(12, 7))
    smap("TButton",
         background=[("pressed", BTN_ACTIVE), ("active", BTN_HOVER), ("disabled", PANEL_2)],
         foreground=[("disabled", FAINT)],
         bordercolor=[("active", BORDER_2), ("disabled", BORDER)])

    cfg("Accent.TButton", background=ACCENT, foreground=ACCENT_TEXT,
        bordercolor=ACCENT, font=FONT_BOLD, padding=(12, 7))
    smap("Accent.TButton",
         background=[("pressed", "#0ea5e9"), ("active", "#7dd3fc"), ("disabled", PANEL_2)],
         foreground=[("disabled", FAINT)],
         bordercolor=[("disabled", BORDER)])

    cfg("Danger.TButton", background="#3d2029", foreground="#fda4af",
        bordercolor="#5b2a35", padding=(12, 7))
    smap("Danger.TButton",
         background=[("pressed", "#57222f"), ("active", "#4a222d"), ("disabled", PANEL_2)],
         foreground=[("disabled", FAINT)],
         bordercolor=[("disabled", BORDER)])

    cfg("TCheckbutton", background=BG, foreground=TEXT)
    cfg("Card.TCheckbutton", background=PANEL, foreground=TEXT)
    smap("TCheckbutton", background=[("active", BG)])
    smap("Card.TCheckbutton", background=[("active", PANEL)])

    cfg("Horizontal.TScale", background=ACCENT, troughcolor=PANEL_2,
        bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT)

    cfg("TSpinbox", fieldbackground=PANEL_2, foreground=TEXT, background=PANEL_2,
        bordercolor=BORDER, insertcolor=TEXT)
    cfg("TCombobox", fieldbackground=PANEL_2, foreground=TEXT, background=PANEL_2,
        bordercolor=BORDER, insertcolor=TEXT,
        selectbackground=SEL_BG, selectforeground=TEXT)

    cfg("TNotebook", background=BG, bordercolor=BG, tabmargins=(0, 4, 0, 0))
    cfg("TNotebook.Tab", background=BG, foreground=FAINT, padding=(14, 8))
    smap("TNotebook.Tab",
         background=[("selected", PANEL), ("active", PANEL_2)],
         foreground=[("selected", TEXT), ("active", DIM)])

    cfg("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
        bordercolor=BORDER, rowheight=26, font=FONT_SM)
    smap("Treeview",
         background=[("selected", SEL_BG)],
         foreground=[("selected", TEXT)])
    cfg("Treeview.Heading", background=PANEL_2, foreground=DIM,
        bordercolor=BORDER, relief="flat", padding=(4, 6))
    smap("Treeview.Heading", background=[("active", BTN_HOVER)])

    cfg("Vertical.TScrollbar", background=PANEL_2, troughcolor=PANEL,
        bordercolor=PANEL, arrowcolor=DIM)
    smap("Vertical.TScrollbar", background=[("active", BTN_HOVER)])

    cfg("Horizontal.TProgressbar", troughcolor=PANEL_2, background=ACCENT,
        bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT)
    cfg("TSeparator", background=BORDER)


# ----------------------------------------------------------------------
# matplotlib 为可选依赖
# ----------------------------------------------------------------------
try:
    import matplotlib

    matplotlib.use("TkAgg")
    # 中文显示：Windows 优先使用微软雅黑 / 黑体
    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
        "Noto Sans CJK SC",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False

    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure

    HAS_MPL = True
except Exception as _exc:  # pragma: no cover - 环境缺库时降级
    HAS_MPL = False
    _MPL_ERROR = str(_exc)


def _spec_defaults(spec) -> Dict[str, object]:
    """从模型元数据里取出参数默认值（没有传入 spec 时用渗流模型的默认值）。"""
    if spec is None:
        return {"p": 0.5, "size": 30}
    return {param.key: param.default for param in getattr(spec, "params", ())}


class PercolationApp:
    """渗流模型的可视化窗口（桌面后端）。"""

    def __init__(self, root: tk.Tk, spec=None) -> None:
        self.root = root
        self.spec = spec
        defaults = _spec_defaults(spec)
        init_p = float(defaults.get("p", 0.5))
        init_size = int(defaults.get("size", 30))
        model_name = getattr(spec, "name", "方格网渗流")

        self.root.title(f"{model_name} · 数学模型可视化（桌面窗口）")
        self.root.geometry("1440x880")
        self.root.minsize(1200, 780)

        # ---------------- 模型与状态 ----------------
        self.grid_model = PercolationGrid(size=init_size, p=init_p, rng=random.Random())
        self.result: Optional[SimResult] = None
        self._wet: set = set()               # 当前已显示的浸润节点
        self._shown_layers = 0               # 已显示的渗透层数
        self._anim_job: Optional[str] = None
        self._regenerate_job: Optional[str] = None
        self._redraw_job: Optional[str] = None

        # 画布元素索引（用于局部刷新，避免整图重绘）
        self._node_items: List[Optional[int]] = []
        self._h_items: List[List[Optional[int]]] = []
        self._v_items: List[List[Optional[int]]] = []
        self._cell = 10.0
        self._drawn_size = 0                 # 当前底图对应的网格边长

        # 后台任务
        self._queue: "queue.Queue" = queue.Queue()
        self._cancel = threading.Event()
        self._busy = False
        self._scan_results: List[BatchResult] = []
        self._scan_meta: Tuple[int, int] = (0, 0)

        # ---------------- 界面变量 ----------------
        self.var_p = tk.DoubleVar(value=init_p)
        self.var_size = tk.IntVar(value=init_size)
        self.var_speed = tk.IntVar(value=35)
        self.var_trials = tk.StringVar(value="1000")
        self.var_scan_trials = tk.StringVar(value="200")
        self.var_scan_step = tk.StringVar(value="0.05")
        self.var_status = tk.StringVar(value="就绪：拖动滑块调整 p，程序会自动重绘网格。")

        self.vals: Dict[str, tk.StringVar] = {
            "p": tk.StringVar(value="-"),
            "size": tk.StringVar(value="-"),
            "edges": tk.StringVar(value="-"),
            "pass": tk.StringVar(value="-"),
            "wet": tk.StringVar(value="-"),
            "depth": tk.StringVar(value="-"),
            "cost": tk.StringVar(value="-"),
            "b_p": tk.StringVar(value="-"),
            "b_trials": tk.StringVar(value="-"),
            "b_success": tk.StringVar(value="-"),
            "b_prob": tk.StringVar(value="-"),
            "b_err": tk.StringVar(value="-"),
            "b_time": tk.StringVar(value="-"),
        }

        self._build_ui()
        self._redraw_curve()

        # 事件绑定（快捷键）
        self.root.bind("<space>", lambda _e: self.start_animation())
        self.root.bind("<Key-r>", lambda _e: self.regenerate_grid())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root.after(80, self._poll_queue)      # 后台消息轮询
        self.root.after(60, self.regenerate_grid)  # 首帧绘制（等窗口完成布局）

    # ==================================================================
    # 界面搭建
    # ==================================================================
    def _build_ui(self) -> None:
        self.root.configure(bg=BG)
        self.root.columnconfigure(0, weight=0)   # 左侧控制栏
        self.root.columnconfigure(1, weight=1)   # 中央画布
        self.root.columnconfigure(2, weight=0)   # 右侧数据面板
        self.root.rowconfigure(1, weight=1)

        self._build_header()
        self._build_sidebar()
        self._build_center()
        self._build_right()
        self._build_status_bar()

    # ---------------------------- 顶部标题栏 ----------------------------
    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=BG)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")

        inner = tk.Frame(header, bg=BG)
        inner.pack(fill="x", padx=16, pady=(12, 10))
        inner.columnconfigure(2, weight=1)

        model_name = getattr(self.spec, "name", "方格网渗流")
        tk.Label(inner, text=f"≋ {model_name}", bg=BG, fg=ACCENT,
                 font=FONT_TITLE).grid(row=0, column=0, sticky="w")
        tk.Label(inner, text="数学模型可视化 · 桌面窗口", bg=BG, fg=FAINT,
                 font=FONT_SM).grid(row=0, column=1, sticky="sw", padx=(12, 0), pady=(0, 2))
        tk.Label(inner, text="空格 播放动画    R 重新生成", bg=BG, fg=FAINT,
                 font=FONT_SM).grid(row=0, column=3, sticky="e")

        tk.Frame(header, bg=BORDER, height=1).pack(fill="x")

    # ---------------------------- 左侧控制栏 ----------------------------
    def _build_sidebar(self) -> None:
        side = ttk.Frame(self.root, style="Side.TFrame", width=292)
        side.grid(row=1, column=0, sticky="ns", padx=(14, 7), pady=12)
        side.grid_propagate(False)

        self._build_param_card(side)
        self._build_action_card(side)
        self._build_batch_card(side)
        self._build_scan_card(side)

        self.btn_stop = ttk.Button(
            side, text="■ 停止后台任务", style="Danger.TButton",
            command=self.stop_work, state="disabled",
        )
        self.btn_stop.pack(fill="x", pady=(2, 0))

    @staticmethod
    def _card(parent: tk.Widget, title: str) -> ttk.LabelFrame:
        card = ttk.LabelFrame(
            parent, text=f" {title} ", style="Card.TLabelframe",
            padding=(14, 10, 14, 12),
        )
        card.pack(fill="x", pady=(0, 10))
        return card

    def _build_param_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "参数")

        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="流通概率 p", style="Card.TLabel").pack(side="left")
        self.lbl_p = ttk.Label(
            head, text=f"p = {self.var_p.get():.2f}", style="MonoAccent.TLabel",
        )
        self.lbl_p.pack(side="right")

        self.scale_p = ttk.Scale(
            card, from_=0.0, to=1.0, variable=self.var_p,
            command=self._on_p_change,
        )
        self.scale_p.pack(fill="x", pady=(4, 12))

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 10))
        ttk.Label(row, text="网格尺寸 n", style="Card.TLabel").pack(side="left")
        ttk.Label(row, text="× n", style="CardDim.TLabel").pack(side="right")
        spin = ttk.Spinbox(
            row, from_=5, to=MAX_SIZE, width=5,
            textvariable=self.var_size, command=self._on_size_change,
        )
        spin.pack(side="right", padx=(0, 4))
        spin.bind("<Return>", lambda _e: self._on_size_change())
        spin.bind("<FocusOut>", lambda _e: self._on_size_change())

        self.var_undirected = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            card,
            text="允许向上流动（标准无向渗流）",
            variable=self.var_undirected,
            style="Card.TCheckbutton",
            command=self._on_direction_change,
        ).pack(anchor="w", pady=(0, 12))

        ttk.Label(card, text="动画间隔（ms）", style="Card.TLabel").pack(anchor="w")
        speed = ttk.Scale(card, from_=1, to=200, command=self._on_speed_change)
        speed.set(self.var_speed.get())
        speed.pack(fill="x", pady=(4, 0))

    def _on_speed_change(self, value: str) -> None:
        try:
            self.var_speed.set(max(1, min(200, int(round(float(value))))))
        except (TypeError, ValueError):
            pass

    def _build_action_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "操作")
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        self.btn_anim = ttk.Button(
            card, text="▶ 播放渗透动画", style="Accent.TButton",
            command=self.start_animation,
        )
        self.btn_anim.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        self.btn_regen = ttk.Button(card, text="↻ 重新生成", command=self.regenerate_grid)
        self.btn_instant = ttk.Button(card, text="⤓ 立即判定", command=self.show_result_instant)
        self.btn_regen.grid(row=1, column=0, sticky="ew", padx=(0, 4))
        self.btn_instant.grid(row=1, column=1, sticky="ew", padx=(4, 0))

    def _build_batch_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "批量统计")

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 10))
        ttk.Label(row, text="统计次数 N", style="Card.TLabel").pack(side="left")
        ttk.Combobox(
            row, width=8, textvariable=self.var_trials,
            values=("100", "500", "1000", "5000", "10000"),
        ).pack(side="right")

        self.btn_batch = ttk.Button(
            card, text="开始批量统计", command=self.start_batch_statistics,
        )
        self.btn_batch.pack(fill="x")

    def _build_scan_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "曲线扫描")

        row1 = ttk.Frame(card, style="Card.TFrame")
        row1.pack(fill="x", pady=(0, 8))
        ttk.Label(row1, text="曲线每点次数", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(
            row1, from_=20, to=5000, increment=20, width=7,
            textvariable=self.var_scan_trials,
        ).pack(side="right")

        row2 = ttk.Frame(card, style="Card.TFrame")
        row2.pack(fill="x", pady=(0, 10))
        ttk.Label(row2, text="p 扫描步进", style="Card.TLabel").pack(side="left")
        ttk.Combobox(
            row2, width=6, textvariable=self.var_scan_step,
            values=("0.02", "0.05", "0.1"),
        ).pack(side="right")

        self.btn_scan = ttk.Button(card, text="绘制 P(p) 曲线", command=self.start_scan)
        self.btn_scan.pack(fill="x")

        self._action_buttons = [
            self.btn_regen,
            self.btn_anim,
            self.btn_instant,
            self.btn_batch,
            self.btn_scan,
        ]

    # ---------------------------- 中央画布 ----------------------------
    def _build_center(self) -> None:
        center = ttk.Frame(self.root, style="Side.TFrame")
        center.grid(row=1, column=1, sticky="nsew", pady=12)
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            center, bg=BG_CANVAS, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        self._build_legend(center).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _build_legend(self, parent: tk.Widget) -> tk.Canvas:
        cv = tk.Canvas(
            parent, height=30, bg=PANEL, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,
        )
        items = [
            ("line", COL_OPEN, "流通边"),
            ("dash", COL_BLOCKED, "阻断边"),
            ("dot", COL_NODE, "未浸润节点"),
            ("dot", _lerp_color(COL_WET_FROM, COL_WET_TO, 0.5), "已浸润节点"),
            ("dot", COL_TOP, "顶端水源"),
            ("dot", COL_BOTTOM, "底端出口"),
        ]
        x = 12
        for kind, color, text in items:
            if kind == "line":
                cv.create_line(x, 15, x + 20, 15, fill=color, width=3)
            elif kind == "dash":
                cv.create_line(x, 15, x + 20, 15, fill=color, width=2, dash=(2, 3))
            else:
                cv.create_oval(x + 5, 10, x + 15, 20, fill=color, outline=COL_NODE_EDGE)
            cv.create_text(x + 25, 15, text=text, anchor="w", fill=DIM, font=FONT_SM)
            x += 25 + len(text) * 13 + 16
        return cv

    # ---------------------------- 右侧数据面板 ----------------------------
    def _build_right(self) -> None:
        self.notebook = ttk.Notebook(self.root, width=412)
        self.notebook.grid(row=1, column=2, sticky="nsew", padx=(7, 14), pady=12)

        self.tab_single = ttk.Frame(self.notebook, style="Panel.TFrame", padding=12)
        self.tab_batch = ttk.Frame(self.notebook, style="Panel.TFrame", padding=12)
        self.tab_curve = ttk.Frame(self.notebook, style="Panel.TFrame", padding=8)
        self.notebook.add(self.tab_single, text=" 本次模拟 ")
        self.notebook.add(self.tab_batch, text=" 批量统计 ")
        self.notebook.add(self.tab_curve, text=" P(p) 曲线 ")

        self._build_single_tab()
        self._build_batch_tab()
        self._build_curve_tab()

    def _add_stat_row(self, parent: tk.Widget, row: int, label: str, var: tk.StringVar) -> None:
        ttk.Label(parent, text=label, style="CardDim.TLabel", width=14, anchor="w").grid(
            row=row, column=0, sticky="w", pady=4
        )
        ttk.Label(parent, textvariable=var, style="Mono.TLabel", anchor="w").grid(
            row=row, column=1, sticky="w", pady=4
        )

    def _build_single_tab(self) -> None:
        tab = self.tab_single
        tab.columnconfigure(1, weight=1)

        self.badge = tk.Label(
            tab, text="— 等待生成 —", bg=PANEL_2, fg=FAINT,
            font=("Microsoft YaHei UI", 12, "bold"), pady=12,
        )
        self.badge.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))

        rows = [
            ("当前概率 p", "p"),
            ("网格规模", "size"),
            ("流通边 / 总边数", "edges"),
            ("是否渗流出水", "pass"),
            ("浸润节点数", "wet"),
            ("渗透层数", "depth"),
            ("判定耗时", "cost"),
        ]
        for i, (label, key) in enumerate(rows, start=1):
            self._add_stat_row(tab, i, label, self.vals[key])

        sep_row = len(rows) + 1
        ttk.Separator(tab, orient="horizontal").grid(
            row=sep_row, column=0, columnspan=2, sticky="ew", pady=10
        )
        ttk.Label(
            tab,
            style="CardDim.TLabel",
            wraplength=350,
            justify="left",
            font=FONT_SM,
            text=(
                "说明：\n"
                "· 顶端整行视为水源，底端整行视为出口；\n"
                "· 只要存在一条由流通边组成的路径把两者连起来，\n"
                "  就认为本次模拟「渗流出水」；\n"
                f"· 二维方格网键渗流的理论阈值 p_c = {THEORETICAL_PC}，\n"
                "  在它附近渗流概率急剧上升 —— 量变引起质变。"
            ),
        ).grid(row=sep_row + 1, column=0, columnspan=2, sticky="w")

    def _build_batch_tab(self) -> None:
        tab = self.tab_batch
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        info = ttk.LabelFrame(
            tab, text=" 最近一次批量统计 ", style="Card.TLabelframe",
            padding=(14, 10, 14, 12),
        )
        info.grid(row=0, column=0, columnspan=2, sticky="ew")
        info.columnconfigure(1, weight=1)
        rows = [
            ("统计概率 p", "b_p"),
            ("模拟次数 N", "b_trials"),
            ("成功次数", "b_success"),
            ("渗流概率", "b_prob"),
            ("标准误", "b_err"),
            ("总耗时", "b_time"),
        ]
        for i, (label, key) in enumerate(rows):
            self._add_stat_row(info, i, label, self.vals[key])

        head = ttk.Frame(tab, style="Panel.TFrame")
        head.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        ttk.Label(head, text="历史记录", style="Card.TLabel", font=FONT_BOLD).pack(side="left")
        ttk.Button(head, text="清空", width=6, command=self._clear_history).pack(side="right")

        cols = ("p", "n", "trials", "success", "prob", "time")
        self.tree = ttk.Treeview(tab, columns=cols, show="headings", height=10)
        for col, text, width in zip(
            cols,
            ("概率 p", "网格 n", "次数", "成功", "渗流概率", "耗时(s)"),
            (56, 56, 60, 56, 84, 66),
        ):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="center")
        self.tree.grid(row=2, column=0, sticky="nsew")
        self.tree.tag_configure("ok", foreground="#4ade80")
        self.tree.tag_configure("no", foreground="#fb7185")

        bar = ttk.Scrollbar(tab, orient="vertical", command=self.tree.yview)
        bar.grid(row=2, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=bar.set)

    def _build_curve_tab(self) -> None:
        tab = self.tab_curve
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        if not HAS_MPL:
            ttk.Label(
                tab,
                text="未检测到 matplotlib，无法绘制曲线。\n可执行 pip install matplotlib 后重试。",
                style="Danger.TLabel",
                justify="left",
            ).grid(row=0, column=0, sticky="nw", padx=10, pady=10)
            self.figure = None
            self.ax = None
            self.figure_canvas = None
            return

        self.figure = Figure(figsize=(4.3, 3.4), dpi=100, facecolor=PANEL)
        self.ax = self.figure.add_subplot(111)
        self.figure_canvas = FigureCanvasTkAgg(self.figure, master=tab)
        self.figure_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar = NavigationToolbar2Tk(self.figure_canvas, tab, pack_toolbar=False)
        toolbar.update()
        toolbar.configure(bg=PANEL)
        for child in toolbar.winfo_children():
            try:
                child.configure(bg=PANEL)
            except tk.TclError:
                pass
        toolbar.grid(row=1, column=0, sticky="ew")

    # ---------------------------- 状态栏 ----------------------------
    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self.root)
        bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=(2, 10))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, textvariable=self.var_status, style="Dim.TLabel", anchor="w").grid(
            row=0, column=0, sticky="ew"
        )
        self.progress = ttk.Progressbar(bar, length=260, mode="determinate")
        self.progress.grid(row=0, column=1, padx=(12, 0))

    # ==================================================================
    # 参数与事件
    # ==================================================================
    def _current_size(self) -> int:
        try:
            size = int(self.var_size.get())
        except (tk.TclError, ValueError):
            size = self.grid_model.size
        return max(2, min(MAX_SIZE, size))

    @staticmethod
    def _parse_int(text: str, default: int, low: int = 1, high: int = 10_000_000) -> int:
        try:
            value = int(str(text).strip())
        except (TypeError, ValueError):
            return default
        return max(low, min(high, value))

    @staticmethod
    def _parse_float(text: str, default: float, low: float = 0.0, high: float = 1.0) -> float:
        try:
            value = float(str(text).strip())
        except (TypeError, ValueError):
            return default
        return max(low, min(high, value))

    def _on_p_change(self, value: Optional[str] = None) -> None:
        """滑块变化：更新显示，并防抖地重新生成网格。"""
        if value is not None:
            try:
                self.var_p.set(round(float(value), 2))
            except (TypeError, ValueError):
                pass
        self.lbl_p.configure(text=f"p = {self.var_p.get():.2f}")
        self._debounce_regenerate()

    def _on_size_change(self) -> None:
        size = self._current_size()
        if size != self.grid_model.size:
            # 尺寸变化会重建边数组，旧尺寸的动画结果必须立即作废，否则渲染会越界
            self._cancel_animation()
            self._discard_result()
            self.grid_model.size = size
            self.grid_model.regenerate()
        self._debounce_regenerate(delay=60)

    def _discard_result(self) -> None:
        """丢弃当前结果（网格尺寸/模式变化后调用）。"""
        self.result = None
        self._shown_layers = 0
        self._wet = set()

    def _on_direction_change(self) -> None:
        self.grid_model.directed = not self.var_undirected.get()
        mode = "标准无向渗流" if not self.grid_model.directed else "有向渗流（只向下/左/右）"
        self.var_status.set(f"已切换为 {mode}。")
        self.regenerate_grid()

    def _on_canvas_resize(self, _event=None) -> None:
        """画布尺寸变化后重绘（防抖，避免拖动窗口时频繁重绘）。"""
        if self._redraw_job is not None:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(120, self._redraw_grid)

    def _debounce_regenerate(self, delay: int = 160) -> None:
        if self._regenerate_job is not None:
            self.root.after_cancel(self._regenerate_job)
        self._regenerate_job = self.root.after(delay, self.regenerate_grid)

    def _sync_model_params(self) -> None:
        """把界面上的参数同步进模型。

        滑块拖动会做防抖（延迟重绘），用户可能在防抖触发前就点了按钮，
        因此每次操作前都强制同步一次 p 与网格尺寸，避免用到过期参数。
        """
        p = round(self.var_p.get(), 2)
        size = self._current_size()
        if size != self.grid_model.size:
            self._cancel_animation()
            self._discard_result()
            self.grid_model.size = size
            self.grid_model.directed = not self.var_undirected.get()
            self.grid_model.regenerate(p)   # 尺寸变了必须重建边数组
        else:
            self.grid_model.p = p

    # ==================================================================
    # 网格生成与绘制
    # ==================================================================
    def regenerate_grid(self) -> None:
        """重新随机生成网格，并立即显示出水/不出水的结果（不做动画）。"""
        self._regenerate_job = None
        self._cancel_animation()
        self._sync_model_params()
        self.grid_model.regenerate()
        self._simulate_and_show(reset=True)
        self.var_status.set(
            f"已重新生成网格：n={self.grid_model.size}，p={self.grid_model.p:.2f}。"
            "按空格可播放渗透动画。"
        )

    def _simulate_and_show(self, reset: bool = True) -> None:
        """重新计算一次渗透过程并刷新画布与指标。"""
        self.result = self.grid_model.simulate()
        self._shown_layers = len(self.result.layers)
        self._wet = set(self.result.wet)
        self._redraw_grid()
        self._update_result_labels()

    def _layout_params(self) -> Tuple[int, float, float, float]:
        """计算当前画布下的节点间距与左上角偏移。"""
        n = self.grid_model.size
        width = max(self.canvas.winfo_width(), 60)
        height = max(self.canvas.winfo_height(), 60)
        pad = 24
        span_w = max(width - 2 * pad, 10)
        span_h = max(height - 2 * pad, 10)
        cell = min(span_w / (n - 1), span_h / (n - 1))
        ox = (width - cell * (n - 1)) / 2.0
        oy = (height - cell * (n - 1)) / 2.0
        return n, cell, ox, oy

    def _draw_base(self) -> None:
        """绘制底层网格：所有边 + 所有节点（不含量变信息）。"""
        cv = self.canvas
        cv.delete("all")
        n, cell, ox, oy = self._layout_params()
        self._cell = cell
        self._drawn_size = n   # 记录底图使用的网格尺寸，供增量上色时校验

        radius = max(1.2, min(5.0, cell * 0.17))
        lw_open = max(1.0, min(2.8, cell * 0.16))
        lw_block = max(0.6, min(1.5, cell * 0.08))

        self._node_items = [None] * (n * n)
        self._h_items = [[None] * (n - 1) for _ in range(n)]
        self._v_items = [[None] * n for _ in range(n - 1)]

        h_edge, v_edge = self.grid_model.h_edge, self.grid_model.v_edge

        # 第一遍：阻断边（虚线，画在下层）
        for r in range(n):
            y = oy + r * cell
            for c in range(n - 1):
                if h_edge[r][c]:
                    continue
                x1 = ox + c * cell
                self._h_items[r][c] = cv.create_line(
                    x1, y, x1 + cell, y, fill=COL_BLOCKED, width=lw_block, dash=(2, 3)
                )
        for r in range(n - 1):
            y1 = oy + r * cell
            for c in range(n):
                if v_edge[r][c]:
                    continue
                x = ox + c * cell
                self._v_items[r][c] = cv.create_line(
                    x, y1, x, y1 + cell, fill=COL_BLOCKED, width=lw_block, dash=(2, 3)
                )

        # 第二遍：流通边（实线，画在上层）
        for r in range(n):
            y = oy + r * cell
            for c in range(n - 1):
                if not h_edge[r][c]:
                    continue
                x1 = ox + c * cell
                self._h_items[r][c] = cv.create_line(
                    x1, y, x1 + cell, y, fill=COL_OPEN, width=lw_open
                )
        for r in range(n - 1):
            y1 = oy + r * cell
            for c in range(n):
                if not v_edge[r][c]:
                    continue
                x = ox + c * cell
                self._v_items[r][c] = cv.create_line(
                    x, y1, x, y1 + cell, fill=COL_OPEN, width=lw_open
                )

        # 节点
        for r in range(n):
            y = oy + r * cell
            for c in range(n):
                x = ox + c * cell
                if r == 0:
                    outline, ow = COL_TOP, 1.6
                elif r == n - 1:
                    outline, ow = COL_BOTTOM, 1.6
                else:
                    outline, ow = COL_NODE_EDGE, 1
                self._node_items[r * n + c] = cv.create_oval(
                    x - radius, y - radius, x + radius, y + radius,
                    fill=COL_NODE, outline=outline, width=ow,
                )

        # 水源 / 出口提示
        cv.create_text(10, 8, anchor="nw", text="▼ 顶端水源（水从这里倒入）",
                       fill=COL_TOP, font=("Microsoft YaHei", 8))
        cv.create_text(10, int(cv.winfo_height()) - 8, anchor="sw",
                       text="▲ 底端出口（水从这里流出）",
                       fill=COL_BOTTOM, font=("Microsoft YaHei", 8))

    def _apply_wet(self, nodes: Sequence[int], color: str) -> None:
        """把一批节点标记为已浸润，并高亮它与已浸润邻居之间的流通边。

        注意：节点索引必须与当前底图尺寸一致，否则直接跳过（避免越界）。
        """
        cv = self.canvas
        n = self._drawn_size
        if n <= 0:
            return
        h_items, v_items, node_items = self._h_items, self._v_items, self._node_items
        lw = max(2.0, min(4.2, self._cell * 0.26))

        for idx in nodes:
            item = node_items[idx]
            if item is not None:
                cv.itemconfigure(item, fill=color)
            r, c = divmod(idx, n)
            if c + 1 < n and (idx + 1) in self._wet:
                it = h_items[r][c]
                if it is not None:
                    cv.itemconfigure(it, fill=COL_WET_EDGE, width=lw, dash=())
            if c > 0 and (idx - 1) in self._wet:
                it = h_items[r][c - 1]
                if it is not None:
                    cv.itemconfigure(it, fill=COL_WET_EDGE, width=lw, dash=())
            if r + 1 < n and (idx + n) in self._wet:
                it = v_items[r][c]
                if it is not None:
                    cv.itemconfigure(it, fill=COL_WET_EDGE, width=lw, dash=())
            if r > 0 and (idx - n) in self._wet:
                it = v_items[r - 1][c]
                if it is not None:
                    cv.itemconfigure(it, fill=COL_WET_EDGE, width=lw, dash=())

    def _layer_color(self, layer_index: int, total_layers: int) -> str:
        """按渗透层数做颜色渐变：越晚到达的节点越红。"""
        if total_layers <= 1:
            t = 0.0
        else:
            t = layer_index / (total_layers - 1)
        return _lerp_color(COL_WET_FROM, COL_WET_TO, t)

    def _redraw_grid(self) -> None:
        """整图重绘：底图 + 当前已显示的浸润层。"""
        self._redraw_job = None
        if self.grid_model is None:
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width <= 40 or height <= 40:   # 布局尚未完成，等待 Configure 事件
            return

        self._draw_base()
        self._wet = set()
        # 结果必须与底图尺寸一致，否则只画底图（防止切换尺寸瞬间的越界渲染）
        if (
            self.result is None
            or self._shown_layers <= 0
            or self.result.size != self.grid_model.size
        ):
            return

        layers = self.result.layers
        total = len(layers)
        for i in range(min(self._shown_layers, total)):
            batch = layers[i]
            self._wet.update(batch)
            self._apply_wet(batch, self._layer_color(i, total))

        # 贯通 / 未贯通的结论提示
        if self._shown_layers >= total and self.result.percolates:
            self.canvas.create_text(
                width // 2, height - 8, anchor="s",
                text="✔ 渗流成功：水已从顶端流到底端",
                fill="#7ee787", font=("Microsoft YaHei", 10, "bold"),
            )
        elif self._shown_layers >= total:
            self.canvas.create_text(
                width // 2, height - 8, anchor="s",
                text="✘ 未贯通：水被阻断，无法流到底端",
                fill="#ff8a80", font=("Microsoft YaHei", 10, "bold"),
            )

    # ==================================================================
    # 动画
    # ==================================================================
    def start_animation(self) -> None:
        """播放水从顶端向下渗透的动画。"""
        if self._busy:
            return
        self._cancel_animation()
        self._sync_model_params()
        self.grid_model.directed = not self.var_undirected.get()
        self.result = self.grid_model.simulate()
        self._shown_layers = 0
        self._wet = set()
        self._draw_base()
        self._update_result_labels()
        self.var_status.set(
            f"正在演示渗透过程：p={self.grid_model.p:.2f}，n={self.grid_model.size}。"
        )
        self._step_animation()

    def _step_animation(self) -> None:
        self._anim_job = None
        if self.result is None:
            return
        if self._drawn_size != self.result.size:
            # 底图已被其它尺寸重建，当前动画结果作废
            self._cancel_animation()
            return
        layers = self.result.layers
        total = len(layers)

        if self._shown_layers >= total:
            self._finish_animation()
            return

        # 层数太多时每帧多播几层，保证动画总时长可控（最多约 60 帧）
        per_frame = max(1, math.ceil(total / 60))
        for _ in range(per_frame):
            if self._shown_layers >= total:
                break
            i = self._shown_layers
            batch = [idx for idx in layers[i] if idx not in self._wet]
            self._wet.update(batch)
            self._apply_wet(batch, self._layer_color(i, total))
            self._shown_layers += 1

        self._update_result_labels()
        delay = max(1, int(self.var_speed.get()))
        self._anim_job = self.root.after(delay, self._step_animation)

    def _finish_animation(self) -> None:
        self._cancel_animation()
        self._redraw_grid()
        self._update_result_labels()
        state = "渗流成功（已贯通）" if (self.result and self.result.percolates) else "未贯通"
        self.var_status.set(
            f"模拟结束：{state}。可点击「批量统计」考察该 p 值下的渗流概率。"
        )

    def _cancel_animation(self) -> None:
        if self._anim_job is not None:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None

    def show_result_instant(self) -> None:
        """跳过动画，直接显示最终浸润结果。"""
        self._cancel_animation()
        self._sync_model_params()
        self._simulate_and_show(reset=True)
        state = "渗流成功（已贯通）" if self.result and self.result.percolates else "未贯通"
        self.var_status.set(f"单次模拟结果：{state}。")

    # ==================================================================
    # 指标刷新
    # ==================================================================
    def _update_result_labels(self) -> None:
        model = self.grid_model
        res = self.result
        self.vals["p"].set(f"{model.p:.2f}")
        self.vals["size"].set(f"{model.size} × {model.size}（{model.node_count} 个节点）")
        if res is not None:
            self.vals["edges"].set(
                f"{res.open_edge_count} / {res.total_edge_count}（实测比例 {res.open_ratio:.3f}）"
            )
            if self._shown_layers < len(res.layers):
                self.vals["pass"].set("渗透中…")
            else:
                self.vals["pass"].set("✔ 出水" if res.percolates else "✘ 未出水")
            self.vals["wet"].set(f"{len(self._wet)} / {res.node_count}（{len(self._wet)/res.node_count:.1%}）")
            self.vals["depth"].set(f"{min(self._shown_layers, len(res.layers))} / {len(res.layers)} 层")
            self.vals["cost"].set(f"{res.elapsed * 1000:.1f} ms")
        else:
            self.vals["edges"].set(f"- / {model.total_edge_count()}")

        # 顶部的结论徽章
        if res is None:
            self.badge.configure(text="— 等待生成 —", bg=PANEL_2, fg=FAINT)
        elif self._shown_layers < len(res.layers):
            self.badge.configure(text="渗透中 …", bg=PANEL_2, fg=WARN)
        elif res.percolates:
            self.badge.configure(text="✔ 渗流出水：已从顶端贯通到底端", bg="#0f2e1f", fg="#4ade80")
        else:
            self.badge.configure(text="✘ 未贯通：水被阻断", bg="#331420", fg="#fb7185")

    def _insert_history(self, res: BatchResult, tag: str) -> None:
        self.tree.insert(
            "", 0,
            values=(
                f"{res.p:.2f}",
                res.size,
                res.trials,
                res.success,
                f"{res.probability:.4f}",
                f"{res.elapsed:.2f}",
            ),
            tags=(tag,),
        )
        if len(self.tree.get_children()) > 300:
            self.tree.delete(self.tree.get_children()[-1])

    def _clear_history(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    # ==================================================================
    # 批量统计 / 曲线扫描（后台线程）
    # ==================================================================
    def _set_busy(self, busy: bool, text: str = "") -> None:
        self._busy = busy
        for btn in self._action_buttons:
            btn.configure(state="disabled" if busy else "normal")
        self.btn_stop.configure(state="normal" if busy else "disabled")
        if text:
            self.var_status.set(text)

    def stop_work(self) -> None:
        """请求停止后台批量统计 / 扫描。"""
        self._cancel.set()
        self.var_status.set("正在停止…")

    def start_batch_statistics(self) -> None:
        """对当前 p 值做 N 次独立模拟，统计渗流频率。"""
        if self._busy:
            return
        size = self._current_size()
        p = round(self.var_p.get(), 2)
        trials = self._parse_int(self.var_trials.get(), 1000)
        self._cancel.clear()
        self.progress.configure(maximum=trials, value=0)
        self._set_busy(True, f"正在统计：p={p:.2f}，n={size}×{size}，共 {trials} 次独立模拟…")

        def job() -> None:
            try:
                res = batch_percolation_probability(
                    size=size, p=p, trials=trials,
                    progress=lambda done, total, success: self._queue.put(("progress", (done, total))),
                    cancel=self._cancel,
                )
                self._queue.put(("batch_done", res))
            except Exception as exc:  # pragma: no cover
                self._queue.put(("error", f"批量统计失败：{exc}"))

        threading.Thread(target=job, daemon=True).start()

    def start_scan(self) -> None:
        """扫描 p ∈ [0, 1]，绘制渗流概率曲线。"""
        if self._busy:
            return
        size = self._current_size()
        trials = self._parse_int(self.var_scan_trials.get(), 200, low=10)
        step = self._parse_float(self.var_scan_step.get(), 0.05, low=0.01, high=0.5)
        p_values = [round(i * step, 2) for i in range(int(round(1.0 / step)) + 1)]
        p_values = [p for p in p_values if p <= 1.0]

        self._cancel.clear()
        self._scan_results = []
        self._scan_meta = (size, trials)
        self.progress.configure(maximum=len(p_values), value=0)
        self.notebook.select(self.tab_curve)
        self._set_busy(
            True,
            f"正在扫描 p（共 {len(p_values)} 个点，每点 {trials} 次，网格 {size}×{size}）…",
        )

        def job() -> None:
            try:
                scan_curve(
                    p_values, size=size, trials=trials,
                    progress=lambda done, total, res: self._queue.put(("scan_point", (done, total, res))),
                    cancel=self._cancel,
                )
                self._queue.put(("scan_done", None))
            except Exception as exc:  # pragma: no cover
                self._queue.put(("error", f"曲线扫描失败：{exc}"))

        threading.Thread(target=job, daemon=True).start()

    def _poll_queue(self) -> None:
        """主线程定时取出后台线程的消息。"""
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                self._handle_message(kind, payload)
        except queue.Empty:
            pass
        self.root.after(70, self._poll_queue)

    def _handle_message(self, kind: str, payload) -> None:
        if kind == "progress":
            done, total = payload
            self.progress.configure(maximum=total, value=done)
            self.var_status.set(f"正在统计：{done}/{total} 次…")

        elif kind == "batch_done":
            res: BatchResult = payload
            self._set_busy(False)
            self.progress.configure(value=self.progress.cget("maximum"))
            self.vals["b_p"].set(f"{res.p:.2f}")
            self.vals["b_trials"].set(f"{res.trials}")
            self.vals["b_success"].set(f"{res.success}")
            self.vals["b_prob"].set(f"{res.probability:.4f}（{res.probability:.2%}）")
            self.vals["b_err"].set(f"±{res.stderr:.4f}")
            self.vals["b_time"].set(f"{res.elapsed:.2f} s")
            self._insert_history(res, "ok" if res.probability >= 0.5 else "no")
            self.notebook.select(self.tab_batch)
            self.var_status.set(
                f"统计完成：p={res.p:.2f} 时渗流概率 ≈ {res.probability:.4f}"
                f"（{res.success}/{res.trials}），耗时 {res.elapsed:.2f} s。"
            )

        elif kind == "scan_point":
            done, total, res = payload
            self._scan_results.append(res)
            self.progress.configure(maximum=total, value=done)
            self.var_status.set(f"曲线扫描：{done}/{total} 个 p 值已计算…")
            self._redraw_curve()

        elif kind == "scan_done":
            self._set_busy(False)
            self._redraw_curve()
            self.var_status.set(
                f"曲线绘制完成：共 {len(self._scan_results)} 个点，"
                f"每点 {self._scan_meta[1]} 次模拟。"
            )

        elif kind == "error":
            self._set_busy(False)
            messagebox.showerror("出错了", str(payload))
            self.var_status.set(str(payload))

    # ==================================================================
    # 曲线绘制
    # ==================================================================
    def _style_ax(self) -> None:
        """把坐标轴刷成暗色（clear 之后需要重新设置）。"""
        if self.ax is None:
            return
        ax = self.ax
        ax.set_facecolor(PANEL)
        for spine in ax.spines.values():
            spine.set_color(BORDER)
        ax.tick_params(colors=DIM)
        ax.xaxis.label.set_color(DIM)
        ax.yaxis.label.set_color(DIM)

    def _redraw_curve(self) -> None:
        if not HAS_MPL or self.ax is None:
            return
        ax = self.ax
        ax.clear()

        if not self._scan_results:
            ax.text(
                0.5, 0.5,
                "点击「绘制 P(p) 曲线」开始扫描",
                transform=ax.transAxes, ha="center", va="center",
                color=FAINT, fontsize=10,
            )
            ax.set_xticks([])
            ax.set_yticks([])
        else:
            xs = [r.p for r in self._scan_results]
            ys = [r.probability * 100.0 for r in self._scan_results]
            ax.plot(
                xs, ys, "-o", color=ACCENT, lw=1.8, ms=3.4,
                mfc=BG_CANVAS, mec=TEXT, mew=0.8,
                label="实验结果（蒙特卡洛）",
            )
            ax.axvline(
                THEORETICAL_PC, color=DANGER, ls="--", lw=1.3,
                label=f"理论阈值 p_c = {THEORETICAL_PC}",
            )
            ax.set_xlabel("流通概率 p", fontsize=9)
            ax.set_ylabel("渗流出水概率 P(p)  (%)", fontsize=9)
            ax.set_xlim(0, 1)
            ax.set_ylim(-3, 103)
            ax.grid(color="#22303f", lw=0.8, ls=":")
            ax.tick_params(labelsize=8)
            ax.legend(
                loc="upper left", fontsize=8,
                facecolor=PANEL_2, edgecolor=BORDER, labelcolor=TEXT,
            )
            size, trials = self._scan_meta
            ax.set_title(f"P(p) 曲线（网格 {size}×{size}，每点 {trials} 次）", fontsize=9, color=TEXT)
            if ys and max(ys) >= 100 and min(ys) <= 0:
                ax.annotate(
                    "相变：量变引起质变",
                    xy=(THEORETICAL_PC, 50), xytext=(THEORETICAL_PC + 0.06, 22),
                    fontsize=8, color=WARN,
                    arrowprops=dict(arrowstyle="->", color=WARN, lw=1),
                )

        self._style_ax()
        self.figure_canvas.draw_idle()

    # ==================================================================
    def _on_close(self) -> None:
        self._cancel_animation()
        self._cancel.set()
        self.root.destroy()


def launch(spec=None, **_kwargs) -> int:
    """启动桌面窗口界面。

    ``spec`` 由 :mod:`awe_math.launcher` 传入，用于取模型名称与参数默认值；
    直接运行本文件时也可以省略。
    """
    root = tk.Tk()
    _install_theme(root)
    PercolationApp(root, spec=spec)
    root.mainloop()
    return 0


if __name__ == "__main__":
    launch()
