# -*- coding: utf-8 -*-
"""
桌面视图与模型之间的**显式契约**
==================================

``ui/tk/kit`` 的骨架通过**鸭子类型**访问模型对象（``model.rows``、``model.regenerate()``、
``model.spanning_nodes()`` ……）。以往这份"隐式协议"只散落在实现里，新模型作者只能靠通读
基类代码来猜"我到底必须提供什么"，静态检查器也无从判断。

本模块把它写成**可执行的契约**：

* :class:`PercolationModel` —— 渗流类模型必须提供的属性与方法（``PercolationViewBase`` 所需）；
* :class:`SimResultLike` —— 单次结果对象必须有的字段（``_active_view`` 会读取）；
* :class:`BatchResultLike` —— 批量统计结果对象必须有的字段（结果面板与历史表会读取）；
* :class:`BatchRunner` / :class:`ScanRunner` —— ``_model_functions()`` 返回的两个可调用对象；
* :class:`ViewContract` —— 供各 mixin 继承的"视图共享属性"清单，仅用于 ``TYPE_CHECKING``，
  用来消掉静态检查器单独分析某个 mixin 时的 "Cannot access attribute" 告警，
  同时把"基类必须提供什么"写成一处可查的文档。

这些都是 :class:`typing.Protocol`（结构化类型）：**模型不需要显式继承它们**，只要长得像即可；
需要写新模型时，照这份契约实现方法名与属性名就足够了。
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    runtime_checkable,
)

if TYPE_CHECKING:                       # 仅类型检查期导入，运行时不引入 tkinter / 循环依赖
    import tkinter as tk
    from tkinter import ttk

    from .common import ActiveView, Terms
    from .criteria import Criterion

__all__ = [
    "PercolationModel",
    "SimResultLike",
    "BatchResultLike",
    "BatchRunner",
    "ScanRunner",
    "ViewContract",
]


# ----------------------------------------------------------------------
# 模型侧契约
# ----------------------------------------------------------------------
@runtime_checkable
class PercolationModel(Protocol):
    """渗流类模型（``PercolationViewBase`` 的 ``_create_model`` 返回值）必须满足的接口。

    属性读写：``rows`` / ``cols`` / ``p`` / ``lattice`` / ``direction`` / ``inject`` /
    ``criterion`` / ``threshold`` —— 基类的参数状态机会直接给这些字段赋值。
    """

    rows: int
    cols: int
    p: float
    lattice: str
    direction: str
    inject: str
    criterion: str
    threshold: float

    # ---------------- 只读属性 ----------------
    @property
    def node_count(self) -> int:
        """单元总数（画布、比例、历史表都用它）。"""
        ...

    @property
    def shape(self) -> Tuple[int, int]:
        """``(rows, cols)``；结果与底图是否一致靠它校验。"""
        ...

    @property
    def lattice_name(self) -> str:
        """格子类型的中文名（界面文案用）。"""
        ...

    @property
    def direction_name(self) -> str:
        """方向模式的中文名。"""
        ...

    @property
    def inject_name(self) -> str:
        """注水（起始）方式的中文名。"""
        ...

    @property
    def criterion_name(self) -> str:
        """当前成功判据的中文名。"""
        ...

    @property
    def theoretical_pc(self) -> Optional[float]:
        """当前（格子, 方向）组合的临界值；未知时返回 ``None``。"""
        ...

    @property
    def pc_applies(self) -> bool:
        """当前判据下 ``p_c`` 是否有意义（只有贯通判据为真）。"""
        ...

    @property
    def pc_is_estimate(self) -> bool:
        """临界值是蒙特卡洛估计（而非解析解 / 文献值）时为真。"""
        ...

    @property
    def pc_label(self) -> str:
        """临界值的展示文本（随判据变化）。"""
        ...

    # ---------------- 行为 ----------------
    def regenerate(self, p: Optional[float] = None, seed: Optional[int] = None) -> Any:
        """按当前结构重新随机生成区域。"""
        ...

    def simulate(self, origins: Optional[Sequence[int]] = None) -> "SimResultLike":
        """完整模拟一次，返回逐层结果（供动画与指标使用）。"""
        ...

    def source_nodes(self) -> Sequence[int]:
        """按注水方式给出注水点（画布描边用）。"""
        ...

    def spanning_nodes(self) -> Sequence[int]:
        """纵贯簇的单元清单（没有则空列表；判据关注的对象）。"""
        ...

    def is_open(self, a: int, b: int) -> bool:
        """两个单元之间的边 / 连接是否导通。"""
        ...

    def iter_all_edges(self) -> Any:
        """迭代所有边 ``(a, b)``（画布铺底用）。"""
        ...

    def traversable_neighbors(self, index: int) -> Any:
        """与 ``index`` 之间沿允许方向可走通的邻居（给已走过的路径上色用）。"""
        ...


@runtime_checkable
class SimResultLike(Protocol):
    """一次「逐层活动」结果对象：``_active_view`` 会把这些字段归一化成 :class:`ActiveView`。"""

    wet: Sequence[int]
    wet_count: int
    node_count: int
    layers: Sequence[Sequence[int]]
    origins: Sequence[int]
    spans: bool
    origin_spans: bool
    engulfed: bool
    spanning_count: int
    origin_in_spanning: bool
    criterion: str
    threshold: float
    elapsed: float
    depth: int
    shape: Tuple[int, int]


@runtime_checkable
class BatchResultLike(Protocol):
    """一批独立实验的统计结果：结果面板与历史表直接读取这些字段。"""

    p: float
    rows: int
    cols: int
    trials: int
    success: int
    probability: float
    mean_ratio: float
    stderr: float
    elapsed: float
    criterion: str
    criterion_name: str


# ----------------------------------------------------------------------
# 后台任务契约：``_model_functions()`` 返回的 (批量统计, 曲线扫描) 两个可调用对象
# ----------------------------------------------------------------------
class BatchRunner(Protocol):
    """批量统计函数：固定 ``p`` 做 ``trials`` 次独立实验。"""

    def __call__(
        self,
        rows: int = ...,
        cols: Optional[int] = ...,
        p: float = ...,
        trials: int = ...,
        rng: Any = ...,
        progress: Optional[Callable[..., None]] = ...,
        cancel: Any = ...,
        **options: Any,
    ) -> BatchResultLike:
        ...


class ScanRunner(Protocol):
    """曲线扫描函数：对一组 ``p`` 值各做 ``trials`` 次实验。"""

    def __call__(
        self,
        p_values: Sequence[float],
        rows: int = ...,
        cols: Optional[int] = ...,
        trials: int = ...,
        rng: Any = ...,
        progress: Optional[Callable[..., None]] = ...,
        cancel: Any = ...,
        **options: Any,
    ) -> Sequence[BatchResultLike]:
        ...


# ----------------------------------------------------------------------
# 视图共享属性契约（TYPE_CHECKING only）
# ----------------------------------------------------------------------
class ViewContract:
    """各 mixin 共享的宿主属性声明（**仅用于类型检查，运行时不定义任何东西**）。

    基类 :class:`~awe_math.ui.tk.kit.chart.ChartViewBase` /
    :class:`~awe_math.ui.tk.kit.base.ModelViewBase` / ``PercolationViewBase``
    与各 mixin（画布 / 侧栏 / 结果 / 后台任务）都继承本类，于是静态检查器在单独分析某个
    mixin 时也能看到 ``self.model``、``self.var_status`` 等属性的类型，不再报
    "Cannot access attribute"。这也把"基类必须提供什么"集中写在了这一处。
    """

    if TYPE_CHECKING:                       # pragma: no cover - 只在类型检查期存在
        # 宿主与元数据（``host`` / ``spec`` 交给 Any：它们被各 mixin 以多种方式使用）
        root: "tk.Tk"
        host: Any
        spec: Any
        model: Any
        canvas: "tk.Canvas"
        terms: "Terms"
        output: "tk.Text"

        # 侧栏 / 结果面板用到的类级选项词表（由 PercolationViewBase 提供）
        TERMS: "Terms"
        CRITERION_CHOICES: Mapping[str, str]
        LATTICE_CHOICES: Mapping[str, str]
        DIRECTION_CHOICES: Mapping[str, str]
        INJECT_CHOICES: Mapping[str, str]
        CRITERIA: Mapping[str, "Criterion"]

        # 状态与参数变量（由基类 / 侧栏 mixin 建立）
        var_status: "tk.StringVar"
        var_speed: "tk.IntVar"
        var_p: "tk.DoubleVar"
        var_rows: "tk.IntVar"
        var_cols: "tk.IntVar"
        var_threshold: "tk.StringVar"
        var_seed: "tk.StringVar"
        var_trials: "tk.StringVar"
        var_scan_trials: "tk.StringVar"
        var_scan_step: "tk.StringVar"
        var_lattice: "tk.StringVar"
        var_direction: "tk.StringVar"
        var_inject: "tk.StringVar"
        var_criterion: "tk.StringVar"

        # 控件
        lbl_p: "ttk.Label"
        lbl_threshold: "ttk.Label"
        lbl_pc: "ttk.Label"
        btn_anim: "ttk.Button"
        btn_regen: "ttk.Button"
        btn_instant: "ttk.Button"
        btn_batch: "ttk.Button"
        btn_scan: "ttk.Button"
        btn_stop: "ttk.Button"
        progress: "ttk.Progressbar"
        notebook: "ttk.Notebook"
        tab_single: "ttk.Frame"
        tab_batch: "ttk.Frame"
        tab_curve: "ttk.Frame"
        tree: "ttk.Treeview"
        badge: "tk.Label"
        figure: Any
        ax: Any
        figure_canvas: Any
        _accent_btn: str
        _sidebar_area: Any
        _param_value_labels: dict

        # 运行时状态
        result: Optional[Any]
        vals: Any
        _action_buttons: list
        _stat_labels: dict
        _alive: bool
        _busy: bool
        _cancel: Any
        _queue: Any
        _node_xy: list
        _node_items: list
        _edge_items: dict
        _cell: float
        _drawn_shape: tuple
        _active_set: set
        _shown_layers: int
        _anim_job: Optional[str]
        _regenerate_job: Optional[str]
        _redraw_job: Optional[str]
        _poll_job: Optional[str]
        _first_job: Optional[str]
        _scan_results: list
        _scan_meta: tuple
        _scan_cols: int
        _scan_lattice: str
        _scan_direction: str
        _scan_inject: str
        _scan_criterion: str
        _scan_threshold: float
        _scan_pc: Optional[float]

        # ---------------- 各 mixin 互相调用的方法（签名契约） ----------------
        @property
        def _terms(self) -> "Terms":
            ...

        # 参数与状态（PercolationViewBase）
        def _criterion_rule(self) -> str:
            ...

        def _criterion_strategy(self, key: str) -> "Criterion":
            ...

        def _result_summary(self) -> str:
            ...

        def _verdict_phrase(self, view: "ActiveView") -> str:
            ...

        def _sync_model_params(self) -> None:
            ...

        def _current_shape(self) -> Tuple[int, int]:
            ...

        def _current_seed(self) -> Optional[int]:
            ...

        def _on_param_change(self, key: str) -> None:
            ...

        def _on_p_change(self, value: Optional[str] = None) -> None:
            ...

        def _on_shape_change(self) -> None:
            ...

        def _on_lattice_change(self) -> None:
            ...

        def _on_direction_change(self) -> None:
            ...

        def _on_inject_change(self) -> None:
            ...

        def _on_criterion_change(self) -> None:
            ...

        # 参数表单（ParamFormMixin）
        def _build_param_cards(self, parent: Any, **kwargs: Any) -> None:
            ...

        def spec_choices(self, key: str, fallback: Any = ...) -> Tuple[str, ...]:
            ...

        def spec_bounds(self, key: str, low: Any, high: Any) -> Tuple[Any, Any]:
            ...

        # 画布与动画（CanvasMixin）
        def regenerate(self) -> None:
            ...

        def start_animation(self, origins: Optional[Sequence[int]] = None) -> None:
            ...

        def show_result_instant(self) -> None:
            ...

        def _cancel_animation(self) -> None:
            ...

        def _run_once(self, origins: Optional[Sequence[int]] = None) -> Any:
            ...

        def _active_view(self) -> "ActiveView":
            ...

        # 结果面板（ResultPanelMixin）
        def _update_result_labels(self) -> None:
            ...

        def _redraw_curve(self) -> None:
            ...

        def _insert_history(self, res: Any, tag: str) -> None:
            ...

        def _fill_extra_rows(self, view: Optional["ActiveView"]) -> None:
            ...

        def _size_text(self, model: Any) -> str:
            ...

        # 后台任务（JobsMixin）
        def _model_functions(self) -> Any:
            ...

        def start_batch_statistics(self) -> None:
            ...

        def start_scan(self) -> None:
            ...

        # 通用后台任务机制（ModelViewBase）：mixin 需要它们，故一并声明
        def _submit(self, job: Any) -> None:
            ...

        def _set_busy(self, busy: bool, text: str = "") -> None:
            ...

        def stop_work(self) -> None:
            ...

        def _handle_message(self, kind: str, payload: Any) -> None:
            ...

        def shutdown(self) -> None:
            ...
