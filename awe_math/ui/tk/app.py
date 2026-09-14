# -*- coding: utf-8 -*-
"""
格子网渗流 · 桌面窗口视图（Tkinter）
====================================

本文件是渗流模型在桌面窗口里的**视图**，由 :class:`awe_math.ui.tk.shell.DesktopShell`
放进窗口中部（窗口顶部是模型下拉框）；渲染与计算共用同一份模型代码
（:mod:`awe_math.models.percolation.model`），网页界面则另有一套 Canvas 实现。

界面构成（与点渗流视图保持一致的结构）
----------------------------------------
* 左侧控制栏：流通概率 p、网格尺寸、面积判据阈值、成功判据、格子类型、方向模式、
  注水方式、动画速度、批量统计与曲线扫描参数、各类按钮。
* 中央画布：绘制全部边与节点（流通边灰白实线、阻断边暗色虚线），并以逐层动画展示水的
  渗透过程（浸润节点按层数着色），**点击节点可指定注水点**。方格网与三角网共用同一套
  绘制逻辑，差别只在于节点的单位坐标与边表。

  配色分工（与点渗流视图一致）：**基底走中性灰，饱和颜色留给判据关注的对象** ——
  纵贯簇用青色（簇内节点与簇内流通边都变青，连成一条贯通路线），
  浸润路径用琥珀→红，注水点蓝色描边、底端出口绿色描边。灰白的流通边与暗色虚线化的
  阻断边只靠明度、虚实与粗细区分，避免跟青色纵贯簇抢眼（原本流通边是青蓝，
  与青绿纵贯簇撞色）。
* 右侧面板（三个标签页）：
  1. 「单次结果」——当前 p、格子与规模、注水点、浸润节点数与比例、结论徽章；
  2. 「批量统计」——成功概率、平均浸润比例与多次实验的历史记录表；
  3. 「P(p) 曲线」——成功概率与平均浸润比例随 p 变化的曲线（含理论阈值 p_c）。

成功判据决定「什么算成功」，也决定界面上的说法：
``span``（贯通）判定整张网格是否存在顶行 ↔ 底行的纵贯簇 —— 这是 ``p_c`` 所对应的
判据；``area``（面积）判定浸润面积是否达到设定比例 —— 没有固定临界值。
两种判据下统计行标题、结论徽章、曲线纵轴与 p_c 参考线都会随之变化。

性能与线程
----------
批量统计与曲线扫描都在后台线程执行，进度通过 ``queue`` 回传主线程刷新界面，
因此界面在数千次模拟期间依然可以响应「停止」；视图被切换或关闭时会置位取消标志。

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
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # 作为包的一部分导入
    from ...models.percolation.model import (
        DEFAULT_THRESHOLD,
        BatchResult,
        PercolationGrid,
        SimResult,
        batch_percolation_probability,
        lattice_layout,
        scan_curve,
    )
    from ...models.percolation.spec import (
        CRITERION_CHOICES,
        DIRECTION_CHOICES,
        INJECT_CHOICES,
        LATTICE_CHOICES,
    )
    from .theme import (
        ACCENT,
        BG,
        BORDER,
        DANGER,
        DIM,
        FAINT,
        FONT_BADGE,
        FONT_BOLD,
        FONT_SM,
        PANEL,
        PANEL_2,
        TEXT,
        WARN,
        ScrollArea,
        install_theme,
        lerp_color,
        make_accent_button,
    )
except ImportError:  # 允许直接运行本文件（把项目根目录加入 import 路径）
    from pathlib import Path

    _ROOT = Path(__file__).resolve().parents[3]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from awe_math.models.percolation.model import (  # type: ignore
        DEFAULT_THRESHOLD,
        BatchResult,
        PercolationGrid,
        SimResult,
        batch_percolation_probability,
        lattice_layout,
        scan_curve,
    )
    from awe_math.models.percolation.spec import (  # type: ignore
        CRITERION_CHOICES,
        DIRECTION_CHOICES,
        INJECT_CHOICES,
        LATTICE_CHOICES,
    )
    from awe_math.ui.tk.theme import (  # type: ignore
        ACCENT, BG, BORDER, DANGER, DIM, FAINT, FONT_BADGE, FONT_BOLD, FONT_SM,
        PANEL, PANEL_2, TEXT, WARN, ScrollArea, install_theme, lerp_color,
        make_accent_button,
    )

# 画布配色
#
# 分工（与点渗流视图一致）：**基底用中性灰、判据关注的对象用青色**。
# 流通边原本是青蓝 #2fa9c9，与纵贯簇的青绿 #2dd4bf 色相相邻、明度也接近，
# 屏幕上分不清「哪些是普通流通边、哪些属于纵贯簇」，所以流通边改成灰白，
# 只靠明度与虚线/粗细区分流通/阻断，把饱和的青色全部让给纵贯簇。
BG_CANVAS = "#0c1118"       # 画布背景
COL_BLOCKED = "#2a333f"     # 阻断边（更暗：与灰白流通边拉开明度差）
COL_OPEN = "#93a1b3"        # 流通边（灰白：不跟青色纵贯簇抢眼）
COL_WET_EDGE = "#ffb703"    # 已被水浸透的流通边
COL_NODE = "#5b6878"        # 未浸润节点
COL_NODE_EDGE = "#0a0e13"   # 节点描边
COL_SPAN_FILL = "#12433c"   # 纵贯簇（顶行 ↔ 底行连通的簇）的填充
COL_SPAN_EDGE = "#2dd4bf"   # 纵贯簇描边（与点渗流视图保持一致）
COL_TOP = "#4dabf7"         # 注水点
COL_BOTTOM = "#51cf66"      # 底端出口
COL_WET_FROM = (255, 222, 118)   # 早层浸润色（黄）
COL_WET_TO = (255, 74, 92)       # 深层浸润色（红）

#: 行数 / 列数上限（画布要画 rows×cols 个节点，太大就卡了）
MAX_SIZE = 80

#: 「面积判据」阈值下拉框候选项
THRESHOLD_CHOICES = ("0.3", "0.5", "0.7", "0.9")


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


def _spec_defaults(spec) -> Dict[str, Any]:
    """从模型元数据里取出参数默认值（没有传入 spec 时用渗流模型的默认值）。"""
    if spec is None:
        return {"p": 0.5, "rows": 30, "cols": 30}
    return {param.key: param.default for param in getattr(spec, "params", ())}


def _pick(mapping: Dict[str, str], value: Any, fallback: str) -> str:
    """界面选项（中文）-> 模型取值；无法识别时回退到 fallback。"""
    return mapping.get(str(value), fallback)


def _label(mapping: Dict[str, str], value: str) -> str:
    """模型取值 -> 界面选项（中文）。"""
    for text, key in mapping.items():
        if key == value:
            return text
    return next(iter(mapping))


def _half_crossing(points: Sequence[Tuple[float, float]]) -> Optional[float]:
    """线性插值求曲线与 50% 的交点（扫描范围内跨不过 50% 时返回 None）。

    这个交点是**有限尺寸 + 网格长宽比**一起决定的结果，和理论 p_c（无限大格子、
    只由格子与方向决定）不是一回事：长宽比一变，它就跟着移动
    （例如方格网无向：20×20 约 0.50、20×60 约 0.45、60×20 约 0.54）。
    """
    for (p1, v1), (p2, v2) in zip(points, points[1:]):
        if v1 != v2 and (v1 - 0.5) * (v2 - 0.5) <= 0:
            return p1 + (p2 - p1) * (0.5 - v1) / (v2 - v1)
    return None


class PercolationApp:
    """渗流模型的可视化视图（由 :class:`DesktopShell` 放入窗口中部）。"""

    #: 顶部标题栏右侧显示的快捷键提示
    HINTS = "空格 播放动画    R 重新生成    点击网格可指定注水点"

    def __init__(self, root: tk.Tk, host: tk.Misc, spec=None) -> None:
        self.root = root
        self.host = host
        self.spec = spec
        defaults = _spec_defaults(spec)
        init_p = float(defaults.get("p", 0.5))
        init_rows = int(defaults.get("rows", 30) or 30)
        init_cols = int(defaults.get("cols", init_rows) or init_rows)
        init_lattice = _pick(LATTICE_CHOICES, defaults.get("lattice"), "square")
        init_direction = _pick(DIRECTION_CHOICES, defaults.get("direction"), "undirected")
        init_inject = _pick(INJECT_CHOICES, defaults.get("inject"), "top")
        init_criterion = _pick(CRITERION_CHOICES, defaults.get("criterion"), "span")
        init_threshold = float(defaults.get("threshold", DEFAULT_THRESHOLD) or DEFAULT_THRESHOLD)

        # ---------------- 模型与状态 ----------------
        self.grid_model = PercolationGrid(
            rows=init_rows, cols=init_cols, p=init_p, rng=random.Random(),
            lattice=init_lattice, direction=init_direction, inject=init_inject,
            criterion=init_criterion, threshold=init_threshold,
        )
        self.result: Optional[SimResult] = None
        self._wet: set = set()               # 当前已显示的浸润节点
        self._shown_layers = 0               # 已显示的渗透层数
        self._anim_job: Optional[str] = None
        self._regenerate_job: Optional[str] = None
        self._redraw_job: Optional[str] = None
        self._alive = True

        # 画布元素索引（用于局部刷新，避免整图重绘）
        self._node_items: List[Optional[int]] = []
        self._edge_items: Dict[Tuple[int, int], int] = {}
        self._node_xy: List[Tuple[float, float]] = []
        self._cell = 10.0
        #: 当前底图对应的 (行数, 列数, 格子, 方向)，用于增量上色时校验
        self._drawn_shape: Tuple[int, int, str, str] = (0, 0, "", "")

        # 后台任务
        self._queue: "queue.Queue" = queue.Queue()
        self._cancel = threading.Event()
        self._busy = False
        self._scan_results: List[BatchResult] = []
        self._scan_meta: Tuple[int, int] = (0, 0)        # 曲线对应的 (行数, 每点次数)
        self._scan_cols = 0                              # 曲线对应的列数
        self._scan_lattice = self.grid_model.lattice     # 曲线对应的格子类型
        self._scan_direction = self.grid_model.direction  # 曲线对应的方向模式
        self._scan_inject = self.grid_model.inject       # 曲线对应的注水方式
        self._scan_criterion = self.grid_model.criterion  # 曲线对应的成功判据
        self._scan_threshold = init_threshold            # 曲线对应的面积判据阈值
        self._scan_pc = self.grid_model.theoretical_pc   # 曲线对应的阈值（可能为 None）

        # ---------------- 界面变量 ----------------
        self.var_p = tk.DoubleVar(value=init_p)
        self.var_rows = tk.IntVar(value=init_rows)
        self.var_cols = tk.IntVar(value=init_cols)
        self.var_speed = tk.IntVar(value=35)
        self.var_threshold = tk.StringVar(value=f"{init_threshold:g}")
        self.var_seed = tk.StringVar(value=str(defaults.get("seed", -1)))
        self.var_trials = tk.StringVar(value=str(defaults.get("trials", "1000")))
        self.var_scan_trials = tk.StringVar(value=str(defaults.get("scanTrials", "200")))
        self.var_scan_step = tk.StringVar(value=str(defaults.get("scanStep", "0.05")))
        self.var_lattice = tk.StringVar(value=_label(LATTICE_CHOICES, init_lattice))
        self.var_direction = tk.StringVar(value=_label(DIRECTION_CHOICES, init_direction))
        self.var_inject = tk.StringVar(value=_label(INJECT_CHOICES, init_inject))
        self.var_criterion = tk.StringVar(
            value=_label(CRITERION_CHOICES, init_criterion)
        )
        self.var_status = tk.StringVar(value="就绪：拖动滑块调整 p，程序会自动重绘网格。")
        #: 统计面板里随判据变化的行标题（key -> Label 控件）
        self._stat_labels: Dict[str, ttk.Label] = {}

        self.vals: Dict[str, tk.StringVar] = {
            "p": tk.StringVar(value="-"),
            "size": tk.StringVar(value="-"),
            "edges": tk.StringVar(value="-"),
            "origins": tk.StringVar(value="-"),
            "wet": tk.StringVar(value="-"),
            "ratio": tk.StringVar(value="-"),
            "spanning": tk.StringVar(value="-"),
            "depth": tk.StringVar(value="-"),
            "cost": tk.StringVar(value="-"),
            "b_p": tk.StringVar(value="-"),
            "b_trials": tk.StringVar(value="-"),
            "b_success": tk.StringVar(value="-"),
            "b_prob": tk.StringVar(value="-"),
            "b_mean": tk.StringVar(value="-"),
            "b_err": tk.StringVar(value="-"),
            "b_time": tk.StringVar(value="-"),
        }

        self._accent_btn = make_accent_button(root, getattr(spec, "accent", ACCENT))
        self._build_ui()
        self._redraw_curve()

        # 定时任务句柄要留着：视图被切换 / 关闭时必须取消，
        # 否则挂起的回调会继续访问已经销毁的画布（TclError）。
        self._poll_job: Optional[str] = self.root.after(80, self._poll_queue)
        self._first_job: Optional[str] = self.root.after(60, self.regenerate_grid)

    # ==================================================================
    # 界面搭建
    # ==================================================================
    def _build_ui(self) -> None:
        self.host.configure(bg=BG)
        self.host.columnconfigure(0, weight=0)   # 左侧控制栏
        self.host.columnconfigure(1, weight=1)   # 中央画布
        self.host.columnconfigure(2, weight=0)   # 右侧数据面板
        self.host.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_center()
        self._build_right()
        self._build_status_bar()
        self._refresh_criterion_texts()   # 按初始判据修正行标题

    # ---------------------------- 左侧控制栏 ----------------------------
    def _build_sidebar(self) -> None:
        # 参数一多，侧边栏就会比窗口还高；此时 pack 会直接不显示装不下的控件
        # （按钮会「凭空消失」），所以用可滚动容器承载。
        area = ScrollArea(self.host, width=306)
        area.outer.grid(row=0, column=0, sticky="ns", padx=(14, 7), pady=12)
        side = area.inner

        self._build_param_card(side)
        self._build_advanced_card(side)
        self._build_action_card(side)
        self._build_batch_card(side)
        self._build_scan_card(side)

        self.btn_stop = ttk.Button(
            side, text="■ 停止后台任务", style="Danger.TButton",
            command=self.stop_work, state="disabled",
        )
        self.btn_stop.pack(fill="x", pady=(2, 0))
        area.bind_wheel()           # 滚轮滚动 + 下拉框弹出列表配色

    @staticmethod
    def _card(parent: tk.Widget, title: str) -> ttk.LabelFrame:
        card = ttk.LabelFrame(
            parent, text=f" {title} ", style="Card.TLabelframe",
            padding=(12, 8, 12, 10),
        )
        card.pack(fill="x", pady=(0, 6))
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
        self.scale_p.pack(fill="x", pady=(4, 8))

        rows_row = ttk.Frame(card, style="Card.TFrame")
        rows_row.pack(fill="x", pady=(0, 6))
        ttk.Label(rows_row, text="行数 n", style="Card.TLabel").pack(side="left")
        spin_rows = ttk.Spinbox(
            rows_row, from_=5, to=MAX_SIZE, width=5,
            textvariable=self.var_rows, command=self._on_shape_change,
        )
        spin_rows.pack(side="right")
        spin_rows.bind("<Return>", lambda _e: self._on_shape_change())
        spin_rows.bind("<FocusOut>", lambda _e: self._on_shape_change())

        cols_row = ttk.Frame(card, style="Card.TFrame")
        cols_row.pack(fill="x", pady=(0, 6))
        ttk.Label(cols_row, text="列数 m", style="Card.TLabel").pack(side="left")
        ttk.Label(cols_row, text="≠ 行数 即矩形", style="CardDim.TLabel",
                  font=FONT_SM).pack(side="left", padx=(6, 0))
        spin_cols = ttk.Spinbox(
            cols_row, from_=5, to=MAX_SIZE, width=5,
            textvariable=self.var_cols, command=self._on_shape_change,
        )
        spin_cols.pack(side="right")
        spin_cols.bind("<Return>", lambda _e: self._on_shape_change())
        spin_cols.bind("<FocusOut>", lambda _e: self._on_shape_change())

        thr_row = ttk.Frame(card, style="Card.TFrame")
        thr_row.pack(fill="x", pady=(0, 6))
        self.lbl_threshold = ttk.Label(
            thr_row, text="面积判据阈值", style="Card.TLabel",
        )
        self.lbl_threshold.pack(side="left")
        threshold = ttk.Combobox(
            thr_row, width=5, state="readonly",
            textvariable=self.var_threshold, values=THRESHOLD_CHOICES,
        )
        threshold.pack(side="right")
        threshold.bind("<<ComboboxSelected>>", lambda _e: self.regenerate_grid())

        seed_row = ttk.Frame(card, style="Card.TFrame")
        seed_row.pack(fill="x", pady=(0, 6))
        ttk.Label(seed_row, text="统计种子（-1 = 随机）", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(
            seed_row, from_=-1, to=2147483647, width=11, textvariable=self.var_seed,
        ).pack(side="right")

        speed_row = ttk.Frame(card, style="Card.TFrame")
        speed_row.pack(fill="x")
        ttk.Label(speed_row, text="动画间隔", style="Card.TLabel").pack(side="left")
        speed = ttk.Scale(speed_row, from_=1, to=200, length=130,
                          command=self._on_speed_change)
        speed.set(self.var_speed.get())
        speed.pack(side="right", pady=(0, 2))

    def _on_speed_change(self, value: str) -> None:
        try:
            self.var_speed.set(max(1, min(200, int(round(float(value))))))
        except (TypeError, ValueError):
            pass

    # ---------------------------- 高级选项 ----------------------------
    @staticmethod
    def _option_row(parent: tk.Misc, title: str, var: tk.StringVar,
                    values: Tuple[str, ...], command) -> None:
        """一行「标题 + 只读下拉框」（中文标签较长，所以下拉框占满整行）。"""
        ttk.Label(parent, text=title, style="Card.TLabel").pack(anchor="w")
        combo = ttk.Combobox(
            parent, state="readonly", textvariable=var, values=values, font=FONT_SM,
        )
        combo.pack(fill="x", pady=(2, 6))
        combo.bind("<<ComboboxSelected>>", lambda _e: command())

    def _build_advanced_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "高级选项")

        # 判据放最前面：它决定「什么算成功」，也就决定 p_c 是否有意义
        self._option_row(card, "成功判据", self.var_criterion,
                         tuple(CRITERION_CHOICES), self._on_criterion_change)
        self._option_row(card, "格子类型", self.var_lattice,
                         tuple(LATTICE_CHOICES), self._on_lattice_change)
        self._option_row(card, "方向模式", self.var_direction,
                         tuple(DIRECTION_CHOICES), self._on_direction_change)
        self._option_row(card, "注水方式", self.var_inject,
                         tuple(INJECT_CHOICES), self._on_inject_change)

        self.lbl_pc = ttk.Label(
            card, text="", style="CardDim.TLabel",
            wraplength=252, justify="left", font=FONT_SM,
        )
        self.lbl_pc.pack(anchor="w")
        self._update_pc_label()

    def _update_pc_label(self) -> None:
        """显示临界值说明：贯通判据给出 p_c，面积判据说明它没有固定阈值。"""
        self.lbl_pc.configure(
            text=self.grid_model.pc_label,
            foreground=WARN if not self.grid_model.pc_applies else DIM,
        )

    def _current_criterion(self) -> str:
        return _pick(CRITERION_CHOICES, self.var_criterion.get(), "span")

    def _current_threshold(self) -> float:
        try:
            value = float(self.var_threshold.get())
        except (TypeError, ValueError):
            value = DEFAULT_THRESHOLD
        return min(1.0, max(0.05, value))

    def _current_seed(self) -> Optional[int]:
        """统计用的随机种子：≥0 时批量统计/曲线完全可复现，-1 表示随机。

        固定种子后，「同一片网格上换判据 / 换注水方式」的横向比较才是严格可比的
        （否则只能看到蒙特卡洛噪声，例如贯通判据本应与注水方式无关）。
        """
        try:
            value = int(float(self.var_seed.get()))
        except (TypeError, ValueError):
            return None
        return None if value < 0 else value

    def _criterion_rule(self) -> str:
        """当前判据的简短说法（界面各处复用）。"""
        if self.grid_model.criterion == "span":
            return "判据 贯通（网格有无纵贯簇）"
        if self.grid_model.criterion == "origin":
            return "判据 起点纵贯（注水点的簇碰顶又碰底）"
        return f"判据 面积 ≥ {self.grid_model.threshold:.0%}"

    def _refresh_criterion_texts(self) -> None:
        """判据变化后，刷新那些「随判据改变含义」的界面文案。"""
        criterion = self.grid_model.criterion
        head = {"span": "存在纵贯簇", "origin": "起点纵贯", "area": "面积达标"}[criterion]
        short = {"span": "贯通", "origin": "起点", "area": "面积"}[criterion]
        self._set_stat_label("b_success", f"{head}次数")
        self._set_stat_label("b_prob", f"{head}概率")
        self.lbl_threshold.configure(
            text="面积判据阈值" if criterion == "area" else "面积判据阈值（面积判据下才生效）",
            foreground=DIM if criterion == "area" else FAINT,
        )
        try:
            self.tree.heading("success", text=short)
        except tk.TclError:      # 视图销毁过程中可能已被回收
            pass

    def _set_stat_label(self, key: str, text: str) -> None:
        label = self._stat_labels.get(key)
        if label is not None:
            label.configure(text=text)

    def _rebuild_after_option_change(self, message: str) -> None:
        """格子 / 方向 / 注水方式变化后：作废旧结果、重建网格并重绘。"""
        self._cancel_animation()
        self._discard_result()
        self.grid_model.regenerate()
        self._update_pc_label()
        self.regenerate_grid()
        self.var_status.set(message)

    def _on_lattice_change(self) -> None:
        """切换格子类型：整张网格的连接关系都变了，必须重建。"""
        lattice = _pick(LATTICE_CHOICES, self.var_lattice.get(), "square")
        if lattice == self.grid_model.lattice:
            return
        self.grid_model.lattice = lattice
        self._rebuild_after_option_change(
            f"已切换为{self.grid_model.lattice_name}：{self.grid_model.pc_label}。"
        )

    def _on_direction_change(self) -> None:
        """切换方向模式：可达关系变了，重建网格并重新判定。"""
        direction = _pick(DIRECTION_CHOICES, self.var_direction.get(), "undirected")
        if direction == self.grid_model.direction:
            return
        self.grid_model.direction = direction
        self._rebuild_after_option_change(
            f"已切换为「{self.grid_model.direction_name}」：{self.grid_model.pc_label}。"
        )

    def _on_inject_change(self) -> None:
        """切换注水方式：网格不变，只需重新挑注水点并重绘。"""
        inject = _pick(INJECT_CHOICES, self.var_inject.get(), "top")
        if inject == self.grid_model.inject:
            return
        self.grid_model.inject = inject
        if self.grid_model.criterion == "span":
            message = (f"注水方式：{self.grid_model.inject_name}。"
                       "贯通判据只看整张网格有没有纵贯簇，与注水位置无关 —— "
                       "它只影响单次动画的起点。")
        elif self.grid_model.criterion == "origin":
            message = (f"注水方式：{self.grid_model.inject_name}。"
                       "起点判据下注水位置影响很大 —— 顶端整行一定在纵贯簇上，"
                       "随机/中心单点则可能落在簇外（只浸透一小片）。")
        else:
            message = (f"注水方式：{self.grid_model.inject_name}。"
                       "面积判据下起始位置影响很大：单点注水额外要求「起点落在巨簇里」，"
                       "所以曲线整体比顶端整行注水更平缓。")
        self._rebuild_after_option_change(message)

    def _on_criterion_change(self) -> None:
        """切换成功判据：网格不用重建，但结论、统计与曲线的含义都变了。"""
        criterion = self._current_criterion()
        if criterion == self.grid_model.criterion:
            return
        self._cancel_animation()
        self._discard_result()
        self.grid_model.criterion = criterion
        self._refresh_criterion_texts()
        self._update_pc_label()
        self.regenerate_grid()
        if criterion == "span":
            self.var_status.set(
                "已切换为「贯通判据」：判定**整张网格**上是否存在顶行↔底行的纵贯簇"
                "（青色节点）。它的成功概率 = 1/2 交点就是临界值 p_c"
                "（方格网无向 = 1/2），且与注水方式无关。"
            )
        elif criterion == "origin":
            self.var_status.set(
                "已切换为「起点判据」：判定**从注水点出发的那一簇**是否纵贯（碰到顶行"
                "与底行）。它与贯通判据的差别是「还要求注水点落在纵贯簇里」，"
                "所以交点高于 p_c —— 随机注水常常落在簇外。"
            )
        else:
            self.var_status.set(
                "已切换为「面积判据」：判定浸润面积是否达到设定比例。"
                "注意它没有固定的临界值 —— 交点随比例、网格尺寸、注水方式一起变，"
                "不要把它当成 p_c。"
            )

    def _build_action_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "操作")
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        self.btn_anim = ttk.Button(
            card, text="▶ 播放动画", style=self._accent_btn,
            command=self.start_animation,
        )
        self.btn_anim.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self.btn_regen = ttk.Button(card, text="↻ 重新生成", command=self.regenerate_grid)
        self.btn_instant = ttk.Button(card, text="⤓ 直接看结果", command=self.show_result_instant)
        self.btn_regen.grid(row=1, column=0, sticky="ew", padx=(0, 4))
        self.btn_instant.grid(row=1, column=1, sticky="ew", padx=(4, 0))

    def _build_batch_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "批量统计")

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="实验次数 N", style="Card.TLabel").pack(side="left")
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
        row1.pack(fill="x", pady=(0, 6))
        ttk.Label(row1, text="曲线每点次数", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(
            row1, from_=20, to=5000, increment=20, width=7,
            textvariable=self.var_scan_trials,
        ).pack(side="right")

        row2 = ttk.Frame(card, style="Card.TFrame")
        row2.pack(fill="x", pady=(0, 6))
        ttk.Label(row2, text="p 扫描步进", style="Card.TLabel").pack(side="left")
        ttk.Combobox(
            row2, width=6, textvariable=self.var_scan_step,
            values=("0.02", "0.05", "0.1"),
        ).pack(side="right")

        self.btn_scan = ttk.Button(card, text="▶ 绘制曲线", command=self.start_scan)
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
        center = ttk.Frame(self.host, style="Side.TFrame")
        center.grid(row=0, column=1, sticky="nsew", pady=12)
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            center, bg=BG_CANVAS, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        self._build_legend(center).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _build_legend(self, parent: tk.Widget) -> tk.Canvas:
        cv = tk.Canvas(
            parent, height=30, bg=PANEL, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,
        )
        items = [
            ("line", COL_OPEN, "流通边"),
            ("dash", COL_BLOCKED, "阻断边"),
            ("dot", COL_SPAN_FILL, "纵贯簇"),
            ("dot", COL_NODE, "未浸润节点"),
            ("dot", lerp_color(COL_WET_FROM, COL_WET_TO, 0.5), "已浸润节点"),
            ("dot", COL_TOP, "注水点"),
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
        self.notebook = ttk.Notebook(self.host, width=412)
        self.notebook.grid(row=0, column=2, sticky="nsew", padx=(7, 14), pady=12)

        self.tab_single = ttk.Frame(self.notebook, style="Panel.TFrame", padding=12)
        self.tab_batch = ttk.Frame(self.notebook, style="Panel.TFrame", padding=12)
        self.tab_curve = ttk.Frame(self.notebook, style="Panel.TFrame", padding=8)
        self.notebook.add(self.tab_single, text=" 单次结果 ")
        self.notebook.add(self.tab_batch, text=" 批量统计 ")
        self.notebook.add(self.tab_curve, text=" P(p) 曲线 ")

        self._build_single_tab()
        self._build_batch_tab()
        self._build_curve_tab()

    def _add_stat_row(self, parent: tk.Widget, row: int, label: str, var: tk.StringVar,
                      key: Optional[str] = None) -> None:
        lbl = ttk.Label(parent, text=label, style="CardDim.TLabel", width=14, anchor="w")
        lbl.grid(row=row, column=0, sticky="w", pady=4)
        if key is not None:
            self._stat_labels[key] = lbl
        ttk.Label(parent, textvariable=var, style="Mono.TLabel", anchor="w").grid(
            row=row, column=1, sticky="w", pady=4
        )

    def _build_single_tab(self) -> None:
        tab = self.tab_single
        tab.columnconfigure(1, weight=1)

        self.badge = tk.Label(
            tab, text="— 等待计算 —", bg=PANEL_2, fg=FAINT,
            font=FONT_BADGE, pady=12,
        )
        self.badge.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))

        rows = [
            ("流通概率 p", "p"),
            ("格子 / 规模", "size"),
            ("流通边 / 总边数", "edges"),
            ("注水点", "origins"),
            ("浸润节点数", "wet"),
            ("浸润比例", "ratio"),
            ("纵贯簇", "spanning"),
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
                "· 每条边以概率 p 独立地流通或阻断，水从注水点沿流通边蔓延；\n"
                "· 青色节点是**纵贯簇**：同时连通顶行与底行的那一串节点。三种判据：\n"
                "  · 贯通判据 = 网格上有没有纵贯簇 —— p_c 说的就是这个相变\n"
                "    （方格网 0.5、三角网 ≈ 0.3473、有向 ≈ 0.6447），与注水方式无关；\n"
                "  · 起点判据 = 你这次注水的那一簇是否纵贯 —— 随机/中心注水经常\n"
                "    落在簇外，所以交点高于 p_c（顶端整行注水时两者相同）；\n"
                "  · 面积判据 = 浸润面积达到设定比例 —— 没有固定临界值，交点随\n"
                "    比例、网格尺寸、注水方式一起漂移；\n"
                "· 只有贯通判据的 1/2 交点等于 p_c；点击节点可指定注水点。"
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
            ("统计所用 p", "b_p"),
            ("实验次数 N", "b_trials"),
            ("成功次数", "b_success"),
            ("成功概率", "b_prob"),
            ("平均浸润比例", "b_mean"),
            ("标准误", "b_err"),
            ("总耗时", "b_time"),
        ]
        for i, (label, key) in enumerate(rows):
            self._add_stat_row(info, i, label, self.vals[key], key=key)

        head = ttk.Frame(tab, style="Panel.TFrame")
        head.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        ttk.Label(head, text="历史记录", style="Card.TLabel", font=FONT_BOLD).pack(side="left")
        ttk.Button(head, text="清空", width=6, command=self._clear_history).pack(side="right")

        cols = ("p", "shape", "trials", "success", "prob", "mean", "time")
        self.tree = ttk.Treeview(tab, columns=cols, show="headings", height=10)
        for col, text, width in zip(
            cols,
            ("概率 p", "形状", "次数", "成功", "成功概率", "平均比例", "耗时(s)"),
            (46, 62, 46, 46, 52, 66, 50),
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
        # 与点渗流视图保持一致：状态栏挂在宿主容器的第 1 行（画布下方）
        bar = ttk.Frame(self.host)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=16, pady=(2, 10))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, textvariable=self.var_status, style="Dim.TLabel", anchor="w").grid(
            row=0, column=0, sticky="ew"
        )
        self.progress = ttk.Progressbar(bar, length=260, mode="determinate")
        self.progress.grid(row=0, column=1, padx=(12, 0))

    # ==================================================================
    # 参数与事件
    # ==================================================================
    def _current_shape(self) -> Tuple[int, int]:
        """界面上的行数 / 列数（越界或非法时回退到模型当前值）。"""
        try:
            rows = int(self.var_rows.get())
        except (tk.TclError, ValueError):
            rows = self.grid_model.rows
        try:
            cols = int(self.var_cols.get())
        except (tk.TclError, ValueError):
            cols = self.grid_model.cols
        return max(2, min(MAX_SIZE, rows)), max(2, min(MAX_SIZE, cols))

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

    def _on_shape_change(self) -> None:
        rows, cols = self._current_shape()
        if (rows, cols) != (self.grid_model.rows, self.grid_model.cols):
            # 尺寸变化会重建边数组，旧尺寸的动画结果必须立即作废，否则渲染会越界
            self._cancel_animation()
            self._discard_result()
            self.grid_model.rows, self.grid_model.cols = rows, cols
            self.grid_model.regenerate()
        self._debounce_regenerate(delay=60)

    def _discard_result(self) -> None:
        """丢弃当前结果（网格尺寸/模式变化后调用）。"""
        self.result = None
        self._shown_layers = 0
        self._wet = set()

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

        滑块 / 下拉框改动会做防抖（延迟重绘），用户可能在防抖触发前就点了按钮，
        因此每次操作前都强制同步一次 p、行列数、格子类型、方向模式与注水方式。
        """
        p = round(self.var_p.get(), 2)
        rows, cols = self._current_shape()
        lattice = _pick(LATTICE_CHOICES, self.var_lattice.get(), "square")
        direction = _pick(DIRECTION_CHOICES, self.var_direction.get(), "undirected")
        inject = _pick(INJECT_CHOICES, self.var_inject.get(), "top")
        # 判据与阈值都不改变网格结构，直接同步即可
        criterion = self._current_criterion()
        if criterion != self.grid_model.criterion:
            self._discard_result()
        self.grid_model.criterion = criterion
        self.grid_model.threshold = self._current_threshold()

        structural = (
            lattice != self.grid_model.lattice
            or direction != self.grid_model.direction
            or (rows, cols) != (self.grid_model.rows, self.grid_model.cols)
        )
        if structural or inject != self.grid_model.inject:
            self._cancel_animation()
            self._discard_result()
            self.grid_model.rows, self.grid_model.cols = rows, cols
            self.grid_model.lattice = lattice
            self.grid_model.direction = direction
            self.grid_model.inject = inject
            self.grid_model.regenerate(p)      # 结构 / 注水点变了必须重建网格
            if structural:
                self._update_pc_label()
        else:
            self.grid_model.p = p

    # ==================================================================
    # 网格生成与绘制
    # ==================================================================
    def _canvas_ready(self) -> bool:
        """画布是否仍然可用（视图被销毁后，挂起的回调不应继续画图）。"""
        return self._alive and bool(self.canvas.winfo_exists())

    def regenerate_grid(self) -> None:
        """重新随机生成网格，并立即显示出水/不出水的结果（不做动画）。"""
        self._regenerate_job = None
        if not self._canvas_ready():
            return
        self._cancel_animation()
        self._sync_model_params()
        self.grid_model.regenerate()
        self._simulate_and_show()
        model = self.grid_model
        self.var_status.set(
            f"已重新生成网格：{model.lattice_name} {model.rows}×{model.cols}"
            f"（{model.direction_name}），p={model.p:.2f}。按空格可播放渗透动画。"
        )

    def _simulate_and_show(self, origins: Optional[Sequence[int]] = None) -> None:
        """重新计算一次渗透过程并刷新画布与指标。"""
        self.result = self.grid_model.simulate(origins)
        self._shown_layers = len(self.result.layers)
        self._wet = set(self.result.wet)
        self._redraw_grid()
        self._update_result_labels()

    def _layout_params(self) -> Tuple[float, float, float]:
        """计算画布下每个节点的屏幕坐标，返回 (节点间距, 左上偏移x, 左上偏移y)。

        方格网 / 三角网、方形 / 矩形网格共用同一套缩放逻辑，区别只在单位坐标：
        三角网的奇数行右移半格、行距 √3/2，恰好铺成等边三角形。
        """
        model = self.grid_model
        width = max(self.canvas.winfo_width(), 60)
        height = max(self.canvas.winfo_height(), 60)
        pad = 24
        units = lattice_layout(model.rows, model.cols, model.lattice)
        span_x = max(u[0] for u in units) or 1.0
        span_y = max(u[1] for u in units) or 1.0
        cell = min(max(width - 2 * pad, 10) / span_x, max(height - 2 * pad, 10) / span_y)
        ox = (width - cell * span_x) / 2.0
        oy = (height - cell * span_y) / 2.0
        self._node_xy = [(ox + ux * cell, oy + uy * cell) for ux, uy in units]
        return cell, ox, oy

    def _draw_base(self) -> None:
        """绘制底层网格：所有边 + 所有节点（不含量变信息）。"""
        cv = self.canvas
        cv.delete("all")
        model = self.grid_model
        cell, _ox, _oy = self._layout_params()
        self._cell = cell
        # 记录底图对应的形状 / 格子 / 方向，供增量上色时校验
        self._drawn_shape = (model.rows, model.cols, model.lattice, model.direction)

        radius = max(1.2, min(5.0, cell * 0.17))
        lw_open = max(1.0, min(2.8, cell * 0.16))
        lw_block = max(0.6, min(1.5, cell * 0.08))

        xy = self._node_xy
        self._node_items = [None] * model.node_count
        #: 边 -> 画布元素；键是 (较小的节点索引, 较大的节点索引)
        self._edge_items = {}
        # 纵贯簇单独上色：判据问的就是「有没有这么一串节点纵贯顶底」，
        # 不画出来的话，「判定贯通 + 浸润面积很小」会显得莫名其妙
        spanning = set(model.spanning_nodes())

        for a, b in model.iter_all_edges():
            x1, y1 = xy[a]
            x2, y2 = xy[b]
            if model.is_open(a, b):
                # 纵贯簇内部的流通边跟着簇一起变青：整条贯通路线连成一条青色路径
                color = (COL_SPAN_EDGE if (a in spanning and b in spanning)
                         else COL_OPEN)
                item = cv.create_line(x1, y1, x2, y2, fill=color, width=lw_open)
            else:
                item = cv.create_line(x1, y1, x2, y2, fill=COL_BLOCKED,
                                      width=lw_block, dash=(2, 3))
            self._edge_items[(a, b)] = item

        # 注水点优先取「本次实际使用」的（点击网格指定后与 inject 的默认选择不同）；
        # 形状不一致时说明结果属于上一张网格，退回按注水方式现算
        if (self.result is not None and self.result.origins
                and self.result.shape == model.shape):
            sources = set(self.result.origins)
        else:
            sources = set(model.source_nodes())
        last_row_start = (model.rows - 1) * model.cols
        for idx, (x, y) in enumerate(xy):
            # 描边表达「角色」（注水点蓝、底端出口绿），填充表达「是否在纵贯簇里」，
            # 两者叠加正好说明「这个簇是否既碰顶又碰底」
            if idx in sources:
                outline, ow = COL_TOP, 1.6
            elif idx >= last_row_start:
                outline, ow = COL_BOTTOM, 1.6
            elif idx in spanning:
                outline, ow = COL_SPAN_EDGE, 1.2
            else:
                outline, ow = COL_NODE_EDGE, 1
            fill = COL_SPAN_FILL if idx in spanning else COL_NODE
            self._node_items[idx] = cv.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill=fill, outline=outline, width=ow,
            )

        # 当前配置 / 出口提示
        cv.create_text(10, 8, anchor="nw",
                       fill=COL_TOP, font=FONT_SM,
                       text=f"▼ {model.direction_name} · {model.inject_name} · "
                            f"{self._criterion_rule()}（蓝色描边为注水点）")
        cv.create_text(10, int(cv.winfo_height()) - 8, anchor="sw",
                       text="▲ 底端出口（水从这里流出）；点击节点可指定注水点",
                       fill=COL_BOTTOM, font=FONT_SM)

    def _apply_wet(self, nodes: Sequence[int], color: str) -> None:
        """把一批节点标记为已浸润，并高亮它与已浸润邻居之间的流通边。

        注意：节点索引必须与当前底图一致（形状 / 格子 / 方向变了就画不出来），
        因此这里先校验 ``_drawn_shape``。
        """
        cv = self.canvas
        model = self.grid_model
        if self._drawn_shape != (model.rows, model.cols, model.lattice, model.direction):
            return
        node_items = self._node_items
        edges = self._edge_items
        lw = max(2.0, min(4.2, self._cell * 0.26))

        for idx in nodes:
            item = node_items[idx]
            if item is not None:
                cv.itemconfigure(item, fill=color)
            # 找已经浸润的邻居给这条边染色。必须用 traversable_neighbors 而不是
            # neighbors：后者只给「出边」，有向模式下从后来浸润的节点看前一个节点是
            # 「逆方向」的，那条边就漏色了（三角网 + 方向限制时最明显）。
            for nb in self.grid_model.traversable_neighbors(idx):
                if nb not in self._wet:
                    continue
                it = edges.get((idx, nb) if idx < nb else (nb, idx))
                if it is not None:
                    cv.itemconfigure(it, fill=COL_WET_EDGE, width=lw, dash=())

    def _layer_color(self, layer_index: int, total_layers: int) -> str:
        """按渗透层数做颜色渐变：越晚到达的节点越红。"""
        if total_layers <= 1:
            t = 0.0
        else:
            t = layer_index / (total_layers - 1)
        return lerp_color(COL_WET_FROM, COL_WET_TO, t)

    def _redraw_grid(self) -> None:
        """整图重绘：底图 + 当前已显示的浸润层。"""
        self._redraw_job = None
        if not self._canvas_ready():
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width <= 40 or height <= 40:   # 布局尚未完成，等待 Configure 事件
            return

        self._draw_base()
        self._wet = set()
        # 结果必须与底图一致，否则只画底图（防止切换尺寸/方向瞬间的越界渲染）
        if (
            self.result is None
            or self._shown_layers <= 0
            or self.result.shape != self.grid_model.shape
        ):
            self._hide_verdict()
            return

        layers = self.result.layers
        total = len(layers)
        for i in range(min(self._shown_layers, total)):
            batch = layers[i]
            self._wet.update(batch)
            self._apply_wet(batch, self._layer_color(i, total))

        if self._shown_layers >= total:
            self._show_verdict()

    def _show_verdict(self) -> None:
        """画布底部显示结论（按当前判据给出不同的说法）。"""
        if self.result is None:
            return
        res = self.result
        if res.criterion == "span":
            ok = res.spans
            text = ("✔ 网格存在纵贯簇（顶行 ↔ 底行）"
                    if ok else "✘ 网格没有纵贯簇")
            text += f"；本次注水浸润 {res.wet_ratio:.1%}"
        elif res.criterion == "origin":
            ok = res.origin_spans
            if ok:
                text = (f"✔ 起点纵贯：注水的这一簇碰到顶行与底行"
                        f"（浸润 {res.wet_ratio:.1%}）")
            elif res.spans:
                text = (f"✘ 起点未纵贯：网格有纵贯簇（{res.spanning_count} 节点，青色），"
                        f"但注水点不在簇内（浸润 {res.wet_ratio:.1%}）")
            else:
                text = (f"✘ 起点未纵贯，网格也没有纵贯簇"
                        f"（浸润 {res.wet_ratio:.1%}）")
        else:
            ok = res.engulfed
            text = (f"✔ 面积判据达标：浸润 {res.wet_ratio:.1%}（≥{res.threshold:.0%}）"
                    if ok else
                    f"✘ 面积未达标：浸润 {res.wet_ratio:.1%}（<{res.threshold:.0%}）")
        self.canvas.delete("verdict")
        self.canvas.create_text(
            self.canvas.winfo_width() // 2, self.canvas.winfo_height() - 8,
            anchor="s", text=text, fill="#4ade80" if ok else "#fb7185",
            font=FONT_BOLD, tags="verdict",
        )

    def _hide_verdict(self) -> None:
        self.canvas.delete("verdict")

    # ==================================================================
    # 动画
    # ==================================================================
    def start_animation(self, origins: Optional[Sequence[int]] = None) -> None:
        """播放水渗透的逐层动画（origins 省略时按注水方式自动挑选注水点）。

        不重新生成网格：按空格是「重播当前这次渗透」，想换一张网格请点「重新生成」；
        点击画布上的节点则从那个节点开始注水。
        """
        if self._busy:
            return
        self._cancel_animation()
        self._sync_model_params()
        self.result = self.grid_model.simulate(origins)
        self._shown_layers = 0
        self._wet = set()
        self._draw_base()
        self._hide_verdict()
        self._update_result_labels()
        model = self.grid_model
        self.var_status.set(
            f"正在演示渗透过程：{model.lattice_name} {model.rows}×{model.cols}，"
            f"p={model.p:.2f}，{model.direction_name} · {model.inject_name}。"
        )
        self._step_animation()

    def _step_animation(self) -> None:
        self._anim_job = None
        if self.result is None:
            return
        if self._drawn_shape[:2] != self.result.shape:
            # 底图已被其它形状重建，当前动画结果作废
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
        if self.result is not None:
            self.var_status.set(
                f"动画结束：{self._verdict_phrase(self.result)}"
                f"（本次注水浸润 {self.result.wet_ratio:.1%}）。"
                "可点击「开始批量统计」考察该 p 值下的成功概率。"
            )

    def _cancel_animation(self) -> None:
        if self._anim_job is not None:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None

    def show_result_instant(self) -> None:
        """跳过动画，直接显示最终浸润结果。"""
        self._cancel_animation()
        self._sync_model_params()
        self._simulate_and_show()
        if self.result is None:
            return
        self.var_status.set(
            f"单次结果：{self._verdict_phrase(self.result)}，浸润 "
            f"{self.result.wet_count}/{self.result.node_count}"
            f"（{self.result.wet_ratio:.1%}）。"
        )

    def _on_canvas_click(self, event) -> None:
        """点击画布：把最近的节点设为注水点并播放动画。"""
        if not self._node_xy or len(self._node_xy) != self.grid_model.node_count:
            return
        best, best_dist = -1, float("inf")
        for idx, (x, y) in enumerate(self._node_xy):
            dist = (x - event.x) ** 2 + (y - event.y) ** 2
            if dist < best_dist:
                best, best_dist = idx, dist
        if best >= 0:
            self.start_animation(origins=[best])

    # ==================================================================
    # 指标刷新
    # ==================================================================
    def _update_result_labels(self) -> None:
        model = self.grid_model
        res = self.result
        self.vals["p"].set(f"{model.p:.2f}")
        self.vals["size"].set(
            f"{model.lattice_name} {model.rows}×{model.cols}"
            f"（{model.node_count} 节点，{model.inject_name}）"
        )
        if res is None:
            self.vals["edges"].set(f"- / {model.total_edge_count()}")
            for key in ("origins", "wet", "ratio", "depth", "cost"):
                self.vals[key].set("-")
        else:
            self.vals["edges"].set(
                f"{res.open_edge_count} / {res.total_edge_count}（实测比例 {res.open_ratio:.3f}）"
            )
            self.vals["origins"].set(
                f"{len(res.origins)} 个（{model.inject_name}）" if res.origins else "-"
            )
            wet_ratio = len(self._wet) / res.node_count if res.node_count else 0.0
            self.vals["wet"].set(
                f"{len(self._wet)} / {res.node_count}（{wet_ratio:.1%}）"
            )
            shown = min(self._shown_layers, len(res.layers))
            self.vals["ratio"].set(f"{wet_ratio:.1%}（动画 {shown}/{len(res.layers)} 层）")
            self.vals["depth"].set(f"{shown} / {len(res.layers)} 层")
            self.vals["cost"].set(f"{res.elapsed * 1000:.1f} ms")

        # 纵贯簇是网格本身的性质（与注水点无关），没有模拟结果时也显示
        nodes = self.grid_model.spanning_nodes()
        if nodes:
            total = self.grid_model.node_count
            value = f"{len(nodes)} 节点（{len(nodes) / total:.1%}）" if total else f"{len(nodes)} 节点"
            if res is not None:
                value += "·水在簇内" if res.origin_in_spanning else "·水在簇外"
        else:
            value = "无"
        self.vals["spanning"].set(value)

        # 顶部的结论徽章（随判据变化）
        if res is None:
            self.badge.configure(text="— 等待计算 —", bg=PANEL_2, fg=FAINT)
        elif self._shown_layers < len(res.layers):
            self.badge.configure(text="渗透中 …", bg=PANEL_2, fg=WARN)
        elif res.criterion == "span":
            # 贯通判据：结论看整张网格有没有纵贯簇，浸润面积只是附带信息
            if res.spans:
                self.badge.configure(
                    text=f"✔ 存在纵贯簇（{res.spanning_count} 节点，浸润 {res.wet_ratio:.1%}）",
                    bg="#2b2340", fg="#c4b5fd",
                )
            else:
                self.badge.configure(
                    text=f"✘ 没有纵贯簇（浸润 {res.wet_ratio:.1%}）",
                    bg="#131c28", fg="#93c5fd",
                )
        elif res.criterion == "origin":
            # 起点判据：最容易困惑的一档 —— 网格有纵贯簇，但注水点在簇外
            if res.origin_spans:
                self.badge.configure(
                    text=f"✔ 起点纵贯（浸润 {res.wet_ratio:.1%}）",
                    bg="#2b2340", fg="#c4b5fd",
                )
            elif res.spans:
                self.badge.configure(
                    text=f"✘ 起点在纵贯簇外（簇 {res.spanning_count} 节点）",
                    bg="#131c28", fg="#93c5fd",
                )
            else:
                self.badge.configure(
                    text=f"✘ 起点未纵贯（浸润 {res.wet_ratio:.1%}）",
                    bg="#131c28", fg="#93c5fd",
                )
        elif res.engulfed:
            self.badge.configure(
                text=f"✔ 面积达标 {res.wet_ratio:.1%}（≥{res.threshold:.0%}）",
                bg="#2b2340", fg="#c4b5fd",
            )
        else:
            self.badge.configure(
                text=f"✘ 面积不足 {res.wet_ratio:.1%}（<{res.threshold:.0%}）",
                bg="#131c28", fg="#93c5fd",
            )

    def _result_summary(self) -> str:
        """当前配置的简短描述，用于状态栏与结论行。"""
        model = self.grid_model
        return (f"{model.lattice_name} {model.rows}×{model.cols} · "
                f"{model.direction_name} · 注水 {model.inject_name} · "
                f"{self._criterion_rule()}")

    @staticmethod
    def _verdict_phrase(res: SimResult) -> str:
        """把一次模拟的结果说成一句话（随判据变化）。"""
        if res.criterion == "span":
            return "网格存在纵贯簇" if res.spans else "网格没有纵贯簇"
        if res.criterion == "origin":
            if res.origin_spans:
                return "起点纵贯（注水的这一簇碰顶又碰底）"
            if res.spans:
                return "起点未纵贯（网格有纵贯簇，但注水点在簇外）"
            return "起点未纵贯，网格也没有纵贯簇"
        return "面积判据达标" if res.engulfed else "面积判据未达标"

    def _insert_history(self, res: BatchResult, tag: str) -> None:
        self.tree.insert(
            "", 0,
            values=(
                f"{res.p:.2f}",
                f"{res.rows}×{res.cols}",
                res.trials,
                res.success,
                f"{res.probability:.4f}",
                f"{res.mean_ratio:.3f}",
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

    def _batch_options(self) -> Dict[str, Any]:
        model = self.grid_model
        return {
            "lattice": model.lattice,
            "direction": model.direction,
            "inject": model.inject,
            "criterion": model.criterion,
            "threshold": model.threshold,
        }

    def start_batch_statistics(self) -> None:
        """对当前 p 值做 N 次独立模拟，统计当前判据下的成功频率。"""
        if self._busy:
            return
        # 先把界面上的形状 / 格子 / 方向 / 注水 / 判据 / 阈值全部同步进模型，
        # 保证「统计的就是屏幕上看到的这一套设置」——不能依赖下拉框回调是否已经跑过
        self._sync_model_params()
        rows, cols = self._current_shape()
        p = round(self.var_p.get(), 2)
        model = self.grid_model
        trials = self._parse_int(self.var_trials.get(), 1000)
        seed = self._current_seed()
        options = self._batch_options()
        self._cancel.clear()
        self.progress.configure(maximum=trials, value=0)
        self._set_busy(
            True,
            f"正在统计：{model.lattice_name} {rows}×{cols}，"
            f"{self._result_summary()}，p={p:.2f}，共 {trials} 次独立模拟"
            + (f"（种子 {seed}）" if seed is not None else "") + "…",
        )

        def job() -> None:
            try:
                res = batch_percolation_probability(
                    rows=rows, cols=cols, p=p, trials=trials, rng=seed, **options,
                    progress=lambda done, total, success: self._queue.put(("progress", (done, total))),
                    cancel=self._cancel,
                )
                self._queue.put(("batch_done", res))
            except Exception as exc:  # pragma: no cover
                self._queue.put(("error", f"批量统计失败：{exc}"))

        threading.Thread(target=job, daemon=True).start()

    def start_scan(self) -> None:
        """扫描 p ∈ [0, 1]，绘制当前判据下的成功概率与平均浸润比例曲线。"""
        if self._busy:
            return
        # 同批量统计：先同步界面设置，曲线必须反映当前的形状 / 格子 / 方向 / 注水 / 判据
        self._sync_model_params()
        rows, cols = self._current_shape()
        trials = self._parse_int(self.var_scan_trials.get(), 200, low=10)
        step = self._parse_float(self.var_scan_step.get(), 0.05, low=0.01, high=0.5)
        p_values = [round(i * step, 2) for i in range(int(round(1.0 / step)) + 1)]
        p_values = [p for p in p_values if p <= 1.0]

        model = self.grid_model
        seed = self._current_seed()
        options = self._batch_options()
        self._cancel.clear()
        self._scan_results = []
        self._scan_meta = (rows, trials)
        self._scan_cols = cols
        self._scan_lattice = model.lattice
        self._scan_direction = model.direction
        self._scan_inject = model.inject
        self._scan_criterion = model.criterion
        self._scan_threshold = model.threshold
        self._scan_pc = model.theoretical_pc
        self.progress.configure(maximum=len(p_values), value=0)
        self.notebook.select(self.tab_curve)
        self._set_busy(
            True,
            f"正在扫描 p（共 {len(p_values)} 个点，每点 {trials} 次，"
            f"{self._result_summary()}"
            + (f"，种子 {seed}" if seed is not None else "") + "）…",
        )

        def job() -> None:
            try:
                scan_curve(
                    p_values, rows=rows, cols=cols, trials=trials, rng=seed, **options,
                    progress=lambda done, total, res: self._queue.put(("scan_point", (done, total, res))),
                    cancel=self._cancel,
                )
                self._queue.put(("scan_done", None))
            except Exception as exc:  # pragma: no cover
                self._queue.put(("error", f"曲线扫描失败：{exc}"))

        threading.Thread(target=job, daemon=True).start()

    def _poll_queue(self) -> None:
        """主线程定时取出后台线程的消息（视图关闭后自动停止）。"""
        if not self._alive:
            return
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
            self.var_status.set(f"正在统计：{done}/{total} 次实验…")

        elif kind == "batch_done":
            res: BatchResult = payload
            self._set_busy(False)
            self.progress.configure(value=self.progress.cget("maximum"))
            self.vals["b_p"].set(f"{res.p:.2f}")
            self.vals["b_trials"].set(f"{res.trials}")
            self.vals["b_success"].set(f"{res.success}")
            self.vals["b_prob"].set(f"{res.probability:.4f}（{res.probability:.2%}）")
            self.vals["b_mean"].set(f"{res.mean_ratio:.1%}")
            self.vals["b_err"].set(f"±{res.stderr:.4f}")
            self.vals["b_time"].set(f"{res.elapsed:.2f} s")
            self._insert_history(res, "ok" if res.probability >= 0.5 else "no")
            self.notebook.select(self.tab_batch)
            if res.criterion == "span":
                pc = self.grid_model.theoretical_pc
                tail = ("贯通判据下，成功概率 ≈ 1/2 的位置就是临界值 p_c"
                        + (f" = {pc:.4f}。" if pc is not None else "（该组合暂无已知值）。"))
            elif res.criterion == "origin":
                tail = ("起点判据下，1/2 交点高于 p_c —— 它还额外要求"
                        "「注水点落在纵贯簇里」；注水方式选「顶端整行」时才等于 p_c。")
            else:
                tail = ("面积判据下这个概率随所设比例变化，其 1/2 交点不是 p_c"
                        "（想量 p_c 请把判据切到「贯通判据」）。")
            self.var_status.set(
                f"统计完成：{self._result_summary()}，p={res.p:.2f} 时"
                f"「{res.criterion_name}」的成功概率 ≈ {res.probability:.4f}"
                f"（{res.success}/{res.trials}），平均浸润 {res.mean_ratio:.1%}，"
                f"耗时 {res.elapsed:.2f} s。{tail}"
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
                f"每点 {self._scan_meta[1]} 次实验。"
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
        if not HAS_MPL or self.ax is None or self.figure_canvas is None:
            return
        ax = self.ax
        ax.clear()

        if not self._scan_results:
            ax.text(
                0.5, 0.5,
                "点击左侧「绘制曲线」开始扫描",
                transform=ax.transAxes, ha="center", va="center",
                color=FAINT, fontsize=10,
            )
            ax.set_xticks([])
            ax.set_yticks([])
        else:
            xs = [r.p for r in self._scan_results]
            prob = [r.probability * 100.0 for r in self._scan_results]
            ratio = [r.mean_ratio * 100.0 for r in self._scan_results]
            span = self._scan_criterion == "span"
            ax.plot(
                xs, prob, "-o", color=ACCENT, lw=1.8, ms=3.4,
                mfc=BG_CANVAS, mec=TEXT, mew=0.8,
                label="成功概率 (%)",
            )
            ax.plot(
                xs, ratio, "--", color="#7dd3fc", lw=1.5,
                label="平均浸润比例 (%)",
            )
            # p_c 只属于贯通判据：面积判据下这条线画出来只会误导
            pc = self._scan_pc if span else None
            if pc is not None:
                kind = "估计" if self.grid_model.pc_is_estimate else "阈值"
                ax.axvline(
                    pc, color=DANGER, ls="--", lw=1.3,
                    label=f"{kind} p_c = {pc:.4f}",
                )
            ax.set_xlabel("流通概率 p", fontsize=9)
            ax.set_ylabel("百分比 (%)", fontsize=9)
            ax.set_xlim(0, 1)
            ax.set_ylim(-3, 103)
            ax.grid(color="#22303f", lw=0.8, ls=":")
            ax.tick_params(labelsize=8)
            ax.legend(
                loc="upper left", fontsize=8,
                facecolor=PANEL_2, edgecolor=BORDER, labelcolor=TEXT,
            )
            rows, trials = self._scan_meta
            cols = self._scan_cols or rows
            lattice_name = _label(LATTICE_CHOICES, self._scan_lattice)
            direction_name = _label(DIRECTION_CHOICES, self._scan_direction)
            rule = {
                "span": "贯通判据",
                "origin": "起点判据",
                "area": f"面积判据 ≥ {self._scan_threshold:.0%}",
            }[self._scan_criterion]
            inject_name = _label(INJECT_CHOICES, self._scan_inject)
            title = (f"P(p) 曲线（{lattice_name} {rows}×{cols} · {direction_name} · "
                     f"注水 {inject_name} · {rule}，每点 {trials} 次）")
            # 把「本次曲线自己的 1/2 交点」标出来：它随长宽比移动，理论 p_c 不会动
            cross = _half_crossing([(p, v / 100.0) for p, v in zip(xs, prob)])
            if cross is not None:
                pc = self._scan_pc
                title += (f"\n1/2 交点 = {cross:.3f}（有限尺寸 + 长宽比决定；理论 p_c"
                          + (f" = {pc:.4f}）" if pc is not None else " 未知）"))
            ax.set_title(title, fontsize=9, color=TEXT)
            if pc is not None and prob and max(prob) >= 100 and min(prob) <= 0:
                ax.annotate(
                    "相变：量变引起质变",
                    xy=(pc, 50), xytext=(pc + 0.06, 22),
                    fontsize=8, color=WARN,
                    arrowprops=dict(arrowstyle="->", color=WARN, lw=1),
                )
            elif not span:
                note = ("起点判据：交点高于 p_c —— 还要看注水点是否落在纵贯簇里；"
                        "注水方式选「顶端整行」时才等于 p_c"
                        if self._scan_criterion == "origin" else
                        "面积判据：曲线交点随「比例 / 网格尺寸 / 注水方式」变化，不是 p_c")
                ax.text(
                    0.03, 0.03, note,
                    transform=ax.transAxes, ha="left", va="bottom",
                    fontsize=7.5, color=WARN,
                )

        self._style_ax()
        self.figure_canvas.draw_idle()

    # ==================================================================
    # 生命周期与快捷操作（由 DesktopShell 调用）
    # ==================================================================
    def on_key(self, key: str) -> None:
        """响应全局快捷键：空格播放动画，R 重新生成。"""
        k = key.lower()
        if k in (" ", "space"):
            self.start_animation()
        elif k == "r":
            self.regenerate_grid()

    def shutdown(self) -> None:
        """视图被关闭（或切换到别的模型）时释放资源。"""
        self._alive = False
        self._cancel_animation()
        for job in (self._regenerate_job, self._redraw_job, self._poll_job, self._first_job):
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        self._regenerate_job = None
        self._redraw_job = None
        self._poll_job = None
        self._first_job = None
        self._cancel.set()          # 通知后台线程停止


def launch(spec=None, **_kwargs) -> int:
    """启动桌面窗口界面（带顶部的模型下拉框）。

    真正的窗口外壳在 :mod:`awe_math.ui.tk.shell` 中，这里只是转发，
    以便 ``python -m awe_math.ui.tk.app`` 也能直接打开同一个窗口。
    """
    from .shell import launch as _launch

    return _launch(spec)


if __name__ == "__main__":
    launch()
