# -*- coding: utf-8 -*-
"""
桌面视图基类：万能骨架 + 渗流特化子类
========================================

桌面视图层分成两层，避免"想要一个界面"就得先成为渗流模型：

* :class:`ModelViewBase` —— **万能骨架，不认识任何模型**。它提供三栏布局、状态栏与进度条、
  后台任务机制（线程 / 队列 / 取消）、生命周期与快捷键，以及**由 ``spec.params`` 自动生成
  的参数表单**（见 :mod:`~prismath.ui.tk.kit.form`）与**由 ``spec.actions`` 生成的动作按钮**。
  一个模型只要有了 ``ModelSpec``，继承本类就能立刻拿到一套可用的桌面界面（跑动作 + 看结果）。
* :class:`PercolationViewBase` —— **渗流特化子类**。它在万能骨架之上补上"概率 p + 格子 +
  判据 + 逐层蔓延"这套语义：参数/判据状态机、逐层动画画布、批量统计与 P(p) 曲线、纵贯簇
  高亮等。边渗流与点渗流两个视图都继承它，只需给出术语表、指标行与几个画布钩子。

留给子类的三类东西（渗流特化部分）
----------------------------------
1. **数据**（类属性，最省事）：

   * :attr:`PercolationViewBase.TERMS`：术语表（网格/格地、节点/格、浸润/蔓延……）；
   * :attr:`PercolationViewBase.STAT_ROWS`：单次结果页的指标行 ``((标题, vals 键), ...)``；
   * :attr:`PercolationViewBase.EXPLAIN`：单次结果页底部的说明段落；
   * :attr:`PercolationViewBase.INJECT_CHOICES`：注水方式下拉框；``DEFAULT_P`` /
     ``DEFAULT_INJECT`` / ``FALLBACK_ACCENT`` / ``INTRO_STATUS`` / ``HINTS`` /
     ``CRITERION_STATUS`` / ``INJECT_STATUS``：初始值与文案。

2. **模型适配**（4 个方法）：

   * :meth:`PercolationViewBase._create_model`：按界面参数造模型；
   * :meth:`PercolationViewBase._active_view`：把模型结果归一化成 :class:`ActiveView`；
   * :meth:`PercolationViewBase._model_functions`：给出批量统计 / 曲线扫描要调的两个模型函数；
   * :meth:`PercolationViewBase._run_once`：算一次过程（默认 ``model.simulate``）。

3. **画布与指标**（绘制钩子，见 :mod:`~prismath.ui.tk.kit.canvas` 与
   :mod:`~prismath.ui.tk.kit.results`）：``_draw_base`` / ``_apply_active`` /
   ``_layer_color`` / ``_legend_items`` / ``_fill_extra_rows`` / ``_size_text``。

万能骨架（:class:`ModelViewBase`）则负责与模型无关的共性：三栏布局与滚动侧栏、参数表单、
动作分派、后台任务轮询、状态栏与进度、快捷键与资源释放。它要求"模型对象长什么样"这一点，
已写成显式契约 :mod:`~prismath.ui.tk.kit.protocols`（``PercolationModel`` 等）。
"""

from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ....models import _options
from ..theme import (
    ACCENT,
    BG,
    DIM,
    FAINT,
    FONT_MONO,
    PANEL,
    WARN,
    ScrollArea,
    make_accent_button,
)
from .canvas import CanvasMixin
from .common import (
    MAX_SIZE,
    ActiveView,
    Terms,
    label,
    pick,
    spec_defaults,
)
from .controls import SidebarMixin
from .criteria import DEFAULT_CRITERIA, Criterion
from .form import ParamFormMixin
from .jobs import JobsMixin
from .protocols import ViewContract
from .results import ResultPanelMixin

__all__ = ["ModelViewBase", "PercolationViewBase"]

#: 面积判据阈值的兜底值（spec 未声明 ``threshold`` 参数时使用）。
#: 这里刻意不引用任何具体模型的常量——工具箱不认识模型。
FALLBACK_THRESHOLD = 0.5


class ModelViewBase(ParamFormMixin, ViewContract):
    """**通用**桌面视图骨架（不认识任何模型）。

    子类只需在 ``__init__`` 前提供 :attr:`TERMS` / :attr:`FALLBACK_ACCENT` / :attr:`INTRO_STATUS`
    等类属性，并按需覆盖 ``_build_center`` / ``_build_right`` / ``_setup_state`` / ``_after_build``
    这些钩子；参数表单与动作按钮会自动由 ``spec`` 生成。

    ``_setup_state`` 里应完成"模型实例与状态"的初始化，``_build_*`` 里完成控件构建。
    """

    # ---------------- 子类可覆盖的类属性 ----------------
    #: 术语表（决定状态栏等通用文案；渗流子类会整套覆盖）
    TERMS: Terms = Terms()
    #: 强调色回退值（``spec.accent`` 缺失时使用）
    FALLBACK_ACCENT: str = ACCENT
    #: 状态栏初始文案
    INTRO_STATUS: str = "就绪。"
    #: 顶部标题栏右侧的快捷键提示
    HINTS: str = ""

    # ==================================================================
    # 初始化
    # ==================================================================
    def __init__(self, root: tk.Tk, host: Any, spec: Any = None) -> None:
        self.root = root
        self.host = host
        self.spec = spec

        # ---------------- 通用运行时状态 ----------------
        self._alive = True
        self._busy = False
        self._queue: "queue.Queue" = queue.Queue()
        self._cancel = threading.Event()
        self._action_buttons: List[ttk.Button] = []
        self._anim_job: Optional[str] = None
        self._regenerate_job: Optional[str] = None
        self._redraw_job: Optional[str] = None
        self._poll_job: Optional[str] = None
        self._first_job: Optional[str] = None

        #: ``spec.params`` 生成的 Tk 变量：``参数 key -> Variable``
        self.param_vars: Dict[str, tk.Variable] = {}
        self.var_status = tk.StringVar(value=self.INTRO_STATUS)

        self._setup_state()                     # 子类：造模型与状态变量
        self._accent_btn = make_accent_button(
            root, getattr(spec, "accent", self.FALLBACK_ACCENT))
        self._build_ui()                        # 子类可覆盖三个 _build_* 钩子
        self._after_build()                     # 子类：构建完成后的收尾（如首次生成 / 画曲线）
        self._poll_job = self.root.after(80, self._poll_queue)

    @property
    def _terms(self) -> Terms:
        """术语表的短别名（各 mixin 内部统一用它，子类只覆盖 :attr:`TERMS`）。"""
        return self.TERMS

    # ------------------------------------------------------------------
    # 供子类覆盖的钩子
    # ------------------------------------------------------------------
    def _setup_state(self) -> None:
        """初始化模型实例与状态变量（``_build_ui`` 之前调用）。默认什么都不做。"""

    def _after_build(self) -> None:
        """界面构建完成后的收尾（默认什么都不做）。"""

    def _build_ui(self) -> None:
        self.host.configure(bg=BG)
        self.host.columnconfigure(0, weight=0)   # 左侧控制栏
        self.host.columnconfigure(1, weight=1)   # 中央画布 / 结果区
        self.host.columnconfigure(2, weight=0)   # 右侧数据面板
        self.host.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_center()
        self._build_right()
        self._build_status_bar()

    def _build_status_bar(self) -> None:
        # 状态栏挂在宿主容器的第 1 行（内容区下方）
        bar = ttk.Frame(self.host)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=16, pady=(2, 10))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, textvariable=self.var_status, style="Dim.TLabel", anchor="w").grid(
            row=0, column=0, sticky="ew"
        )
        self.progress = ttk.Progressbar(bar, length=260, mode="determinate")
        self.progress.grid(row=0, column=1, padx=(12, 0))

    @staticmethod
    def _card(parent: tk.Widget, title: str) -> ttk.LabelFrame:
        """造一张侧栏卡片（统一样式与间距）。"""
        card = ttk.LabelFrame(
            parent, text=f" {title} ", style="Card.TLabelframe",
            padding=(12, 8, 12, 10),
        )
        card.pack(fill="x", pady=(0, 6))
        return card

    # ------------------------------------------------------------------
    # 通用侧栏：spec.params 表单 + spec.actions 按钮
    # ------------------------------------------------------------------
    def _build_sidebar(self) -> None:
        area = ScrollArea(self.host, width=306)
        area.outer.grid(row=0, column=0, sticky="ns", padx=(14, 7), pady=12)
        self._sidebar_area = area
        side = area.inner

        self._build_top_cards(side)        # 常用控件（如"动画"卡片）放侧栏最上面
        self._build_param_cards(side)
        self._build_action_card(side)
        self._build_extra_cards(side)

        self.btn_stop = ttk.Button(
            side, text="■ 停止后台任务", style="Danger.TButton",
            command=self.stop_work, state="disabled",
        )
        self.btn_stop.pack(fill="x", pady=(2, 0))
        area.bind_wheel()

    def _build_action_card(self, parent: tk.Widget) -> None:
        """按 ``spec.actions`` 生成动作按钮（通用模型点一下就用默认参数跑一次）。"""
        actions: Tuple[Any, ...] = tuple(getattr(self.spec, "actions", ()) or ())
        if not actions:
            return
        card = self._card(parent, "操作")
        for action in actions:
            style = self._accent_btn if getattr(action, "kind", "") == "primary" else "TButton"
            btn = ttk.Button(
                card, text=getattr(action, "label", action.key), style=style,
                command=lambda key=action.key: self.run_action(key),
            )
            btn.pack(fill="x", pady=(0, 4))
            self._action_buttons.append(btn)

    def _build_top_cards(self, parent: tk.Widget) -> None:
        """侧栏**最上面**的自定义卡片（默认没有）。

        与 :meth:`_build_extra_cards` 对称：有些控件用得太频繁（例如"动画 / 播放"卡片），
        放在参数与动作下方要滚到底才看得见，所以给它一个置顶的位置。
        """

    def _build_extra_cards(self, parent: tk.Widget) -> None:
        """给子类追加自定义卡片的位置（默认没有，排在参数与动作卡片之后）。"""

    def _build_center(self) -> None:
        """通用中央区：一块只读文本，用来展示动作返回的 JSON 结果。"""
        center = ttk.Frame(self.host, style="Panel.TFrame", padding=12)
        center.grid(row=0, column=1, sticky="nsew", pady=12)
        center.rowconfigure(1, weight=1)
        center.columnconfigure(0, weight=1)
        ttk.Label(center, text="运行结果", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8))
        self.output = tk.Text(
            center, bg=PANEL, fg="#172033", insertbackground="#172033", relief="flat",
            wrap="none", padx=10, pady=8, font=FONT_MONO,
        )
        self.output.grid(row=1, column=0, sticky="nsew")
        self._render_result({"提示": "点击左侧动作按钮，用当前参数运行一次；结果以 JSON 显示。"})

    def _build_right(self) -> None:
        """通用右侧区：模型说明卡片。"""
        panel = ttk.Frame(self.host, style="Panel.TFrame", padding=14)
        panel.grid(row=0, column=2, sticky="nsew", padx=(7, 14), pady=12)
        panel.columnconfigure(0, weight=1)
        spec = self.spec
        if spec is None:
            return
        ttk.Label(panel, text=spec.name, style="Card.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(panel, text=spec.summary, style="CardDim.TLabel", wraplength=320,
                  justify="left").grid(row=1, column=0, sticky="w", pady=(6, 0))
        if spec.description:
            ttk.Label(panel, text=spec.description, style="CardDim.TLabel", wraplength=320,
                      justify="left").grid(row=2, column=0, sticky="w", pady=(8, 0))

    # ------------------------------------------------------------------
    # 通用动作分派（走 ModelSpec.handler）
    # ------------------------------------------------------------------
    def run_action(self, key: str) -> None:
        """用当前参数运行一次动作，把结果（或错误）交给 :meth:`_render_result` 渲染。

        状态栏先写一句通用文案，**渲染器可以覆盖它**（:meth:`_render_result` 里改
        ``var_status`` 即可）——于是自定义视图不必为了换一句话而重写本方法。
        """
        if self.spec is None:
            return
        try:
            result = self.spec.run(key, self.current_params(), {})
        except Exception as exc:          # 把模型异常直接展示出来，方便排查
            message = f"{type(exc).__name__}: {exc}"
            self.var_status.set(f"运行失败：{message}")
            self._render_result({"error": message})
            return
        self.var_status.set(f"动作「{key}」已完成。")
        self._render_result(result)

    def _render_result(self, payload: Any) -> None:
        """把结果渲染进 :attr:`output`（通用中央区的只读文本框）。"""
        output = getattr(self, "output", None)
        if output is None:
            return
        if isinstance(payload, str):
            text = payload
        else:
            try:
                text = json.dumps(payload, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                text = str(payload)
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("1.0", text)
        output.configure(state="disabled")

    # ------------------------------------------------------------------
    # 通用后台任务机制（线程 / 队列 / 轮询 / 取消）
    # ------------------------------------------------------------------
    def _submit(self, job: Callable[[], None]) -> None:
        """把一个后台任务丢进线程执行（任务内部只许通过 ``self._queue`` 回传消息）。"""
        threading.Thread(target=job, daemon=True).start()

    def _set_busy(self, busy: bool, text: str = "") -> None:
        """切换忙碌态：执行中的按钮禁用、停止按钮启用。"""
        self._busy = busy
        for btn in self._action_buttons:
            btn.configure(state="disabled" if busy else "normal")
        btn_stop = getattr(self, "btn_stop", None)
        if btn_stop is not None:
            btn_stop.configure(state="normal" if busy else "disabled")
        if text:
            self.var_status.set(text)

    def stop_work(self) -> None:
        """请求停止后台任务（后台线程在每轮迭代检查取消标志）。"""
        self._cancel.set()
        self.var_status.set("正在停止…")

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
        self._poll_job = self.root.after(70, self._poll_queue)

    def _handle_message(self, kind: str, payload: Any) -> None:
        """处理后台线程回传的消息；子类可覆盖并 ``super()`` 兜底。"""
        if kind == "error":
            self._set_busy(False)
            messagebox.showerror("出错了", str(payload))
            self.var_status.set(str(payload))

    # ------------------------------------------------------------------
    # 生命周期与快捷键
    # ------------------------------------------------------------------
    def on_key(self, key: str) -> None:
        """万能骨架不响应快捷键（渗流子类会覆盖：空格播放动画、R 重新生成）。"""

    def shutdown(self) -> None:
        """视图被关闭（或切换到别的模型）时释放资源并停止后台任务。"""
        self._alive = False
        for name in ("_anim_job", "_regenerate_job", "_redraw_job", "_poll_job", "_first_job"):
            job = getattr(self, name, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, name, None)
        self._cancel.set()          # 通知后台线程停止

    # ------------------------------------------------------------------
    # 参数变更（ParamFormMixin 的默认回调 + 便捷取用）
    # ------------------------------------------------------------------
    def _on_param_change(self, key: str) -> None:
        """通用模型的参数只影响下一次动作，默认仅刷新数值标签。"""
        super()._on_param_change(key)


class PercolationViewBase(JobsMixin, SidebarMixin, ResultPanelMixin, CanvasMixin,
                          ModelViewBase):
    """渗流类模型的桌面视图骨架：在万能骨架上补「概率 + 格子 + 判据 + 逐层蔓延」语义。"""

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
    #: 判据 -> 策略对象（徽章 / 结论 / 曲线标注都由它给出）。
    #: 模型要扩展判据，覆盖这个映射即可，不必改工具箱。
    CRITERIA: Mapping[str, Criterion] = DEFAULT_CRITERIA

    def _criterion_strategy(self, key: str) -> Criterion:
        """按判据名取策略对象（未知判据退化为贯通判据，保证界面不崩）。"""
        return self.CRITERIA.get(key) or DEFAULT_CRITERIA["span"]

    # ==================================================================
    # 状态初始化（模型 + 变量 + 扫描元信息）
    # ==================================================================
    def _setup_state(self) -> None:
        spec = self.spec
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
        # rng=None：交给内核自己的默认随机源（每次进模型都是一个新开局）。
        # 别在这里自己造随机数对象 —— 内核只接受 None / int / numpy Generator，
        # 传 ``random.Random()`` 会在 ``default_rng`` 里直接抛异常，窗口就只剩空壳。
        self.model = self._create_model(
            rows=init_rows, cols=init_cols, p=init_p, rng=None,
            lattice=init_lattice, direction=init_direction, inject=init_inject,
            criterion=init_criterion, threshold=init_threshold,
        )
        self.result: Optional[Any] = None
        self._active_set: set = set()        # 当前已显示的（活动）单元
        self._shown_layers = 0               # 已显示的层数

        # 画布元素索引（用于局部刷新，避免整图重绘）
        self._node_items: List[Optional[int]] = []
        self._edge_items: Dict[Tuple[int, int], int] = {}
        self._node_xy: List[Tuple[float, float]] = []
        self._cell = 10.0
        #: 当前底图对应的 (行数, 列数, 格子, 方向)，用于增量上色时校验
        self._drawn_shape: Tuple[int, int, str, str] = (0, 0, "", "")

        # 曲线元信息
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
        #: 统计面板里随判据变化的行标题（key -> Label 控件）
        self._stat_labels: Dict[str, ttk.Label] = {}

        self.vals: Dict[str, tk.StringVar] = {
            key: tk.StringVar(value="-") for _label_text, key in self.STAT_ROWS
        }
        for key in ("b_p", "b_trials", "b_success", "b_prob", "b_mean", "b_err", "b_time"):
            self.vals[key] = tk.StringVar(value="-")

    def _after_build(self) -> None:
        """界面构建完成：刷新判据文案、画一次空曲线，并安排首次生成。"""
        self._refresh_criterion_texts()   # 按初始判据修正行标题
        self._redraw_curve()
        # 定时任务句柄要留着：视图被切换 / 关闭时必须取消，
        # 否则挂起的回调会继续访问已经销毁的画布（TclError）。
        # 排队到下一轮 Tk 事件循环即可；固定等待 60ms 会让首次打开时画布短暂为空，
        # 在高 DPI 或窗口刚布局完成时尤其容易被用户看到。
        self._first_job = self.root.after(0, self.regenerate)

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
        """当前判据的简短说法（界面各处复用）——由判据策略给出。"""
        return self._criterion_strategy(self.model.criterion).rule(self.model, self._terms)

    def _refresh_criterion_texts(self) -> None:
        """判据变化后，刷新那些「随判据改变含义」的界面文案。"""
        strategy = self._criterion_strategy(self.model.criterion)
        active = strategy.uses_threshold
        self._set_stat_label("b_success", f"{strategy.head}次数")
        self._set_stat_label("b_prob", f"{strategy.head}概率")
        self.lbl_threshold.configure(
            text="面积判据阈值" if active else "面积判据阈值（面积判据下才生效）",
            foreground=DIM if active else FAINT,
        )
        try:
            self.tree.heading("success", text=strategy.short)
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
        """按界面参数创建模型实例。

        默认走 ``spec.factory``：模型只要声明一次「由参数造模型」的函数，
        **数据级契约**（``spec.handler``）与**对象级契约**（桌面视图）就共用同一处换算，
        视图不必再写一遍。子类也可以直接覆盖本方法。

        注意：``kwargs`` 里已经是**模型内部取值**（格子 / 方向 / 注水 / 判据均已翻译过）。
        """
        factory = getattr(self.spec, "factory", None)
        if factory is not None:
            return factory(kwargs)
        raise NotImplementedError(
            f"模型 {getattr(self.spec, 'key', '?')} 未提供 spec.factory；"
            "请在 spec 里声明 factory，或由视图覆盖 _create_model"
        )

    def _model_functions(self):
        """给出 ``(批量统计函数, 曲线扫描函数)``，供后台任务调用。

        默认取 ``spec.batch`` / ``spec.scan``（签名见
        :class:`~prismath.ui.tk.kit.protocols.BatchRunner` / ``ScanRunner``）。
        """
        batch = getattr(self.spec, "batch", None)
        scan = getattr(self.spec, "scan", None)
        if batch is None or scan is None:
            raise NotImplementedError(
                f"模型 {getattr(self.spec, 'key', '?')} 未提供 spec.batch / spec.scan；"
                "请在 spec 里声明它们，或由视图覆盖 _model_functions"
            )
        return batch, scan

    def _active_view(self) -> ActiveView:
        """把模型结果归一化成 :class:`ActiveView`（``self.result`` 非空时调用）。"""
        raise NotImplementedError

    def _run_once(self, origins: Optional[Sequence[int]] = None):
        """算一次过程（默认调用 ``model.simulate``；方法名不同时覆盖）。"""
        return self.model.simulate(origins)
