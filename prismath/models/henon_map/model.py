# -*- coding: utf-8 -*-
"""Hénon Map：用一个二维递推展示混沌吸引子。

经典 Hénon 映射为：

    x[n+1] = 1 - a*x[n]**2 + y[n]
    y[n+1] = b*x[n]

在 ``a=1.4, b=0.3`` 附近，轨道会落到著名的 Hénon 混沌吸引子上。模块只
依赖标准库和 NumPy，不含任何界面代码。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

__all__ = [
    "DEFAULT_A",
    "DEFAULT_B",
    "DEFAULT_X0",
    "DEFAULT_Y0",
    "DEFAULT_ITERATIONS",
    "DEFAULT_DISCARD",
    "MAX_ITERATIONS",
    "MAX_DISCARD",
    "HenonMap",
    "HenonOrbit",
    "henon_step",
    "iterate",
    "lyapunov_exponent",
]

DEFAULT_A: float = 1.4
DEFAULT_B: float = 0.3
DEFAULT_X0: float = 0.0
DEFAULT_Y0: float = 0.0
DEFAULT_ITERATIONS: int = 6000
DEFAULT_DISCARD: int = 300

MIN_A: float = 0.0
MAX_A: float = 2.0
MIN_B: float = -1.0
MAX_B: float = 1.0
MIN_COORD: float = -2.0
MAX_COORD: float = 2.0
MIN_ITERATIONS: int = 20
MAX_ITERATIONS: int = 20_000
MAX_DISCARD: int = 20_000
# 数值保护阈值，不作为数学上的逃逸半径使用。
MAX_MAGNITUDE: float = 1e6


def _clamp_float(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return max(low, min(high, number))


def _clamp_int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return fallback
    return max(low, min(high, number))


def _resolve_parameters(a: Any, b: Any, x0: Any, y0: Any,
                        iterations: Any, discard: Any) -> Tuple[float, float, float, float, int, int]:
    return (
        _clamp_float(a, MIN_A, MAX_A, DEFAULT_A),
        _clamp_float(b, MIN_B, MAX_B, DEFAULT_B),
        _clamp_float(x0, MIN_COORD, MAX_COORD, DEFAULT_X0),
        _clamp_float(y0, MIN_COORD, MAX_COORD, DEFAULT_Y0),
        _clamp_int(iterations, MIN_ITERATIONS, MAX_ITERATIONS, DEFAULT_ITERATIONS),
        _clamp_int(discard, 0, MAX_DISCARD, DEFAULT_DISCARD),
    )


def henon_step(x: Any, y: Any, a: Any = DEFAULT_A,
               b: Any = DEFAULT_B) -> Tuple[np.ndarray, np.ndarray]:
    """计算一步 Hénon 映射，支持标量和 NumPy 数组广播。"""
    x_value = np.asarray(x, dtype=float)
    y_value = np.asarray(y, dtype=float)
    a_value = np.asarray(a, dtype=float)
    b_value = np.asarray(b, dtype=float)
    return 1.0 - a_value * x_value * x_value + y_value, b_value * x_value


def iterate(a: Any = DEFAULT_A, b: Any = DEFAULT_B,
            x0: Any = DEFAULT_X0, y0: Any = DEFAULT_Y0,
            iterations: Any = DEFAULT_ITERATIONS,
            discard: Any = DEFAULT_DISCARD) -> np.ndarray:
    """返回丢弃瞬态后的轨道；超出数值范围时抛 ValueError，不返回无穷坐标。"""
    values, _exponent, stopped = _evolve(*_resolve_parameters(
        a, b, x0, y0, iterations, discard), with_exponent=False)
    if stopped is not None:
        raise ValueError(f"轨道在第 {stopped} 步超出计算范围，请调整参数或恢复经典参数。")
    return values


def lyapunov_exponent(a: Any = DEFAULT_A, b: Any = DEFAULT_B,
                      x0: Any = DEFAULT_X0, y0: Any = DEFAULT_Y0,
                      iterations: Any = DEFAULT_ITERATIONS,
                      discard: Any = DEFAULT_DISCARD) -> Optional[float]:
    """最大 Lyapunov 指数的有限步估计；超出计算范围返回 None。"""
    return _evolve(*_resolve_parameters(a, b, x0, y0, iterations, discard))[1]


def _evolve(a: float, b: float, x: float, y: float, limit: int, burn: int,
            with_exponent: bool = True) -> Tuple[np.ndarray, Optional[float], Optional[int]]:
    """在一次循环中采样并推进切向量；有限坐标保护覆盖瞬态和采样阶段。"""
    values = np.empty((limit, 2), dtype=np.float64)
    vx = vy = 1.0 / math.sqrt(2.0)
    total_log = 0.0
    collected = 0
    for index in range(burn + limit):
        # 切向量在当前状态推进；瞬态阶段同时预热方向。
        log_norm = 0.0
        if with_exponent:
            tx, ty = -2.0 * a * x * vx + vy, b * vx
            norm = math.hypot(tx, ty)
            if norm == 0.0:
                log_norm = -math.inf
                vx = vy = 1.0 / math.sqrt(2.0)
            else:
                log_norm = math.log(norm)
                vx, vy = tx / norm, ty / norm
        x, y = 1.0 - a * x * x + y, b * x
        if not (math.isfinite(x) and math.isfinite(y)) or max(abs(x), abs(y)) > MAX_MAGNITUDE:
            return values[:collected].copy(), None, index + 1
        if index >= burn:
            values[collected] = x, y
            collected += 1
            total_log += log_norm
    return values, total_log / limit if with_exponent else None, None


@dataclass(frozen=True)
class HenonOrbit:
    a: float
    b: float
    x0: float
    y0: float
    iterations: int
    discard: int
    values: np.ndarray
    lyapunov: Optional[float]
    elapsed: float
    stopped_step: Optional[int] = None

    def records(self) -> List[Dict[str, float]]:
        return [
            {"step": self.discard + index + 1,
             "x": float(value[0]), "y": float(value[1])}
            for index, value in enumerate(self.values)
        ]


class HenonMap:
    """对象级 Hénon Map API，供 Tk 视图与其它后端共用。"""

    def __init__(self, a: float = DEFAULT_A, b: float = DEFAULT_B,
                 x0: float = DEFAULT_X0, y0: float = DEFAULT_Y0,
                 iterations: int = DEFAULT_ITERATIONS,
                 discard: int = DEFAULT_DISCARD) -> None:
        (self.a, self.b, self.x0, self.y0, self.iterations,
         self.discard) = _resolve_parameters(a, b, x0, y0, iterations, discard)

    def orbit(self) -> HenonOrbit:
        started = time.perf_counter()
        values, exponent, stopped = _evolve(self.a, self.b, self.x0, self.y0,
                                            self.iterations, self.discard)
        return HenonOrbit(self.a, self.b, self.x0, self.y0, self.iterations,
                          self.discard, values, exponent,
                          time.perf_counter() - started, stopped)


def _selfcheck() -> None:
    """确定性自检：默认吸引子、一步递推与轨道有界性。"""
    first_x, first_y = henon_step(0.0, 0.0)
    result = HenonMap().orbit()
    values = result.values
    print("Hénon Map 自检")
    print(f"一步递推 (0, 0) → ({float(first_x):.6f}, {float(first_y):.6f})")
    print(f"默认参数 a={result.a:.1f}, b={result.b:.1f}："
          f"采样 {result.iterations} 点，x 范围 [{values[:, 0].min():.6f}, {values[:, 0].max():.6f}]，"
          f"y 范围 [{values[:, 1].min():.6f}, {values[:, 1].max():.6f}]")
    print(f"最大 Lyapunov 指数 {result.lyapunov:.6f}（正值表示混沌吸引子）")


if __name__ == "__main__":  # pragma: no cover
    _selfcheck()
