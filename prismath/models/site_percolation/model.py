# -*- coding: utf-8 -*-
"""
点渗流（Site Percolation）核心模型
====================================

在 **rows × cols** 的格地上，每格以概率 ``p`` 独立地被「占据」（occupied），其余为空位；
只有相邻的**占据格**之间才连通。从注水点（起始格）出发沿相邻占据格蔓延，
蔓延范围就是包含注水点的那个连通簇。

这正是「森林火灾」的抽象：把占据格看成树、空位看成空地，一次点火最终烧掉的面积
就是火源所在连通簇的大小；当密度越过临界值时出现横贯整片格地的巨簇，
一次偶然的点火就能蔓延到全场 —— 量变引起质变。

可选维度
--------
* **格子** ``lattice``：``square``（方格网，4 邻域）/ ``triangular``（三角网，6 邻域）；
* **形状** ``rows`` / ``cols``：行列分开指定，``rows != cols`` 即矩形网格；
* **方向** ``direction``：``undirected`` / ``no_up`` / ``down_right`` / ``down_left``；
* **注水点** ``inject``：``random``（随机一个占据格）/ ``center``（中心附近）/ ``top``（顶端整行）；
* **成功判据** ``criterion``：``span``（贯通）/ ``area``（面积），见下。

三种成功判据（务必区分）
------------------------
``p_c ≈ 0.5927`` 说的是「出现无限大簇 / 纵贯簇」的相变，**不是**「蔓延面积达到某个比例」。
因此本模块把「什么算成功」显式抽成一个维度：

* ``span`` **贯通判据**（默认）：整片格地上**是否存在纵贯簇**，即是否有一个占据簇同时
  连通顶行与底行。这正是文献里 ``p_c`` 所用的判据，所以它的 ``P(p) = 1/2`` 交点才落在
  ``p_c`` 上。该判据**与注水点无关**（等价于「顶端整行注水，水能否到达底行」）；
  选它时 ``inject`` 只影响单次动画的起点，不影响统计结果。
* ``origin`` **起点判据**：**从注水点出发的那一簇**是否纵贯（同时碰到顶行与底行）。
  它与 ``span`` 的唯一差别是「还要求注水点落在那条纵贯簇里」：顶端整行注水时两者
  完全等价；随机 / 中心单点注水时交点会明显高于 ``p_c``（格地上明明有纵贯簇，
  一次随机起火却可能有相当一部分概率**落在簇外**，于是火很小）。
  这正是「一次偶然的起火能不能烧穿整片格地」。
* ``area`` **面积判据**：从注水点出发的蔓延簇占整片格地的比例 ≥ ``threshold``。
  它回答的是「随机一棵树起火最终烧掉多大面积」，**没有固定的临界密度**：
  ``P(p) = 1/2`` 的交点随**所设比例、网格尺寸、注水方式**一起变化——
  比例定得越大交点越高，单点注水还会额外要求「起点恰好落在巨簇里」。
  只有把比例取得很小、网格取得很大时，它才会缓慢地往 ``p_c`` 靠拢。

注意：后两种判据的交点都**不是** ``p_c`` —— 只有 ``span`` 判据的 1/2 交点等于 ``p_c``。

关于临界值
----------
方格点渗流（无向）的理论临界密度 ``p_c ≈ 0.5927``，三角网点渗流 ``p_c = 0.5``；
方向模式会改变临界值（见 :data:`THEORETICAL_PC_BY_COMBO` 与估计值表）。
与边渗流一样：``p_c`` 只取决于格子与方向，与矩形长宽比、注水点位置无关
——但这些结论都**只在 ``span`` 判据下成立**。

实现要点（为什么这样写）
------------------------
1. **格地是一块 numpy 布尔数组**：``occupied[r, c]``；生成一次格地就是一次
   ``rng.random((rows, cols)) < p``，而不是 ``rows × cols`` 次 Python 随机调用。
2. **蔓延用"预编译邻居表 + 逐层推进"**：方向过滤（``undirected`` / ``no_up`` /
   ``down_right`` / ``down_left``）与格子类型在**建模时**编译成邻居表 ``_nbr``
   （与 ``p`` 无关，只取决于几何与方向）与一张边表（测试用来逐条核对几何）。
   蔓延是这里唯一必须串行的部分，所以它**刻意不用 numpy**：内层循环只剩
   "取邻居 + 查 bytes 标记 + 查是否占据"，不再每走一步都付生成器、方向判断与
   二维下标换算（那些是旧实现逐步都要付的）。
   走到"每层几次数组运算"那条路是试过的：在 40×40 上它反而更慢（每层固定开销盖过收益），
   实测后改回了本方案。层内次序不再保证 FIFO（同一层里谁先谁后，界面上看不出区别）。
3. **统计量在整块掩码上数**：蔓延格数 / 是否碰到顶行底行都用 ``bytes`` 的 ``sum`` / ``any``
   一次算出（C 层扫描），不在 BFS 里逐格累加。
4. **"有没有纵贯簇"与"纵贯簇是哪一片"分开**：判据只需要前者，于是它可以走一条更快的
   路径（从顶行整行一次波浪推进，看是否碰到末行）；界面高亮需要后者时再走逐簇扫描
   （:meth:`SitePercolation._scan_span`）——两者的答案保证一致。

本模块只依赖标准库 + ``numpy``；numpy 现在是**必需依赖**（内核统一向量化，不再维护
标准库回退实现 —— 见 README 的「依赖规则」）。不含任何绘图 / GUI 代码，可单独导入。

实测（Windows / Python 3.13，方格网 40×40，p 取在 p_c 附近最费时；中位数）
----------------------------------------------------------------------
复现命令：``python -m tests.bench site_percolation``

* 贯通判据 × 批量 300 次 **88 ms**（≈ 0.29 ms/次试验）；
* **扫描 5 个 p 各 100 次 135 ms** —— 默认组合走"临界 p"单遍扫描（见 :func:`scan_curve`），
  对照"逐 p 重跑"的老路径 181 ms 约快 **1.3×**。点渗流的逐点路径本来就便宜，收益只在点数
  多时才明显（20 点时约 5×）；
* 起点判据 × 随机单点 300 次 **26 ms**；面积判据 × 中心附近 300 次 **45 ms**；
* 三角网贯通批量 300 次 **77 ms**；界面用的单次蔓延（含分层）**0.94 ms**；
* 内置自检整体 **21.6 s → 4.4 s**（约 4.9×）。

一条被实测否掉的方案（留个记录，别重走）：最初把"逐层推进"写成 numpy 的
"边表筛选 + 数组运算"，在 40×40 上反而**慢 8.6×** —— 每层的固定调用开销盖过了收益。
小格地上 Python 的紧凑循环更划算，格地越大 numpy 版才会反超，所以这里选了前者。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple, Union

import numpy as np

__all__ = [
    "THEORETICAL_PC",
    "THEORETICAL_PC_BY_COMBO",
    "ESTIMATED_PC_BY_COMBO",
    "DEFAULT_THRESHOLD",
    "CRITERIA",
    "CRITERION_NAMES",
    "CRITERION_DESCRIPTIONS",
    "DEFAULT_CRITERION",
    "DIRECTIONS",
    "DIRECTION_NAMES",
    "INJECT_MODES",
    "INJECT_NAMES",
    "LATTICES",
    "LATTICE_NAMES",
    "SitePercolation",
    "SpreadResult",
    "SpreadBatchResult",
    "batch_spread_probability",
    "scan_curve",
    "encode_sites",
]

#: 二维方格点渗流（无向）的理论临界密度（对应 ``criterion="span"`` 的贯通相变）
THEORETICAL_PC: float = 0.592746

#: 默认的面积判据阈值（``criterion="area"`` 时蔓延格数占总格数的比例）
DEFAULT_THRESHOLD: float = 0.5

#: 成功判据：
#:
#: * ``span``：整片格地是否存在纵贯簇 —— 对应 ``p_c``，**与注水方式无关**；
#: * ``origin``：从注水点出发的那一簇是否纵贯 —— **随注水方式变化**（顶端整行时与 ``span`` 相同）；
#: * ``area``：蔓延面积达到比例阈值 —— 没有固定临界值。
CRITERIA: Tuple[str, ...] = ("span", "origin", "area")

#: 成功判据的短名（用于结果文本）
CRITERION_NAMES: Dict[str, str] = {
    "span": "贯通判据",
    "origin": "起点判据",
    "area": "面积判据",
}

#: 默认成功判据：贯通判据（这才是 p_c 所对应的判据）
DEFAULT_CRITERION: str = "span"

#: (格子, 方向) -> 临界密度：解析解或文献值
#:
#: 这些值都是**贯通判据**（``criterion="span"``）下的临界密度 —— 即「出现无限大簇 /
#: 纵贯簇」的相变点。面积判据没有对应的固定值，所以不要把它套到这里。
THEORETICAL_PC_BY_COMBO: Dict[Tuple[str, str], float] = {
    ("square", "undirected"): 0.592746,      # 文献值（二维方格点渗流）
    ("triangular", "undirected"): 0.5,       # 解析：三角网点渗流 p_c = 1/2
    ("square", "down_right"): 0.7055,        # 文献值（有向点渗流）
    ("square", "down_left"): 0.7055,         # 与上者镜像同值
}

#: (格子, 方向) -> 蒙特卡洛估计值（没有已知解析解的组合，界面标注「估计值」）
#:
#: 估计方法：用**贯通判据**（``criterion="span"``，等价于「顶端整行注水 → 是否到达底端」）
#: 在 n = 100 / 200 / 400 / 800 上二分求 P(p) = 0.5 的交点，取最大尺寸的结果
#: （有向模式的表观交点从下方逼近真值，例如 (square, down_right) 在 n = 100/200/400
#: 测得 0.695/0.697/0.704，正逼近文献值 0.7055）。
ESTIMATED_PC_BY_COMBO: Dict[Tuple[str, str], float] = {
    ("square", "no_up"): 0.618,
    ("triangular", "no_up"): 0.538,
    ("triangular", "down_right"): 0.578,
    ("triangular", "down_left"): 0.578,
}

#: 支持的格子类型与中文名
LATTICES: Tuple[str, ...] = ("square", "triangular")
LATTICE_NAMES: Dict[str, str] = {
    "square": "方格网",
    "triangular": "三角网",
}

#: 方向模式与中文名
DIRECTIONS: Tuple[str, ...] = ("undirected", "no_up", "down_right", "down_left")
DIRECTION_NAMES: Dict[str, str] = {
    "undirected": "无向（四邻域连通）",
    "no_up": "不允许向上",
    "down_right": "只允许向下/向右",
    "down_left": "只允许向下/向左",
}

#: 注水方式与中文名
INJECT_MODES: Tuple[str, ...] = ("random", "center", "top")
INJECT_NAMES: Dict[str, str] = {
    "random": "随机单点",
    "center": "中心附近",
    "top": "顶端整行",
}

#: 成功判据的完整说明（界面与日志用）
CRITERION_DESCRIPTIONS: Dict[str, str] = {
    "span": "贯通判据：整片格地存在从顶行连通到底行的纵贯簇（p_c 所对应的判据，与注水方式无关）",
    "origin": "起点判据：从注水点出发的蔓延簇同时碰到顶行与底行（随注水方式变化；"
              "顶端整行注水时与贯通判据完全相同）",
    "area": "面积判据：蔓延簇占整片格地的比例达到阈值（无固定临界值，随比例/尺寸/注水方式变化）",
}

#: 随机源可以传入 None / int（种子）/ numpy Generator 实例
RngLike = Union[None, int, np.random.Generator]

#: 进度回调：progress(已完成, 总数, 成功次数)
ProgressCallback = Callable[[int, int, int], None]


def _resolve_rng(rng: RngLike = None) -> np.random.Generator:
    """把 None / 种子 / Generator 实例统一转换成一个 numpy 随机源。

    注意：从 ``random.Random`` 换成 numpy 之后，**同一个种子不再产生同一片格地** ——
    可复现性只在同一实现内成立（这是本次重构被明确接受的代价之一）。
    """
    if isinstance(rng, np.random.Generator):
        return rng
    return np.random.default_rng(rng)


def _derive_rng(parent: np.random.Generator) -> np.random.Generator:
    """从主随机源派生一个独立随机源（给"随机注水点"专用）。

    这样「随机注水」不会消耗生成格地的那串随机数：同一颗种子下，不同注水方式的
    格地序列完全相同，「贯通判据与注水方式无关」这件事才能在同一批格地上逐次验证。
    """
    return np.random.default_rng(int(parent.integers(0, 2 ** 63)))


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


@dataclass
class SpreadResult:
    """一次完整蔓延的结果，供逐层动画与指标展示使用。"""

    rows: int
    cols: int
    p: float
    #: 注水点（起始格）的索引
    origins: List[int] = field(default_factory=list)
    #: 被蔓延到的格子索引（行优先：index = row * cols + col）
    spread: List[int] = field(default_factory=list)
    #: 按蔓延层数分组的格子，layers[k] 表示距注水点 k 步的格子
    layers: List[List[int]] = field(default_factory=list)
    #: 整片格地上被占据的格子数
    occupied_count: int = 0
    #: 面积判据的比例阈值（仅 ``criterion="area"`` 时有意义）
    threshold: float = DEFAULT_THRESHOLD
    #: 本次「是否成功」采用的是哪种判据：``span`` / ``area``
    criterion: str = DEFAULT_CRITERION
    #: 是否蔓延到底端整行
    reached_bottom: bool = False
    #: 整片格地上是否存在纵贯簇（顶行 ↔ 底行，与注水点无关）
    spans: bool = False
    #: 从注水点出发的蔓延簇是否纵贯（同时碰到顶行与底行）
    origin_spans: bool = False
    #: 纵贯簇的格子索引（没有纵贯簇时为空列表）—— 供界面把它高亮出来
    spanning_nodes: List[int] = field(default_factory=list)
    elapsed: float = 0.0

    @property
    def size(self) -> int:
        """行数（便于沿用 ``result.size`` 的写法）。"""
        return self.rows

    @property
    def shape(self) -> Tuple[int, int]:
        return self.rows, self.cols

    @property
    def node_count(self) -> int:
        return self.rows * self.cols

    @property
    def has_source(self) -> bool:
        """是否存在注水点（顶端整行注水时该行可能一个占据格都没有）。"""
        return bool(self.origins)

    @property
    def spread_count(self) -> int:
        return len(self.spread)

    @property
    def spread_ratio(self) -> float:
        """蔓延格数占**整片格地**的比例（面积判据用的量）。"""
        return self.spread_count / self.node_count if self.node_count else 0.0

    @property
    def cluster_ratio(self) -> float:
        """蔓延格数占**占据格**的比例（即簇的相对大小）。"""
        return self.spread_count / self.occupied_count if self.occupied_count else 0.0

    @property
    def occupied_ratio(self) -> float:
        """占据密度（实测值，围绕 p 波动）。"""
        return self.occupied_count / self.node_count if self.node_count else 0.0

    @property
    def depth(self) -> int:
        """蔓延层数（BFS 最大层号 + 1）。"""
        return len(self.layers)

    @property
    def engulfed(self) -> bool:
        """**面积判据**是否成立：蔓延格数占整片格地的比例达到 ``threshold``。"""
        return self.spread_ratio >= self.threshold

    @property
    def success(self) -> bool:
        """按本次采用的 ``criterion`` 判定「是否成功」。"""
        if self.criterion == "span":
            return self.spans
        if self.criterion == "origin":
            return self.origin_spans
        return self.engulfed

    @property
    def criterion_name(self) -> str:
        return CRITERION_NAMES.get(self.criterion, self.criterion)

    @property
    def spanning_count(self) -> int:
        """纵贯簇的格子数。"""
        return len(self.spanning_nodes)

    @property
    def spanning_ratio(self) -> float:
        """纵贯簇占整片格地的比例（与蔓延比例是两回事）。"""
        return self.spanning_count / self.node_count if self.node_count else 0.0

    @property
    def origin_in_spanning(self) -> bool:
        """注水点是否落在纵贯簇里。

        这是「判定贯通、却只看见一小片蔓延」的唯一原因：这次的火源不在纵贯簇内，
        而判据问的是整片格地有没有纵贯簇，两者互不影响。
        """
        if not self.origins or not self.spanning_nodes:
            return False
        inside = set(self.spanning_nodes)
        return any(origin in inside for origin in self.origins)


@dataclass
class SpreadBatchResult:
    """一批独立蔓延实验的统计结果。"""

    p: float
    rows: int
    cols: int
    trials: int
    success: int
    threshold: float = DEFAULT_THRESHOLD
    criterion: str = DEFAULT_CRITERION
    direction: str = "undirected"
    lattice: str = "square"
    inject: str = "top"
    #: 各次实验蔓延比例之和（用于计算平均蔓延比例）
    ratio_sum: float = 0.0
    elapsed: float = 0.0

    @property
    def size(self) -> int:
        return self.rows

    @property
    def shape(self) -> Tuple[int, int]:
        return self.rows, self.cols

    @property
    def criterion_name(self) -> str:
        return CRITERION_NAMES.get(self.criterion, self.criterion)

    @property
    def probability(self) -> float:
        """「成功」的发生频率（对概率的蒙特卡洛估计）。

        ``criterion="span"`` 时统计的是**整片格地存在纵贯簇**的频率（交点即 ``p_c``）；
        ``criterion="origin"`` 时统计的是**注水点的簇纵贯**的频率（随注水方式变化）；
        ``criterion="area"`` 时统计的是蔓延比例达到阈值的频率（无固定交点）。
        """
        return self.success / self.trials if self.trials else 0.0

    @property
    def mean_ratio(self) -> float:
        """平均蔓延比例（随密度上升而急剧抬升，比频率更平滑）。

        注意：这是**蔓延簇占整片格地**的比例，与判据无关，始终可比较。
        """
        return self.ratio_sum / self.trials if self.trials else 0.0

    @property
    def stderr(self) -> float:
        """频率估计的标准误 sqrt(P(1-P)/N)。"""
        prob = self.probability
        return (prob * (1 - prob) / self.trials) ** 0.5 if self.trials else 0.0


class SitePercolation:
    """点渗流模型（方格网 / 三角网，方形 / 矩形，四种方向模式，三种注水方式）。

    参数
    ----
    rows, cols : int
        行数与列数；``cols`` 省略时取 ``rows``（正方形格地）。
    p : float
        每格被占据的概率（密度），取值 ``[0, 1]``。
    rng : None | int | random.Random
        随机源，可以是种子（便于复现）。
    direction : str
        ``undirected`` / ``no_up`` / ``down_right`` / ``down_left``。
    lattice : str
        ``square``（4 邻域）或 ``triangular``（6 邻域）。
    inject : str
        ``top``（顶端整行，默认 —— 与 p_c 的经典实验"顶端注水能否到底端"一致）/
        ``random``（随机一个占据格）/ ``center``（中心附近）。
    criterion : str
        ``span``（贯通判据：是否存在纵贯簇，对应 ``p_c``）/ ``area``（面积判据：蔓延比例 ≥
        ``threshold``）。默认 ``span``。
    threshold : float
        ``criterion="area"`` 时判定「蔓延全场」的蔓延比例，默认 0.5。
    """

    def __init__(
        self,
        rows: int = 30,
        cols: Optional[int] = None,
        p: float = 0.6,
        rng: RngLike = None,
        direction: str = "undirected",
        lattice: str = "square",
        inject: str = "top",
        criterion: str = DEFAULT_CRITERION,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        if int(rows) < 2:
            raise ValueError("行数至少为 2")
        if cols is not None and int(cols) < 2:
            raise ValueError("列数至少为 2")
        if lattice not in LATTICES:
            raise ValueError(f"未知的格子类型：{lattice}（可选：{'、'.join(LATTICES)}）")
        if direction not in DIRECTIONS:
            raise ValueError(f"未知的方向模式：{direction}（可选：{'、'.join(DIRECTIONS)}）")
        if inject not in INJECT_MODES:
            raise ValueError(f"未知的注水方式：{inject}（可选：{'、'.join(INJECT_MODES)}）")
        if criterion not in CRITERIA:
            raise ValueError(f"未知的成功判据：{criterion}（可选：{'、'.join(CRITERIA)}）")

        self.rows = int(rows)
        self.cols = int(cols) if cols is not None else int(rows)
        self.p = _clamp(float(p), 0.0, 1.0)
        self.direction = direction
        self.lattice = lattice
        self.inject = inject
        self.criterion = criterion
        self.threshold = _clamp(float(threshold), 0.05, 1.0)
        self.rng: np.random.Generator = _resolve_rng(rng)
        #: 随机注水点专用的随机源（从主随机源派生）：这样「随机注水」不会去消耗
        #: 生成格地的那串随机数，同一颗种子下不同注水方式的格地序列完全相同，
        #: 「贯通判据与注水方式无关」这件事才能在同一批格地上被逐次验证。
        self._source_rng: np.random.Generator = _derive_rng(self.rng)
        #: occupied[r][c] 表示该格是否被占据（numpy 布尔数组，``occupied[r][c]`` 照旧可用）
        self.occupied: np.ndarray = np.zeros((self.rows, self.cols), dtype=bool)
        #: 末行的起始下标（"碰到末行" = 下标 ≥ 它），热路径上反复用到
        self._last_row_start: int = (self.rows - 1) * self.cols
        #: 蔓延用的有向边表（几何编译结果，见 :meth:`_build_edges`）
        self._edge_src: np.ndarray = np.empty(0, dtype=np.intp)
        self._edge_dst: np.ndarray = np.empty(0, dtype=np.intp)
        #: 邻居表（Python 列表）：逐层推进逐格查它，比 numpy 标量索引快一个量级
        self._nbr: List[List[int]] = []
        #: 展开的占据掩码（bytes）：同上，热路径逐格查它
        self._occupied_bytes: bytes = b""
        #: inject == "random" 时使用的随机注水点（随格地一起生成，便于复现）
        self._random_source: Optional[int] = None
        #: 当前格地纵贯簇的格子清单缓存（None 表示尚未判定，空列表表示没有纵贯簇）
        self._spanning_nodes: Optional[List[int]] = None
        self._build_edges()
        self.regenerate()

    # ------------------------------------------------------------------
    # 基本几何
    # ------------------------------------------------------------------
    @property
    def size(self) -> int:
        """行数（便于沿用 ``model.size`` 的写法）。"""
        return self.rows

    @property
    def shape(self) -> Tuple[int, int]:
        return self.rows, self.cols

    @property
    def node_count(self) -> int:
        return self.rows * self.cols

    @property
    def is_square(self) -> bool:
        return self.rows == self.cols

    @property
    def lattice_name(self) -> str:
        return LATTICE_NAMES[self.lattice]

    @property
    def direction_name(self) -> str:
        return DIRECTION_NAMES[self.direction]

    @property
    def inject_name(self) -> str:
        return INJECT_NAMES[self.inject]

    @property
    def criterion_name(self) -> str:
        return CRITERION_NAMES[self.criterion]

    @property
    def pc_applies(self) -> bool:
        """当前判据下 ``p_c`` 是否有意义（只有贯通判据才对应 ``p_c``）。"""
        return self.criterion == "span"

    @property
    def theoretical_pc(self) -> Optional[float]:
        """当前（格子, 方向）组合的临界密度；文献与估计都没有时返回 None。"""
        key = (self.lattice, self.direction)
        if key in THEORETICAL_PC_BY_COMBO:
            return THEORETICAL_PC_BY_COMBO[key]
        return ESTIMATED_PC_BY_COMBO.get(key)

    @property
    def pc_is_estimate(self) -> bool:
        """临界值是蒙特卡洛估计（而非解析解 / 文献值）时为 True。"""
        return (self.lattice, self.direction) not in THEORETICAL_PC_BY_COMBO

    @property
    def pc_label(self) -> str:
        """临界值的展示文本（随判据变化：只有贯通判据对应 p_c）。"""
        if self.criterion == "origin":
            return ("起点判据没有固定临界值：交点还要求「注水点落在纵贯簇里」，"
                    "所以高于 p_c；注水方式为顶端整行时与贯通判据相同。")
        if not self.pc_applies:
            return ("面积判据没有固定临界值：交点随所设比例、网格尺寸、注水方式变化，"
                    "只有贯通判据才对应 p_c。")
        pc = self.theoretical_pc
        if pc is None:
            return "该组合暂无已知阈值"
        return f"贯通判据：p_c {'≈' if self.pc_is_estimate else '='} {pc:.4f}" + (
            "（估计值）" if self.pc_is_estimate else ""
        )

    def index(self, row: int, col: int) -> int:
        """二维坐标 -> 一维格子索引。"""
        return row * self.cols + col

    def coord(self, index: int) -> Tuple[int, int]:
        """一维格子索引 -> (行, 列)。"""
        return divmod(index, self.cols)

    # ------------------------------------------------------------------
    # 格地构建
    # ------------------------------------------------------------------
    def regenerate(self, p: Optional[float] = None, seed: Optional[int] = None) -> "SitePercolation":
        """重新随机「占据」格地（每格以概率 p 独立决定是否被占据）。

        ``inject == "random"`` 时同时重新随机挑选注水点，因此同一个格地上的多次判定
        结果保持一致，重新生成才会换注水点。

        结构（尺寸 / 格子 / 方向）若被就地改过（界面改尺寸走的就是这条路），这里会
        **先重建边表、再重抽格地** —— 见 :meth:`_ensure_ready`。
        """
        if p is not None:
            self.p = _clamp(float(p), 0.0, 1.0)
        if seed is not None:
            self.rng = np.random.default_rng(seed)
            # 主随机源换了，随注水点的随机源也要跟着换，种子才真正可复现
            self._source_rng = _derive_rng(self.rng)

        if not self._ensure_ready():        # 结构没变、格地没失效 → 自己重抽一遍
            self._draw_field()
        return self

    def _draw_field(self) -> None:
        """按当前 ``p`` 抽满整块格地，并重建全部派生缓存。"""
        # 一次抽满整块格地（行优先）：比逐格 random() 快两个数量级
        self.occupied = self.rng.random((self.rows, self.cols)) < self.p
        # 展开成 bytes 掩码：热路径（逐层推进）逐格查它 —— bytes 下标比 numpy 标量索引快
        self._occupied_bytes = self.occupied.reshape(-1).astype(np.uint8).tobytes()
        self._field_key: Tuple[int, int, str] = (self.rows, self.cols, self.lattice)

        if self.inject == "random":
            self._random_source = None      # 延迟到取用时再挑，避免空位过多时的浪费
        self._spanning_nodes = None         # 格地换了，贯通判定缓存作废

    def _ensure_ready(self) -> bool:
        """让内部表 / 随机格地与当前的 ``rows`` / ``cols`` / ``lattice`` / ``direction`` 对齐。

        返回**是否已经重抽过格地**（为 True 时调用方不必再抽一次）。

        界面改尺寸或形状时是**就地**改这些属性、再调 :meth:`regenerate` 的
        （``ui/tk/kit/base.py`` 的 ``_on_shape_change`` / ``_sync_model_params``）。
        重构前的内核没有缓存表，怎么改都没事；向量化之后 ``_nbr`` 与 ``_last_row_start``
        都是按尺寸预编译的 —— 不在这里对齐，就会拿旧尺寸的表去索引新格地，表现正是
        "长宽比不为 1 就 ``IndexError: bytearray index out of range``"。
        """
        rows, cols = int(self.rows), int(self.cols)
        key = (rows, cols, self.lattice, self.direction)
        if key != self._structure_key:
            self._build_edges()                      # 重编几何（顺带刷新末行起点）
        if (rows, cols, self.lattice) != getattr(self, "_field_key", None):
            self._draw_field()                       # 格地也是按尺寸的：必须重抽
            return True
        return False

    def is_occupied(self, index: int) -> bool:
        r, c = divmod(int(index), self.cols)
        return bool(self.occupied[r, c])

    def occupied_count(self) -> int:
        return int(np.count_nonzero(self.occupied))

    def occupied_ratio(self) -> float:
        return self.occupied_count() / self.node_count if self.node_count else 0.0

    def iter_occupied(self) -> Iterator[int]:
        """迭代所有被占据的格子（行优先，与逐格扫描的次序一致）。"""
        for index in np.flatnonzero(self.occupied.reshape(-1)):
            yield int(index)

    # ------------------------------------------------------------------
    # 邻居（几何邻接 + 方向过滤 + 占据判定）
    # ------------------------------------------------------------------
    def direction_allows(self, dr: int, dc: int) -> bool:
        """方向模式是否允许「行变化 dr、列变化 dc」这一步。"""
        mode = self.direction
        if mode == "undirected":
            return True
        if mode == "no_up":
            return dr >= 0
        if mode == "down_right":
            return dr > 0 or (dr == 0 and dc > 0)
        if mode == "down_left":
            return dr > 0 or (dr == 0 and dc < 0)
        return True

    def _adjacent(self, index: int) -> Iterator[Tuple[int, int, int]]:
        """产出几何上相邻的格子及其 (行变化, 列变化)。"""
        rows, cols = self.rows, self.cols
        r, c = divmod(index, cols)

        if c + 1 < cols:
            yield index + 1, 0, 1
        if c > 0:
            yield index - 1, 0, -1

        if self.lattice == "square":
            if r + 1 < rows:
                yield index + cols, 1, 0
            if r > 0:
                yield index - cols, -1, 0
            return

        shift = r % 2
        if r + 1 < rows:
            for j in (c - 1 + shift, c + shift):
                if 0 <= j < cols:
                    yield r * cols + cols + j, 1, j - c
        if r > 0:
            pshift = (r - 1) % 2
            for k in (c + 1 - pshift, c - pshift):
                if 0 <= k < cols:
                    yield (r - 1) * cols + k, -1, k - c

    def neighbors(self, index: int) -> Iterator[int]:
        """可蔓延到的邻居：几何相邻、方向允许、且被占据。"""
        for nb, dr, dc in self._adjacent(index):
            if self.direction_allows(dr, dc) and self.occupied[nb // self.cols][nb % self.cols]:
                yield nb

    def traversable_neighbors(self, index: int) -> Iterator[int]:
        """相邻、被占据、且**沿允许方向至少一个方向能蔓延**的邻居（给「已走过的边」上色用）。

        与 :meth:`neighbors` 的区别：``neighbors`` 只给出「从 ``index`` 出发能蔓延到的
        邻居」（受方向限制）。给已经烧过的连接染色时必须两个方向都看：后一步才被蔓延到的
        格子，从它看前一步的邻居可能是「逆着方向」的，只看 ``neighbors`` 就会漏色 ——
        有向模式 + 三角网时尤其明显（每个格子有两条斜向上的入边都拿不到颜色）。
        """
        cols = self.cols
        for nb, dr, dc in self._adjacent(index):
            if not self.occupied[nb // cols][nb % cols]:
                continue
            if self.direction_allows(dr, dc) or self.direction_allows(-dr, -dc):
                yield nb

    def _build_edges(self) -> None:
        """把「格子类型 + 方向模式」编译成一张有向边表（只与几何有关，与 ``p`` 无关）。

        ``edge_src[i] -> edge_dst[i]`` 表示"若 ``src`` 已被蔓延到，下一步可以蔓延到
        ``dst``"。方向过滤在这**一次**做完，于是热路径上的每层推进只是"筛出边源在当前
        层的那些边"，不必逐格再判方向。

        这里的每一条都必须与 :meth:`_adjacent` + :meth:`direction_allows` 严格一致
        （``tests/test_site_percolation.py`` 里对小块格地逐条比对过）。用 numpy 直接构造
        而不是逐格调 ``_adjacent``：边长 800 的格地有 64 万格，逐格建表要好几秒，
        而扫描时每个 ``p`` 都会新建一次模型。
        """
        rows, cols = self.rows, self.cols
        index = np.arange(rows * cols, dtype=np.intp).reshape(rows, cols)
        src: List[np.ndarray] = []
        dst: List[np.ndarray] = []

        def link(from_cells, to_cells) -> None:
            src.append(np.asarray(from_cells, dtype=np.intp).reshape(-1))
            dst.append(np.asarray(to_cells, dtype=np.intp).reshape(-1))

        # 水平邻居：两种格子类型都有（对应 _adjacent 的前两段）
        if cols > 1:
            if self.direction_allows(0, 1):
                link(index[:, :-1], index[:, 1:])
            if self.direction_allows(0, -1):
                link(index[:, 1:], index[:, :-1])

        if self.lattice == "square":
            # 方格网：上下两个直向邻居
            if rows > 1:
                if self.direction_allows(1, 0):
                    link(index[:-1, :], index[1:, :])
                if self.direction_allows(-1, 0):
                    link(index[1:, :], index[:-1, :])
        elif rows > 1:
            # 三角网：向下的斜邻居目标列随**行奇偶**偏移（偶数行取 c-1/c，奇数行取 c/c+1，
            # 与 _adjacent 的 shift 一致）；向上的斜邻居就是同一批边的反向。
            for r in range(rows - 1):
                shift = r % 2
                for offset in (shift - 1, shift):
                    lo, hi = max(0, -offset), min(cols, cols - offset)
                    if hi <= lo:
                        continue
                    source_cols = np.arange(lo, hi, dtype=np.intp)
                    down_src = source_cols + r * cols
                    down_dst = source_cols + offset + (r + 1) * cols
                    if self.direction_allows(1, offset):
                        link(down_src, down_dst)
                    if self.direction_allows(-1, offset):
                        link(down_dst, down_src)

        self._edge_src = np.concatenate(src) if src else np.empty(0, dtype=np.intp)
        self._edge_dst = np.concatenate(dst) if dst else np.empty(0, dtype=np.intp)

        # 再由边表派生"邻居表"（Python 列表）。蔓延是唯一必须串行的部分，让它的内层
        # 循环只剩"取邻居 + 查标记 + 查占据"，不必在每一步付 numpy 的标量开销。
        neighbours: List[List[int]] = [[] for _ in range(self.node_count)]
        for source, target in zip(self._edge_src.tolist(), self._edge_dst.tolist()):
            neighbours[source].append(target)
        self._nbr = neighbours
        #: 本次编译对应的结构（尺寸 / 格子 / 方向）—— 结构一变就必须重编（见 _ensure_ready）
        self._structure_key: Tuple[int, int, str, str] = (rows, cols, self.lattice, self.direction)
        #: 末行起始下标（"碰到末行" = 下标 ≥ 它）——它也由尺寸决定，跟着一起刷新
        self._last_row_start: int = (rows - 1) * cols

    def _expand(self, front: List[int], seen: bytearray) -> List[int]:
        """从"当前层"推进一层：返回新进入的格子（并把它们标记进 ``seen``）。

        内层循环是 ``for 邻居 in nbr[index]``（预编译的邻居表）加两个 bytes/bytearray
        下标判断 —— 没有生成器、没有方向判断、没有二维下标换算（旧实现每走一步都要付）。
        实测在 40×40、p_c 附近这一版比"逐层 numpy 推进"快约 3 倍，比旧实现快约 2–3 倍；
        格地越大优势越大（numpy 那版每层都有固定的调用开销）。
        """
        neighbours = self._nbr
        occupied = self._occupied_bytes
        nxt: List[int] = []
        push = nxt.append
        for index in front:
            for neighbour in neighbours[index]:
                if not seen[neighbour] and occupied[neighbour]:
                    seen[neighbour] = 1
                    push(neighbour)
        return nxt

    # ------------------------------------------------------------------
    # 注水点
    # ------------------------------------------------------------------
    def source_nodes(self) -> List[int]:
        """注水点：随机一个占据格 / 中心附近的占据格 / 顶端整行的占据格。"""
        if self.inject == "top":
            return self.top_row_nodes()

        if self.inject == "center":
            best = self._nearest_to_center()
            return [best] if best >= 0 else []

        if self._random_source is None:
            occupied = np.flatnonzero(self.occupied.reshape(-1))
            if occupied.size == 0:
                return []
            # 在"占据格清单"里均匀取一个名次 —— 与逐格数到第 rank 个完全等价
            target = int(self._source_rng.integers(occupied.size))
            self._random_source = int(occupied[target])
        if self._random_source is None or not self.is_occupied(self._random_source):
            return []
        return [self._random_source]

    def top_row_nodes(self) -> List[int]:
        """顶端整行里被占据的格子（纵贯判据的入口，与 ``inject`` 无关）。"""
        return [int(c) for c in np.flatnonzero(self.occupied[0])]

    def bottom_row_nodes(self) -> List[int]:
        """底端整行里被占据的格子（纵贯判据的出口）。"""
        base = self._last_row_start
        return [base + int(c) for c in np.flatnonzero(self.occupied[-1])]

    def sink_nodes(self) -> List[int]:
        """出口：底端整行里被占据的格子（与边渗流的 ``sink_nodes()`` 同名同义）。"""
        return self.bottom_row_nodes()

    def percolates(self, origins: Optional[Sequence[int]] = None) -> bool:
        """水能否从注水点到达**底端整行**。

        与 :meth:`origin_spans` 的区别：这个只要求碰到底行，那个还要求碰到顶行。
        （对应边渗流的 ``percolates()``，便于两个模型交叉对照。）
        """
        return self.spread_stats(origins)[2]

    def _nearest_to_center(self) -> int:
        """离格地中心最近的占据格（按平方距离，平局取行优先靠前者）；无占据格时 -1。"""
        cols = self.cols
        rr, cc = np.nonzero(self.occupied)
        if rr.size == 0:
            return -1
        cr, cw = (self.rows - 1) / 2.0, (cols - 1) / 2.0
        dist = (rr - cr) ** 2 + (cc - cw) ** 2
        # argmin 取**第一个**最小值，而 nonzero 是行优先 —— 与"平局取行优先靠前者"一致
        best = int(dist.argmin())
        return int(rr[best]) * cols + int(cc[best])

    # ------------------------------------------------------------------
    # 贯通判定（criterion == "span"）
    # ------------------------------------------------------------------
    def spanning_nodes(self) -> List[int]:
        """纵贯簇的格子清单（同时连通顶行与底行的那个簇）；没有则返回空列表。

        这就是 ``p_c`` 所对应的判据所关注的那个簇：判据只问「有没有」，而界面需要
        把**到底是哪一片格子**纵贯画出来 —— 否则很容易把「蔓延面积」误当成判据的判据
        （一次随机注水的火可以很小，但它和「格地上有没有纵贯簇」是两件事）。

        **与注水点无关**：``inject`` 只决定单次动画从哪儿开始；判据问的是
        「整片格地有没有纵贯簇」，所以统计时不受注水方式影响。
        （当 ``inject == "top"`` 时，它与「水从顶端整行到达底行」完全等价。）

        结果在同一个格地上缓存，重新生成格地后失效。
        """
        self._ensure_ready()                # 结构若被就地改过，先对齐（否则表与格地对不上）
        if self._spanning_nodes is None:
            self._spanning_nodes = self._scan_span()
        return self._spanning_nodes

    def has_spanning_cluster(self) -> bool:
        """格地上是否存在**纵贯簇**（等价于 :meth:`spanning_nodes` 非空）。

        判据只需要一个"有没有"，所以这里走**更快的那条路**：把顶行整行当作起点推进一次，
        看是否碰到末行。逐簇扫描（:meth:`_scan_span`）留给界面"指出是哪一片"用。
        两者答案必然一致：顶行各簇的并集碰到末行 ⟺ 其中某一个簇碰到了末行。
        """
        top = self.top_row_nodes()
        if not top or not self.bottom_row_nodes():
            return False
        seen = bytearray(self.node_count)
        front: List[int] = []
        for index in top:
            seen[index] = 1
            front.append(index)
        while front:
            front = self._expand(front, seen)
        return any(seen[self._last_row_start:])

    def _scan_span(self) -> List[int]:
        """逐簇 BFS：从顶行每个占据格出发，返回**第一个**纵贯（顶行 ↔ 底行）的簇。

        分成一个个簇来试，而不是把顶行所有占据格一次连通：这样能精确指出是哪个簇
        纵贯，界面才能把它单独高亮（一次大 BFS 会把互不相连的簇混在一起）。
        方向模式照常生效，所以有向模式得到的是「有向纵贯簇」。
        """
        top = self.top_row_nodes()
        if not top or not self.bottom_row_nodes():
            return []

        last_row_start = self._last_row_start
        seen = bytearray(self.node_count)
        for start in top:
            if seen[start]:
                continue
            seen[start] = 1
            front: List[int] = [start]
            members: List[int] = []
            reaches_bottom = False
            while front:
                members.extend(front)
                if not reaches_bottom and max(front) >= last_row_start:
                    reaches_bottom = True
                front = self._expand(front, seen)
            if reaches_bottom:
                return members          # 一圈下来能碰到末行，这一簇就是纵贯簇
        return []

    # ------------------------------------------------------------------
    # 蔓延
    # ------------------------------------------------------------------
    def _spread(self, origins: Sequence[int], with_layers: bool = True):
        """从给定注水点做 BFS，返回 (蔓延格子, 分层, 是否蔓延到底端)。

        分层语义与旧实现一致（多个注水点同属第 0 层）；层**内**次序为行优先，
        不再保证 FIFO —— 界面上同一层是一起出现的，看不出区别。
        """
        self._ensure_ready()                # 结构若被就地改过，先对齐（否则表与格地对不上）
        occupied = self._occupied_bytes
        start = [int(i) for i in origins if occupied[int(i)]]
        if not start:
            return [], [] if with_layers else [], False

        seen = bytearray(self.node_count)
        front: List[int] = []
        for index in start:              # 去重（同一点可能被多个注水点重复给出）
            if not seen[index]:
                seen[index] = 1
                front.append(index)

        order: List[List[int]] = []
        layers: List[List[int]] = []
        while front:
            order.append(front)
            if with_layers:
                layers.append(list(front))
            front = self._expand(front, seen)

        spread = [index for layer in order for index in layer]
        return spread, layers, any(seen[self._last_row_start:])

    def spread_stats(self, origins: Optional[Sequence[int]] = None) -> Tuple[int, bool, bool]:
        """一次 BFS 同时得到：(蔓延格数, 是否碰到顶行, 是否碰到底行)。

        「面积判据」要的是第一项，「起点判据」要的是后两项，批量统计因此只需跑一遍。

        与 :meth:`_spread` 的一个既有差别照旧保留：**传入的注水点即使没被占据也会被
        算作已到达**（``_spread`` 会跳过未占据的起点）。只有显式传入未占据起点时才看得
        出来，而正常调用方（:meth:`source_nodes`）给的都是占据格。
        """
        cols = self.cols
        source = self.source_nodes() if origins is None else origins
        start = [int(i) for i in source]
        if not start:
            return 0, False, False

        seen = bytearray(self.node_count)
        front: List[int] = []
        for index in start:
            if not seen[index]:
                seen[index] = 1
                front.append(index)
        while front:
            front = self._expand(front, seen)

        return sum(seen), any(seen[:cols]), any(seen[self._last_row_start:])

    def spread_size(self, origins: Optional[Sequence[int]] = None) -> int:
        """只统计蔓延格数（批量统计的高速路径，不记录分层）。"""
        return self.spread_stats(origins)[0]

    def origin_spans(self, origins: Optional[Sequence[int]] = None) -> bool:
        """从注水点出发的蔓延簇是否**纵贯**（同时碰到顶行与底行）。

        与 :meth:`has_spanning_cluster` 的区别：那个问「整片格地有没有纵贯簇」，
        这个问「这次注水的那一簇是不是纵贯的」。注水方式为顶端整行时两者等价；
        单点注水（随机 / 中心）额外要求起点落在纵贯簇里，所以概率更低。
        """
        _count, touches_top, touches_bottom = self.spread_stats(origins)
        return touches_top and touches_bottom

    def simulate(self, origins: Optional[Sequence[int]] = None) -> SpreadResult:
        """从注水点蔓延一次，返回完整结果（含逐层信息）。

        ``origins`` 省略时按 ``inject`` 设定自动挑选注水点。
        """
        started = time.perf_counter()
        cols = self.cols
        source = list(origins) if origins is not None else self.source_nodes()
        spread, layers, reached_bottom = self._spread(source)
        spanning = self.spanning_nodes()
        touches_top = any(idx < cols for idx in spread)
        return SpreadResult(
            rows=self.rows,
            cols=self.cols,
            p=self.p,
            origins=source,
            spread=spread,
            layers=layers,
            occupied_count=self.occupied_count(),
            threshold=self.threshold,
            criterion=self.criterion,
            reached_bottom=reached_bottom,
            spans=bool(spanning),
            origin_spans=touches_top and reached_bottom,
            spanning_nodes=spanning,
            elapsed=time.perf_counter() - started,
        )

    def engulf_probability_single(self) -> float:
        """单次实验的蔓延比例（批量统计与自检使用）。"""
        return self.spread_size() / self.node_count if self.node_count else 0.0


# ----------------------------------------------------------------------
# 批量统计与扫描
# ----------------------------------------------------------------------
def batch_spread_probability(
    rows: int = 40,
    cols: Optional[int] = None,
    p: float = 0.6,
    trials: int = 1000,
    rng: RngLike = None,
    direction: str = "undirected",
    lattice: str = "square",
    inject: str = "top",
    criterion: str = DEFAULT_CRITERION,
    threshold: float = DEFAULT_THRESHOLD,
    progress: Optional[ProgressCallback] = None,
    cancel=None,
) -> SpreadBatchResult:
    """在固定密度 ``p`` 下做 ``trials`` 次独立实验，统计「成功」的频率。

    每次实验都重新生成格地。「成功」由 ``criterion`` 决定：

    * ``criterion="span"``：这次生成的格地上**存在纵贯簇**（顶行 ↔ 底行）。
      交点即 ``p_c``，且**与注水方式无关**（判据问的是整片格地的性质）；
    * ``criterion="origin"``：按 ``inject`` 挑注水点出发，这一簇是否**纵贯**
      （同时碰到顶行与底行）。顶端整行时与 ``span`` 等价，单点注水时交点高于 ``p_c``；
    * ``criterion="area"``：按 ``inject`` 挑注水点出发，蔓延比例 ≥ ``threshold``。
      交点随比例 / 尺寸 / 注水方式漂移，不是 ``p_c``。

    progress : callable(done, total, success) | None
        进度回调，每完成一批实验调用一次（在调用者线程内执行）。
    cancel : object | None
        任何带有 ``is_set()`` 方法的对象（如 ``threading.Event``），置位后提前结束。
    """
    rng = _resolve_rng(rng)
    trials = max(1, int(trials))
    model = SitePercolation(
        rows=rows, cols=cols, p=p, rng=rng, direction=direction, lattice=lattice,
        inject=inject, criterion=criterion, threshold=threshold,
    )
    step = max(1, trials // 50)      # 进度回调频率：最多约 50 次
    span_criterion = criterion == "span"
    origin_criterion = criterion == "origin"
    node_count = model.node_count
    success = 0
    ratio_sum = 0.0
    done = 0
    started = time.perf_counter()

    for i in range(1, trials + 1):
        model.regenerate()
        if span_criterion:
            # 贯通判据：整片格地是否存在纵贯簇（与注水点无关）
            ok = model.has_spanning_cluster()
            ratio_sum += model.spread_size() / node_count if node_count else 0.0
        else:
            # 起点判据 / 面积判据都要先跑一次蔓延：一遍 BFS 同时得到两者所需的量
            count, touches_top, touches_bottom = model.spread_stats()
            ratio = count / node_count if node_count else 0.0
            ratio_sum += ratio
            if origin_criterion:
                ok = touches_top and touches_bottom
            else:
                ok = ratio >= model.threshold
        if ok:
            success += 1
        done = i
        if progress is not None and (i % step == 0 or i == trials):
            progress(i, trials, success)
        if cancel is not None and cancel.is_set():
            break

    return SpreadBatchResult(
        p=p,
        rows=model.rows,
        cols=model.cols,
        trials=done,
        success=success,
        threshold=model.threshold,
        criterion=criterion,
        direction=direction,
        lattice=lattice,
        inject=inject,
        ratio_sum=ratio_sum,
        elapsed=time.perf_counter() - started,
    )


class _UnionFind:
    """并查集（路径压缩 + 按秩合并 + 分量大小）。

    与 ``percolation/model.py`` 里那份同源。两个内核都要求"可单独导入、可单独运行"，
    所以按本仓库的既有约定**各自持有一份**，而不是抽共享模块 —— 共享会引入相对导入，
    让 ``python prismath/models/xxx/model.py`` 这种直接运行方式失效。
    """

    __slots__ = ("parent", "rank", "count", "size")

    def __init__(self, n: int) -> None:
        self.parent: List[int] = list(range(n))
        self.rank: List[int] = [0] * n
        self.count: int = n
        self.size: List[int] = [1] * n

    def find(self, x: int) -> int:
        parent = self.parent
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:           # 路径压缩
            parent[x], x = root, parent[x]
        return root

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        self.count -= 1
        return True

    def connected(self, a: int, b: int) -> bool:
        return self.find(a) == self.find(b)

    def component_size(self, x: int) -> int:
        """``x`` 所在分量的节点数。"""
        return self.size[self.find(x)]


def _scan_curve_by_critical(
    p_values: Sequence[float],
    rows: int,
    cols: Optional[int],
    trials: int,
    rng: np.random.Generator,
    lattice: str,
    progress: Optional[Callable[[int, int, SpreadBatchResult], None]],
    cancel,
) -> List[SpreadBatchResult]:
    """贯通判据的"临界 p"单遍扫描：一次试验做一遍并查集扫描，给出整条 P(p) 曲线。

    做法：给每个格子抽一个 ``U(0,1)`` 权重、按升序"激活"；激活时与已激活的邻居并起来，
    并把顶行的格子接到虚拟水源、底行的格子接到虚拟出口。一旦水源与出口连通，
    **当时那个格子的权重就是该试验的临界密度 c** —— 于是任意 ``p`` 都有
    ``P(p) = P(c ≤ p)``，一遍 ``O(N α)`` 扫描替代了"每个 p 重跑一遍全部试验"。
    同时跟踪顶端簇大小随 ``p`` 的分段常量轨迹，"平均蔓延比例"一并得到。

    只在 ``criterion="span"`` + ``inject="top"`` + ``direction="undirected"`` 时成立，
    原因见 :func:`scan_curve`。

    注意：整条曲线共用一遍扫描，所以每个结果里的 ``elapsed`` 是**这一遍**的耗时。
    """
    grid = SitePercolation(rows=rows, cols=cols, p=0.5, rng=rng, lattice=lattice,
                           direction="undirected", inject="top")
    node_count = grid.node_count
    neighbours = grid._nbr
    columns = grid.cols
    sink_start = grid._last_row_start
    top_virtual, sink_virtual = node_count, node_count + 1

    started = time.perf_counter()
    critical: List[float] = []
    #: 只在**请求到的那些 p** 上给顶端簇大小拍快照（不必每次激活都数一遍）：
    #: 激活按权重升序进行，所以"走到第一个权重 ≥ p 的格子"时，所有权重 < p 的格子都已激活 ——
    #: 那一刻的分量大小正是该 p 下的"蔓延比例"，与逐 p 路径的口径完全一致。
    targets = sorted({float(p) for p in p_values})
    snapshots: List[List[float]] = []

    def top_ratio(current: "_UnionFind") -> float:
        """顶端簇占全网格的比例（虚拟节点不计入；已连通时连虚拟出口也扣掉）。"""
        virtuals = 2 if current.connected(top_virtual, sink_virtual) else 1
        return max(current.component_size(top_virtual) - virtuals, 0) / node_count

    for _ in range(trials):
        if cancel is not None and cancel.is_set():
            break
        weights = rng.random(node_count)
        order = np.argsort(weights, kind="stable")
        uf = _UnionFind(node_count + 2)
        active = bytearray(node_count)
        snapshot = [0.0] * len(targets)
        cursor = 0
        reached = 1.0
        connected_done = False
        for raw in order:
            index = int(raw)
            weight = float(weights[index])
            while cursor < len(targets) and weight >= targets[cursor]:
                snapshot[cursor] = top_ratio(uf)
                cursor += 1
            active[index] = 1
            if index < columns:
                uf.union(top_virtual, index)
            if index >= sink_start:
                uf.union(sink_virtual, index)
            for neighbour in neighbours[index]:
                if active[neighbour]:
                    uf.union(index, neighbour)
            if not connected_done and uf.connected(top_virtual, sink_virtual):
                reached = weight
                connected_done = True
            if connected_done and cursor >= len(targets):
                break                     # 临界值已拿到、该拍的快照也都拍完了
        while cursor < len(targets):
            snapshot[cursor] = top_ratio(uf)
            cursor += 1
        critical.append(reached)
        snapshots.append(snapshot)
    elapsed = time.perf_counter() - started

    done = len(critical)
    results: List[SpreadBatchResult] = []
    total_points = len(p_values)
    for k, p in enumerate(p_values, start=1):
        success = sum(1 for value in critical if value <= p)
        ratio_sum = sum(snapshot[targets.index(float(p))] for snapshot in snapshots)
        res = SpreadBatchResult(
            p=p,
            rows=grid.rows,
            cols=grid.cols,
            trials=done,
            success=success,
            threshold=grid.threshold,
            criterion="span",
            direction="undirected",
            lattice=lattice,
            inject="top",
            ratio_sum=ratio_sum,
            elapsed=elapsed,
        )
        results.append(res)
        if progress is not None:
            progress(k, total_points, res)
        if cancel is not None and cancel.is_set():
            break
    return results


def scan_curve(
    p_values: Sequence[float],
    rows: int = 40,
    cols: Optional[int] = None,
    trials: int = 200,
    rng: RngLike = None,
    direction: str = "undirected",
    lattice: str = "square",
    inject: str = "top",
    criterion: str = DEFAULT_CRITERION,
    threshold: float = DEFAULT_THRESHOLD,
    progress: Optional[Callable[[int, int, SpreadBatchResult], None]] = None,
    cancel=None,
) -> List[SpreadBatchResult]:
    """扫描一组 ``p`` 值，返回每个密度下的统计结果，用于绘制曲线。

    progress : callable(done, total, SpreadBatchResult) | None
        每完成一个 p 值调用一次。

    **单遍扫描加速**：默认组合（``criterion="span"`` + ``inject="top"`` +
    ``direction="undirected"``）走 :func:`_scan_curve_by_critical` —— 一次试验做一遍并查集
    扫描就给出整条曲线（实测快约"点数"倍）。其余组合仍走"逐 p 重跑"，因为这三点是它成立的
    前提：判据要与注水点无关（``span`` ✓，``origin`` / ``area`` ✗）；注水点要与 ``p`` 无关
    （``top`` ✓，``random`` / ``center`` 的起点本身随 ``p`` 变 ✗）；方向必须无向
    （有向模式下"从顶行沿允许方向可达底行"与"顶行与底行无向连通"不是一回事 ✗）。
    """
    rng = _resolve_rng(rng)
    if criterion == "span" and inject == "top" and direction == "undirected":
        return _scan_curve_by_critical(
            p_values, rows=rows, cols=cols, trials=trials, rng=rng,
            lattice=lattice, progress=progress, cancel=cancel,
        )
    results: List[SpreadBatchResult] = []
    total_points = len(p_values)
    for k, p in enumerate(p_values, start=1):
        res = batch_spread_probability(
            rows=rows, cols=cols, p=p, trials=trials, rng=rng, direction=direction,
            lattice=lattice, inject=inject, criterion=criterion,
            threshold=threshold, cancel=cancel,
        )
        results.append(res)
        if progress is not None:
            progress(k, total_points, res)
        if cancel is not None and cancel.is_set():
            break
    return results


# ----------------------------------------------------------------------
# 与界面层的数据交换：把格地压缩成 0/1 字符串
# ----------------------------------------------------------------------
def encode_sites(model: "SitePercolation") -> str:
    """把格地编码成 0/1 字符串（行优先，1 表示被占据），供前端轻量还原。

    走"字节数组 -> 字符串"而不是逐格拼字符：大格地（几百 × 几百）也不必逐格 Python 化。
    """
    chars = np.where(model.occupied.reshape(-1), ord("1"), ord("0")).astype(np.uint8)
    return chars.tobytes().decode("ascii")


# ----------------------------------------------------------------------
# 直接运行本文件时的自检：对比实验值与阈值表
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    try:  # Windows 控制台默认 GBK，需要切到 UTF-8 才能正常输出中文
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    def apparent_crossing(rows, direction, trials, lo, hi, rng, steps=8):
        """二分求「贯通概率 = 1/2」的表观交点（判据固定为贯通）。"""
        for _ in range(steps):
            mid = (lo + hi) / 2.0
            res = batch_spread_probability(
                rows=rows, p=mid, trials=trials, rng=rng,
                direction=direction, criterion="span",
            )
            if res.probability < 0.5:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    print("=" * 78)
    print("点渗流自检 1：贯通判据的表观交点 vs 理论临界密度 p_c")
    print("=" * 78)
    print("判据：格地上是否存在「顶行 ↔ 底行」的纵贯簇 —— 这才是 p_c 所对应的判据。")
    print("说明：n = 40 的有限尺寸下，表观交点在 p_c 附近有百分之几的偏差，尺寸越大越紧。")
    print(f"{'方向模式':<16}{'p_c':>9}{'来源':>7} | {'表观交点':>9} | {'P(p_c)':>8} | {'平均比例':>8}")
    print("-" * 78)

    shared_rng = np.random.default_rng(20260913)
    for direction in DIRECTIONS:
        model = SitePercolation(rows=40, p=0.6, direction=direction)
        pc = model.theoretical_pc
        if pc is None:
            continue
        source = "估计" if model.pc_is_estimate else "文献"
        mid = batch_spread_probability(
            rows=40, p=pc, trials=400, rng=shared_rng,
            direction=direction, criterion="span",
        )
        cross = apparent_crossing(40, direction, 200, pc - 0.10, pc + 0.10, shared_rng)
        print(f"{DIRECTION_NAMES[direction]:<16}{pc:>9.4f}{source:>7} |"
              f"{cross:>9.4f} | {mid.probability:>8.3f} | {mid.mean_ratio:>8.3f}")
    print("-" * 78)
    print("尺寸依赖（方格网无向）：表观交点随尺寸逼近 p_c，P(p_c) 始终在 0.5 上下抖动。")
    for n, trials in ((40, 200), (80, 120)):
        cross = apparent_crossing(n, "undirected", trials, 0.55, 0.65, shared_rng)
        res = batch_spread_probability(
            rows=n, p=THEORETICAL_PC, trials=400, rng=shared_rng, criterion="span"
        )
        print(f"  n = {n:<4}表观交点 {cross:.4f} | P(p_c) = {res.probability:.3f}"
              f"  （p_c = {THEORETICAL_PC:.4f}）")
    print("-" * 78)

    print("自检 2：面积判据的「交点」不是固定的（方格网 40×40，p = 0.60）")
    print("说明：蔓延比例 ≥ 阈值就算成功。阈值越高，要求越苛刻，同一 p 下的概率越低；")
    print("      把这条曲线与 p 轴的交点找出来，会随阈值（以及网格尺寸、注水方式）漂移。")
    print(f"{'阈值':>8} | " + " | ".join(f"{INJECT_NAMES[i]:>10}" for i in INJECT_MODES))
    print("-" * 78)
    for threshold in (0.1, 0.3, 0.5, 0.7, 0.9):
        cells: List[str] = []
        for inject in INJECT_MODES:
            res = batch_spread_probability(
                rows=40, p=0.60, trials=300, rng=shared_rng,
                inject=inject, criterion="area", threshold=threshold,
            )
            cells.append(f"{res.probability:>10.3f}")
        print(f"{threshold:>8.0%} | " + " | ".join(cells))
    print("-" * 78)

    print("自检 3：三种判据 × 三种注水方式（方格网 32×32，p = 0.6，各 300 次）")
    print("关键差别：贯通判据问「格地上有没有纵贯簇」，起点判据问「你这一把火纵贯吗」。")
    for criterion in CRITERIA:
        for inject in INJECT_MODES:
            res = batch_spread_probability(
                rows=32, p=0.6, trials=300, rng=shared_rng,
                inject=inject, criterion=criterion,
            )
            print(f"  [{res.criterion_name}] {INJECT_NAMES[inject]:<8}"
                  f" P = {res.probability:.3f}   平均蔓延比例 = {res.mean_ratio:.3f}")
        print("-" * 78)

    probe = SitePercolation(rows=32, p=0.6, rng=shared_rng, inject="random")
    span_ok = 0
    origin_in = 0
    for _ in range(300):
        probe.regenerate()
        if probe.has_spanning_cluster():
            span_ok += 1
            if probe.origin_spans():
                origin_in += 1
    if span_ok:
        print(f"同一批格地：存在纵贯簇 {span_ok}/300，其中随机注水点恰好落在簇内 "
              f"{origin_in} 次（{origin_in / span_ok:.1%}）")
        print("—— 这就是「起点判据」比「贯通判据」低的原因：火源可能落在纵贯簇之外。")
    print("-" * 78)
    print("提示：贯通判据下注水方式完全不影响结果（判据问的是整片格地的性质）；")
    print("      起点判据 / 面积判据下影响很大 —— 单点注水额外要求「起点落在纵贯簇里」。")
