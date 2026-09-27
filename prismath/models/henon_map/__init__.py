# -*- coding: utf-8 -*-
"""Hénon Map（亨农映射）模型。"""

from ...registry import register
from .model import (
    DEFAULT_A,
    DEFAULT_B,
    DEFAULT_DISCARD,
    DEFAULT_ITERATIONS,
    DEFAULT_X0,
    DEFAULT_Y0,
    MAX_DISCARD,
    MAX_ITERATIONS,
    HenonMap,
    HenonOrbit,
    iterate,
    henon_step,
    lyapunov_exponent,
)
from .spec import build_spec

SPEC = register(build_spec())

__all__ = [
    "SPEC",
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
