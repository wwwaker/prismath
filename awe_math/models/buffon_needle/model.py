# -*- coding: utf-8 -*-
"""
蒲丰投针（Buffon's Needle）核心模型
====================================

在间距为 ``d`` 的一组平行线上随机投 ``N`` 根长度 ``L``（``L ≤ d``）的针，统计其中与某条线
相交的根数 ``H``。理论命中概率为

    P = 2L / (π d)

于是反解出 π 的蒙特卡洛估计

    π ≈ 2 L N / (d H)

**几何约定**（与界面绘图一致）：

* 平行线是水平线，位置 ``y = k · d``（``k`` 为整数）；
* 针的中心 ``(cx, cy)`` 在视口 ``[0, width] × [0, height]`` 内均匀分布；
* 针与水平方向的夹角 ``θ`` 在 ``[0, π)`` 上均匀分布；
* 「命中」指针与某条线相交，判据是「中心到最近一条线的距离 ≤ (L/2)·sin θ」。

``L > d`` 时经典结论失效（命中概率不再是 ``2L/(πd)``），所以本模型把 ``L/d`` 限制在 ``[0.05, 1]``。

本模块**只依赖 Python 标准库**，可单独导入使用（不含任何绘图 / GUI 代码）：

    python -m awe_math.models.buffon_needle.model     # 跑一段收敛自检
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

__all__ = [
    "PI",
    "DEFAULT_RATIO",
    "DEFAULT_THROWS",
    "DEFAULT_REPEATS",
    "MIN_RATIO",
    "MAX_RATIO",
    "VIEWPORT_WIDTH",
    "VIEWPORT_HEIGHT",
    "Needle",
    "ThrowResult",
    "ConvergeResult",
    "BuffonNeedle",
    "estimate_pi",
    "encode_needles",
]

#: 圆周率（估计的目标）
PI: float = math.pi

#: 默认「针长 / 线距」比值（经典的蒲丰投针常取 0.8）
DEFAULT_RATIO: float = 0.8
#: 默认一次投掷的针数
DEFAULT_THROWS: int = 1000
#: 默认「多组重复估计」的组数
DEFAULT_REPEATS: int = 12

#: ``L / d`` 的允许范围：``L > d`` 时经典公式不成立
MIN_RATIO: float = 0.05
MAX_RATIO: float = 1.0

#: 绘图视口的尺寸（以线距 ``d`` 为单位）：12 格宽、8 格高
VIEWPORT_WIDTH: float = 12.0
VIEWPORT_HEIGHT: float = 8.0

#: 随机源可以传入 None / int（种子）/ random.Random 实例
RngLike = Union[None, int, random.Random]


def _resolve_rng(rng: RngLike = None) -> random.Random:
    """把 None / 种子 / Random 实例统一转换成一个 ``random.Random`` 对象。"""
    if isinstance(rng, random.Random):
        return rng
    if rng is None:
        return random.Random()
    return random.Random(rng)


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


def estimate_pi(length: float, gap: float, throws: int, hits: int) -> Optional[float]:
    """由命中次数反解 π：``π ≈ 2 L N / (d H)``；一次都没命中时返回 ``None``。

    注意：``L ≤ d`` 时 ``P = 2L/(πd)`` 才是严格成立的（这是经典结论的前提）。
    """
    if hits <= 0 or gap <= 0 or throws <= 0:
        return None
    return 2.0 * float(length) * float(throws) / (float(gap) * float(hits))


@dataclass
class Needle:
    """一根针：中心坐标 + 与水平方向的夹角 + 是否命中。"""

    cx: float
    cy: float
    theta: float
    hit: bool

    def segment(self, length: float) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """按给定针长算出两端点坐标 ``((x1, y1), (x2, y2))``（供界面直接连线）。"""
        half = float(length) / 2.0
        dx = half * math.cos(self.theta)
        dy = half * math.sin(self.theta)
        return (self.cx - dx, self.cy - dy), (self.cx + dx, self.cy + dy)


@dataclass
class ThrowResult:
    """一次投针（``N`` 根）的结果，供可视化与统计使用。"""

    ratio: float
    length: float                   # 针长 L
    gap: float                      # 线距 d
    width: float                    # 视口宽（单位 d）
    height: float                   # 视口高（单位 d）
    needles: List[Needle] = field(default_factory=list)
    elapsed: float = 0.0

    @property
    def throws(self) -> int:
        """本次投出的针数 N。"""
        return len(self.needles)

    @property
    def hits(self) -> int:
        """与线相交的针数 H。"""
        return sum(1 for n in self.needles if n.hit)

    @property
    def hit_rate(self) -> float:
        """实测命中率 H / N。"""
        return self.hits / self.throws if self.throws else 0.0

    @property
    def theory_rate(self) -> float:
        """理论命中率 2L/(πd)（只在 L ≤ d 时成立）。"""
        return 2.0 * self.length / (PI * self.gap) if self.gap else 0.0

    @property
    def pi_estimate(self) -> Optional[float]:
        """π 的估计值 2LN/(dH)。"""
        return estimate_pi(self.length, self.gap, self.throws, self.hits)

    @property
    def abs_error(self) -> Optional[float]:
        """估计值与 π 的绝对偏差。"""
        value = self.pi_estimate
        return None if value is None else abs(value - PI)

    @property
    def rel_error(self) -> Optional[float]:
        """估计值的相对偏差（``|π̂ − π| / π``）。"""
        value = self.abs_error
        return None if value is None else value / PI


@dataclass
class ConvergeResult:
    """「多组重复估计」的结果：看 π 的估计值随样本量收敛。"""

    ratio: float
    length: float
    gap: float
    throws_per_group: int
    repeats: int
    #: 累计投针数
    total_throws: int = 0
    #: 累计命中数
    total_hits: int = 0
    #: 每个样本点的 (累计针数, 累计命中数, 累计估计值)——估计值可能为 None（尚未命中）
    samples: List[Tuple[int, int, Optional[float]]] = field(default_factory=list)
    #: 每一组独立实验自己的估计值（用于算组间均值与标准误）
    per_group: List[Optional[float]] = field(default_factory=list)
    elapsed: float = 0.0

    @property
    def hit_rate(self) -> float:
        return self.total_hits / self.total_throws if self.total_throws else 0.0

    @property
    def theory_rate(self) -> float:
        return 2.0 * self.length / (PI * self.gap) if self.gap else 0.0

    @property
    def pi_estimate(self) -> Optional[float]:
        """用全部样本累计得到的最终估计值。"""
        return estimate_pi(self.length, self.gap, self.total_throws, self.total_hits)

    @property
    def abs_error(self) -> Optional[float]:
        value = self.pi_estimate
        return None if value is None else abs(value - PI)

    @property
    def mean_estimate(self) -> Optional[float]:
        """各组估计值的平均（无有效组时返回 None）。"""
        values = [v for v in self.per_group if v is not None]
        return sum(values) / len(values) if values else None

    @property
    def stderr(self) -> float:
        """各组估计值的标准误 sqrt(Σ(v−mean)²/(n(n−1)))。"""
        values = [v for v in self.per_group if v is not None]
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return (var / len(values)) ** 0.5


class BuffonNeedle:
    """蒲丰投针模型（纯计算）。

    参数
    ----
    ratio : float
        「针长 / 线距」比值 ``L/d``，会被夹到 ``[MIN_RATIO, MAX_RATIO]``。
    throws : int
        一次投掷的针数 ``N``。
    gap : float
        平行线间距 ``d``（默认 1，于是 ``L = ratio``）。
    width / height : float
        视口尺寸（以 ``d`` 为单位），决定针心均匀分布的矩形范围。
    rng : None | int | random.Random
        随机源，可以是种子（便于复现）。
    """

    def __init__(
        self,
        ratio: float = DEFAULT_RATIO,
        throws: int = DEFAULT_THROWS,
        gap: float = 1.0,
        width: float = VIEWPORT_WIDTH,
        height: float = VIEWPORT_HEIGHT,
        rng: RngLike = None,
    ) -> None:
        self.gap = float(gap) if float(gap) > 0 else 1.0
        self.ratio = _clamp(float(ratio), MIN_RATIO, MAX_RATIO)
        #: 针长 L = ratio · d
        self.length = self.ratio * self.gap
        self.throws = max(1, int(throws))
        self.width = float(width) if float(width) > 0 else VIEWPORT_WIDTH
        self.height = float(height) if float(height) > 0 else VIEWPORT_HEIGHT
        self.rng: random.Random = _resolve_rng(rng)

    @property
    def theory_rate(self) -> float:
        """理论命中率 2L/(πd)。"""
        return 2.0 * self.length / (PI * self.gap)

    def throw(self, throws: Optional[int] = None) -> ThrowResult:
        """投一次针：返回每根针的几何与命中情况。"""
        started = time.perf_counter()
        count = self.throws if throws is None else max(1, int(throws))
        gap, width, height = self.gap, self.width, self.height
        half_length = self.length / 2.0
        rnd = self.rng.random

        needles: List[Needle] = []
        append = needles.append
        for _ in range(count):
            cx = rnd() * width
            cy = rnd() * height
            theta = rnd() * PI
            # 到最近一条水平线 y = k·d 的距离
            nearest = abs(cy - math.floor(cy / gap + 0.5) * gap)
            append(Needle(cx, cy, theta, nearest <= half_length * math.sin(theta)))

        return ThrowResult(
            ratio=self.ratio,
            length=self.length,
            gap=gap,
            width=width,
            height=height,
            needles=needles,
            elapsed=time.perf_counter() - started,
        )

    def converge(self, repeats: int = DEFAULT_REPEATS,
                 throws: Optional[int] = None) -> ConvergeResult:
        """做 ``repeats`` 组独立实验，记录累计估计值随样本量的收敛过程。"""
        started = time.perf_counter()
        groups = max(1, int(repeats))
        per_group: List[Optional[float]] = []
        samples: List[Tuple[int, int, Optional[float]]] = []
        total_throws = 0
        total_hits = 0

        for _ in range(groups):
            res = self.throw(throws)
            total_throws += res.throws
            total_hits += res.hits
            per_group.append(res.pi_estimate)
            samples.append((
                total_throws,
                total_hits,
                estimate_pi(self.length, self.gap, total_throws, total_hits),
            ))

        return ConvergeResult(
            ratio=self.ratio,
            length=self.length,
            gap=self.gap,
            throws_per_group=self.throws if throws is None else max(1, int(throws)),
            repeats=groups,
            total_throws=total_throws,
            total_hits=total_hits,
            samples=samples,
            per_group=per_group,
            elapsed=time.perf_counter() - started,
        )


def encode_needles(result: ThrowResult) -> Dict[str, Any]:
    """把投针结果压成"坐标数组 + 0/1 掩码"，供前端极轻量地还原几何。

    相比给每根针传一个字典，数组 + 字符串掩码体积小一个数量级，前端解析也只要一次遍历。
    """
    return {
        "xs": [round(n.cx, 3) for n in result.needles],
        "ys": [round(n.cy, 3) for n in result.needles],
        "thetas": [round(n.theta, 4) for n in result.needles],
        "hitsMask": "".join("1" if n.hit else "0" for n in result.needles),
    }


# ----------------------------------------------------------------------
# 直接运行本文件时的自检：估计值随投针数收敛到 π
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    try:  # Windows 控制台默认 GBK，需要切到 UTF-8 才能正常输出中文
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    print("=" * 66)
    print("蒲丰投针自检：π 的估计值随投针数收敛（L/d = 0.8，固定种子）")
    print("=" * 66)
    print(f"理论命中率 2L/(πd) = {2 * 0.8 / PI:.4f}；真值 π = {PI:.6f}")
    print(f"{'投针数 N':>10}{'命中数 H':>10}{'实测命中率':>12}{'π 估计':>10}{'误差':>10}")
    print("-" * 66)

    model = BuffonNeedle(ratio=0.8, rng=random.Random(20260914))
    for count in (100, 500, 1000, 5000, 20000):
        res = model.throw(count)
        pi_hat = res.pi_estimate
        shown = "—" if pi_hat is None else f"{pi_hat:.4f}"
        err = "—" if res.abs_error is None else f"{res.abs_error:.4f}"
        print(f"{res.throws:>10}{res.hits:>10}{res.hit_rate:>12.4f}{shown:>10}{err:>10}")
    print("-" * 66)
    print("提示：误差大致按 1/√N 缩小；命中率为 0 时无法反解 π（该次投针没有意义）。")

    conv = BuffonNeedle(ratio=0.8, rng=random.Random(7)).converge(repeats=8, throws=500)
    print()
    print(f"多组重复（8 组 × 500 根）：累计估计 π ≈ {conv.pi_estimate:.4f}"
          f"，组间均值 {conv.mean_estimate:.4f} ± {conv.stderr:.4f}")
