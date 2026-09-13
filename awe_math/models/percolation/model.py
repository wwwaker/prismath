# -*- coding: utf-8 -*-
"""
方格网边渗流（Bond Percolation）核心模型
=========================================

模型约定
--------
* 在 ``size × size`` 的方格网上，每条「边」（相邻节点之间的连接）以概率 ``p``
  独立地设置为「流通」或「阻断」。
* 采用**标准渗流定义（无向连通）**：水沿流通边可以向上、下、左、右任意方向流动，
  只要某节点与顶端节点处于同一个连通分量中，即认为该节点被浸润。
  （原题中「只能向下/向左/向右」属于有向渗流，作为可选项 ``directed=True`` 保留。）
* 若至少存在一个底端节点与顶端节点连通，则认为本次模拟「渗流出水」。
* 顶端整体视为水源、底端整体视为出口，因此用「虚拟水源 / 虚拟出口」+ 并查集即可判定。

理论背景
--------
二维方格网的键渗流临界值 ``p_c = 1/2``。当 ``p`` 明显小于 1/2 时几乎不可能贯通；
``p`` 超过 1/2 后几乎必然贯通；在 ``p_c`` 附近发生**相变**，即「量变引起质变」。

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
    "UnionFind",
    "PercolationGrid",
    "SimResult",
    "BatchResult",
    "batch_percolation_probability",
    "scan_curve",
    "encode_edges",
]

#: 二维方格网键渗流（bond percolation）的理论临界概率
THEORETICAL_PC: float = 0.5

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


class UnionFind:
    """并查集（带路径压缩 + 按秩合并），用于快速判断连通性。"""

    __slots__ = ("parent", "rank", "count")

    def __init__(self, n: int) -> None:
        self.parent: List[int] = list(range(n))
        self.rank: List[int] = [0] * n
        self.count: int = n

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
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        self.count -= 1
        return True

    def connected(self, a: int, b: int) -> bool:
        return self.find(a) == self.find(b)


@dataclass
class SimResult:
    """一次完整模拟（单次生成 + 渗透）的结果，供可视化使用。"""

    size: int
    p: float
    percolates: bool
    #: 所有被浸润的节点索引（行优先：index = row * size + col）
    wet: List[int] = field(default_factory=list)
    #: 按 BFS 层分组的浸润节点，layers[k] 表示距顶端 k 步的节点
    layers: List[List[int]] = field(default_factory=list)
    open_edge_count: int = 0
    total_edge_count: int = 0
    elapsed: float = 0.0

    @property
    def node_count(self) -> int:
        return self.size * self.size

    @property
    def wet_count(self) -> int:
        return len(self.wet)

    @property
    def wet_ratio(self) -> float:
        """浸润节点占全部节点的比例。"""
        return self.wet_count / self.node_count if self.node_count else 0.0

    @property
    def open_ratio(self) -> float:
        """实际流通边占全部边的比例（有限网格下的实测值，围绕 p 波动）。"""
        return self.open_edge_count / self.total_edge_count if self.total_edge_count else 0.0

    @property
    def depth(self) -> int:
        """水渗透的层数（BFS 最大层数）。"""
        return len(self.layers)


@dataclass
class BatchResult:
    """一批独立重复实验的统计结果。"""

    p: float
    size: int
    trials: int
    success: int
    directed: bool = False
    elapsed: float = 0.0

    @property
    def probability(self) -> float:
        """渗流发生频率（对渗流概率的蒙特卡洛估计）。"""
        return self.success / self.trials if self.trials else 0.0

    @property
    def stderr(self) -> float:
        """频率估计的标准误 sqrt(P(1-P)/N)。"""
        prob = self.probability
        return (prob * (1.0 - prob) / self.trials) ** 0.5 if self.trials else 0.0


class PercolationGrid:
    """二维方格网边渗流模型。

    参数
    ----
    size : int
        网格边长（节点数为 ``size × size``）。
    p : float
        每条边的流通概率，取值 ``[0, 1]``。
    rng : None | int | random.Random
        随机源，可以是种子（便于复现）。
    directed : bool
        ``False``（默认）= 标准无向渗流，水可上下左右流动；
        ``True`` = 有向渗流，只允许向下 / 向左 / 向右（原题的严格版本）。
    """

    def __init__(
        self,
        size: int = 30,
        p: float = 0.5,
        rng: RngLike = None,
        directed: bool = False,
    ) -> None:
        if size < 2:
            raise ValueError("网格尺寸至少为 2")
        self.size = int(size)
        self.p = min(1.0, max(0.0, float(p)))
        self.directed = bool(directed)
        self.rng: random.Random = _resolve_rng(rng)
        #: h_edge[r][c] 表示 (r, c) 与 (r, c+1) 之间的水平边是否流通
        self.h_edge: List[List[bool]] = []
        #: v_edge[r][c] 表示 (r, c) 与 (r+1, c) 之间的垂直边是否流通
        self.v_edge: List[List[bool]] = []
        self.regenerate()

    # ------------------------------------------------------------------
    # 网格构建
    # ------------------------------------------------------------------
    @property
    def node_count(self) -> int:
        return self.size * self.size

    def index(self, row: int, col: int) -> int:
        """二维坐标 -> 一维节点索引。"""
        return row * self.size + col

    def coord(self, index: int) -> Tuple[int, int]:
        """一维节点索引 -> (行, 列)。"""
        return divmod(index, self.size)

    def regenerate(self, p: Optional[float] = None, seed: Optional[int] = None) -> "PercolationGrid":
        """重新随机生成所有边（每条边以概率 p 独立判定是否流通）。"""
        if p is not None:
            self.p = min(1.0, max(0.0, float(p)))
        if seed is not None:
            self.rng = random.Random(seed)

        n, prob, rnd = self.size, self.p, self.rng.random
        self.h_edge = [[rnd() < prob for _ in range(n - 1)] for _ in range(n)]
        self.v_edge = [[rnd() < prob for _ in range(n)] for _ in range(n - 1)]
        return self

    def total_edge_count(self) -> int:
        """方格网中所有的边数：2 * n * (n - 1)。"""
        return 2 * self.size * (self.size - 1)

    def open_edge_count(self) -> int:
        """实际流通的边数。"""
        return sum(sum(row) for row in self.h_edge) + sum(sum(row) for row in self.v_edge)

    def iter_open_edges(self) -> Iterator[Tuple[int, int]]:
        """迭代所有流通边，返回 (节点a, 节点b)。"""
        n = self.size
        for r in range(n):
            base = r * n
            row_h = self.h_edge[r]
            for c in range(n - 1):
                if row_h[c]:
                    yield base + c, base + c + 1
        for r in range(n - 1):
            base = r * n
            row_v = self.v_edge[r]
            for c in range(n):
                if row_v[c]:
                    yield base + c, base + c + n

    def neighbors(self, index: int) -> Iterator[int]:
        """沿流通边可直接到达的邻居节点。

        标准模式（无向）向四个方向扩散；有向模式只允许 下 / 左 / 右。
        """
        n = self.size
        r, c = divmod(index, n)
        if c + 1 < n and self.h_edge[r][c]:
            yield index + 1
        if c > 0 and self.h_edge[r][c - 1]:
            yield index - 1
        if r + 1 < n and self.v_edge[r][c]:
            yield index + n
        if r > 0 and not self.directed and self.v_edge[r - 1][c]:
            yield index - n

    # ------------------------------------------------------------------
    # 渗流判定
    # ------------------------------------------------------------------
    def simulate(self) -> SimResult:
        """完整模拟一次：从顶端所有节点同时注水，返回浸润节点与分层信息。

        采用多源 BFS，天然支持无向与有向两种模式；BFS 的层号即水到达该节点的步数，
        可直接用于逐层渲染渗透过程。
        """
        started = time.perf_counter()
        n = self.size
        dist: Dict[int, int] = {}
        layers: List[List[int]] = []
        queue: deque = deque()

        # 顶端所有节点同时作为水源
        for c in range(n):
            dist[c] = 0
            queue.append(c)

        last_row_start = (n - 1) * n
        percolates = False

        while queue:
            idx = queue.popleft()
            d = dist[idx]
            if d == len(layers):
                layers.append([])
            layers[d].append(idx)
            if idx >= last_row_start:
                percolates = True  # 水已经到达底端
            nd = d + 1
            for nb in self.neighbors(idx):
                if nb not in dist:
                    dist[nb] = nd
                    queue.append(nb)

        return SimResult(
            size=n,
            p=self.p,
            percolates=percolates,
            wet=list(dist.keys()),
            layers=layers,
            open_edge_count=self.open_edge_count(),
            total_edge_count=self.total_edge_count(),
            elapsed=time.perf_counter() - started,
        )

    def percolates_uf(self) -> bool:
        """用并查集快速判定是否渗流（仅适用于无向模式，批量统计的加速路径）。"""
        n = self.size
        uf = UnionFind(n * n + 2)
        source, sink = n * n, n * n + 1

        for c in range(n):                       # 虚拟水源连接顶端整行
            uf.union(source, c)

        for r in range(n - 1):                   # 水平边 + 垂直边
            base = r * n
            row_h = self.h_edge[r]
            for c in range(n - 1):
                if row_h[c]:
                    uf.union(base + c, base + c + 1)
            row_v = self.v_edge[r]
            for c in range(n):
                if row_v[c]:
                    uf.union(base + c, base + c + n)

        last_base = (n - 1) * n                  # 最后一行只有水平边
        row_h = self.h_edge[n - 1]
        for c in range(n - 1):
            if row_h[c]:
                uf.union(last_base + c, last_base + c + 1)
        for c in range(n):                       # 虚拟出口连接底端整行
            uf.union(last_base + c, sink)

        return uf.connected(source, sink)

    def percolates(self) -> bool:
        """判断顶端的水能否流到底端（自动选择最快的判定路径）。"""
        if self.directed:
            return self.simulate().percolates
        return self.percolates_uf()


# ----------------------------------------------------------------------
# 批量统计与扫描
# ----------------------------------------------------------------------
def batch_percolation_probability(
    size: int = 40,
    p: float = 0.5,
    trials: int = 1000,
    rng: RngLike = None,
    directed: bool = False,
    progress: Optional[ProgressCallback] = None,
    cancel=None,
) -> BatchResult:
    """在固定概率 ``p`` 下独立生成 ``trials`` 个网格并统计渗流频率。

    参数
    ----
    progress : callable(done, total, success) | None
        进度回调，每完成一批实验调用一次（在调用者线程内执行）。
    cancel : object | None
        任何带有 ``is_set()`` 方法的对象（如 ``threading.Event``），置位后提前结束。
    """
    rng = _resolve_rng(rng)
    trials = max(1, int(trials))
    grid = PercolationGrid(size=size, p=p, rng=rng, directed=directed)
    step = max(1, trials // 50)   # 进度回调频率：最多约 50 次
    success = 0
    done = 0
    started = time.perf_counter()

    for i in range(1, trials + 1):
        grid.regenerate()
        if grid.percolates():
            success += 1
        done = i
        if progress is not None and (i % step == 0 or i == trials):
            progress(i, trials, success)
        if cancel is not None and cancel.is_set():
            break

    return BatchResult(
        p=p,
        size=size,
        trials=done,
        success=success,
        directed=directed,
        elapsed=time.perf_counter() - started,
    )


def scan_curve(
    p_values: Sequence[float],
    size: int = 40,
    trials: int = 200,
    rng: RngLike = None,
    directed: bool = False,
    progress: Optional[Callable[[int, int, BatchResult], None]] = None,
    cancel=None,
) -> List[BatchResult]:
    """扫描一组 ``p`` 值，返回每个 p 对应的渗流概率，用于绘制 P(p) 曲线。

    progress : callable(done, total, BatchResult) | None
        每完成一个 p 值调用一次。
    """
    rng = _resolve_rng(rng)
    results: List[BatchResult] = []
    total_points = len(p_values)
    for k, p in enumerate(p_values, start=1):
        res = batch_percolation_probability(
            size=size, p=p, trials=trials, rng=rng, directed=directed, cancel=cancel
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
def encode_edges(grid: "PercolationGrid") -> Tuple[str, str]:
    """把网格的所有边编码成两段 0/1 字符串，供前端极轻量地还原网格。

    * ``h``：行优先的水平边，长度 ``n * (n - 1)``，位置 ``r * (n - 1) + c``
    * ``v``：行优先的垂直边，长度 ``(n - 1) * n``，位置 ``r * n + c``

    相比逐个传边坐标，字符串编码体积小一个数量级，前端解析也只需一次遍历。
    """
    h = "".join("1" if flag else "0" for row in grid.h_edge for flag in row)
    v = "".join("1" if flag else "0" for row in grid.v_edge for flag in row)
    return h, v


# ----------------------------------------------------------------------
# 直接运行本文件时的自检：对比实验值与理论阈值
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    try:  # Windows 控制台默认 GBK，需要切到 UTF-8 才能正常输出中文
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    print("=" * 66)
    print("方格网边渗流自检：理论与实验对照（网格 40×40，每点 400 次）")
    print(f"理论临界值 p_c = {THEORETICAL_PC}（二维方格网键渗流）")
    print("=" * 66)
    print(f"{'概率 p':>8} | {'实验渗流概率':>12} | {'成功/总次数':>14} | 变化趋势")
    print("-" * 66)

    shared_rng = random.Random(20260912)
    for p in (0.2, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8):
        res = batch_percolation_probability(size=40, p=p, trials=400, rng=shared_rng)
        bar = "█" * int(round(res.probability * 20))
        print(f"{p:>8.2f} | {res.probability:>12.3f} | {res.success:>6}/{res.trials:<6} | {bar}")

    print("-" * 66)
    print("可见：p < p_c 时渗流概率≈0，p > p_c 时迅速趋近 1，在 p_c 附近发生相变。")
