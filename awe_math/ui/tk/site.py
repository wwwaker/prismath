# -*- coding: utf-8 -*-
"""
点渗流 · 桌面窗口视图（Tkinter）
==================================

与边渗流视图（:mod:`awe_math.ui.tk.app`）结构一致，共用同一套主题与布局：

* 左侧控制栏：占据密度 p、行列数（矩形格地）、面积判据阈值、成功判据、格子类型、
  方向模式、注水（起始）方式、动画速度、统计与扫描参数；
* 中央画布：画出格地与逐层蔓延的过程，**点击格地可指定注水点**；
* 右侧面板（三个标签页）：单次结果、批量统计、P(p) 曲线（p → 成功概率）。

成功判据决定「什么算成功」，也决定界面上的说法：
``span``（贯通）判定格地上是否存在顶行 ↔ 底行的纵贯簇 —— 这是 ``p_c`` 所对应的判据；
``area``（面积）判定蔓延面积是否达到设定比例 —— 没有固定临界值。
两种判据下统计行标题、结论徽章、曲线纵轴与 p_c 参考线都会随之变化。

计算全部落在 :class:`~awe_math.models.site_percolation.model.SitePercolation` 上，
批量统计与密度扫描在后台线程执行，可随时「停止」。
"""

from __future__ import annotations

import math
import queue
import random
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # 作为包的一部分导入
    from ...models.percolation.model import lattice_layout   # 共用的格子几何
    from ...models.site_percolation.model import (
        DEFAULT_THRESHOLD,
        SitePercolation,
        SpreadBatchResult,
        SpreadResult,
        batch_spread_probability,
        scan_curve,
    )
    from ...models.site_percolation.spec import (
        DIRECTION_CHOICES,
        LATTICE_CHOICES,
        CRITERION_CHOICES,
        SITE_INJECT_CHOICES,
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
        lerp_color,
        make_accent_button,
    )
except ImportError:  # 允许直接运行本文件（把项目根目录加入 import 路径）
    from pathlib import Path

    _ROOT = Path(__file__).resolve().parents[3]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from awe_math.models.percolation.model import lattice_layout  # type: ignore
    from awe_math.models.site_percolation.model import (  # type: ignore
        DEFAULT_THRESHOLD,
        SitePercolation,
        SpreadBatchResult,
        SpreadResult,
        batch_spread_probability,
        scan_curve,
    )
    from awe_math.models.site_percolation.spec import (  # type: ignore
        DIRECTION_CHOICES,
        LATTICE_CHOICES,
        CRITERION_CHOICES,
        SITE_INJECT_CHOICES,
    )
    from awe_math.ui.tk.theme import (  # type: ignore
        ACCENT, BG, BORDER, DANGER, DIM, FAINT, FONT_BADGE, FONT_BOLD, FONT_SM,
        PANEL, PANEL_2, TEXT, WARN, ScrollArea, lerp_color, make_accent_button,
    )

try:
    import matplotlib

    matplotlib.use("TkAgg")
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

# ----------------------------------------------------------------------
# 画布配色
# ----------------------------------------------------------------------
BG_CANVAS = "#0c1118"       # 格地底色
COL_GROUND = "#1b2430"      # 相邻格子的连线（可蔓延关系）
COL_EMPTY = "#222b38"       # 空位
COL_SITE = "#5c6b80"        # 被占据但还没蔓延到的格子
COL_SITE_EDGE = "#0a0e13"   # 占据格描边
COL_SPAN_FILL = "#12433c"   # 纵贯簇（顶行 ↔ 底行连通的簇）的填充
COL_SPAN_EDGE = "#2dd4bf"   # 纵贯簇描边
COL_SEED = "#fbbf24"        # 注水点（起始格）
COL_SPREAD_EDGE = "#a78bfa"  # 蔓延路径

#: 蔓延层的颜色渐变：刚蔓延到偏浅紫，越晚越深
SPREAD_RAMP = [
    (0.00, (196, 181, 253)),
    (0.45, (167, 139, 250)),
    (0.78, (139, 92, 246)),
    (1.00, (59, 130, 246)),
]

#: 行数 / 列数上限
MAX_SIZE = 80

#: 「面积判据」阈值下拉框候选项
THRESHOLD_CHOICES = ("0.3", "0.5", "0.7", "0.9")


def _ramp_color(t: float) -> str:
    """按 0..1 的进度在 :data:`SPREAD_RAMP` 上取色。"""
    value = 0.0 if t < 0 else (1.0 if t > 1 else t)
    for i in range(1, len(SPREAD_RAMP)):
        pos, rgb = SPREAD_RAMP[i]
        if value <= pos:
            p0, c0 = SPREAD_RAMP[i - 1]
            k = (value - p0) / (pos - p0 or 1.0)
            return lerp_color(c0, rgb, k)
    return lerp_color(SPREAD_RAMP[-1][1], SPREAD_RAMP[-1][1], 0.0)


def _spec_defaults(spec) -> Dict[str, Any]:
    """从模型元数据里取出参数默认值（没有 spec 时用点渗流模型的默认值）。"""
    if spec is None:
        return {"p": 0.6, "rows": 30, "cols": 30}
    return {param.key: param.default for param in getattr(spec, "params", ())}


def _pick(mapping: Dict[str, str], value: object, fallback: str) -> str:
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


class SitePercolationApp:
    """点渗流模型的可视化视图（由 :class:`DesktopShell` 放入窗口中部）。"""

    HINTS = "空格 播放动画    R 重新生成    点击格地可指定注水点"

    def __init__(self, root: tk.Tk, host: tk.Misc, spec=None) -> None:
        self.root = root
        self.host = host
        self.spec = spec
        defaults = _spec_defaults(spec)
        init_p = float(defaults.get("p", 0.6))
        init_rows = int(defaults.get("rows", 30) or 30)
        init_cols = int(defaults.get("cols", init_rows) or init_rows)
        init_lattice = _pick(LATTICE_CHOICES, defaults.get("lattice"), "square")
        init_direction = _pick(DIRECTION_CHOICES, defaults.get("direction"), "undirected")
        init_inject = _pick(SITE_INJECT_CHOICES, defaults.get("inject"), "random")
        init_criterion = _pick(CRITERION_CHOICES, defaults.get("criterion"), "span")
        init_threshold = float(defaults.get("threshold", DEFAULT_THRESHOLD) or DEFAULT_THRESHOLD)

        # ---------------- 模型与状态 ----------------
        self.model = SitePercolation(
            rows=init_rows, cols=init_cols, p=init_p, rng=random.Random(),
            lattice=init_lattice, direction=init_direction, inject=init_inject,
            criterion=init_criterion, threshold=init_threshold,
        )
        self.result: Optional[SpreadResult] = None
        self._spread_set: set = set()        # 当前已显示的蔓延格子
        self._shown_layers = 0               # 已显示的蔓延层数
        self._anim_job: Optional[str] = None
        self._regenerate_job: Optional[str] = None
        self._redraw_job: Optional[str] = None
        self._alive = True

        # 画布元素索引（用于局部刷新，避免整图重绘）
        self._node_items: List[Optional[int]] = []
        self._edge_items: Dict[Tuple[int, int], int] = {}
        self._node_xy: List[Tuple[float, float]] = []
        self._cell = 10.0
        #: 当前底图对应的 (行数, 列数, 格子, 方向)
        self._drawn_shape: Tuple[int, int, str, str] = (0, 0, "", "")

        # 后台任务
        self._queue: "queue.Queue" = queue.Queue()
        self._cancel = threading.Event()
        self._busy = False
        self._scan_results: List[SpreadBatchResult] = []
        self._scan_meta: Tuple[int, int] = (0, 0)        # (行数, 每点次数)
        self._scan_cols = 0
        self._scan_lattice = self.model.lattice
        self._scan_direction = self.model.direction
        self._scan_inject = self.model.inject
        self._scan_criterion = self.model.criterion
        self._scan_threshold = init_threshold
        self._scan_pc = self.model.theoretical_pc

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
        self.var_inject = tk.StringVar(value=_label(SITE_INJECT_CHOICES, init_inject))
        self.var_criterion = tk.StringVar(
            value=_label(CRITERION_CHOICES, init_criterion)
        )
        self.var_status = tk.StringVar(
            value="就绪：拖动滑块调整占据密度 p，程序会自动重新生成格地并蔓延。"
        )
        #: 统计面板里随判据变化的行标题（key -> Label 控件）
        self._stat_labels: Dict[str, ttk.Label] = {}

        self.vals: Dict[str, tk.StringVar] = {
            "p": tk.StringVar(value="-"),
            "size": tk.StringVar(value="-"),
            "sites": tk.StringVar(value="-"),
            "seeds": tk.StringVar(value="-"),
            "area": tk.StringVar(value="-"),
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

        self._accent_btn = make_accent_button(root, getattr(spec, "accent", "#a78bfa"))
        self._build_ui()
        self._redraw_curve()

        # 定时任务句柄要留着：视图被切换 / 关闭时必须取消，
        # 否则挂起的回调会继续访问已经销毁的画布（TclError）。
        self._poll_job: Optional[str] = self.root.after(80, self._poll_queue)
        self._first_job: Optional[str] = self.root.after(60, self.regenerate_sites)

    # ==================================================================
    # 界面搭建
    # ==================================================================
    def _build_ui(self) -> None:
        self.host.configure(bg=BG)
        self.host.columnconfigure(0, weight=0)
        self.host.columnconfigure(1, weight=1)
        self.host.columnconfigure(2, weight=0)
        self.host.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_center()
        self._build_right()
        self._build_status_bar()
        self._refresh_criterion_texts()   # 按初始判据修正行标题

    # ---------------------------- 左侧控制栏 ----------------------------
    def _build_sidebar(self) -> None:
        # 参数一多，侧边栏就会比窗口还高；用可滚动容器承载，避免控件被裁掉
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
    def _card(parent: tk.Misc, title: str) -> ttk.LabelFrame:
        card = ttk.LabelFrame(
            parent, text=f" {title} ", style="Card.TLabelframe",
            padding=(12, 8, 12, 10),
        )
        card.pack(fill="x", pady=(0, 6))
        return card

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

    def _build_param_card(self, parent: tk.Misc) -> None:
        card = self._card(parent, "参数")

        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="占据密度 p", style="Card.TLabel").pack(side="left")
        self.lbl_p = ttk.Label(
            head, text=f"p = {self.var_p.get():.2f}", style="MonoAccent.TLabel",
        )
        self.lbl_p.pack(side="right")

        self.scale_p = ttk.Scale(
            card, from_=0.0, to=1.0, variable=self.var_p, command=self._on_p_change,
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
        threshold.bind("<<ComboboxSelected>>", lambda _e: self.regenerate_sites())

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
    def _build_advanced_card(self, parent: tk.Misc) -> None:
        card = self._card(parent, "高级选项")

        # 判据放最前面：它决定「什么算成功」，也就决定 p_c 是否有意义
        self._option_row(card, "成功判据", self.var_criterion,
                         tuple(CRITERION_CHOICES), self._on_criterion_change)
        self._option_row(card, "格子类型", self.var_lattice,
                         tuple(LATTICE_CHOICES), self._on_lattice_change)
        self._option_row(card, "方向模式", self.var_direction,
                         tuple(DIRECTION_CHOICES), self._on_direction_change)
        self._option_row(card, "注水（起始）方式", self.var_inject,
                         tuple(SITE_INJECT_CHOICES), self._on_inject_change)

        self.lbl_pc = ttk.Label(
            card, text="", style="CardDim.TLabel",
            wraplength=252, justify="left", font=FONT_SM,
        )
        self.lbl_pc.pack(anchor="w")
        self._update_pc_label()

    def _update_pc_label(self) -> None:
        """显示临界值说明：贯通判据给出 p_c，面积判据说明它没有固定阈值。"""
        self.lbl_pc.configure(
            text=self.model.pc_label,
            foreground=WARN if not self.model.pc_applies else DIM,
        )

    def _current_criterion(self) -> str:
        return _pick(CRITERION_CHOICES, self.var_criterion.get(), "span")

    def _refresh_criterion_texts(self) -> None:
        """判据变化后，刷新那些「随判据改变含义」的界面文案。"""
        criterion = self.model.criterion
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
        """格子 / 方向 / 注水方式变化后：作废旧结果、重建格地并重绘。"""
        self._cancel_animation()
        self._discard_result()
        self.model.regenerate()
        self._update_pc_label()
        self.regenerate_sites()
        self.var_status.set(message)

    def _on_lattice_change(self) -> None:
        """切换格子类型：邻接关系整体改变，必须重建。"""
        lattice = _pick(LATTICE_CHOICES, self.var_lattice.get(), "square")
        if lattice == self.model.lattice:
            return
        self.model.lattice = lattice
        self._rebuild_after_option_change(
            f"已切换为{self.model.lattice_name}：{self.model.pc_label}。"
        )

    def _on_direction_change(self) -> None:
        """切换方向模式：可达关系变了，重建格地并重新蔓延。"""
        direction = _pick(DIRECTION_CHOICES, self.var_direction.get(), "undirected")
        if direction == self.model.direction:
            return
        self.model.direction = direction
        self._rebuild_after_option_change(
            f"已切换为「{self.model.direction_name}」：{self.model.pc_label}。"
        )

    def _on_inject_change(self) -> None:
        """切换注水方式：格地不变，只需重新挑注水点。"""
        inject = _pick(SITE_INJECT_CHOICES, self.var_inject.get(), "random")
        if inject == self.model.inject:
            return
        self.model.inject = inject
        if self.model.criterion == "span":
            message = (f"注水方式：{self.model.inject_name}。"
                       "贯通判据只看整片格地有没有纵贯簇，与注水位置无关 —— "
                       "它只影响单次动画的起点。")
        elif self.model.criterion == "origin":
            message = (f"注水方式：{self.model.inject_name}。"
                       "起点判据下注水位置影响很大 —— 顶端整行一定在纵贯簇上，"
                       "随机/中心单点则可能落在簇外（火很小却仍可能判定成功）。")
        else:
            message = (f"注水方式：{self.model.inject_name}。"
                       "面积判据下起始位置影响很大：单点注水额外要求「起点落在巨簇里」，"
                       "所以曲线整体比顶端整行注水更平缓。")
        self._rebuild_after_option_change(message)

    def _on_criterion_change(self) -> None:
        """切换成功判据：格地不用重建，但结论、统计与曲线的含义都变了。"""
        criterion = self._current_criterion()
        if criterion == self.model.criterion:
            return
        self._cancel_animation()
        self._discard_result()
        self.model.criterion = criterion
        self._refresh_criterion_texts()
        self._update_pc_label()
        self.regenerate_sites()
        if criterion == "span":
            self.var_status.set(
                "已切换为「贯通判据」：判定**整片格地**上是否存在顶行↔底行的纵贯簇"
                "（青色格子）。它的成功概率 = 1/2 交点就是临界密度 p_c"
                "（方格网无向 ≈ 0.5927），且与注水方式无关。"
            )
        elif criterion == "origin":
            self.var_status.set(
                "已切换为「起点判据」：判定**从注水点出发的那一簇**是否纵贯（碰到顶行"
                "与底行）。它与贯通判据的差别是「还要求注水点落在纵贯簇里」，"
                "所以交点高于 p_c —— 随机起火常常烧在簇外。"
            )
        else:
            self.var_status.set(
                "已切换为「面积判据」：判定蔓延面积是否达到设定比例。"
                "注意它没有固定的临界值 —— 交点随比例、网格尺寸、注水方式一起变，"
                "不要把它当成 p_c。"
            )

    def _build_action_card(self, parent: tk.Misc) -> None:
        card = self._card(parent, "操作")
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        self.btn_spread = ttk.Button(
            card, text="▶ 播放动画", style=self._accent_btn,
            command=self.start_spread,
        )
        self.btn_spread.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self.btn_regen = ttk.Button(card, text="↻ 重新生成", command=self.regenerate_sites)
        self.btn_instant = ttk.Button(card, text="⤓ 直接看结果", command=self.show_result_instant)
        self.btn_regen.grid(row=1, column=0, sticky="ew", padx=(0, 4))
        self.btn_instant.grid(row=1, column=1, sticky="ew", padx=(4, 0))

    def _build_batch_card(self, parent: tk.Misc) -> None:
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

    def _build_scan_card(self, parent: tk.Misc) -> None:
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
            self.btn_spread,
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

    def _build_legend(self, parent: tk.Misc) -> tk.Canvas:
        cv = tk.Canvas(
            parent, height=30, bg=PANEL, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,
        )
        items = [
            ("dot", COL_SITE, "占据格"),
            ("dot", COL_EMPTY, "空位"),
            ("dot", COL_SPAN_FILL, "纵贯簇"),
            ("dot", _ramp_color(0.5), "已蔓延"),
            ("dot", COL_SEED, "注水点"),
            ("line", COL_GROUND, "相邻可蔓延"),
        ]
        x = 12
        for kind, color, label in items:
            if kind == "line":
                cv.create_line(x, 15, x + 20, 15, fill=color, width=2)
            else:
                cv.create_oval(x + 5, 10, x + 15, 20, fill=color, outline=COL_SITE_EDGE)
            cv.create_text(x + 25, 15, text=label, anchor="w", fill=DIM, font=FONT_SM)
            x += 25 + len(label) * 13 + 16
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

    def _add_stat_row(self, parent: tk.Misc, row: int, label: str, var: tk.StringVar,
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
            ("占据密度 p", "p"),
            ("格子 / 规模", "size"),
            ("占据格数量", "sites"),
            ("注水点", "seeds"),
            ("蔓延格数", "area"),
            ("蔓延比例", "ratio"),
            ("纵贯簇", "spanning"),
            ("蔓延层数", "depth"),
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
                "· 每格以概率 p 被占据，相邻占据格之间才连通；蔓延范围 = 包含注水点\n"
                "  的那个连通簇（「随机一棵树起火，火只沿相邻的树烧」）；\n"
                "· 青色格子是**纵贯簇**：同时连通顶行与底行的那个簇。三种判据：\n"
                "  · 贯通判据 = 格地上有没有纵贯簇 —— p_c 说的就是这个相变\n"
                "    （方格网 ≈ 0.5927、三角网 0.5），与注水方式无关；\n"
                "  · 起点判据 = 你这次注水的那一簇是否纵贯 —— 随机/中心起火经常\n"
                "    落在纵贯簇之外，所以交点高于 p_c（顶端整行注水时两者相同）；\n"
                "  · 面积判据 = 蔓延面积达到设定比例 —— 没有固定临界值，交点随\n"
                "    比例、网格尺寸、注水方式一起漂移；\n"
                "· 只有贯通判据的 1/2 交点等于 p_c；点击占据格可指定注水点。"
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
            ("平均蔓延比例", "b_mean"),
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
            rows = self.model.rows
        try:
            cols = int(self.var_cols.get())
        except (tk.TclError, ValueError):
            cols = self.model.cols
        return max(2, min(MAX_SIZE, rows)), max(2, min(MAX_SIZE, cols))

    def _current_threshold(self) -> float:
        try:
            value = float(self.var_threshold.get())
        except (TypeError, ValueError):
            value = DEFAULT_THRESHOLD
        return min(1.0, max(0.05, value))

    def _current_seed(self) -> Optional[int]:
        """统计用的随机种子：≥0 时批量统计/曲线完全可复现，-1 表示随机。

        固定种子后，「同一片格地上换判据 / 换注水方式」的横向比较才是严格可比的
        （否则只能看到蒙特卡洛噪声，例如贯通判据本应与注水方式无关）。
        """
        try:
            value = int(float(self.var_seed.get()))
        except (TypeError, ValueError):
            return None
        return None if value < 0 else value

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
        """滑块变化：更新显示，并防抖地重新生成格地。"""
        if value is not None:
            try:
                self.var_p.set(round(float(value), 2))
            except (TypeError, ValueError):
                pass
        self.lbl_p.configure(text=f"p = {self.var_p.get():.2f}")
        self._debounce_regenerate()

    def _on_shape_change(self) -> None:
        rows, cols = self._current_shape()
        if (rows, cols) != (self.model.rows, self.model.cols):
            self._cancel_animation()
            self._discard_result()
            self.model.rows, self.model.cols = rows, cols
            self.model.regenerate()
        self._debounce_regenerate(delay=60)

    def _discard_result(self) -> None:
        """丢弃当前结果（格地尺寸 / 选项变化后调用）。"""
        self.result = None
        self._shown_layers = 0
        self._spread_set = set()

    def _on_canvas_resize(self, _event=None) -> None:
        if self._redraw_job is not None:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(120, self._redraw_grid)

    def _debounce_regenerate(self, delay: int = 160) -> None:
        if self._regenerate_job is not None:
            self.root.after_cancel(self._regenerate_job)
        self._regenerate_job = self.root.after(delay, self.regenerate_sites)

    def _sync_model_params(self) -> None:
        """把界面上的参数同步进模型（结构或注水点变了必须重建格地）。"""
        p = round(self.var_p.get(), 2)
        rows, cols = self._current_shape()
        lattice = _pick(LATTICE_CHOICES, self.var_lattice.get(), "square")
        direction = _pick(DIRECTION_CHOICES, self.var_direction.get(), "undirected")
        inject = _pick(SITE_INJECT_CHOICES, self.var_inject.get(), "random")
        # 判据与阈值都不改变格地结构，直接同步即可
        if self._current_criterion() != self.model.criterion:
            self._discard_result()
        self.model.criterion = self._current_criterion()
        self.model.threshold = self._current_threshold()

        structural = (
            lattice != self.model.lattice
            or direction != self.model.direction
            or (rows, cols) != (self.model.rows, self.model.cols)
        )
        if structural or inject != self.model.inject:
            self._cancel_animation()
            self._discard_result()
            self.model.rows, self.model.cols = rows, cols
            self.model.lattice = lattice
            self.model.direction = direction
            self.model.inject = inject
            self.model.regenerate(p)
            if structural:
                self._update_pc_label()
        else:
            self.model.p = p

    # ==================================================================
    # 格地生成与绘制
    # ==================================================================
    def _canvas_ready(self) -> bool:
        """画布是否仍然可用（视图被销毁后，挂起的回调不应继续画图）。"""
        return self._alive and bool(self.canvas.winfo_exists())

    def regenerate_sites(self) -> None:
        """重新生成格地，并立即蔓延一次（不做动画），展示最终结果。"""
        self._regenerate_job = None
        if not self._canvas_ready():
            return
        self._cancel_animation()
        self._sync_model_params()
        self.model.regenerate()
        self._spread_and_show()
        model = self.model
        self.var_status.set(
            f"已重新生成格地：{model.lattice_name} {model.rows}×{model.cols}"
            f"（{model.direction_name}），p={model.p:.2f}。按空格可播放蔓延动画。"
        )

    def _spread_and_show(self) -> None:
        """蔓延一次并刷新画布与指标（直接显示最终结果）。"""
        self.result = self.model.simulate()
        self._shown_layers = 0 if self.result is None else len(self.result.layers)
        self._spread_set = set() if self.result is None else set(self.result.spread)
        self._redraw_grid()
        self._update_result_labels()

    def _layout_params(self) -> Tuple[float, float, float]:
        """计算画布下每个格子的屏幕坐标，返回 (格子间距, 左上偏移x, 左上偏移y)。"""
        model = self.model
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
        """绘制底层格地：可蔓延关系（浅线）+ 占据格 / 空位。"""
        cv = self.canvas
        cv.delete("all")
        model = self.model
        cell, _ox, _oy = self._layout_params()
        self._cell = cell
        # 记录底图对应的形状 / 格子 / 方向，供增量上色时校验
        self._drawn_shape = (model.rows, model.cols, model.lattice, model.direction)

        radius = max(1.2, min(5.0, cell * 0.30))
        xy = self._node_xy
        self._node_items = [None] * model.node_count
        self._edge_items = {}

        # 相邻格子的可蔓延关系（画在最下层，作为格点提示）
        for idx in range(model.node_count):
            for nb in self._adjacent_pairs(idx):
                key = (idx, nb) if idx < nb else (nb, idx)
                if key in self._edge_items:
                    continue
                x1, y1 = xy[idx]
                x2, y2 = xy[nb]
                self._edge_items[key] = cv.create_line(
                    x1, y1, x2, y2, fill=COL_GROUND, width=1
                )

        # 占据格与空位
        occupied = model.occupied
        cols = model.cols
        # 纵贯簇单独上色：判据问的就是「有没有这么一片格子纵贯顶底」，
        # 不画出来的话，「判定贯通 + 蔓延面积很小」会显得莫名其妙
        spanning = set(model.spanning_nodes())
        for idx, (x, y) in enumerate(xy):
            if not occupied[idx // cols][idx % cols]:
                outline, ow, fill = "", 0, COL_EMPTY
            elif idx in spanning:
                outline, ow, fill = COL_SPAN_EDGE, 1, COL_SPAN_FILL
            else:
                outline, ow, fill = COL_SITE_EDGE, 1, COL_SITE
            self._node_items[idx] = cv.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill=fill, outline=outline, width=ow,
            )

        cv.create_text(10, 8, anchor="nw",
                       text=f"▦ {model.direction_name} · {model.inject_name} · "
                            f"{self._criterion_rule()}（深色为空位）",
                       fill=DIM, font=FONT_SM)
        cv.create_text(10, int(cv.winfo_height()) - 8, anchor="sw",
                       text="点击任意占据格可指定注水点（空位不可选）",
                       fill=FAINT, font=FONT_SM)

    def _adjacent_pairs(self, index: int):
        """几何相邻的格子（不受方向与占据状态限制），供底图画线使用。"""
        model = self.model
        rows, cols = model.rows, model.cols
        r, c = divmod(index, cols)
        if c + 1 < cols:
            yield index + 1
        if c > 0:
            yield index - 1
        if model.lattice == "square":
            if r + 1 < rows:
                yield index + cols
            if r > 0:
                yield index - cols
            return
        shift = r % 2
        if r + 1 < rows:
            for j in (c - 1 + shift, c + shift):
                if 0 <= j < cols:
                    yield r * cols + cols + j
        if r > 0:
            pshift = (r - 1) % 2
            for k in (c + 1 - pshift, c - pshift):
                if 0 <= k < cols:
                    yield (r - 1) * cols + k

    def _apply_spread(self, nodes: Sequence[int], color: str) -> None:
        """把一批格子标记为已蔓延，并高亮它与已蔓延邻居之间的路径。"""
        cv = self.canvas
        model = self.model
        if self._drawn_shape != (model.rows, model.cols, model.lattice, model.direction):
            return
        node_items = self._node_items
        edges = self._edge_items
        lw = max(1.6, min(3.6, self._cell * 0.22))

        for idx in nodes:
            item = node_items[idx]
            if item is not None:
                cv.itemconfigure(item, fill=color, outline=COL_SITE_EDGE, width=1)
            # 找已经蔓延到的邻居给这条边染色。必须用 traversable_neighbors 而不是
            # neighbors：后者只给「出边」，有向模式下从后来蔓延到的格子看前一个格子是
            # 「逆方向」的，那条边就漏色了（三角网 + 方向限制时最明显）。
            for nb in model.traversable_neighbors(idx):
                if nb not in self._spread_set:
                    continue
                it = edges.get((idx, nb) if idx < nb else (nb, idx))
                if it is not None:
                    cv.itemconfigure(it, fill=COL_SPREAD_EDGE, width=lw)

    def _layer_color(self, layer_index: int, total_layers: int) -> str:
        """按蔓延层数做颜色渐变：刚蔓延到偏浅紫，越晚越深。"""
        t = 0.0 if total_layers <= 1 else layer_index / (total_layers - 1)
        return _ramp_color(t)

    def _redraw_grid(self) -> None:
        """整图重绘：底图 + 当前已显示的蔓延层。"""
        self._redraw_job = None
        if not self._canvas_ready():
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width <= 40 or height <= 40:      # 布局尚未完成，等待 Configure 事件
            return

        self._draw_base()
        self._spread_set = set()

        if (self.result is None or self._shown_layers <= 0
                or self.result.shape != self.model.shape):
            self._hide_verdict()
            return

        layers = self.result.layers
        total = len(layers)
        for i in range(min(self._shown_layers, total)):
            batch = layers[i]
            self._spread_set.update(batch)
            self._apply_spread(batch, self._layer_color(i, total))

        if self._shown_layers >= total:
            self._draw_seed()
            self._show_verdict()

    def _draw_seed(self) -> None:
        """把注水点圈出来（画在最上层）。"""
        if self.result is None:
            return
        for origin in self.result.origins[:64]:      # 顶端整行注水时可能有很多点
            if not 0 <= origin < len(self._node_xy):
                continue
            x, y = self._node_xy[origin]
            r = max(3.0, min(9.0, self._cell * 0.42))
            self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                outline=COL_SEED, width=2, tags="seed",
            )

    def _show_verdict(self) -> None:
        """画布底部显示结论（按当前判据给出不同的说法）。"""
        if self.result is None:
            return
        res = self.result
        if res.criterion == "span":
            ok = res.spans
            text = ("✔ 格地存在纵贯簇（顶行 ↔ 底行）" if ok
                    else "✘ 格地没有纵贯簇")
            text += f"；本次蔓延 {res.spread_ratio:.1%}"
        elif res.criterion == "origin":
            ok = res.origin_spans
            if ok:
                text = (f"✔ 起点纵贯：注水点的簇碰到顶行与底行"
                        f"（蔓延 {res.spread_ratio:.1%}）")
            elif res.spans:
                text = (f"✘ 起点未纵贯：格地有纵贯簇（{res.spanning_count} 格，青色），"
                        f"但注水点不在簇内（蔓延 {res.spread_ratio:.1%}）")
            else:
                text = (f"✘ 起点未纵贯，格地也没有纵贯簇"
                        f"（蔓延 {res.spread_ratio:.1%}）")
        else:
            ok = res.engulfed
            text = (f"✔ 面积判据达标：蔓延 {res.spread_ratio:.1%}（≥{res.threshold:.0%}）"
                    if ok else
                    f"✘ 面积未达标：蔓延 {res.spread_ratio:.1%}（<{res.threshold:.0%}）")
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
    def start_spread(self, origins: Optional[Sequence[int]] = None) -> None:
        """从注水点开始逐层播放蔓延过程（origins 省略时按注水方式自动挑选）。

        不重新生成格地：按空格是「重播当前这次蔓延」，想换一片格地请点「重新生成」；
        点击画布上的占据格则从那一格开始蔓延。
        """
        if self._busy:
            return
        self._cancel_animation()
        self._sync_model_params()
        self.result = self.model.simulate(origins)
        self._shown_layers = 0
        self._spread_set = set()
        self._draw_base()
        self._hide_verdict()
        self._update_result_labels()

        if not self.result.has_source:
            self.var_status.set("没有可用的注水点（顶端整行注水时该行可能一个占据格都没有）。")
            return
        model = self.model
        self.var_status.set(
            f"正在演示蔓延过程：{model.lattice_name} {model.rows}×{model.cols}，"
            f"p={model.p:.2f}，{model.direction_name} · {model.inject_name}。"
        )
        self._step_animation()

    def _step_animation(self) -> None:
        self._anim_job = None
        if self.result is None:
            return
        if self._drawn_shape[:2] != self.result.shape:
            self._cancel_animation()     # 底图已被其它形状重建，本次动画作废
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
            batch = [idx for idx in layers[i] if idx not in self._spread_set]
            self._spread_set.update(batch)
            self._apply_spread(batch, self._layer_color(i, total))
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
                f"（本次蔓延覆盖 {self.result.spread_ratio:.1%}）。"
                "可点击「开始批量统计」考察该 p 值下的成功概率。"
            )

    @staticmethod
    def _verdict_phrase(res: SpreadResult) -> str:
        """把一次蔓延的结果说成一句话（随判据变化）。"""
        if res.criterion == "span":
            return "格地存在纵贯簇" if res.spans else "格地没有纵贯簇"
        if res.criterion == "origin":
            if res.origin_spans:
                return "起点纵贯（注水点的簇碰顶又碰底）"
            if res.spans:
                return "起点未纵贯（格地有纵贯簇，但注水点在簇外）"
            return "起点未纵贯，格地也没有纵贯簇"
        return "面积判据达标" if res.engulfed else "面积判据未达标"

    def _cancel_animation(self) -> None:
        if self._anim_job is not None:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None

    def show_result_instant(self) -> None:
        """跳过动画，直接显示最终蔓延结果。"""
        self._cancel_animation()
        self._sync_model_params()
        self._spread_and_show()
        if self.result is None or not self.result.has_source:
            self.var_status.set("没有可用的注水点（顶端整行注水时该行可能一个占据格都没有）。")
            return
        self.var_status.set(
            f"单次结果：{self._verdict_phrase(self.result)}，覆盖 "
            f"{self.result.spread_count}/{self.result.node_count}"
            f"（{self.result.spread_ratio:.1%}）。"
        )

    def _on_canvas_click(self, event) -> None:
        """点击画布：把最近的占据格设为注水点并播放动画。"""
        if not self._node_xy or len(self._node_xy) != self.model.node_count:
            return
        best, best_dist = -1, float("inf")
        for idx, (x, y) in enumerate(self._node_xy):
            dist = (x - event.x) ** 2 + (y - event.y) ** 2
            if dist < best_dist:
                best, best_dist = idx, dist
        if best >= 0 and self.model.is_occupied(best):
            self.start_spread(origins=[best])
        else:
            self.var_status.set("那里是空位（或已超出格地范围），请点击一个占据格。")

    # ==================================================================
    # 指标刷新
    # ==================================================================
    def _result_summary(self) -> str:
        """当前配置的简短描述。"""
        model = self.model
        return (f"{model.lattice_name} {model.rows}×{model.cols} · "
                f"{model.direction_name} · 注水 {model.inject_name} · "
                f"{self._criterion_rule()}")

    def _criterion_rule(self) -> str:
        """当前判据的简短说法（界面各处复用）。"""
        if self.model.criterion == "span":
            return "判据 贯通（格地有无纵贯簇）"
        if self.model.criterion == "origin":
            return "判据 起点纵贯（注水点的簇碰顶又碰底）"
        return f"判据 面积 ≥ {self.model.threshold:.0%}"

    def _update_result_labels(self) -> None:
        model = self.model
        res = self.result
        self.vals["p"].set(f"{model.p:.2f}")
        self.vals["size"].set(
            f"{model.lattice_name} {model.rows}×{model.cols}（{model.node_count} 格）"
        )

        if res is None:
            self.vals["sites"].set("-")
            self.vals["seeds"].set("-")
            self.vals["area"].set("-")
            self.vals["ratio"].set("-")
            self.vals["depth"].set("-")
            self.vals["cost"].set("-")
        else:
            self.vals["sites"].set(
                f"{res.occupied_count} / {res.node_count}（{res.occupied_ratio:.1%}）"
            )
            self.vals["seeds"].set(
                "-" if not res.has_source else f"{len(res.origins)} 个（{model.inject_name}）"
            )
            self.vals["area"].set(f"{len(self._spread_set)} / {res.node_count} 格")
            ratio = len(self._spread_set) / res.node_count if res.node_count else 0.0
            self.vals["ratio"].set(
                f"{ratio:.1%}（簇内 {res.cluster_ratio:.1%}，"
                f"动画 {min(self._shown_layers, res.depth)}/{res.depth} 层）"
            )
            self.vals["depth"].set(f"{min(self._shown_layers, res.depth)} / {res.depth} 层")
            self.vals["cost"].set(f"{res.elapsed * 1000:.1f} ms")

        # 纵贯簇是格地本身的性质（与注水点无关），没有蔓延结果时也显示
        nodes = self.model.spanning_nodes()
        if nodes:
            total = self.model.node_count
            value = f"{len(nodes)} 格（{len(nodes) / total:.1%}）" if total else f"{len(nodes)} 格"
            if res is not None:
                value += "·水在簇内" if res.origin_in_spanning else "·水在簇外"
        else:
            value = "无"
        self.vals["spanning"].set(value)

        # 顶部的结论徽章
        if res is None:
            self.badge.configure(text="— 等待计算 —", bg=PANEL_2, fg=FAINT)
        elif not res.has_source:
            self.badge.configure(text="没有可用的注水点", bg="#331420", fg="#fb7185")
        elif self._shown_layers < res.depth:
            self.badge.configure(text="蔓延中 …", bg=PANEL_2, fg=WARN)
        elif res.criterion == "span":
            # 贯通判据：结论看整片格地有没有纵贯簇，蔓延面积只是附带信息
            if res.spans:
                self.badge.configure(
                    text=f"✔ 存在纵贯簇（{res.spanning_count} 格，蔓延 {res.spread_ratio:.1%}）",
                    bg="#2b2340", fg="#c4b5fd",
                )
            else:
                self.badge.configure(
                    text=f"✘ 没有纵贯簇（蔓延 {res.spread_ratio:.1%}）",
                    bg="#131c28", fg="#93c5fd",
                )
        elif res.criterion == "origin":
            # 起点判据：最容易困惑的一档 —— 格地有纵贯簇，但火源在簇外
            if res.origin_spans:
                self.badge.configure(
                    text=f"✔ 起点纵贯（蔓延 {res.spread_ratio:.1%}）",
                    bg="#2b2340", fg="#c4b5fd",
                )
            elif res.spans:
                self.badge.configure(
                    text=f"✘ 起点在纵贯簇外（簇 {res.spanning_count} 格）",
                    bg="#131c28", fg="#93c5fd",
                )
            else:
                self.badge.configure(
                    text=f"✘ 起点未纵贯（蔓延 {res.spread_ratio:.1%}）",
                    bg="#131c28", fg="#93c5fd",
                )
        elif res.engulfed:
            self.badge.configure(
                text=f"✔ 面积达标 {res.spread_ratio:.1%}（≥{res.threshold:.0%}）",
                bg="#2b2340", fg="#c4b5fd",
            )
        else:
            self.badge.configure(
                text=f"✘ 面积不足 {res.spread_ratio:.1%}（<{res.threshold:.0%}）",
                bg="#131c28", fg="#93c5fd",
            )

    def _insert_history(self, res: SpreadBatchResult, tag: str) -> None:
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
    # 批量统计 / 密度扫描（后台线程）
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
        model = self.model
        return {
            "lattice": model.lattice,
            "direction": model.direction,
            "inject": model.inject,
            "criterion": model.criterion,
            "threshold": model.threshold,
        }

    def start_batch_statistics(self) -> None:
        """做 N 次独立实验，统计当前判据下的成功频率与平均蔓延比例。"""
        if self._busy:
            return
        # 先把界面上的形状 / 格子 / 方向 / 注水 / 判据 / 阈值全部同步进模型，
        # 保证「统计的就是屏幕上看到的这一套设置」——不能依赖下拉框回调是否已经跑过
        self._sync_model_params()
        rows, cols = self._current_shape()
        p = round(self.var_p.get(), 2)
        model = self.model
        trials = self._parse_int(self.var_trials.get(), 1000)
        seed = self._current_seed()
        self._cancel.clear()
        self.progress.configure(maximum=trials, value=0)
        self._set_busy(
            True,
            f"正在统计：{model.lattice_name} {rows}×{cols}，"
            f"{self._result_summary()}，p={p:.2f}，共 {trials} 次独立实验"
            + (f"（种子 {seed}）" if seed is not None else "") + "…",
        )

        def job() -> None:
            try:
                res = batch_spread_probability(
                    rows=rows, cols=cols, p=p, trials=trials, rng=seed,
                    **self._batch_options(),
                    progress=lambda done, total, success: self._queue.put(
                        ("progress", (done, total))
                    ),
                    cancel=self._cancel,
                )
                self._queue.put(("batch_done", res))
            except Exception as exc:  # pragma: no cover
                self._queue.put(("error", f"批量统计失败：{exc}"))

        threading.Thread(target=job, daemon=True).start()

    def start_scan(self) -> None:
        """扫描 p ∈ [0, 1]，绘制当前判据下的成功概率与平均蔓延比例曲线。"""
        if self._busy:
            return
        # 同批量统计：先同步界面设置，曲线必须反映当前的形状 / 格子 / 方向 / 注水 / 判据
        self._sync_model_params()
        rows, cols = self._current_shape()
        model = self.model
        seed = self._current_seed()
        trials = self._parse_int(self.var_scan_trials.get(), 200, low=10)
        step = self._parse_float(self.var_scan_step.get(), 0.05, low=0.01, high=0.5)
        p_values = [round(i * step, 2) for i in range(int(round(1.0 / step)) + 1)]
        p_values = [p for p in p_values if p <= 1.0]

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
            f"正在扫描占据密度（共 {len(p_values)} 个点，每点 {trials} 次实验，"
            f"{self._result_summary()}"
            + (f"，种子 {seed}" if seed is not None else "") + "）…",
        )

        def job() -> None:
            try:
                scan_curve(
                    p_values, rows=rows, cols=cols, trials=trials, rng=seed,
                    **self._batch_options(),
                    progress=lambda done, total, res: self._queue.put(
                        ("scan_point", (done, total, res))
                    ),
                    cancel=self._cancel,
                )
                self._queue.put(("scan_done", None))
            except Exception as exc:  # pragma: no cover
                self._queue.put(("error", f"密度扫描失败：{exc}"))

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
            res: SpreadBatchResult = payload
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
                pc = self.model.theoretical_pc
                tail = ("贯通判据下，成功概率 ≈ 1/2 的位置就是临界密度 p_c"
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
                f"（{res.success}/{res.trials}），平均蔓延 {res.mean_ratio:.1%}，"
                f"耗时 {res.elapsed:.2f} s。{tail}"
            )

        elif kind == "scan_point":
            done, total, res = payload
            self._scan_results.append(res)
            self.progress.configure(maximum=total, value=done)
            self.var_status.set(f"密度扫描：{done}/{total} 个 p 值已计算…")
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
                0.5, 0.5, "点击左侧「绘制曲线」开始扫描",
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
                xs, ratio, "--", color="#c4b5fd", lw=1.5,
                label="平均蔓延比例 (%)",
            )
            # p_c 只属于贯通判据：面积判据下这条线画出来只会误导
            pc = self._scan_pc if span else None
            if pc is not None:
                kind = "估计" if self.model.pc_is_estimate else "阈值"
                ax.axvline(
                    pc, color=DANGER, ls="--", lw=1.3,
                    label=f"{kind} p_c = {pc:.4f}",
                )
            ax.set_xlabel("占据密度 p", fontsize=9)
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
            rule = {
                "span": "贯通判据",
                "origin": "起点判据",
                "area": f"面积判据 ≥ {self._scan_threshold:.0%}",
            }[self._scan_criterion]
            inject_name = _label(SITE_INJECT_CHOICES, self._scan_inject)
            title = (f"P(p) 曲线（{_label(LATTICE_CHOICES, self._scan_lattice)} "
                     f"{rows}×{cols} · {_label(DIRECTION_CHOICES, self._scan_direction)} · "
                     f"注水 {inject_name} · {rule}，每点 {trials} 次）")
            # 把「本次曲线自己的 1/2 交点」标出来：它随长宽比移动，理论 p_c 不会动
            cross = _half_crossing([(p, v / 100.0) for p, v in zip(xs, prob)])
            if cross is not None:
                pc = self._scan_pc
                title += (f"\n1/2 交点 = {cross:.3f}（有限尺寸 + 长宽比决定；理论 p_c"
                          + (f" = {pc:.4f}）" if pc is not None else " 未知）"))
            ax.set_title(title, fontsize=9, color=TEXT)
            if pc is not None and max(prob) >= 100 and min(prob) <= 0:
                ax.annotate(
                    "相变：量变引起质变",
                    xy=(pc, 50), xytext=(pc + 0.06, 20),
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
        """响应全局快捷键：空格重新蔓延并播放，R 重新生成格地。"""
        k = key.lower()
        if k in (" ", "space"):
            self.start_spread()
        elif k == "r":
            self.regenerate_sites()

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


if __name__ == "__main__":
    import tkinter as tk

    from .shell import DesktopShell
    from .theme import install_theme

    _root = tk.Tk()
    install_theme(_root)
    _shell = DesktopShell(_root)
    for _spec in _shell.models:
        if _spec.view == "site_percolation":
            _shell.show(_spec)
            break
    _root.mainloop()
