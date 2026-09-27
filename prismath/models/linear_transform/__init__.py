# -*- coding: utf-8 -*-
"""线性变换实验室：把矩阵作用在网格、基向量和任意向量上。"""

from ...registry import register
from .model import (  # noqa: F401
    DEFAULT_ANGLE,
    DEFAULT_MODE,
    LinearTransform,
    LinearTransformResult,
    matrix_for,
)
from .spec import build_spec

SPEC = register(build_spec())

__all__ = ["SPEC", "LinearTransform", "LinearTransformResult", "matrix_for"]
