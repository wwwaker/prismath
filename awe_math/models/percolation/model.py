# -*- coding: utf-8 -*-
"""
格子网边渗流（Bond Percolation）核心模型
=========================================

在 **rows × cols** 的格子网（行数 ≠ 列数就是矩形网格）上，每条「边」以概率 ``p``
独立地设为「流通」或「阻断」，水从注水点出发沿流通边蔓延。

可选维度
--------
* **格子** ``lattice``：

  - ``square``：方格网，每点最多 4 个邻居；
  - ``triangular``：三角网，每点最多 6 个邻居（奇数行右移半格 + 两条斜边）。

* **形状** ``rows`` / ``cols``：行列分开指定，``rows != cols`` 即矩形网格。

* **方向** ``direction``：

  - ``undirected``：无向，水可向四面八方流动（标准渗流）；
  - ``no_up``：不允许向上，只向下 / 左 / 右；
  - ``down_right``：只允许向下 / 向右（两个出边，经典有向渗流）；
  - ``down_left``：只允许向下 / 向左（``down_right`` 的镜像）。

* **注水点** ``inject``：

  - ``top``：顶端整行同时注水（经典渗流实验，判定的是「横贯」事件）；
  - ``center``：中心单点注水（观察一个水团能否长到底端）；
  - ``random``：随机单点注水（等价于「随机挑一个点，看它所在的水团能否到底端」）。

* **成功判据** ``criterion``：``span``（贯通）/ ``area``（面积），见下。

三种成功判据（务必区分）
------------------------
``criterion`` 决定「什么算成功」：

* ``span`` **贯通判据**（默认）：整张网格上**是否存在从顶行连通到底行的纵贯簇**，
  也就是「顶端整行注水能否流到底端」。这才是 ``p_c`` 所用的判据，它的
  ``P(p) = 1/2`` 交点才落在 ``p_c`` 上；该判据**与注水点无关**（选它时 ``inject``
  只影响单次动画的起点，不影响统计结果）。
* ``origin`` **起点判据**：**从注水点出发的那一簇**是否纵贯（同时碰到顶行与底行）。
  与 ``span`` 的唯一差别是「还要求注水点落在纵贯簇里」：顶端整行注水时完全等价，
  单点注水（中心 / 随机）时交点明显更高 —— 网格上明明有纵贯簇，
  但水从一个随机节点注入时，可能根本没落在簇里。
* ``area`` **面积判据**：浸润节点数占总节点数的比例 ≥ ``threshold``。
  它回答的是「一次注水能浸透多大范围」，**没有固定的临界值**：交点随所设比例、
  网格尺寸、注水方式一起变化（比例越大交点越高，单点注水还会额外要求
  「起点恰好落在巨簇里」）。

后两种判据的交点都**不是** ``p_c`` —— 只有 ``span`` 判据的 1/2 交点等于 ``p_c``。

关于临界值
----------
``p_c`` 是**无限大格子的性质**，只取决于格子的连接结构与方向模式，与网格是正方形
还是矩形、以及注水点在哪里都**无关**（后两者只影响有限尺寸下的表观曲线形状）
—— 这些结论都**只在 ``span`` 判据下成立**。
已知的解析值 / 文献值见 :data:`THEORETICAL_PC_BY_COMBO`，文献不全的组合给出蒙特卡洛
估计值（见 :data:`ESTIMATED_PC_BY_COMBO`，界面会标注为「估计值」）。

实现要点（为什么这样写）
------------------------
1. **边的流通状态是一整块 numpy 布尔数组**：生成一次网格 = 一次
   ``rng.random(边数) < p``，而不是逐边 Python 随机调用；四张分类型边表
   （``h_edge`` / ``v_edge`` / ``dl_edge`` / ``dr_edge``）仍是"唯一真相"，
   :func:`encode_edges` 与界面读的就是它们。
2. **另有一条"按边号摊平"的 ``bytes`` 缓存**：逐层推进要逐边问"这条边通不通"，
   ``bytes`` 下标比 numpy 标量索引快一个量级。
3. **邻居表 + 逐层推进**：方向过滤（四种模式）与格子类型在**建模时**编译成邻居表
   （每个节点"允许走出去"的 ``(邻居, 边号)``）。蔓延是唯一必须串行的部分，所以它
   **刻意不用 numpy**：内层循环只剩"查这条边通不通 + 查这个点浸过没有"。
   （点渗流那边试过"逐层数组运算"，实测在小网格上反而更慢，这里直接采用紧凑循环。）
4. **无向模式的并查集路径照旧保留**（:meth:`PercolationGrid.percolates_uf`）：它一次
   union 所有流通边，比 BFS 更快，而且正是"临界 p"单遍扫描的现成地基。

实测（Windows / Python 3.13，方格网 40×40，p 取在 p_c 附近最费时；中位数）
----------------------------------------------------------------------
复现命令：``python -m tests.bench percolation``

* 贯通判据 × 无向批量 300 次 **142 ms**（≈ 0.47 ms/次试验，走并查集）；
* **扫描 5 个 p 各 100 次 174 ms** —— 默认组合走"临界 p"单遍扫描（见 :func:`scan_curve`），
  对照"逐 p 重跑"的老路径 502 ms 约快 **3×**；点数越多越划算（20 点时约 11×）；
* 贯通判据 × 有向下右批量 300 次 **97 ms**（有向模式走 BFS，反而比并查集那条路更快）；
* 起点判据 × 随机单点 300 次 **29 ms**；面积判据 × 中心单点 300 次 **38 ms**；
* 三角网贯通批量 300 次 **787 ms**（p 正落在 p_c = 0.5 上：簇最大、每点最多 6 条边）；
* 界面用的单次模拟（含分层）**5.6 ms**（含建邻居表）；内置自检 **24.35 s → 10.6 s**（约 2.3×）。

**为什么这里只快了 2.3×（点渗流是 4.9×）**：无向模式的批量统计走
:meth:`PercolationGrid.percolates_uf`，它逐边 ``union`` 是纯 Python 循环 —— 生成与遍历
变快之后，**并查集成了新的瓶颈**。这也正是"临界 p 单遍扫描"（一次试验做一遍 union 扫描
就能给出整条 ``P(p)`` 曲线，而不是每个 ``p`` 重跑一遍）值得做的原因。

本模块只依赖标准库 + ``numpy``；numpy 现在是**必需依赖**（内核统一向量化，不再维护
标准库回退实现 —— 见 README 的「依赖规则」）。不含任何绘图 / GUI 代码，可单独导入。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple, Union

import numpy as np

__all__ = [
    "THEORETICAL_PC",
    "THEORETICAL_PC_BY_LATTICE",
    "THEORETICAL_PC_BY_COMBO",
    "ESTIMATED_PC_BY_COMBO",
    "DEFAULT_THRESHOLD",
    "CRITERIA",
    "CRITERION_NAMES",
    "CRITERION_DESCRIPTIONS",
    "DEFAULT_CRITERION",
    "LATTICES",
    "LATTICE_NAMES",
    "DIRECTIONS",
    "DIRECTION_NAMES",
    "INJECT_MODES",
    "INJECT_NAMES",
    "UnionFind",
    "PercolationGrid",
    "SimResult",
    "BatchResult",
    "batch_percolation_probability",
    "scan_curve",
    "encode_edges",
]

#: 方格网键渗流的经典临界值（保留旧名，便于外部引用；对应 ``criterion="span"``）
THEORETICAL_PC: float = 0.5

#: 成功判据：
#:
#: * ``span``：整张网格是否存在纵贯簇 —— 对应 ``p_c``，**与注水方式无关**；
#: * ``origin``：从注水点出发的那一簇是否纵贯 —— **随注水方式变化**（顶端整行时与 ``span`` 相同）；
#: * ``area``：浸润面积达到比例阈值 —— 没有固定临界值。
CRITERIA: Tuple[str, ...] = ("span", "origin", "area")

#: 成功判据的短名（用于结果文本）
CRITERION_NAMES: Dict[str, str] = {
    "span": "贯通判据",
    "origin": "起点判据",
    "area": "面积判据",
}

#: 成功判据的完整说明（界面与日志用）
CRITERION_DESCRIPTIONS: Dict[str, str] = {
    "span": "贯通判据：整张网格存在从顶行连通到底行的纵贯簇"
            "（p_c 所对应的判据，与注水方式无关）",
    "origin": "起点判据：从注水点出发的那一簇同时碰到顶行与底行"
              "（随注水方式变化；顶端整行注水时与贯通判据完全相同）",
    "area": "面积判据：浸润节点占总节点的比例达到阈值"
            "（无固定临界值，随比例/尺寸/注水方式变化）",
}

#: 默认成功判据：贯通判据（这才是 p_c 所对应的判据）
DEFAULT_CRITERION: str = "span"

#: ``criterion="area"`` 时判定「浸透全网格」的浸润比例阈值
DEFAULT_THRESHOLD: float = 0.5

#: 「格子 -> 无向键渗流临界值」的简表（保留旧名）
THEORETICAL_PC_BY_LATTICE: Dict[str, float] = {
    "square": 0.5,                                   # 1/2（解析）
    "triangular": 2.0 * math.sin(math.pi / 18.0),    # ≈ 0.347296（解析）
}

#: (格子, 方向) -> 临界值：解析解或文献值
#:
#: 这些值都是**贯通判据**（``criterion="span"``）下的临界值 —— 即「水从顶行贯通到底行」
#: 的相变点。面积判据没有对应的固定值，所以不要把它套到这里。
THEORETICAL_PC_BY_COMBO: Dict[Tuple[str, str], float] = {
    ("square", "undirected"): 0.5,                       # 解析：1/2
    ("triangular", "undirected"): 2.0 * math.sin(math.pi / 18.0),   # 解析
    ("square", "down_right"): 0.6447,                    # 经典有向渗流（2 出边）
    ("square", "down_left"): 0.6447,                     # 与上者镜像同值
}

#: (格子, 方向) -> 蒙特卡洛估计值（这些组合没有已知解析解，界面会标注「估计值」）
#:
#: 估计方法：在 n = 320 / 640 的方形网格上二分求 P(p) = 0.5 的交点（n=640 与 n=320
#: 的结果一致到 0.001，说明剩余有限尺寸偏差很小）。注意有向渗流的表观交点通常
#: 从下方逼近真值，例如 (square, down_right) 在 n = 60/160/320 时分别测得
#: 0.627 / 0.633 / 0.641，正在逼近文献值 0.6447。
ESTIMATED_PC_BY_COMBO: Dict[Tuple[str, str], float] = {
    ("square", "no_up"): 0.537,
    ("triangular", "no_up"): 0.397,
    ("triangular", "down_right"): 0.453,
    ("triangular", "down_left"): 0.453,
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
    "undirected": "无向（四面流动）",
    "no_up": "不允许向上",
    "down_right": "只允许向下/向右",
    "down_left": "只允许向下/向左",
}

#: 注水方式与中文名
INJECT_MODES: Tuple[str, ...] = ("top", "center", "random")
INJECT_NAMES: Dict[str, str] = {
    "top": "顶端整行",
    "center": "中心单点",
    "random": "随机单点",
}

#: 随机源可以传入 None / int（种子）/ numpy Generator 实例
RngLike = Union[None, int, np.random.Generator]

#: 进度回调：progress(已完成, 总数, 成功次数)
ProgressCallback = Callable[[int, int, int], None]


def _resolve_rng(rng: RngLike = None) -> np.random.Generator:
    """把 None / 种子 / Generator 实例统一转换成一个 numpy 随机源。

    注意：从 ``random.Random`` 换成 numpy 之后，**同一个种子不再生成同一张网格** ——
    可复现性只在同一实现内成立（这是本次重构被明确接受的代价之一）。
    """
    if isinstance(rng, np.random.Generator):
        return rng
    return np.random.default_rng(rng)


def _derive_rng(parent: np.random.Generator) -> np.random.Generator:
    """从主随机源派生一个独立随机源（给"随机注水点"专用）。

    这样「随机注水」不会消耗生成网格的那串随机数：同一颗种子下，不同注水方式生成的
    网格序列完全相同，「贯通判据与注水方式无关」这件事才能在同一批网格上逐次验证。
    """
    return np.random.default_rng(int(parent.integers(0, 2 ** 63)))


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


class UnionFind:
    """并查集（带路径压缩 + 按秩合并），用于快速判断连通性。

    ``size`` 记录每个根所在分量的节点数 —— "临界 p 单遍扫描"要用它跟踪**顶端簇**随概率
    的生长（"平均浸润比例"就是这条分段常量轨迹）。
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
        # 路径压缩
        while parent[x] != root:
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


@dataclass
class SimResult:
    """一次完整模拟（单次生成 + 渗透）的结果，供可视化使用。"""

    rows: int
    cols: int
    p: float
    #: 本次模拟是否从注水点贯通到底端（也就是「水到达底端整行」）
    percolates: bool
    #: 所有被浸润的节点索引（行优先：index = row * cols + col）
    wet: List[int] = field(default_factory=list)
    #: 按 BFS 层分组的浸润节点，layers[k] 表示距注水点 k 步的节点
    layers: List[List[int]] = field(default_factory=list)
    #: 本次实际使用的注水点（指定注水点时与 ``inject`` 的默认选择不同）
    origins: List[int] = field(default_factory=list)
    #: 整张网格是否存在纵贯簇（顶行 ↔ 底行，与注水点无关）
    spans: bool = False
    #: 从注水点出发的那一簇是否纵贯（同时碰到顶行与底行）
    origin_spans: bool = False
    #: 纵贯簇的节点索引（没有纵贯簇时为空列表）—— 供界面把它高亮出来
    spanning_nodes: List[int] = field(default_factory=list)
    #: 本次「是否成功」采用的是哪种判据：``span`` / ``area``
    criterion: str = DEFAULT_CRITERION
    #: ``criterion="area"`` 时的浸润比例阈值
    threshold: float = DEFAULT_THRESHOLD
    open_edge_count: int = 0
    total_edge_count: int = 0
    elapsed: float = 0.0

    @property
    def size(self) -> int:
        """行数（保留旧名，便于外部沿用 ``result.size``）。"""
        return self.rows

    @property
    def shape(self) -> Tuple[int, int]:
        return self.rows, self.cols

    @property
    def node_count(self) -> int:
        return self.rows * self.cols

    @property
    def wet_count(self) -> int:
        return len(self.wet)

    @property
    def wet_ratio(self) -> float:
        """浸润节点占全部节点的比例（面积判据用的量）。"""
        return self.wet_count / self.node_count if self.node_count else 0.0

    @property
    def open_ratio(self) -> float:
        """实际流通边占全部边的比例（有限网格下的实测值，围绕 p 波动）。"""
        return self.open_edge_count / self.total_edge_count if self.total_edge_count else 0.0

    @property
    def depth(self) -> int:
        """水渗透的层数（BFS 最大层数）。"""
        return len(self.layers)

    @property
    def criterion_name(self) -> str:
        return CRITERION_NAMES.get(self.criterion, self.criterion)

    @property
    def engulfed(self) -> bool:
        """**面积判据**是否成立：浸润节点占总节点的比例达到 ``threshold``。"""
        return self.wet_ratio >= self.threshold

    @property
    def success(self) -> bool:
        """按本次采用的 ``criterion`` 判定「是否成功」。"""
        if self.criterion == "span":
            return self.spans
        if self.criterion == "origin":
            return self.origin_spans
        return self.engulfed

    @property
    def spanning_count(self) -> int:
        """纵贯簇的节点数。"""
        return len(self.spanning_nodes)

    @property
    def spanning_ratio(self) -> float:
        """纵贯簇占全部节点的比例（与浸润比例是两回事）。"""
        return self.spanning_count / self.node_count if self.node_count else 0.0

    @property
    def origin_in_spanning(self) -> bool:
        """注水点是否落在纵贯簇里。

        这是「判定贯通、却只看见一小片浸润」的唯一原因：这次的注水点不在纵贯簇内，
        而判据问的是整张网格有没有纵贯簇，两者互不影响。
        """
        if not self.origins or not self.spanning_nodes:
            return False
        inside = set(self.spanning_nodes)
        return any(origin in inside for origin in self.origins)


@dataclass
class BatchResult:
    """一批独立重复实验的统计结果。"""

    p: float
    rows: int
    cols: int
    trials: int
    success: int
    criterion: str = DEFAULT_CRITERION
    threshold: float = DEFAULT_THRESHOLD
    direction: str = "undirected"
    lattice: str = "square"
    inject: str = "top"
    #: 各次实验浸润节点比例之和（用于计算平均浸润比例）
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

        ``criterion="span"`` 时统计的是**整张网格存在纵贯簇**的频率（交点即 ``p_c``）；
        ``criterion="origin"`` 时统计的是**注水点的那一簇纵贯**的频率（随注水方式变化）；
        ``criterion="area"`` 时统计的是浸润比例达到阈值的频率（无固定交点）。
        """
        return self.success / self.trials if self.trials else 0.0

    @property
    def mean_ratio(self) -> float:
        """平均浸润比例（随 p 上升而急剧抬升，比频率更平滑）。

        注意：这是**浸润节点占全部节点**的比例，与判据无关，始终可比较。
        """
        return self.ratio_sum / self.trials if self.trials else 0.0

    @property
    def stderr(self) -> float:
        """频率估计的标准误 sqrt(P(1-P)/N)。"""
        prob = self.probability
        return (prob * (1.0 - prob) / self.trials) ** 0.5 if self.trials else 0.0


class PercolationGrid:
    """格子网边渗流模型（方格网 / 三角网，方形 / 矩形，四种方向模式，三种注水方式）。

    参数
    ----
    rows, cols : int
        行数与列数；``cols`` 省略时取 ``rows``（正方形网格）。
    p : float
        每条边的流通概率，取值 ``[0, 1]``。
    rng : None | int | numpy.random.Generator
        随机源，可以是种子（便于复现；同一种子在同一实现内可复现）。
    direction : str
        ``undirected`` / ``no_up`` / ``down_right`` / ``down_left``，见模块文档。
    lattice : str
        ``square``（4 邻域）或 ``triangular``（6 邻域）。
    inject : str
        ``top``（顶端整行）/ ``center``（中心单点）/ ``random``（随机单点）。
    criterion : str
        ``span``（贯通判据：是否存在纵贯簇，对应 ``p_c``）/ ``area``（面积判据：浸润比例 ≥
        ``threshold``）。默认 ``span``。
    threshold : float
        ``criterion="area"`` 时判定「浸透全网格」的浸润比例，默认 0.5。
    """

    def __init__(
        self,
        rows: int = 30,
        cols: Optional[int] = None,
        p: float = 0.5,
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
        #: 生成网格的那串随机数，同一颗种子下不同注水方式的网格序列完全相同，
        #: 「贯通判据与注水方式无关」这件事才能在同一批网格上被逐次验证。
        self._source_rng: np.random.Generator = _derive_rng(self.rng)

        #: h_edge[r][c] 表示 (r, c) 与 (r, c+1) 之间的水平边是否流通（numpy 布尔表）
        self.h_edge: np.ndarray = np.zeros((self.rows, max(self.cols - 1, 0)), dtype=bool)
        #: 方格网：v_edge[r][c] 表示 (r, c) 与 (r+1, c) 之间的垂直边是否流通
        self.v_edge: np.ndarray = np.zeros((0, 0), dtype=bool)
        #: 三角网：dl_edge[r][c] 表示 (r, c) 与 (r+1, c-1+shift) 之间的左下斜边
        self.dl_edge: np.ndarray = np.zeros((0, 0), dtype=bool)
        #: 三角网：dr_edge[r][c] 表示 (r, c) 与 (r+1, c+shift) 之间的右下斜边
        self.dr_edge: np.ndarray = np.zeros((0, 0), dtype=bool)
        #: 按边号摊平的流通掩码（bytes 缓存，逐层推进逐边查它；见 :meth:`_refresh_open_edges`）
        self._open_bytes: bytes = b""
        #: 邻居表：每个节点"允许走出去"的 ``(邻居, 边号)``（见 :meth:`_build_edge_table`）
        self._nbr: List[List[Tuple[int, int]]] = []
        #: 边号 -> ``(节点a, 节点b)``，``a < b``（``iter_all_edges`` 用）
        self._edge_pairs: List[Tuple[int, int]] = []
        #: 边号 -> 该边在"分类型数组拼成长数组"里的下标（三角网里有越界占位，不能靠数）
        self._edge_source: np.ndarray = np.empty(0, dtype=np.intp)
        #: 末行起始下标（"到底端" = 下标 ≥ 它），热路径反复用到
        self._last_row_start: int = (self.rows - 1) * self.cols
        #: inject == "random" 时使用的随机注水点（随网格一起生成，便于复现）
        self._random_source: Optional[int] = None
        #: 当前网格纵贯簇的节点清单缓存（None 表示尚未判定，空列表表示没有纵贯簇）
        self._spanning_nodes: Optional[List[int]] = None
        self._build_edge_table()
        self.regenerate()

    # ------------------------------------------------------------------
    # 基本几何
    # ------------------------------------------------------------------
    @property
    def size(self) -> int:
        """行数（保留旧名，便于外部沿用 ``grid.size``）。"""
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
        """当前（格子, 方向）组合的临界概率；文献与估计都没有时返回 None。"""
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
        """二维坐标 -> 一维节点索引。"""
        return row * self.cols + col

    def coord(self, index: int) -> Tuple[int, int]:
        """一维节点索引 -> (行, 列)。"""
        return divmod(index, self.cols)

    def _build_edge_table(self) -> None:
        """把「格子类型 + 方向模式」编译成邻居表（只与几何有关，与 ``p`` 无关）。

        边号顺序固定为 **水平边（行优先）→ 方格网的垂直边 / 三角网的左下斜边 → 三角网的
        右下斜边**，与 :meth:`_refresh_open_edges` 的拼接顺序必须一致。

        这里的每一条都必须与 :meth:`_candidate_neighbors` + :meth:`direction_allows`
        严格一致（``tests/test_percolation.py`` 里对小块网格逐条比对过）。
        """
        rows, cols = self.rows, self.cols
        #: (a, b, dr, dc, source)：一条边、"从 a 走到 b"的方向、以及它在拼接长数组里的下标
        edges: List[Tuple[int, int, int, int, int]] = []
        add = edges.append

        h_size = rows * (cols - 1)
        if self.lattice == "square":
            v_offset, dl_offset, dr_offset = h_size, 0, 0
        else:
            v_offset, dl_offset = h_size, h_size
            dr_offset = h_size + (rows - 1) * cols

        for r in range(rows):
            base = r * cols
            for c in range(cols - 1):
                add((base + c, base + c + 1, 0, 1, r * (cols - 1) + c))

        if self.lattice == "square":
            for r in range(rows - 1):
                base, nxt = r * cols, r * cols + cols
                for c in range(cols):
                    add((base + c, nxt + c, 1, 0, v_offset + r * cols + c))
        else:
            # 三角网的斜边数组里有"越界占位"（恒 False），所以每一条边的下标必须
            # 单独算出来（不能靠"数到第几个有效边"来对齐）——这正是护栏抓到的坑。
            for r in range(rows - 1):
                base, nxt, shift = r * cols, r * cols + cols, r % 2
                for c in range(cols):
                    target = c - 1 + shift
                    if 0 <= target < cols:
                        add((base + c, nxt + target, 1, target - c,
                             dl_offset + r * cols + c))
            for r in range(rows - 1):
                base, nxt, shift = r * cols, r * cols + cols, r % 2
                for c in range(cols):
                    target = c + shift
                    if 0 <= target < cols:
                        add((base + c, nxt + target, 1, target - c,
                             dr_offset + r * cols + c))

        self._edge_pairs = [(a, b) for a, b, _dr, _dc, _src in edges]
        self._edge_source = np.asarray([src for _a, _b, _dr, _dc, src in edges],
                                       dtype=np.intp)

        # 邻居表：只保留方向模式允许走出去的那些边（两个方向各自判一次）
        neighbours: List[List[Tuple[int, int]]] = [[] for _ in range(rows * cols)]
        for eid, (a, b, dr, dc, _src) in enumerate(edges):
            if self.direction_allows(dr, dc):
                neighbours[a].append((b, eid))
            if self.direction_allows(-dr, -dc):
                neighbours[b].append((a, eid))
        self._nbr = neighbours
        #: 本次编译对应的结构（尺寸 / 格子 / 方向）—— 结构一变就必须重编（见 _ensure_ready）
        self._structure_key: Tuple[int, int, str, str] = (rows, cols, self.lattice, self.direction)
        #: 末行起始下标（"到底端" = 下标 ≥ 它）——它也由尺寸决定，跟着一起刷新
        self._last_row_start: int = (rows - 1) * cols

    def _refresh_open_edges(self) -> None:
        """把四张分类型边表摊平成**按边号排列**的 ``bytes`` 缓存。

        唯一真相仍是 ``h_edge`` / ``v_edge`` / ``dl_edge`` / ``dr_edge``
        （:func:`encode_edges` 与界面读的就是它们）；这里只是把它们按 :meth:`_build_edge_table`
        的边号顺序拼起来，让逐层推进不必对 numpy 做逐元素索引（``bytes`` 下标快一个量级）。
        """
        arrays = [self.h_edge.reshape(-1)]
        if self.lattice == "square":
            arrays.append(self.v_edge.reshape(-1))
        else:
            arrays.append(self.dl_edge.reshape(-1))
            arrays.append(self.dr_edge.reshape(-1))
        flat = np.concatenate(arrays)
        # 按 _edge_source 取值：三角网的斜边数组里夹着越界占位，边号与下标并不相等
        self._open_bytes = flat[self._edge_source].astype(np.uint8).tobytes()

    def _expand(self, front: List[int], seen: bytearray) -> List[int]:
        """从"当前层"推进一层：返回新浸到的节点（并把它们标记进 ``seen``）。

        内层循环是 ``for 邻居, 边号 in _nbr[idx]`` 加两个 ``bytes`` / ``bytearray``
        下标判断 —— 没有生成器、没有方向判断、没有 numpy 标量索引（旧实现每走一步都要付）。
        """
        neighbours = self._nbr
        opened = self._open_bytes
        nxt: List[int] = []
        push = nxt.append
        for index in front:
            for neighbour, eid in neighbours[index]:
                if opened[eid] and not seen[neighbour]:
                    seen[neighbour] = 1
                    push(neighbour)
        return nxt

    # ------------------------------------------------------------------
    # 网格构建
    # ------------------------------------------------------------------
    def regenerate(self, p: Optional[float] = None, seed: Optional[int] = None) -> "PercolationGrid":
        """重新随机生成所有边（每条边以概率 p 独立判定是否流通）。

        ``inject == "random"`` 时同时重新随机挑选注水点，因此同一个网格上的
        多次判定结果保持一致，重新生成才会换注水点。

        结构（尺寸 / 格子 / 方向）若被就地改过（界面改尺寸走的就是这条路），这里会
        **先重建边表、再重抽边** —— 见 :meth:`_ensure_ready`。
        """
        if p is not None:
            self.p = _clamp(float(p), 0.0, 1.0)
        if seed is not None:
            self.rng = np.random.default_rng(seed)
            # 主随机源换了，随注水点的随机源也要跟着换，种子才真正可复现
            self._source_rng = _derive_rng(self.rng)

        if not self._ensure_ready():        # 结构没变、边没失效 → 自己重抽一遍
            self._draw_field()
        return self

    def _draw_field(self) -> None:
        """按当前 ``p`` 重抽四类边，并重建 ``_open_bytes`` 等派生缓存。"""
        rows, cols, prob = self.rows, self.cols, self.p
        # 一次抽满一类边：比逐边 random() 快一个数量级（边号顺序见 _build_edge_table）
        self.h_edge = self.rng.random((rows, cols - 1)) < prob

        if self.lattice == "square":
            self.v_edge = self.rng.random((rows - 1, cols)) < prob
            self.dl_edge = np.zeros((0, 0), dtype=bool)
            self.dr_edge = np.zeros((0, 0), dtype=bool)
        else:
            self.v_edge = np.zeros((0, 0), dtype=bool)
            # 三角网的两条斜边：目标列随行奇偶偏移；越界的位置恒为 False
            # （与旧实现一致：越界处不算边，但表里保留占位，:func:`encode_edges` 按它输出）
            shift = (np.arange(rows - 1, dtype=np.intp) % 2)[:, None]
            columns = np.arange(cols, dtype=np.intp)[None, :]
            draws = self.rng.random((rows - 1, 2 * cols)) < prob
            left_target = columns - 1 + shift
            right_target = columns + shift
            self.dl_edge = np.where((left_target >= 0) & (left_target < cols),
                                    draws[:, :cols], False)
            self.dr_edge = np.where((right_target >= 0) & (right_target < cols),
                                    draws[:, cols:], False)

        self._refresh_open_edges()
        self._field_key: Tuple[int, int, str] = (rows, cols, self.lattice)

        if self.inject == "random":
            # 延迟到取用时再挑（与点渗流一致）：这样「随机注水」不会额外消耗随机数，
            # 同一颗种子下不同注水方式生成的网格序列完全相同，便于横向比较。
            self._random_source = None
        self._spanning_nodes = None         # 网格换了，贯通判定缓存作废

    def _ensure_ready(self) -> bool:
        """让内部表 / 随机边与当前的 ``rows`` / ``cols`` / ``lattice`` / ``direction`` 对齐。

        返回**是否已经重抽过边**（为 True 时调用方不必再抽一次）。

        界面改尺寸或形状时是**就地**改这些属性、再调 :meth:`regenerate` 的
        （``ui/tk/kit/base.py`` 的 ``_on_shape_change`` / ``_sync_model_params``）。
        重构前的内核没有缓存表，怎么改都没事；向量化之后 ``_nbr`` / ``_edge_pairs`` /
        ``_edge_source`` / ``_last_row_start`` 都是按尺寸预编译的 —— 不在这里对齐，
        就会拿旧尺寸的表去索引新网格，表现正是"长宽比不为 1 就 IndexError"。
        """
        rows, cols = int(self.rows), int(self.cols)
        key = (rows, cols, self.lattice, self.direction)
        if key != self._structure_key:
            self._build_edge_table()                 # 重编几何（顺带刷新末行起点）
        if (rows, cols, self.lattice) != getattr(self, "_field_key", None):
            self._draw_field()                       # 边也是按尺寸的：必须重抽
            return True
        return False

    def total_edge_count(self) -> int:
        """网格中的全部边数（方格网 ``2·rows·cols − rows − cols``）。"""
        rows, cols = self.rows, self.cols
        horizontal = rows * (cols - 1)
        if self.lattice == "square":
            return horizontal + (rows - 1) * cols
        return horizontal + (rows - 1) * (2 * cols - 1)

    def open_edge_count(self) -> int:
        """实际流通的边数。"""
        return int(np.count_nonzero(self.h_edge)) + (
            int(np.count_nonzero(self.v_edge)) if self.lattice == "square"
            else int(np.count_nonzero(self.dl_edge)) + int(np.count_nonzero(self.dr_edge))
        )

    def iter_all_edges(self) -> Iterator[Tuple[int, int]]:
        """迭代所有边（不论是否流通），返回 (节点a, 节点b)，a < b。"""
        yield from self._edge_pairs

    def is_open(self, a: int, b: int) -> bool:
        """判断节点 a、b 之间的边是否流通（与参数顺序无关）。"""
        if a > b:
            a, b = b, a
        cols = self.cols
        r, c = divmod(a, cols)

        if self.lattice == "square":
            if b == a + 1:
                return c + 1 < cols and bool(self.h_edge[r][c])
            if b == a + cols:
                return bool(self.v_edge[r][c])
            return False

        # 三角网：先判同一行内的水平边（行末与下一行行首的索引也相差 1，需排除）
        if b == a + 1 and c + 1 < cols:
            return bool(self.h_edge[r][c])

        j = b - a - cols + c               # 下端节点在下一行中的列号
        if not 0 <= j < cols:
            return False
        shift = r % 2
        if j == c - 1 + shift:
            return bool(self.dl_edge[r][c])
        if j == c + shift:
            return bool(self.dr_edge[r][c])
        return False

    def iter_open_edges(self) -> Iterator[Tuple[int, int]]:
        """迭代所有流通边，返回 (节点a, 节点b)。

        直接走"边号表 + 摊平掩码"：遍历全部边时，逐边调 :meth:`is_open` 得先反查边号，
        而这里正是并查集路径最热的一段循环。
        """
        opened = self._open_bytes
        for eid, pair in enumerate(self._edge_pairs):
            if opened[eid]:
                yield pair

    # ------------------------------------------------------------------
    # 邻居（受方向模式约束）
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

    def _candidate_neighbors(self, index: int) -> Iterator[Tuple[int, int, int]]:
        """产出所有**相连**的邻居及其 (行变化, 列变化)，供方向过滤使用。"""
        rows, cols = self.rows, self.cols
        r, c = divmod(index, cols)

        if c + 1 < cols and self.h_edge[r][c]:
            yield index + 1, 0, 1
        if c > 0 and self.h_edge[r][c - 1]:
            yield index - 1, 0, -1

        if self.lattice == "square":
            if r + 1 < rows and self.v_edge[r][c]:
                yield index + cols, 1, 0
            if r > 0 and self.v_edge[r - 1][c]:
                yield index - cols, -1, 0
            return

        shift = r % 2
        if r + 1 < rows:
            jl = c - 1 + shift
            if 0 <= jl < cols and self.dl_edge[r][c]:
                yield r * cols + cols + jl, 1, jl - c
            jr = c + shift
            if 0 <= jr < cols and self.dr_edge[r][c]:
                yield r * cols + cols + jr, 1, jr - c
        if r > 0:
            pr, pshift = r - 1, (r - 1) % 2
            kl = c + 1 - pshift          # 上一行的左下斜边正好指向当前节点
            if 0 <= kl < cols and self.dl_edge[pr][kl]:
                yield pr * cols + kl, -1, kl - c
            kr = c - pshift              # 上一行的右下斜边正好指向当前节点
            if 0 <= kr < cols and self.dr_edge[pr][kr]:
                yield pr * cols + kr, -1, kr - c

    def neighbors(self, index: int) -> Iterator[int]:
        """沿流通边、且符合方向模式的可达邻居。"""
        for nb, dr, dc in self._candidate_neighbors(index):
            if self.direction_allows(dr, dc):
                yield nb

    def traversable_neighbors(self, index: int) -> Iterator[int]:
        """沿流通边、且**沿允许方向至少一个方向能走**的邻居（给「已走过的边」上色用）。

        与 :meth:`neighbors` 的区别：``neighbors`` 只给出「从 ``index`` 出发能走到的
        邻居」（出边，受方向限制）。给已经走过的边染色时必须两个方向都看：后一步才被
        浸润的节点，从它看前一步的邻居可能是「逆着方向」的，只看 ``neighbors`` 就会
        漏色 —— 有向模式 + 三角网时尤其明显（每个节点有两条斜向上的入边都拿不到颜色）。

        两个端点都已浸润、且这条边沿允许方向能走，它就属于水漫过的区域；
        至于水实际是从哪头流过来的，不影响上色判断。
        """
        for nb, dr, dc in self._candidate_neighbors(index):
            if self.direction_allows(dr, dc) or self.direction_allows(-dr, -dc):
                yield nb

    # ------------------------------------------------------------------
    # 注水点与出口
    # ------------------------------------------------------------------
    def source_nodes(self) -> List[int]:
        """注水点：顶端整行 / 中心单点 / 随机单点。"""
        rows, cols = self.rows, self.cols
        if self.inject == "center":
            return [(rows // 2) * cols + cols // 2]
        if self.inject == "random":
            if self._random_source is None:
                self._random_source = int(self._source_rng.integers(self.node_count))
            return [self._random_source]
        return list(range(cols))

    def top_row_nodes(self) -> List[int]:
        """顶端整行（纵贯判据的入口，与 ``inject`` 无关）。"""
        return list(range(self.cols))

    def sink_nodes(self) -> List[int]:
        """出口：底端整行。"""
        start = (self.rows - 1) * self.cols
        return list(range(start, start + self.cols))

    # ------------------------------------------------------------------
    # 贯通判定（criterion == "span"）
    # ------------------------------------------------------------------
    def spanning_nodes(self) -> List[int]:
        """纵贯簇的节点清单（同时连通顶行与底行的那个连通簇）；没有则返回空列表。

        这就是 ``p_c`` 所对应的判据所关注的那个簇：判据只问「有没有」，而界面需要
        把**到底是哪一个簇**纵贯画出来 —— 否则很容易把「浸润面积」误当成判据的判据
        （一次单点注水可以只浸透一小片，但它和「网格上有没有纵贯簇」是两件事）。

        **与注水点无关**：``inject`` 只决定单次动画从哪儿开始；判据问的是
        「整张网格有没有纵贯簇」。（当 ``inject == "top"`` 时，它与
        ``percolates()`` 完全等价。）

        结果在同一张网格上缓存，重新生成网格后失效。
        """
        self._ensure_ready()                # 结构若被就地改过，先对齐（否则表与网格对不上）
        if self._spanning_nodes is None:
            self._spanning_nodes = self._scan_span()
        return self._spanning_nodes

    def has_spanning_cluster(self) -> bool:
        """整张网格是否存在**纵贯簇**（等价于 :meth:`spanning_nodes` 非空）。

        判据只需要一个"有没有"，所以走**更快的那条路**：把顶行整行当作起点推进一次，
        看是否到底端。逐簇扫描（:meth:`_scan_span`）留给界面"指出是哪一片"用。
        两者答案必然一致：顶行各簇的并集到底端 ⟺ 其中某一个簇到底端。
        """
        seen = bytearray(self.node_count)
        front: List[int] = []
        for index in self.top_row_nodes():
            seen[index] = 1
            front.append(index)
        while front:
            front = self._expand(front, seen)
        return any(seen[self._last_row_start:])

    def _scan_span(self) -> List[int]:
        """逐簇 BFS：从顶行每个节点出发，返回**第一个**纵贯（顶行 ↔ 底行）的簇。

        分成一个个簇来试，而不是把顶行整行一次连通：这样能精确指出是哪个簇纵贯，
        界面才能把它单独高亮（一次大 BFS 会把互不相连的簇混在一起）。
        方向模式照常生效，所以有向模式得到的是「有向纵贯簇」。
        """
        last_row_start = self._last_row_start
        seen = bytearray(self.node_count)
        for start in self.top_row_nodes():
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
                return members          # 这一簇从顶行连到了底行，就是纵贯簇
        return []

    # ------------------------------------------------------------------
    # 渗流判定
    # ------------------------------------------------------------------
    def simulate(self, origins: Optional[Sequence[int]] = None) -> SimResult:
        """完整模拟一次：从注水点开始蔓延，返回浸润节点与分层信息。

        采用 BFS，天然支持四种方向模式、两种格子与矩形网格；BFS 的层号即水到达该
        节点的步数，可直接用于逐层渲染渗透过程。

        ``origins`` 省略时按 ``inject`` 设定自动挑选注水点；给出时从这些节点出发
        （供界面「点击画布指定注水点」使用）。
        """
        self._ensure_ready()                # 结构若被就地改过，先对齐（计时不含这一步）
        started = time.perf_counter()
        rows, cols = self.rows, self.cols
        source = list(origins) if origins is not None else self.source_nodes()
        seen = bytearray(self.node_count)
        front: List[int] = []
        for index in source:
            if not seen[index]:
                seen[index] = 1
                front.append(index)

        layers: List[List[int]] = []
        percolates = False
        while front:
            layers.append(list(front))
            if not percolates and max(front) >= self._last_row_start:
                percolates = True          # 水已经到达底端
            front = self._expand(front, seen)

        wet = [index for layer in layers for index in layer]
        spanning = self.spanning_nodes()
        touches_top = any(idx < cols for idx in wet)
        return SimResult(
            rows=rows,
            cols=cols,
            p=self.p,
            percolates=percolates,
            wet=wet,
            layers=layers,
            origins=source,
            spans=bool(spanning),
            origin_spans=touches_top and percolates,
            spanning_nodes=spanning,
            criterion=self.criterion,
            threshold=self.threshold,
            open_edge_count=self.open_edge_count(),
            total_edge_count=self.total_edge_count(),
            elapsed=time.perf_counter() - started,
        )

    def spread_stats(self, origins: Optional[Sequence[int]] = None) -> Tuple[int, bool, bool]:
        """一次 BFS 同时得到：(浸润节点数, 是否碰到顶行, 是否碰到底行)。

        「面积判据」要的是第一项，「起点判据」要的是后两项，批量统计因此只需跑一遍。
        """
        source = self.source_nodes() if origins is None else origins
        seen = bytearray(self.node_count)
        front: List[int] = []
        for index in source:
            if not seen[index]:
                seen[index] = 1
                front.append(index)
        while front:
            front = self._expand(front, seen)
        return sum(seen), any(seen[: self.cols]), any(seen[self._last_row_start:])

    def spread_size(self, origins: Optional[Sequence[int]] = None) -> int:
        """只统计浸润节点数（面积判据与批量统计的高速路径，不记录分层）。

        与点渗流的 ``spread_size`` 同名同义，方便两个模型交叉对照；
        本模型的惯用词是「浸润」，所以 :meth:`wet_size` 是它的别名。
        """
        return self.spread_stats(origins)[0]

    def wet_size(self, origins: Optional[Sequence[int]] = None) -> int:
        """浸润节点数（本模型惯用词，等价于 :meth:`spread_size`）。"""
        return self.spread_size(origins)

    def origin_spans(self, origins: Optional[Sequence[int]] = None) -> bool:
        """从注水点出发的那一簇是否**纵贯**（同时碰到顶行与底行）。

        与 :meth:`has_spanning_cluster` 的区别：那个问「整张网格有没有纵贯簇」，
        这个问「这次注水的那一簇是不是纵贯的」。顶端整行注水时两者等价；
        单点注水额外要求起点落在纵贯簇里，所以概率更低。
        """
        _count, touches_top, touches_bottom = self.spread_stats(origins)
        return touches_top and touches_bottom

    def _percolates_uf(self, sources: Sequence[int]) -> bool:
        """并查集判定：给定的注水点集合能否连通到底端整行（仅无向模式有效）。"""
        uf = UnionFind(self.node_count + 2)
        source, sink = self.node_count, self.node_count + 1

        for idx in sources:                      # 虚拟水源连接注水点
            uf.union(source, idx)

        for a, b in self.iter_open_edges():      # 所有流通边
            uf.union(a, b)

        for idx in self.sink_nodes():            # 虚拟出口连接底端整行
            uf.union(idx, sink)

        return uf.connected(source, sink)

    def percolates_uf(self) -> bool:
        """用并查集快速判定（仅无向模式有效，批量统计的加速路径）。"""
        return self._percolates_uf(self.source_nodes())

    def _percolates_bfs(self, sources: Sequence[int]) -> bool:
        """轻量 BFS：给定的注水点集合能否到达底端整行（不记录分层）。"""
        seen = bytearray(self.node_count)
        front: List[int] = []
        for index in sources:
            if not seen[index]:
                seen[index] = 1
                front.append(index)
        while front:
            if max(front) >= self._last_row_start:
                return True
            front = self._expand(front, seen)
        return False

    def percolates_bfs(self) -> bool:
        """只用 BFS 判断可达性（不记录分层，比 :meth:`simulate` 轻量）。"""
        return self._percolates_bfs(self.source_nodes())

    def percolates(self, origins: Optional[Sequence[int]] = None) -> bool:
        """判断水能否从注水点流到底端。

        无向模式走并查集（最快），其余方向模式走轻量 BFS。
        ``origins`` 省略时按 ``inject`` 自动挑选注水点。
        """
        if origins is None:
            if self.direction == "undirected":
                return self.percolates_uf()
            return self.percolates_bfs()
        if self.direction == "undirected":
            return self._percolates_uf(list(origins))
        return self._percolates_bfs(list(origins))


# 说明：格点在图纸上的单位坐标 ``lattice_layout`` 由两个模型共用，已移到
# :mod:`awe_math.models._geometry`（本模块保持「可单独导入、可单独运行」的性质）。


# ----------------------------------------------------------------------
# 批量统计与扫描
# ----------------------------------------------------------------------
def batch_percolation_probability(
    rows: int = 40,
    cols: Optional[int] = None,
    p: float = 0.5,
    trials: int = 1000,
    rng: RngLike = None,
    direction: str = "undirected",
    lattice: str = "square",
    inject: str = "top",
    criterion: str = DEFAULT_CRITERION,
    threshold: float = DEFAULT_THRESHOLD,
    progress: Optional[ProgressCallback] = None,
    cancel=None,
) -> BatchResult:
    """在固定概率 ``p`` 下独立生成 ``trials`` 个网格并统计「成功」频率。

    每次实验都重新生成网格。「成功」由 ``criterion`` 决定：

    * ``criterion="span"``：这张网格上**存在纵贯簇**（顶行 ↔ 底行）。
      交点即 ``p_c``，且**与注水方式无关**（判据问的是整张网格的性质）；
    * ``criterion="origin"``：按 ``inject`` 挑注水点出发，这一簇是否**纵贯**
      （同时碰到顶行与底行）。顶端整行时与 ``span`` 等价，单点注水时交点高于 ``p_c``；
    * ``criterion="area"``：按 ``inject`` 挑注水点出发，浸润节点比例 ≥ ``threshold``。
      交点随比例 / 尺寸 / 注水方式漂移，不是 ``p_c``。

    参数
    ----
    rows, cols, lattice, direction, inject
        网格尺寸与模型选项，见 :class:`PercolationGrid`。
    progress : callable(done, total, success) | None
        进度回调，每完成一批实验调用一次（在调用者线程内执行）。
    cancel : object | None
        任何带有 ``is_set()`` 方法的对象（如 ``threading.Event``），置位后提前结束。
    """
    rng = _resolve_rng(rng)
    trials = max(1, int(trials))
    grid = PercolationGrid(
        rows=rows, cols=cols, p=p, rng=rng, direction=direction,
        lattice=lattice, inject=inject, criterion=criterion, threshold=threshold,
    )
    step = max(1, trials // 50)   # 进度回调频率：最多约 50 次
    span_criterion = criterion == "span"
    origin_criterion = criterion == "origin"
    node_count = grid.node_count
    success = 0
    ratio_sum = 0.0
    done = 0
    started = time.perf_counter()

    for i in range(1, trials + 1):
        grid.regenerate()
        if span_criterion:
            # 贯通判据：整张网格是否存在纵贯簇（与注水点无关）
            ok = grid.has_spanning_cluster()
            ratio_sum += grid.wet_size() / node_count if node_count else 0.0
        else:
            # 起点判据 / 面积判据都要先注水一次：一遍 BFS 同时得到两者所需的量
            count, touches_top, touches_bottom = grid.spread_stats()
            ratio = count / node_count if node_count else 0.0
            ratio_sum += ratio
            if origin_criterion:
                ok = touches_top and touches_bottom
            else:
                ok = ratio >= grid.threshold
        if ok:
            success += 1
        done = i
        if progress is not None and (i % step == 0 or i == trials):
            progress(i, trials, success)
        if cancel is not None and cancel.is_set():
            break

    return BatchResult(
        p=p,
        rows=grid.rows,
        cols=grid.cols,
        trials=done,
        success=success,
        criterion=criterion,
        threshold=grid.threshold,
        direction=direction,
        lattice=lattice,
        inject=inject,
        ratio_sum=ratio_sum,
        elapsed=time.perf_counter() - started,
    )


def _scan_curve_by_critical(
    p_values: Sequence[float],
    rows: int,
    cols: Optional[int],
    trials: int,
    rng: np.random.Generator,
    lattice: str,
    progress: Optional[Callable[[int, int, BatchResult], None]],
    cancel,
) -> List[BatchResult]:
    """贯通判据的"临界 p"单遍扫描：一次试验做一遍并查集扫描，给出整条 P(p) 曲线。

    做法（渗流里的标准技巧）：给每条边抽一个 ``U(0,1)`` 权重、按升序加入并查集；
    一旦"顶行整行"与"底端整行"连通，**当时那条边的权重就是该试验的临界概率 c**。
    于是任意 ``p`` 都有 ``P(p) = P(c ≤ p)`` —— 一遍 ``O(E)`` 扫描替代了"每个 p 重跑一遍
    全部试验"。顺带跟踪顶端簇大小随 ``p`` 的分段常量轨迹，"平均浸润比例"也一并得到
    （与逐 p 路径的口径一致：都是"注水簇大小 / 节点总数"）。

    只在 ``criterion="span"`` + ``inject="top"`` + ``direction="undirected"`` 时成立，
    原因写在 :func:`scan_curve` 的说明里。

    注意：整条曲线共用一遍扫描，所以每个结果里的 ``elapsed`` 是**这一遍**的耗时
    （不是该点的独立耗时）。
    """
    grid = PercolationGrid(rows=rows, cols=cols, p=0.5, rng=rng, lattice=lattice,
                           direction="undirected", inject="top")
    node_count = grid.node_count
    pairs = grid._edge_pairs
    edge_count = len(pairs)
    top_nodes = list(range(grid.cols))
    sink_nodes = list(range(grid._last_row_start, node_count))
    top_virtual, sink_virtual = node_count, node_count + 1

    started = time.perf_counter()
    critical: List[float] = []
    #: 只在**请求到的那些 p** 上给顶端簇大小拍快照（不必每加一条边都数一遍）：
    #: 加边按权重升序进行，所以"走到第一条权重 ≥ p 的边"时，所有权重 < p 的边都已加入 ——
    #: 那一刻的分量大小正是该 p 下的"浸润节点比例"，与逐 p 路径的口径完全一致。
    targets = sorted({float(p) for p in p_values})
    snapshots: List[List[float]] = []

    def top_ratio(current: UnionFind) -> float:
        """顶端簇占全网格的比例（虚拟节点不计入；已连通时连虚拟出口也扣掉）。"""
        virtuals = 2 if current.connected(top_virtual, sink_virtual) else 1
        return max(current.component_size(top_virtual) - virtuals, 0) / node_count

    for _ in range(trials):
        if cancel is not None and cancel.is_set():
            break
        weights = rng.random(edge_count)
        order = np.argsort(weights, kind="stable")

        uf = UnionFind(node_count + 2)
        for index in top_nodes:
            uf.union(top_virtual, index)
        for index in sink_nodes:
            uf.union(sink_virtual, index)

        snapshot = [0.0] * len(targets)
        cursor = 0
        reached = 1.0
        connected_done = False
        for eid in order:
            weight = float(weights[eid])
            while cursor < len(targets) and weight >= targets[cursor]:
                snapshot[cursor] = top_ratio(uf)
                cursor += 1
            a, b = pairs[int(eid)]
            uf.union(a, b)
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
    results: List[BatchResult] = []
    total_points = len(p_values)
    for k, p in enumerate(p_values, start=1):
        success = sum(1 for value in critical if value <= p)
        ratio_sum = sum(snapshot[targets.index(float(p))] for snapshot in snapshots)
        res = BatchResult(
            p=p,
            rows=grid.rows,
            cols=grid.cols,
            trials=done,
            success=success,
            criterion="span",
            threshold=grid.threshold,
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
    progress: Optional[Callable[[int, int, BatchResult], None]] = None,
    cancel=None,
) -> List[BatchResult]:
    """扫描一组 ``p`` 值，返回每个 p 对应的成功概率，用于绘制 P(p) 曲线。

    progress : callable(done, total, BatchResult) | None
        每完成一个 p 值调用一次。

    **单遍扫描加速**：默认组合（``criterion="span"`` + ``inject="top"`` +
    ``direction="undirected"``）走 :func:`_scan_curve_by_critical` —— 一次试验做一遍并查集
    扫描就给出整条曲线，而不是每个 ``p`` 重跑一遍全部试验（实测快约"点数"倍）。其余组合
    仍走"逐 p 重跑"，因为这三点是单遍扫描成立的前提：

    * 判据要**与注水点无关**（``span`` 满足；``origin`` / ``area`` 不满足）；
    * 注水点要**与 p 无关**（``top`` 满足；``random`` / ``center`` 的起点本身随 p 变，
      于是"是否成功"不再随 p 单调，"临界 p"就没有定义）；
    * 方向必须**无向**：有向模式下"某一顶行节点能沿允许方向到达底行"与"顶行与底行
      无向连通"**不是一回事**（顶行节点自己也吃左边的入边，不都是源点）。
    """
    rng = _resolve_rng(rng)
    if criterion == "span" and inject == "top" and direction == "undirected":
        return _scan_curve_by_critical(
            p_values, rows=rows, cols=cols, trials=trials, rng=rng,
            lattice=lattice, progress=progress, cancel=cancel,
        )
    results: List[BatchResult] = []
    total_points = len(p_values)
    for k, p in enumerate(p_values, start=1):
        res = batch_percolation_probability(
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
# 与界面层的数据交换：把边压缩成 0/1 字符串
# ----------------------------------------------------------------------
def encode_edges(grid: "PercolationGrid") -> Dict[str, str]:
    """把网格的所有边编码成 0/1 字符串，供前端极轻量地还原网格。

    * 方格网：``{"h": ..., "v": ...}``
      ``h`` 为行优先的水平边（长度 ``rows·(cols−1)``）；``v`` 为垂直边（``(rows−1)·cols``）。
    * 三角网：``{"h": ..., "dl": ..., "dr": ...}``
      额外给出两条斜边（各 ``(rows−1)·cols``），列号按 ``shift = r % 2`` 偏移。

    相比逐个传边坐标，字符串编码体积小一个数量级，前端解析也只需一次遍历。
    """
    def bits(array: "np.ndarray") -> str:
        chars = np.where(array.reshape(-1), ord("1"), ord("0")).astype(np.uint8)
        return chars.tobytes().decode("ascii")

    if grid.lattice == "square":
        return {"h": bits(grid.h_edge), "v": bits(grid.v_edge)}
    return {"h": bits(grid.h_edge), "dl": bits(grid.dl_edge), "dr": bits(grid.dr_edge)}


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
            res = batch_percolation_probability(
                rows=rows, p=mid, trials=trials, rng=rng,
                direction=direction, criterion="span",
            )
            if res.probability < 0.5:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    print("=" * 78)
    print("键渗流自检 1：贯通判据的表观交点 vs 理论临界值 p_c")
    print("=" * 78)
    print("判据：整张网格上是否存在「顶行 ↔ 底行」的纵贯簇 —— 这才是 p_c 所对应的判据。")
    print("说明：n = 40 的有限尺寸下，表观交点在 p_c 附近有百分之几的偏差，尺寸越大越紧。")
    print(f"{'方向模式':<16}{'p_c':>9}{'来源':>7} | {'表观交点':>9} | {'P(p_c)':>8} | {'平均比例':>8}")
    print("-" * 78)

    shared_rng = np.random.default_rng(20260913)
    for direction in DIRECTIONS:
        grid = PercolationGrid(rows=40, p=0.5, direction=direction)
        pc = grid.theoretical_pc
        if pc is None:
            continue
        source = "估计" if grid.pc_is_estimate else "文献"
        mid = batch_percolation_probability(
            rows=40, p=pc, trials=400, rng=shared_rng,
            direction=direction, criterion="span",
        )
        cross = apparent_crossing(40, direction, 200, pc - 0.10, pc + 0.10, shared_rng)
        print(f"{DIRECTION_NAMES[direction]:<16}{pc:>9.4f}{source:>7} |"
              f"{cross:>9.4f} | {mid.probability:>8.3f} | {mid.mean_ratio:>8.3f}")
    print("-" * 78)
    print("尺寸依赖（方格网无向）：表观交点随尺寸逼近 p_c，P(p_c) 始终在 0.5 上下抖动。")
    for n, trials in ((40, 200), (80, 120)):
        cross = apparent_crossing(n, "undirected", trials, 0.42, 0.58, shared_rng)
        res = batch_percolation_probability(
            rows=n, p=THEORETICAL_PC, trials=400, rng=shared_rng, criterion="span"
        )
        print(f"  n = {n:<4}表观交点 {cross:.4f} | P(p_c) = {res.probability:.3f}"
              f"  （p_c = {THEORETICAL_PC:.4f}）")
    print("-" * 78)

    print("自检 2：面积判据的「交点」不是固定的（方格网 40×40，p = 0.50）")
    print("说明：浸润节点比例 ≥ 阈值就算成功。阈值越高，要求越苛刻，同一 p 下的概率越低；")
    print("      把这条曲线与 p 轴的交点找出来，会随阈值（以及网格尺寸、注水方式）漂移。")
    print(f"{'阈值':>8} | " + " | ".join(f"{INJECT_NAMES[i]:>10}" for i in INJECT_MODES))
    print("-" * 78)
    for threshold in (0.1, 0.3, 0.5, 0.7, 0.9):
        cells: List[str] = []
        for inject in INJECT_MODES:
            res = batch_percolation_probability(
                rows=40, p=0.50, trials=300, rng=shared_rng,
                inject=inject, criterion="area", threshold=threshold,
            )
            cells.append(f"{res.probability:>10.3f}")
        print(f"{threshold:>8.0%} | " + " | ".join(cells))
    print("-" * 78)

    print("自检 3：三种判据 × 三种注水方式（方格网 32×32，p = 0.5，各 300 次）")
    print("关键差别：贯通判据问「网格上有没有纵贯簇」，起点判据问「你这一注水纵贯吗」。")
    for criterion in CRITERIA:
        for inject in INJECT_MODES:
            res = batch_percolation_probability(
                rows=32, p=0.5, trials=300, rng=shared_rng,
                inject=inject, criterion=criterion,
            )
            print(f"  [{res.criterion_name}] {INJECT_NAMES[inject]:<8}"
                  f" P = {res.probability:.3f}   平均浸润比例 = {res.mean_ratio:.3f}")
        print("-" * 78)

    probe = PercolationGrid(rows=32, p=0.5, rng=shared_rng, inject="random")
    span_ok = 0
    origin_in = 0
    for _ in range(300):
        probe.regenerate()
        if probe.has_spanning_cluster():
            span_ok += 1
            if probe.origin_spans():
                origin_in += 1
    if span_ok:
        print(f"同一批网格：存在纵贯簇 {span_ok}/300，其中随机注水点恰好落在簇里 "
              f"{origin_in} 次（{origin_in / span_ok:.1%}）")
        print("—— 这就是「起点判据」比「贯通判据」低的原因：注水点可能落在簇外。")
    print("-" * 78)
    print("提示：贯通判据下注水方式完全不影响结果（判据问的是整张网格的性质）；")
    print("      起点判据 / 面积判据下影响很大 —— 单点注水额外要求「起点落在纵贯簇里」。")
