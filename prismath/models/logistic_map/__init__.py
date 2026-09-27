# -*- coding: utf-8 -*-
"""Logistic Map（逻辑斯蒂映射）模型。"""

from ...registry import register
from .model import (
    DEFAULT_DISCARD,
    DEFAULT_ITERATIONS,
    DEFAULT_POINTS_PER_R,
    DEFAULT_R,
    DEFAULT_R_MAX,
    DEFAULT_R_MIN,
    DEFAULT_R_SAMPLES,
    DEFAULT_X0,
    MAX_ITERATIONS,
    MAX_POINTS_PER_R,
    MAX_R_SAMPLES,
    LogisticBifurcation,
    LogisticMap,
    LogisticOrbit,
    bifurcation,
    iterate,
    logistic_step,
    lyapunov_exponent,
)
from .spec import build_spec

SPEC = register(build_spec())

__all__ = [
    "SPEC",
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
