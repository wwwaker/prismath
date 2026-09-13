# -*- coding: utf-8 -*-
"""
方格网渗流模型 · 桌面窗口界面（Tkinter 后端）
==============================================

这是网页界面之外的第二套实现，两者共用同一份模型代码
（:mod:`awe_math.models.percolation.model`），只是渲染方式不同：

* :mod:`awe_math.ui.web` —— 现代网页界面（推荐，Canvas + 实时曲线）
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
# 配色方案
# ----------------------------------------------------------------------
BG_CANVAS = "#101820"       # 画布背景
COL_BLOCKED = "#2c3542"     # 阻断边
COL_OPEN = "#2f9fb8"        # 流通边
COL_WET_EDGE = "#ffb703"    # 已被水浸透的流通边
COL_NODE = "#59636f"        # 未浸润节点
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
        self.root.geometry("1320x840")
        self.root.minsize(1040, 700)

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
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_control_panel()
        self._build_body()
        self._build_status_bar()

    # ---------------------------- 控制面板 ----------------------------
    def _build_control_panel(self) -> None:
        frame = ttk.LabelFrame(self.root, text="控制面板", padding=(12, 8))
        frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        frame.columnconfigure(9, weight=1)

        # --- 第一行：参数 ---
        ttk.Label(frame, text="流通概率 p").grid(row=0, column=0, padx=(0, 6), sticky="w")
        self.scale_p = tk.Scale(
            frame,
            variable=self.var_p,
            from_=0.0,
            to=1.0,
            resolution=0.01,
            orient="horizontal",
            showvalue=False,
            length=240,
            command=self._on_p_change,
        )
        self.scale_p.grid(row=0, column=1, padx=(0, 6))
        self.lbl_p = ttk.Label(frame, text="p = 0.50", width=10, font=("Consolas", 10, "bold"))
        self.lbl_p.grid(row=0, column=2, padx=(0, 16), sticky="w")

        ttk.Label(frame, text="网格尺寸 n").grid(row=0, column=3, padx=(0, 6), sticky="w")
        spin_size = ttk.Spinbox(
            frame,
            from_=5,
            to=MAX_SIZE,
            width=5,
            textvariable=self.var_size,
            command=self._on_size_change,
        )
        spin_size.grid(row=0, column=4, padx=(0, 4))
        spin_size.bind("<Return>", lambda _e: self._on_size_change())
        spin_size.bind("<FocusOut>", lambda _e: self._on_size_change())
        ttk.Label(frame, text="×n").grid(row=0, column=5, padx=(0, 16), sticky="w")

        ttk.Label(frame, text="动画间隔(ms)").grid(row=0, column=6, padx=(0, 6), sticky="w")
        tk.Scale(
            frame,
            variable=self.var_speed,
            from_=1,
            to=200,
            resolution=1,
            orient="horizontal",
            showvalue=False,
            length=120,
        ).grid(row=0, column=7, padx=(0, 16))

        ttk.Label(frame, text="统计次数 N").grid(row=0, column=8, padx=(0, 6), sticky="w")
        ttk.Combobox(
            frame,
            width=8,
            textvariable=self.var_trials,
            values=("100", "500", "1000", "5000", "10000"),
        ).grid(row=0, column=9, padx=(0, 6), sticky="w")

        # --- 第二行：按钮 ---
        btns = ttk.Frame(frame)
        btns.grid(row=1, column=0, columnspan=10, sticky="ew", pady=(8, 0))

        self.btn_regen = ttk.Button(btns, text="重新生成网格", command=self.regenerate_grid)
        self.btn_anim = ttk.Button(btns, text="开始渗透（动画）", command=self.start_animation)
        self.btn_instant = ttk.Button(btns, text="立即判定", command=self.show_result_instant)
        self.btn_batch = ttk.Button(btns, text="批量统计", command=self.start_batch_statistics)
        self.btn_scan = ttk.Button(btns, text="绘制 P(p) 曲线", command=self.start_scan)
        self.btn_stop = ttk.Button(btns, text="停止", command=self.stop_work, state="disabled")

        for i, btn in enumerate(
            (self.btn_regen, self.btn_anim, self.btn_instant, self.btn_batch, self.btn_scan, self.btn_stop)
        ):
            btn.grid(row=0, column=i, padx=(0, 8))

        self.var_undirected = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            btns,
            text="允许向上流动（标准无向渗流）",
            variable=self.var_undirected,
            command=self._on_direction_change,
        ).grid(row=0, column=6, padx=(12, 12))

        ttk.Label(btns, text="曲线每点次数").grid(row=0, column=7, padx=(0, 4))
        ttk.Spinbox(
            btns,
            from_=20,
            to=5000,
            increment=20,
            width=6,
            textvariable=self.var_scan_trials,
        ).grid(row=0, column=8, padx=(0, 10))
        ttk.Label(btns, text="p 步进").grid(row=0, column=9, padx=(0, 4))
        ttk.Combobox(
            btns,
            width=5,
            textvariable=self.var_scan_step,
            values=("0.02", "0.05", "0.1"),
        ).grid(row=0, column=10)

        self._action_buttons = [
            self.btn_regen,
            self.btn_anim,
            self.btn_instant,
            self.btn_batch,
            self.btn_scan,
        ]

    # ---------------------------- 主体区域 ----------------------------
    def _build_body(self) -> None:
        body = ttk.Frame(self.root)
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0)
        body.rowconfigure(0, weight=1)

        # 左：网格画布
        left = ttk.LabelFrame(body, text="网格渗透过程", padding=4)
        left.grid(row=0, column=0, sticky="nsew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(left, bg=BG_CANVAS, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        self._build_legend(left).grid(row=1, column=0, sticky="ew", pady=(4, 0))

        # 右：统计面板
        self.notebook = ttk.Notebook(body, width=440)
        self.notebook.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self.tab_single = ttk.Frame(self.notebook, padding=10)
        self.tab_batch = ttk.Frame(self.notebook, padding=10)
        self.tab_curve = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(self.tab_single, text="本次模拟")
        self.notebook.add(self.tab_batch, text="批量统计")
        self.notebook.add(self.tab_curve, text="P(p) 曲线")

        self._build_single_tab()
        self._build_batch_tab()
        self._build_curve_tab()

    def _build_legend(self, parent: tk.Widget) -> tk.Canvas:
        cv = tk.Canvas(parent, height=26, bg="#f3f4f6", highlightthickness=0)
        items = [
            ("line", COL_OPEN, "流通边"),
            ("dash", COL_BLOCKED, "阻断边"),
            ("dot", COL_NODE, "未浸润节点"),
            ("dot", _lerp_color(COL_WET_FROM, COL_WET_TO, 0.5), "已浸润节点"),
            ("dot", COL_TOP, "顶端水源"),
            ("dot", COL_BOTTOM, "底端出口"),
        ]
        x = 8
        for kind, color, text in items:
            if kind == "line":
                cv.create_line(x, 13, x + 20, 13, fill=color, width=3)
            elif kind == "dash":
                cv.create_line(x, 13, x + 20, 13, fill=color, width=2, dash=(2, 3))
            else:
                cv.create_oval(x + 5, 8, x + 15, 18, fill=color, outline="#0a0e13")
            cv.create_text(x + 25, 13, text=text, anchor="w", fill="#333", font=("Microsoft YaHei", 8))
            x += 25 + len(text) * 12 + 14
        return cv

    def _add_stat_row(self, parent: tk.Widget, row: int, label: str, var: tk.StringVar) -> None:
        ttk.Label(parent, text=label, width=14, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Label(parent, textvariable=var, anchor="w", font=("Consolas", 10)).grid(
            row=row, column=1, sticky="w", pady=3
        )

    def _build_single_tab(self) -> None:
        tab = self.tab_single
        tab.columnconfigure(1, weight=1)
        rows = [
            ("当前概率 p", "p"),
            ("网格规模", "size"),
            ("流通边 / 总边数", "edges"),
            ("是否渗流出水", "pass"),
            ("浸润节点数", "wet"),
            ("渗透层数", "depth"),
            ("判定耗时", "cost"),
        ]
        for i, (label, key) in enumerate(rows):
            self._add_stat_row(tab, i, label, self.vals[key])

        ttk.Separator(tab, orient="horizontal").grid(
            row=len(rows), column=0, columnspan=2, sticky="ew", pady=8
        )
        ttk.Label(
            tab,
            text=(
                "说明：\n"
                "· 顶端整行视为水源，底端整行视为出口；\n"
                "· 只要存在一条由流通边组成的路径把两者连起来，\n"
                "  就认为本次模拟「渗流出水」；\n"
                f"· 二维方格网键渗流的理论阈值 p_c = {THEORETICAL_PC}，\n"
                "  在它附近渗流概率急剧上升 —— 量变引起质变。"
            ),
            justify="left",
            foreground="#555",
            font=("Microsoft YaHei", 9),
        ).grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w")

    def _build_batch_tab(self) -> None:
        tab = self.tab_batch
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        info = ttk.LabelFrame(tab, text="最近一次批量统计", padding=8)
        info.grid(row=0, column=0, sticky="ew")
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

        head = ttk.Frame(tab)
        head.grid(row=1, column=0, sticky="ew", pady=(10, 2))
        ttk.Label(head, text="历史记录", font=("Microsoft YaHei", 9, "bold")).pack(side="left")
        ttk.Button(head, text="清空", width=6, command=self._clear_history).pack(side="right")

        cols = ("p", "n", "trials", "success", "prob", "time")
        self.tree = ttk.Treeview(tab, columns=cols, show="headings", height=10)
        for col, text, width in zip(
            cols,
            ("概率 p", "网格 n", "次数", "成功", "渗流概率", "耗时(s)"),
            (60, 58, 62, 58, 88, 70),
        ):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="center")
        self.tree.grid(row=2, column=0, sticky="nsew")
        self.tree.tag_configure("ok", foreground="#166534")
        self.tree.tag_configure("no", foreground="#9d174d")

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
                justify="left",
                foreground="#a33",
            ).grid(row=0, column=0, sticky="nw", padx=10, pady=10)
            self.figure = None
            self.ax = None
            self.figure_canvas = None
            return

        self.figure = Figure(figsize=(4.3, 3.4), dpi=100, facecolor="#fafafa")
        self.ax = self.figure.add_subplot(111)
        self.figure_canvas = FigureCanvasTkAgg(self.figure, master=tab)
        self.figure_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar = NavigationToolbar2Tk(self.figure_canvas, tab, pack_toolbar=False)
        toolbar.update()
        toolbar.grid(row=1, column=0, sticky="ew")

    # ---------------------------- 状态栏 ----------------------------
    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self.root)
        bar.grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 8))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, textvariable=self.var_status, anchor="w").grid(row=0, column=0, sticky="ew")
        self.progress = ttk.Progressbar(bar, length=240, mode="determinate")
        self.progress.grid(row=0, column=1, padx=(10, 0))

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
                color="#888", fontsize=10,
            )
            ax.set_xticks([])
            ax.set_yticks([])
        else:
            xs = [r.p for r in self._scan_results]
            ys = [r.probability * 100.0 for r in self._scan_results]
            ax.plot(xs, ys, "-o", color="#2f6fed", lw=1.6, ms=3.4, label="实验结果（蒙特卡洛）")
            ax.axvline(
                THEORETICAL_PC, color="#e5533d", ls="--", lw=1.3,
                label=f"理论阈值 p_c = {THEORETICAL_PC}",
            )
            ax.set_xlabel("流通概率 p", fontsize=9)
            ax.set_ylabel("渗流出水概率 P(p)  (%)", fontsize=9)
            ax.set_xlim(0, 1)
            ax.set_ylim(-3, 103)
            ax.grid(alpha=0.25, ls=":")
            ax.tick_params(labelsize=8)
            ax.legend(loc="upper left", fontsize=8)
            size, trials = self._scan_meta
            ax.set_title(f"P(p) 曲线（网格 {size}×{size}，每点 {trials} 次）", fontsize=9)
            if ys and max(ys) >= 100 and min(ys) <= 0:
                ax.annotate(
                    "相变：量变引起质变",
                    xy=(THEORETICAL_PC, 50), xytext=(THEORETICAL_PC + 0.06, 22),
                    fontsize=8, color="#b45309",
                    arrowprops=dict(arrowstyle="->", color="#b45309", lw=1),
                )

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
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    PercolationApp(root, spec=spec)
    root.mainloop()
    return 0


if __name__ == "__main__":
    launch()
