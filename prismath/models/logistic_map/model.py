# -*- coding: utf-8 -*-
"""Logistic Map：从一个确定性递推看到稳定、倍周期与混沌。

逻辑斯蒂映射只有一条规则：

    x[n+1] = r * x[n] * (1 - x[n]),   0 <= x[n] <= 1

参数 ``r`` 从 0 调到 4 时，轨道依次经历固定点、周期轨道、倍周期分岔，
最后进入对初值敏感的混沌。模块只依赖标准库和 NumPy，不含界面代码。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np

__all__ = [
    "DEFAULT_R",
    "DEFAULT_X0",
    "DEFAULT_ITERATIONS",
    "DEFAULT_DISCARD",
    "DEFAULT_R_MIN",
    "DEFAULT_R_MAX",
    "DEFAULT_R_SAMPLES",
    "DEFAULT_POINTS_PER_R",
    "MAX_ITERATIONS",
    "MAX_R_SAMPLES",
    "MAX_POINTS_PER_R",
    "LogisticMap",
    "LogisticOrbit",
    "LogisticBifurcation",
    "logistic_step",
    "iterate",
    "lyapunov_exponent",
    "bifurcation",
]

# 首屏示例使用周期 2：它仍然能展示“状态在两个值之间往返”，但不会像
# 3.55 附近的倍周期 / 混沌边界一样把长轨道画成一团密集的竖线。
DEFAULT_R: float = 3.2
DEFAULT_X0: float = 0.2
DEFAULT_ITERATIONS: int = 120
DEFAULT_DISCARD: int = 100
DEFAULT_R_MIN: float = 2.5
DEFAULT_R_MAX: float = 4.0
DEFAULT_R_SAMPLES: int = 180
DEFAULT_POINTS_PER_R: int = 60

MIN_R: float = 0.0
MAX_R: float = 4.0
MIN_X0: float = 0.0
MAX_X0: float = 1.0
MIN_ITERATIONS: int = 20
MAX_ITERATIONS: int = 5000
MAX_DISCARD: int = 5000
MIN_R_SAMPLES: int = 40
MAX_R_SAMPLES: int = 400
MIN_POINTS_PER_R: int = 20
MAX_POINTS_PER_R: int = 120


def _clamp_float(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return max(low, min(high, number))


def _clamp_int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def logistic_step(x: Any, r: Any) -> np.ndarray:
    """计算一步 ``r*x*(1-x)``，支持标量和 NumPy 数组。"""
    return np.asarray(r, dtype=float) * np.asarray(x, dtype=float) * (1.0 - np.asarray(x, dtype=float))


def _resolve_parameters(r: Any, x0: Any, iterations: Any, discard: Any) -> Tuple[float, float, int, int]:
    r_value = _clamp_float(r, MIN_R, MAX_R, DEFAULT_R)
    x_value = _clamp_float(x0, MIN_X0, MAX_X0, DEFAULT_X0)
    limit = _clamp_int(iterations, MIN_ITERATIONS, MAX_ITERATIONS, DEFAULT_ITERATIONS)
    burn = _clamp_int(discard, 0, MAX_DISCARD, DEFAULT_DISCARD)
    return r_value, x_value, limit, burn


def iterate(r: Any = DEFAULT_R, x0: Any = DEFAULT_X0,
            iterations: Any = DEFAULT_ITERATIONS,
            discard: Any = DEFAULT_DISCARD) -> np.ndarray:
    """丢弃前 ``discard`` 步后，返回连续 ``iterations`` 个轨道值。"""
    r_value, x_value, limit, burn = _resolve_parameters(r, x0, iterations, discard)
    x = x_value
    for _ in range(burn):
        x = r_value * x * (1.0 - x)
    values = np.empty(limit, dtype=np.float64)
    for index in range(limit):
        x = r_value * x * (1.0 - x)
        values[index] = x
    return values


def lyapunov_exponent(r: Any = DEFAULT_R, x0: Any = DEFAULT_X0,
                      iterations: Any = DEFAULT_ITERATIONS,
                      discard: Any = DEFAULT_DISCARD) -> float:
    """计算轨道的 Lyapunov 指数，正值通常意味着混沌。"""
    r_value, x_value, limit, burn = _resolve_parameters(r, x0, iterations, discard)
    x = x_value
    for _ in range(burn):
        x = r_value * x * (1.0 - x)
    logs = np.empty(limit, dtype=np.float64)
    for index in range(limit):
        x = r_value * x * (1.0 - x)
        derivative = abs(r_value * (1.0 - 2.0 * x))
        logs[index] = math.log(max(derivative, np.finfo(float).tiny))
    return float(np.mean(logs))


@dataclass(frozen=True)
class LogisticOrbit:
    r: float
    x0: float
    iterations: int
    discard: int
    values: np.ndarray
    lyapunov: float
    elapsed: float

    def records(self) -> List[Dict[str, float]]:
        return [
            {"step": self.discard + index + 1, "x": float(value)}
            for index, value in enumerate(self.values)
        ]


@dataclass(frozen=True)
class LogisticBifurcation:
    r_min: float
    r_max: float
    r_samples: int
    points_per_r: int
    rs: np.ndarray
    xs: np.ndarray
    elapsed: float

    def records(self) -> List[Dict[str, float]]:
        return [{"r": float(r), "x": float(x)} for r, x in zip(self.rs, self.xs)]


class LogisticMap:
    """逻辑斯蒂映射的对象级 API，供 Tk 视图与其它后端共用。"""

    def __init__(self, r: float = DEFAULT_R, x0: float = DEFAULT_X0,
                 iterations: int = DEFAULT_ITERATIONS,
                 discard: int = DEFAULT_DISCARD,
                 r_min: float = DEFAULT_R_MIN,
                 r_max: float = DEFAULT_R_MAX,
                 r_samples: int = DEFAULT_R_SAMPLES,
                 points_per_r: int = DEFAULT_POINTS_PER_R) -> None:
        self.r, self.x0, self.iterations, self.discard = _resolve_parameters(
            r, x0, iterations, discard)
        self.r_min = _clamp_float(r_min, MIN_R, MAX_R, DEFAULT_R_MIN)
        self.r_max = _clamp_float(r_max, MIN_R, MAX_R, DEFAULT_R_MAX)
        if self.r_max < self.r_min:
            self.r_min, self.r_max = self.r_max, self.r_min
        self.r_samples = _clamp_int(r_samples, MIN_R_SAMPLES, MAX_R_SAMPLES, DEFAULT_R_SAMPLES)
        self.points_per_r = _clamp_int(points_per_r, MIN_POINTS_PER_R,
                                       MAX_POINTS_PER_R, DEFAULT_POINTS_PER_R)

    def orbit(self) -> LogisticOrbit:
        started = time.perf_counter()
        values = iterate(self.r, self.x0, self.iterations, self.discard)
        exponent = lyapunov_exponent(self.r, self.x0, self.iterations, self.discard)
        return LogisticOrbit(self.r, self.x0, self.iterations, self.discard,
                             values, exponent, time.perf_counter() - started)

    def bifurcation(self) -> LogisticBifurcation:
        started = time.perf_counter()
        r_values = np.linspace(self.r_min, self.r_max, self.r_samples)
        rs = np.repeat(r_values, self.points_per_r)
        xs = np.empty(rs.size, dtype=np.float64)
        for index, r_value in enumerate(r_values):
            values = iterate(r_value, self.x0, self.points_per_r, self.discard)
            start = index * self.points_per_r
            xs[start:start + self.points_per_r] = values
        return LogisticBifurcation(self.r_min, self.r_max, self.r_samples,
                                   self.points_per_r, rs, xs,
                                   time.perf_counter() - started)


def bifurcation(r_min: float = DEFAULT_R_MIN, r_max: float = DEFAULT_R_MAX,
                r_samples: int = DEFAULT_R_SAMPLES,
                points_per_r: int = DEFAULT_POINTS_PER_R,
                x0: float = DEFAULT_X0,
                discard: int = DEFAULT_DISCARD) -> LogisticBifurcation:
    """函数式分岔图入口。"""
    return LogisticMap(x0=x0, discard=discard, r_min=r_min, r_max=r_max,
                       r_samples=r_samples, points_per_r=points_per_r).bifurcation()


def _selfcheck() -> None:
    """确定性自检：固定点、周期 2、混沌指数和分岔采样。"""
    fixed = iterate(2.5, 0.2, 20, 100)
    period2 = iterate(3.2, 0.2, 12, 300)
    chaotic = iterate(4.0, 0.2, 20, 100)
    diagram = bifurcation(3.0, 4.0, r_samples=40, points_per_r=20,
                          x0=0.2, discard=100)
    print("Logistic Map 自检")
    print(f"固定点 r=2.5：末项 {fixed[-1]:.12f}（理论 0.6）")
    print(f"周期 2 r=3.2：末 4 项 "
          + ", ".join(f"{value:.9f}" for value in period2[-4:]))
    print(f"混沌 r=4：末项范围 [{chaotic.min():.6f}, {chaotic.max():.6f}]，"
          f"Lyapunov {lyapunov_exponent(4.0, 0.2, 1000, 200):.6f}（理论 ln 2 ≈ {math.log(2):.6f}）")
    print(f"分岔采样：r={diagram.r_samples} 个 × 每个 {diagram.points_per_r} 点，"
          f"范围 [{diagram.rs.min():.1f}, {diagram.rs.max():.1f}]，"
          f"x∈[{diagram.xs.min():.6f}, {diagram.xs.max():.6f}]")


if __name__ == "__main__":  # pragma: no cover
    _selfcheck()
