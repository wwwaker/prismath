# -*- coding: utf-8 -*-
"""Fourier Epicycles（傅里叶旋转矢量绘图）模型。"""

from ...registry import register
from .model import (
    DEFAULT_FRAMES,
    DEFAULT_SAMPLES,
    DEFAULT_SHAPE,
    DEFAULT_TERMS,
    MAX_FRAMES,
    SHAPE_LABELS,
    FourierEpicycle,
    FourierResult,
    analyze_points,
    dft_coefficients,
    evaluate_series,
    extract_image_contour,
    sample_shape,
)
from .spec import build_spec

SPEC = register(build_spec())

__all__ = [
    "SPEC",
    "DEFAULT_SHAPE",
    "DEFAULT_SAMPLES",
    "DEFAULT_TERMS",
    "DEFAULT_FRAMES",
    "MAX_FRAMES",
    "SHAPE_LABELS",
    "FourierEpicycle",
    "FourierResult",
    "sample_shape",
    "extract_image_contour",
    "dft_coefficients",
    "evaluate_series",
    "analyze_points",
]
