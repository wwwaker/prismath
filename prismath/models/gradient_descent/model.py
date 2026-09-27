# -*- coding: utf-8 -*-
"""一维函数上的梯度下降：把微积分中的切线变成可观察的路径。"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

import numpy as np

DEFAULT_FUNCTION = "quadratic"
DEFAULT_START = 3.2
DEFAULT_RATE = 0.12
DEFAULT_ITERATIONS = 60
FUNCTIONS = (
    "quadratic", "double_well", "tilted", "sinusoidal", "wiggly",
    "sixth_order", "smooth_abs",
)
FUNCTION_LABELS = {
    "quadratic": "x²",
    "double_well": "x⁴ - 2x²",
    "tilted": "0.5x² + 0.8x",
    "sinusoidal": "sin(x) + 0.15x²",
    "wiggly": "0.2x² + sin(3x)",
    "sixth_order": "0.08x⁶ - 0.8x⁴ + 1.2x²",
    "smooth_abs": "√(x² + 0.05)",
}


def function_pair(name: str) -> Tuple[Callable[[float], float], Callable[[float], float]]:
    key = str(name).strip().lower()
    if key == "double_well":
        return lambda x: x**4 - 2.0*x*x, lambda x: 4.0*x**3 - 4.0*x
    if key == "tilted":
        return lambda x: 0.5*x*x + 0.8*x, lambda x: x + 0.8
    if key == "sinusoidal":
        return lambda x: math.sin(x) + 0.15*x*x, lambda x: math.cos(x) + 0.3*x
    if key == "wiggly":
        return lambda x: 0.2*x*x + math.sin(3.0*x), lambda x: 0.4*x + 3.0*math.cos(3.0*x)
    if key == "sixth_order":
        return (lambda x: 0.08*x**6 - 0.8*x**4 + 1.2*x*x,
                lambda x: 0.48*x**5 - 3.2*x**3 + 2.4*x)
    if key == "smooth_abs":
        return lambda x: math.sqrt(x*x + 0.05), lambda x: x / math.sqrt(x*x + 0.05)
    return lambda x: x*x, lambda x: 2.0*x


def _clamp(value, low, high, fallback):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return fallback
    return fallback if not math.isfinite(value) else max(low, min(high, value))


@dataclass(frozen=True)
class GradientResult:
    function: str
    start: float
    rate: float
    iterations: int
    records: List[Dict[str, float]]
    curve: List[Dict[str, float]]
    minimum_x: float
    final_x: float
    final_value: float
    converged: bool
    elapsed: float


class GradientDescent:
    def __init__(self, function: str = DEFAULT_FUNCTION, start: float = DEFAULT_START,
                 rate: float = DEFAULT_RATE, iterations: int = DEFAULT_ITERATIONS) -> None:
        self.function = str(function).strip().lower() if str(function).strip().lower() in FUNCTIONS else DEFAULT_FUNCTION
        self.start = _clamp(start, -4.0, 4.0, DEFAULT_START)
        self.rate = _clamp(rate, 0.001, 1.0, DEFAULT_RATE)
        try:
            self.iterations = max(1, min(500, int(float(iterations))))
        except (TypeError, ValueError):
            self.iterations = DEFAULT_ITERATIONS

    def run(self) -> GradientResult:
        started = time.perf_counter()
        f, grad = function_pair(self.function)
        x = self.start
        records: List[Dict[str, float]] = []
        for step in range(self.iterations + 1):
            value, slope = float(f(x)), float(grad(x))
            records.append({"step": step, "x": x, "y": value, "gradient": slope})
            if not math.isfinite(value) or not math.isfinite(slope) or abs(x) > 1e6:
                break
            x -= self.rate * slope
        # 高阶函数在端点变化很快，但把横轴限制在课堂上容易读的范围内，
        # 避免少量极端值把下降轨迹压扁成一条线。
        xs = np.linspace(-4.0, 4.0, 420)
        curve = [{"x": float(v), "y": float(f(float(v)))} for v in xs]
        if self.function == "double_well":
            minimum_x = -1.0 if abs(x + 1.0) < abs(x - 1.0) else 1.0
        elif self.function == "tilted":
            minimum_x = -0.8
        elif self.function in ("sinusoidal", "wiggly", "sixth_order"):
            # 这些预设没有必要把闭式根写死在界面里；在同一显示范围内
            # 做一次密集扫描，给学习者一个可靠的全局谷底参考。
            minimum_x = float(xs[int(np.argmin([f(float(v)) for v in xs]))])
        elif self.function == "smooth_abs":
            minimum_x = 0.0
        else:
            minimum_x = 0.0
        final_value = float(records[-1]["y"])
        converged = abs(float(records[-1]["gradient"])) < 1e-3
        return GradientResult(self.function, self.start, self.rate, self.iterations,
                              records, curve, minimum_x, float(records[-1]["x"]),
                              final_value, converged, time.perf_counter() - started)
