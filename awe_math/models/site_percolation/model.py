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

两种成功判据（务必区分）
------------------------
``p_c ≈ 0.5927`` 说的是「出现无限大簇 / 纵贯簇」的相变，**不是**「蔓延面积达到某个比例」。
因此本模块把「什么算成功」显式抽成一个维度：

* ``span`` **贯通判据**（默认）：格地上**是否存在纵贯簇**，即是否有一个占据簇同时连通
  顶行与底行。这正是文献里 ``p_c`` 所用的判据，所以它的 ``P(p) = 1/2`` 交点才落在
  ``p_c`` 上。该判据**与注水点无关**（等价于「顶端整行注水，水能否到达底行」）；
  选它时 ``inject`` 只影响单次动画的起点，不影响统计结果。
* ``area`` **面积判据**：从注水点出发的蔓延簇占整片格地的比例 ≥ ``threshold``。
  它回答的是「随机一棵树起火最终烧掉多大面积」，**没有固定的临界密度**：
  ``P(p) = 1/2`` 的交点随**所设比例、网格尺寸、注水方式**一起变化——
  比例定得越大交点越高，单点注水还会额外要求「起点恰好落在巨簇里」。
  只有把比例取得很小、网格取得很大时，它才会缓慢地往 ``p_c`` 靠拢。

关于临界值
----------
方格点渗流（无向）的理论临界密度 ``p_c ≈ 0.5927``，三角网点渗流 ``p_c = 0.5``；
方向模式会改变临界值（见 :data:`THEORETICAL_PC_BY_COMBO` 与估计值表）。
与边渗流一样：``p_c`` 只取决于格子与方向，与矩形长宽比、注水点位置无关
——但这些结论都**只在 ``span`` 判据下成立**。

本模块只依赖 Python 标准库，可单独导入使用（不含任何绘图/GUI 代码）。
"""

from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple, Union

__all__ = [
    "THEORETICAL_PC",
    "THEORETICAL_PC_BY_COMBO",
    "ESTIMATED_PC_BY_COMBO",
    "DEFAULT_THRESHOLD",
    "CRITERIA",
    "CRITERION_NAMES",
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

#: 成功判据：``span`` = 存在纵贯簇（对应 p_c）/ ``area`` = 蔓延面积达到比例阈值
CRITERIA: Tuple[str, ...] = ("span", "area")

#: 成功判据的短名（用于结果文本）
CRITERION_NAMES: Dict[str, str] = {
    "span": "贯通判据",
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
    "span": "贯通判据：格地上存在从顶行连通到底行的纵贯簇（这就是 p_c 所对应的判据）",
    "area": "面积判据：蔓延簇占整片格地的比例达到阈值（无固定临界值，随比例/尺寸/注水方式变化）",
}

#: 随机源可以传入 None / int（种子）/ random.Random 实例
RngLike = Union[None, int, random.Random]

#: 进度回调：progress(已完成, 总数, 成功次数)
ProgressCallback = Callable[[int, int, int], None]


def _resolve_rng(rng: RngLike = None) -> random.Random:
    """把 None / 种子 / Random 实例统一转换成一个 ``random.Random`` 对象。"""
    if isinstance(rng, random.Random):
        return rng
    if rng is None:
        return random.Random()
    return random.Random(rng)


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
        return self.spans if self.criterion == "span" else self.engulfed

    @property
    def criterion_name(self) -> str:
        return CRITERION_NAMES.get(self.criterion, self.criterion)


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
    inject: str = "random"
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

        ``criterion="span"`` 时统计的是**存在纵贯簇**的频率（交点即 ``p_c``）；
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
        ``random``（随机一个占据格）/ ``center``（中心附近）/ ``top``（顶端整行）。
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
        inject: str = "random",
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
        self.rng: random.Random = _resolve_rng(rng)
        #: occupied[r][c] 表示该格是否被占据
        self.occupied: List[List[bool]] = []
        #: inject == "random" 时使用的随机注水点（随格地一起生成，便于复现）
        self._random_source: Optional[int] = None
        #: 当前格地「是否存在纵贯簇」的缓存（None 表示尚未判定）
        self._spanned: Optional[bool] = None
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
        """临界值的展示文本（随判据变化：面积判据下没有固定阈值）。"""
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
        """
        if p is not None:
            self.p = _clamp(float(p), 0.0, 1.0)
        if seed is not None:
            self.rng = random.Random(seed)

        rows, cols, prob, rnd = self.rows, self.cols, self.p, self.rng.random
        self.occupied = [[rnd() < prob for _ in range(cols)] for _ in range(rows)]

        if self.inject == "random":
            self._random_source = None      # 延迟到取用时再挑，避免空位过多时的浪费
        self._spanned = None                # 格地换了，贯通判定缓存作废
        return self

    def is_occupied(self, index: int) -> bool:
        r, c = divmod(index, self.cols)
        return self.occupied[r][c]

    def occupied_count(self) -> int:
        return sum(sum(row) for row in self.occupied)

    def occupied_ratio(self) -> float:
        return self.occupied_count() / self.node_count if self.node_count else 0.0

    def iter_occupied(self) -> Iterator[int]:
        """迭代所有被占据的格子。"""
        cols = self.cols
        for r, row in enumerate(self.occupied):
            base = r * cols
            for c, flag in enumerate(row):
                if flag:
                    yield base + c

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

    # ------------------------------------------------------------------
    # 注水点
    # ------------------------------------------------------------------
    def source_nodes(self) -> List[int]:
        """注水点：随机一个占据格 / 中心附近的占据格 / 顶端整行的占据格。"""
        rows, cols = self.rows, self.cols

        if self.inject == "top":
            return [c for c in range(cols) if self.occupied[0][c]]

        if self.inject == "center":
            return [self._nearest_to_center()] if self.occupied_count() else []

        if self._random_source is None:
            total = self.occupied_count()
            if total <= 0:
                return []
            target = self.rng.randrange(total)
            for rank, index in enumerate(self.iter_occupied()):
                if rank == target:
                    self._random_source = index
                    break
        if self._random_source is None or not self.is_occupied(self._random_source):
            return []
        return [self._random_source]

    def _nearest_to_center(self) -> int:
        """离格地中心最近的占据格（按平方距离，平局取行优先靠前者）。"""
        rows, cols = self.rows, self.cols
        cr, cc = (rows - 1) / 2.0, (cols - 1) / 2.0
        best, best_dist = -1, float("inf")
        for index in self.iter_occupied():
            r, c = divmod(index, cols)
            dist = (r - cr) ** 2 + (c - cc) ** 2
            if dist < best_dist:
                best, best_dist = index, dist
        return best

    # ------------------------------------------------------------------
    # 贯通判定（criterion == "span"）
    # ------------------------------------------------------------------
    def has_spanning_cluster(self) -> bool:
        """格地上是否存在**纵贯簇**（同时连通顶行与底行的占据簇）。

        这就是 ``p_c`` 所对应的判据：从顶行的每个占据格出发，看能否沿可蔓延关系
        到达底行。判定结果会在同一个格地上缓存，重新生成格地后失效。

        **与注水点无关**：``inject`` 只决定单次动画从哪儿开始；判据问的是
        「整片格地有没有纵贯簇」，所以统计时不受注水方式影响。
        （当 ``inject == "top"`` 时，它与「水从顶端整行到达底行」完全等价。）
        """
        if self._spanned is None:
            self._spanned = self._scan_span()
        return self._spanned

    def _scan_span(self) -> bool:
        """自上而下的 BFS：顶行占据格能否到达底行（方向模式照常生效）。"""
        rows, cols = self.rows, self.cols
        if not any(self.occupied[0]) or not any(self.occupied[rows - 1]):
            return False

        last_row_start = (rows - 1) * cols
        seen = bytearray(self.node_count)
        queue: deque = deque()
        for c in range(cols):
            if self.occupied[0][c]:
                seen[c] = 1
                queue.append(c)

        while queue:
            idx = queue.popleft()
            if idx >= last_row_start:
                return True
            for nb in self.neighbors(idx):
                if not seen[nb]:
                    seen[nb] = 1
                    queue.append(nb)
        return False

    # ------------------------------------------------------------------
    # 蔓延
    # ------------------------------------------------------------------
    def _spread(self, origins: Sequence[int], with_layers: bool = True):
        """从给定注水点做 BFS，返回 (蔓延格子, 分层, 是否蔓延到底端)。"""
        rows, cols = self.rows, self.cols
        last_row_start = (rows - 1) * cols
        seen = bytearray(self.node_count)
        layers: List[List[int]] = []
        order: List[int] = []
        reached_bottom = False
        queue: deque = deque()

        for idx in origins:
            if seen[idx] or not self.occupied[idx // cols][idx % cols]:
                continue
            seen[idx] = 1
            queue.append((idx, 0))       # 多个注水点同属第 0 层

        while queue:
            idx, depth = queue.popleft()
            order.append(idx)
            if idx >= last_row_start:
                reached_bottom = True
            if with_layers:
                if depth == len(layers):
                    layers.append([])
                layers[depth].append(idx)
            nd = depth + 1
            for nb in self.neighbors(idx):
                if not seen[nb]:
                    seen[nb] = 1
                    queue.append((nb, nd))

        return order, layers, reached_bottom

    def spread_size(self, origins: Optional[Sequence[int]] = None) -> int:
        """只统计蔓延格数（批量统计的高速路径，不记录分层）。"""
        return len(self._spread(origins or self.source_nodes(), with_layers=False)[0])

    def simulate(self, origins: Optional[Sequence[int]] = None) -> SpreadResult:
        """从注水点蔓延一次，返回完整结果（含逐层信息）。

        ``origins`` 省略时按 ``inject`` 设定自动挑选注水点。
        """
        started = time.perf_counter()
        source = list(origins) if origins is not None else self.source_nodes()
        spread, layers, reached_bottom = self._spread(source)
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
            spans=self.has_spanning_cluster(),
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
    inject: str = "random",
    criterion: str = DEFAULT_CRITERION,
    threshold: float = DEFAULT_THRESHOLD,
    progress: Optional[ProgressCallback] = None,
    cancel=None,
) -> SpreadBatchResult:
    """在固定密度 ``p`` 下做 ``trials`` 次独立实验，统计「成功」的频率。

    每次实验都重新生成格地。「成功」由 ``criterion`` 决定：

    * ``criterion="span"``：这次生成的格地上**存在纵贯簇**（顶行 ↔ 底行）。
      交点即 ``p_c``，且**与注水方式无关**（判据问的是整片格地的性质）；
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
        else:
            ok = (model.spread_size() / node_count) >= model.threshold if node_count else False
        if ok:
            success += 1
        ratio_sum += model.spread_size() / node_count if node_count else 0.0
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


def scan_curve(
    p_values: Sequence[float],
    rows: int = 40,
    cols: Optional[int] = None,
    trials: int = 200,
    rng: RngLike = None,
    direction: str = "undirected",
    lattice: str = "square",
    inject: str = "random",
    criterion: str = DEFAULT_CRITERION,
    threshold: float = DEFAULT_THRESHOLD,
    progress: Optional[Callable[[int, int, SpreadBatchResult], None]] = None,
    cancel=None,
) -> List[SpreadBatchResult]:
    """扫描一组 ``p`` 值，返回每个密度下的统计结果，用于绘制曲线。

    progress : callable(done, total, SpreadBatchResult) | None
        每完成一个 p 值调用一次。
    """
    rng = _resolve_rng(rng)
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
    """把格地编码成 0/1 字符串（行优先，1 表示被占据），供前端轻量还原。"""
    return "".join("1" if flag else "0" for row in model.occupied for flag in row)


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

    shared_rng = random.Random(20260913)
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

    print("注水方式对照（方格网 32×32，p = 0.6，各 300 次）")
    for criterion in CRITERIA:
        for inject in INJECT_MODES:
            res = batch_spread_probability(
                rows=32, p=0.6, trials=300, rng=shared_rng,
                inject=inject, criterion=criterion,
            )
            print(f"  [{res.criterion_name}] {INJECT_NAMES[inject]:<8}"
                  f" P = {res.probability:.3f}   平均蔓延比例 = {res.mean_ratio:.3f}")
        print("-" * 78)
    print("提示：贯通判据下注水方式完全不影响结果（判据问的是整片格地的性质），")
    print("      面积判据下注水方式影响很大 —— 单点注水额外要求「起点落在巨簇里」。")
