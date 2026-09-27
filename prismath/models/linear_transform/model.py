# -*- coding: utf-8 -*-
"""线性变换实验室的纯计算内核。"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

DEFAULT_MODE = "identity"
DEFAULT_ANGLE = 30.0
DEFAULT_SCALE_X = 1.35
DEFAULT_SCALE_Y = 0.75
DEFAULT_SHEAR = 0.8
DEFAULT_VECTOR_X = 1.25
DEFAULT_VECTOR_Y = 0.65
DEFAULT_EXTENT = 3.0
MODES = ("identity", "rotation", "scale", "shear", "mirror")
MODE_LABELS = {
    "identity": "单位变换",
    "rotation": "旋转",
    "scale": "缩放",
    "shear": "剪切",
    "mirror": "镜像",
}


def _clamp(value: float, low: float, high: float, fallback: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(value):
        return fallback
    return max(low, min(high, value))


def matrix_for(mode: str = DEFAULT_MODE, angle: float = DEFAULT_ANGLE,
               scale_x: float = DEFAULT_SCALE_X, scale_y: float = DEFAULT_SCALE_Y,
               shear: float = DEFAULT_SHEAR) -> np.ndarray:
    """根据教学用预设返回 2×2 矩阵，约定 ``(x', y') = M @ (x, y)``。"""
    key = str(mode).strip().lower()
    if key not in MODES:
        key = DEFAULT_MODE
    angle = math.radians(_clamp(angle, -180.0, 180.0, DEFAULT_ANGLE))
    sx = _clamp(scale_x, 0.1, 4.0, DEFAULT_SCALE_X)
    sy = _clamp(scale_y, 0.1, 4.0, DEFAULT_SCALE_Y)
    k = _clamp(shear, -3.0, 3.0, DEFAULT_SHEAR)
    if key == "rotation":
        c, s = math.cos(angle), math.sin(angle)
        return np.array(((c, -s), (s, c)), dtype=float)
    if key == "scale":
        return np.diag((sx, sy)).astype(float)
    if key == "shear":
        return np.array(((1.0, k), (0.0, 1.0)), dtype=float)
    if key == "mirror":
        return np.array(((-1.0, 0.0), (0.0, 1.0)), dtype=float)
    return np.eye(2, dtype=float)


def _grid(extent: float, matrix: np.ndarray, spacing: float = 0.5) -> List[Dict[str, List[List[float]]]]:
    extent = _clamp(extent, 1.0, 6.0, DEFAULT_EXTENT)
    values = np.arange(-extent, extent + spacing * 0.5, spacing)
    lines: List[Dict[str, List[List[float]]]] = []
    for value in values:
        original = [[-extent, float(value)], [extent, float(value)]]
        vertical = [[float(value), -extent], [float(value), extent]]
        for points in (original, vertical):
            transformed = (matrix @ np.asarray(points, dtype=float).T).T
            lines.append({
                "original": [[float(x), float(y)] for x, y in points],
                "transformed": transformed.tolist(),
            })
    return lines


@dataclass(frozen=True)
class LinearTransformResult:
    mode: str
    matrix: np.ndarray
    vector: np.ndarray
    transformed_vector: np.ndarray
    determinant: float
    area_scale: float
    orientation: str
    grid: List[Dict[str, List[List[float]]]]
    elapsed: float


class LinearTransform:
    """教学预设 + 基向量 / 网格的线性变换。"""

    def __init__(self, mode: str = DEFAULT_MODE, angle: float = DEFAULT_ANGLE,
                 scale_x: float = DEFAULT_SCALE_X, scale_y: float = DEFAULT_SCALE_Y,
                 shear: float = DEFAULT_SHEAR, vector_x: float = DEFAULT_VECTOR_X,
                 vector_y: float = DEFAULT_VECTOR_Y, extent: float = DEFAULT_EXTENT) -> None:
        self.mode = str(mode).strip().lower() if str(mode).strip().lower() in MODES else DEFAULT_MODE
        self.angle = _clamp(angle, -180.0, 180.0, DEFAULT_ANGLE)
        self.scale_x = _clamp(scale_x, 0.1, 4.0, DEFAULT_SCALE_X)
        self.scale_y = _clamp(scale_y, 0.1, 4.0, DEFAULT_SCALE_Y)
        self.shear = _clamp(shear, -3.0, 3.0, DEFAULT_SHEAR)
        self.vector = np.array((_clamp(vector_x, -4.0, 4.0, DEFAULT_VECTOR_X),
                                _clamp(vector_y, -4.0, 4.0, DEFAULT_VECTOR_Y)), dtype=float)
        self.extent = _clamp(extent, 1.0, 6.0, DEFAULT_EXTENT)

    def transform(self) -> LinearTransformResult:
        started = time.perf_counter()
        matrix = matrix_for(self.mode, self.angle, self.scale_x, self.scale_y, self.shear)
        transformed = matrix @ self.vector
        determinant = float(np.linalg.det(matrix))
        return LinearTransformResult(
            mode=self.mode, matrix=matrix, vector=self.vector.copy(),
            transformed_vector=transformed, determinant=determinant,
            area_scale=abs(determinant),
            orientation="方向翻转" if determinant < 0 else "方向保持",
            grid=_grid(self.extent, matrix), elapsed=time.perf_counter() - started,
        )
