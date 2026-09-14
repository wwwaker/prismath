# -*- coding: utf-8 -*-
"""
桌面视图基类：把「一个模型的桌面界面」抽成可复用的骨架
======================================================

边渗流与点渗流两个视图本来是两份各自 1700 行的文件，但 90% 的代码是逐字重复的。
这里把重复的部分收进基类，只把**真正因模型而异**的东西留成钩子：

留给子类的三类东西
------------------
1. **数据**（类属性，最省事）：

   * :attr:`TERMS`：术语表（网格/格地、节点/格、浸润/蔓延……），基类的全部文案由它拼出；
   * :attr:`STAT_ROWS`：单次结果页的指标行 ``((标题, vals 键), ...)``；
   * :attr:`EXPLAIN`：单次结果页底部的说明段落；
   * :attr:`INJECT_CHOICES`：注水方式下拉框；``DEFAULT_P`` / ``DEFAULT_INJECT`` /
     ``FALLBACK_ACCENT`` / ``INTRO_STATUS`` / ``HINTS`` / ``CRITERION_STATUS`` /
     ``INJECT_STATUS``：初始值与文案。

2. **模型适配**（4 个方法）：

   * :meth:`_create_model`：按界面参数造模型；
   * :meth:`_active_view`：把模型结果归一化成 :class:`ActiveView`；
   * :meth:`_model_functions`：给出批量统计 / 曲线扫描要调的两个模型函数；
   * :meth:`_run_once`：算一次过程（默认 ``model.simulate``，必要时覆盖）。

3. **画布与指标**（绘制钩子，见 :mod:`~awe_math.ui.tk.views.canvas` 与
   :mod:`~awe_math.ui.tk.views.results`）：``_draw_base`` / ``_apply_active`` /
   ``_layer_color`` / ``_legend_items`` / ``_fill_extra_rows`` / ``_size_text``。

基类负责的**共性**：三栏布局与卡片、参数与判据的状态机、防抖重绘、逐层动画、点击注水、
指标刷新、历史表、后台批量统计与曲线扫描、快捷键与资源释放。

界面结构（两个模型完全一致）
----------------------------
* 左：参数 / 高级选项 / 操作 / 批量统计 / 曲线扫描 五张卡片 + 停止按钮；
* 中：画布 + 图例条；
* 右：单次结果 / 批量统计 / P(p) 曲线 三个标签页；
* 下：状态栏 + 进度条。

成功判据决定「什么算成功」，也决定界面上的说法：``span``（贯通）判定整片区域是否存在
顶行 ↔ 底行的纵贯簇 —— 这是 ``p_c`` 对应的判据；``origin``（起点）额外要求注水点落在这
个簇里；``area``（面积）判定活动面积是否达到设定比例 —— 没有固定临界值。
"""

from __future__ import annotations

import queue
import random
import threading
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ....models import _options
from ..theme import ACCENT, BG, DIM, FAINT, WARN, make_accent_button
from .canvas import CanvasMixin
from .common import MAX_SIZE, ActiveView, Terms, label, parse_int, pick, spec_defaults
from .controls import SidebarMixin
from .jobs import JobsMixin
from .results import ResultPanelMixin

__all__ = ["PercolationViewBase"]

#: 面积判据阈值的兜底值（spec 未声明 ``threshold`` 参数时使用）。
#: 这里刻意不引用任何具体模型的常量——工具箱不认识模型。
FALLBACK_THRESHOLD = 0.5


class PercolationViewBase(JobsMixin, SidebarMixin, ResultPanelMixin, CanvasMixin):
    """桌面视图的共享骨架（子类只需给数据 + 少量钩子）。"""

    # ==================================================================
    # 子类提供的「数据」
    # ==================================================================
    #: 术语表（决定界面全部文案的用词）
    TERMS: Terms = Terms()
    #: 单次结果页的指标行：``((标题, vals 键), ...)``
    STAT_ROWS: Sequence[Tuple[str, str]] = ()
    #: 单次结果页底部的说明段落
    EXPLAIN: str = ""
    #: 注水方式下拉框（中文标签 -> 模型取值）
    INJECT_CHOICES: Mapping[str, str] = {}
    #: 初始 p 与注水方式（没有 spec 时的回退值）
    DEFAULT_P: float = 0.5
    DEFAULT_INJECT: str = "top"
    #: 强调色回退值（``spec.accent`` 缺失时使用）
    FALLBACK_ACCENT: str = ACCENT
    #: 状态栏初始文案
    INTRO_STATUS: str = "就绪：拖动滑块调整 p，程序会自动重绘网格。"
    #: 切换判据时的状态栏文案（键同 ``CRITERION_CHOICES``）
    CRITERION_STATUS: Mapping[str, str] = {}
    #: 切换注水方式时的状态栏文案（键同 ``CRITERION_CHOICES``，值里可用 ``{inject}``）
    INJECT_STATUS: Mapping[str, str] = {}
    #: 顶部标题栏右侧的快捷键提示
    HINTS: str = ""

    # ==================================================================
    # 两个模型共用的选项词表（放在类上便于子类覆盖与引用）
    # ==================================================================
    CRITERION_CHOICES: Mapping[str, str] = _options.CRITERION_CHOICES
    LATTICE_CHOICES: Mapping[str, str] = _options.LATTICE_CHOICES
    DIRECTION_CHOICES: Mapping[str, str] = _options.DIRECTION_CHOICES

    # ==================================================================
    # 初始化
    # ==================================================================
    def __init__(self, root: tk.Tk, host: tk.Misc, spec=None) -> None:
        self.root = root
        self.host = host
        self.spec = spec
        defaults = spec_defaults(spec, self.DEFAULT_P)
        init_p = float(defaults.get("p", self.DEFAULT_P))
        init_rows = int(defaults.get("rows", 30) or 30)
        init_cols = int(defaults.get("cols", init_rows) or init_rows)
        init_lattice = pick(self.LATTICE_CHOICES, defaults.get("lattice"), "square")
        init_direction = pick(self.DIRECTION_CHOICES, defaults.get("direction"), "undirected")
        init_inject = pick(self.INJECT_CHOICES, defaults.get("inject"), self.DEFAULT_INJECT)
        init_criterion = pick(self.CRITERION_CHOICES, defaults.get("criterion"), "span")
        init_threshold = float(defaults.get("threshold", FALLBACK_THRESHOLD) or FALLBACK_THRESHOLD)

        # ---------------- 模型与状态 ----------------
        self.model = self._create_model(
            rows=init_rows, cols=init_cols, p=init_p, rng=random.Random(),
            lattice=init_lattice, direction=init_direction, inject=init_inject,
            criterion=init_criterion, threshold=init_threshold,
        )
        self.result: Optional[Any] = None
        self._active_set: set = set()        # 当前已显示的（活动）单元
        self._shown_layers = 0               # 已显示的层数
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
        self._scan_results: List[Any] = []
        self._scan_meta: Tuple[int, int] = (0, 0)        # 曲线对应的 (行数, 每点次数)
        self._scan_cols = 0                              # 曲线对应的列数
        self._scan_lattice = self.model.lattice          # 曲线对应的格子类型
        self._scan_direction = self.model.direction      # 曲线对应的方向模式
        self._scan_inject = self.model.inject            # 曲线对应的注水方式
        self._scan_criterion = self.model.criterion      # 曲线对应的成功判据
        self._scan_threshold = init_threshold            # 曲线对应的面积判据阈值
        self._scan_pc = self.model.theoretical_pc        # 曲线对应的阈值（可能为 None）

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
        self.var_lattice = tk.StringVar(value=label(self.LATTICE_CHOICES, init_lattice))
        self.var_direction = tk.StringVar(value=label(self.DIRECTION_CHOICES, init_direction))
        self.var_inject = tk.StringVar(value=label(self.INJECT_CHOICES, init_inject))
        self.var_criterion = tk.StringVar(
            value=label(self.CRITERION_CHOICES, init_criterion)
        )
        self.var_status = tk.StringVar(value=self.INTRO_STATUS)
        #: 统计面板里随判据变化的行标题（key -> Label 控件）
        self._stat_labels: Dict[str, ttk.Label] = {}

        self.vals: Dict[str, tk.StringVar] = {
            key: tk.StringVar(value="-") for _label_text, key in self.STAT_ROWS
        }
        for key in ("b_p", "b_trials", "b_success", "b_prob", "b_mean", "b_err", "b_time"):
            self.vals[key] = tk.StringVar(value="-")

        self._accent_btn = make_accent_button(
            root, getattr(spec, "accent", self.FALLBACK_ACCENT))
        self._build_ui()
        self._redraw_curve()

        # 定时任务句柄要留着：视图被切换 / 关闭时必须取消，
        # 否则挂起的回调会继续访问已经销毁的画布（TclError）。
        self._poll_job: Optional[str] = self.root.after(80, self._poll_queue)
        self._first_job: Optional[str] = self.root.after(60, self.regenerate)

    @property
    def _terms(self) -> Terms:
        """术语表的短别名（各 mixin 内部统一用它，子类只覆盖 :attr:`TERMS`）。"""
        return self.TERMS

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

    def _build_status_bar(self) -> None:
        # 状态栏挂在宿主容器的第 1 行（画布下方）
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

    def _current_criterion(self) -> str:
        return pick(self.CRITERION_CHOICES, self.var_criterion.get(), "span")

    def _current_threshold(self) -> float:
        try:
            value = float(self.var_threshold.get())
        except (TypeError, ValueError):
            value = FALLBACK_THRESHOLD
        return min(1.0, max(0.05, value))

    def _current_seed(self) -> Optional[int]:
        """统计用的随机种子：≥0 时批量统计/曲线完全可复现，-1 表示随机。

        固定种子后，「同一片区域上换判据 / 换注水方式」的横向比较才是严格可比的
        （否则只能看到蒙特卡洛噪声，例如贯通判据本应与注水方式无关）。
        """
        try:
            value = int(float(self.var_seed.get()))
        except (TypeError, ValueError):
            return None
        return None if value < 0 else value

    def _criterion_rule(self) -> str:
        """当前判据的简短说法（界面各处复用）。"""
        if self.model.criterion == "span":
            return f"判据 贯通（{self._terms.arena}有无纵贯簇）"
        if self.model.criterion == "origin":
            return "判据 起点纵贯（注水点的簇碰顶又碰底）"
        return f"判据 面积 ≥ {self.model.threshold:.0%}"

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
        lab = self._stat_labels.get(key)
        if lab is not None:
            lab.configure(text=text)

    def _update_pc_label(self) -> None:
        """显示临界值说明：贯通判据给出 p_c，面积判据说明它没有固定阈值。"""
        self.lbl_pc.configure(
            text=self.model.pc_label,
            foreground=WARN if not self.model.pc_applies else DIM,
        )

    def _rebuild_after_option_change(self, message: str) -> None:
        """格子 / 方向 / 注水方式变化后：作废旧结果、重建区域并重绘。"""
        self._cancel_animation()
        self._discard_result()
        self.model.regenerate()
        self._update_pc_label()
        self.regenerate()
        self.var_status.set(message)

    def _on_lattice_change(self) -> None:
        """切换格子类型：整片区域的连接关系都变了，必须重建。"""
        lattice = pick(self.LATTICE_CHOICES, self.var_lattice.get(), "square")
        if lattice == self.model.lattice:
            return
        self.model.lattice = lattice
        self._rebuild_after_option_change(
            f"已切换为{self.model.lattice_name}：{self.model.pc_label}。"
        )

    def _on_direction_change(self) -> None:
        """切换方向模式：可达关系变了，重建区域并重新判定。"""
        direction = pick(self.DIRECTION_CHOICES, self.var_direction.get(), "undirected")
        if direction == self.model.direction:
            return
        self.model.direction = direction
        self._rebuild_after_option_change(
            f"已切换为「{self.model.direction_name}」：{self.model.pc_label}。"
        )

    def _on_inject_change(self) -> None:
        """切换注水方式：区域不变，只需重新挑注水点并重绘。"""
        inject = pick(self.INJECT_CHOICES, self.var_inject.get(), self.DEFAULT_INJECT)
        if inject == self.model.inject:
            return
        self.model.inject = inject
        template = self.INJECT_STATUS.get(self.model.criterion, "")
        self._rebuild_after_option_change(
            template.format(inject=self.model.inject_name) if template
            else f"注水方式：{self.model.inject_name}。"
        )

    def _on_criterion_change(self) -> None:
        """切换成功判据：区域不用重建，但结论、统计与曲线的含义都变了。"""
        criterion = self._current_criterion()
        if criterion == self.model.criterion:
            return
        self._cancel_animation()
        self._discard_result()
        self.model.criterion = criterion
        self._refresh_criterion_texts()
        self._update_pc_label()
        self.regenerate()
        self.var_status.set(self.CRITERION_STATUS.get(criterion, ""))

    def _on_p_change(self, value: Optional[str] = None) -> None:
        """滑块变化：更新显示，并防抖地重新生成区域。"""
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
            # 尺寸变化会重建内部结构，旧尺寸的动画结果必须立即作废，否则渲染会越界
            self._cancel_animation()
            self._discard_result()
            self.model.rows, self.model.cols = rows, cols
            self.model.regenerate()
        self._debounce_regenerate(delay=60)

    def _discard_result(self) -> None:
        """丢弃当前结果（区域尺寸 / 模式变化后调用）。"""
        self.result = None
        self._shown_layers = 0
        self._active_set = set()

    def _debounce_regenerate(self, delay: int = 160) -> None:
        if self._regenerate_job is not None:
            self.root.after_cancel(self._regenerate_job)
        self._regenerate_job = self.root.after(delay, self.regenerate)

    def _sync_model_params(self) -> None:
        """把界面上的参数同步进模型。

        滑块 / 下拉框改动会做防抖（延迟重绘），用户可能在防抖触发前就点了按钮，
        因此每次操作前都强制同步一次 p、行列数、格子类型、方向模式与注水方式。
        """
        p = round(self.var_p.get(), 2)
        rows, cols = self._current_shape()
        lattice = pick(self.LATTICE_CHOICES, self.var_lattice.get(), "square")
        direction = pick(self.DIRECTION_CHOICES, self.var_direction.get(), "undirected")
        inject = pick(self.INJECT_CHOICES, self.var_inject.get(), self.DEFAULT_INJECT)
        # 判据与阈值都不改变结构，直接同步即可
        criterion = self._current_criterion()
        if criterion != self.model.criterion:
            self._discard_result()
        self.model.criterion = criterion
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
            self.model.regenerate(p)      # 结构 / 注水点变了必须重建
            if structural:
                self._update_pc_label()
        else:
            self.model.p = p

    # ==================================================================
    # 结果描述
    # ==================================================================
    def _result_summary(self) -> str:
        """当前配置的简短描述，用于状态栏与结论行。"""
        model = self.model
        return (f"{model.lattice_name} {model.rows}×{model.cols} · "
                f"{model.direction_name} · 注水 {model.inject_name} · "
                f"{self._criterion_rule()}")

    def _verdict_phrase(self, view: ActiveView) -> str:
        """把一次结果说成一句话（随判据变化）。"""
        terms = self._terms
        if view.criterion == "span":
            return (f"{terms.arena}存在纵贯簇" if view.spans
                    else f"{terms.arena}没有纵贯簇")
        if view.criterion == "origin":
            if view.origin_spans:
                return f"起点纵贯（{terms.origin_cluster_phrase}碰顶又碰底）"
            if view.spans:
                return f"起点未纵贯（{terms.arena}有纵贯簇，但注水点在簇外）"
            return f"起点未纵贯，{terms.arena}也没有纵贯簇"
        return "面积判据达标" if view.engulfed else "面积判据未达标"

    # ==================================================================
    # 生命周期与快捷操作（由 DesktopShell 调用）
    # ==================================================================
    def on_key(self, key: str) -> None:
        """响应全局快捷键：空格播放动画，R 重新生成。"""
        k = key.lower()
        if k in (" ", "space"):
            self.start_animation()
        elif k == "r":
            self.regenerate()

    # ==================================================================
    # 交给子类的「模型适配」钩子
    # ==================================================================
    def _create_model(self, **kwargs):
        """按界面参数创建模型实例（``kwargs`` 与模型构造函数同名）。"""
        raise NotImplementedError

    def _active_view(self) -> ActiveView:
        """把模型结果归一化成 :class:`ActiveView`（``self.result`` 非空时调用）。"""
        raise NotImplementedError

    def _model_functions(self):
        """给出 ``(批量统计函数, 曲线扫描函数)``，供后台任务调用。"""
        raise NotImplementedError

    def _run_once(self, origins: Optional[Sequence[int]] = None):
        """算一次过程（默认调用 ``model.simulate``；方法名不同时覆盖）。"""
        return self.model.simulate(origins)
