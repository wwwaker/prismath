# -*- coding: utf-8 -*-
"""梯度下降实验室。"""

from ...registry import register
from .model import GradientDescent, GradientResult
from .spec import build_spec

SPEC = register(build_spec())

__all__ = ["SPEC", "GradientDescent", "GradientResult"]
