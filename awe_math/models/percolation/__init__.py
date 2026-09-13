# -*- coding: utf-8 -*-
"""
方格网渗流模型（量变引起质变）
================================

* :mod:`awe_math.models.percolation.model` —— 纯计算内核（并查集 + 多源 BFS）
* :mod:`awe_math.models.percolation.spec` —— 界面元数据与动作处理器

导入本包即完成模型注册。
"""

from ...registry import register
from .model import (  # noqa: F401  便于外部直接引用
    THEORETICAL_PC,
    BatchResult,
    PercolationGrid,
    SimResult,
    batch_percolation_probability,
    scan_curve,
)
from .spec import build_spec

SPEC = register(build_spec())

__all__ = [
    "SPEC",
    "THEORETICAL_PC",
    "BatchResult",
    "PercolationGrid",
    "SimResult",
    "batch_percolation_probability",
    "scan_curve",
]
