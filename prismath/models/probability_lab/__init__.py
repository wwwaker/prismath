# -*- coding: utf-8 -*-
"""概率实验室：大数定理、中心极限定理和高尔顿钉板。"""

from ...registry import register
from .model import ProbabilityLab, ProbabilityResult
from .spec import build_spec

SPEC = register(build_spec())

__all__ = ["SPEC", "ProbabilityLab", "ProbabilityResult"]
