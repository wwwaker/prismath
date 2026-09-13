# -*- coding: utf-8 -*-
"""
边渗流模型（量变引起质变）
============================

在 rows × cols 的格子上每条边以概率 p 随机连通，水从注水点沿流通边蔓延：
支持方格网 / 三角网、方形 / 矩形网格、四种方向模式与三种注水方式。

* :mod:`awe_math.models.percolation.model` —— 纯计算内核（并查集 + BFS 分层）
* :mod:`awe_math.models.percolation.spec` —— 界面元数据与动作处理器

导入本包即完成模型注册。
"""

from ...registry import register
from .model import (  # noqa: F401  便于外部直接引用
    CRITERIA,
    CRITERION_NAMES,
    DEFAULT_CRITERION,
    DEFAULT_THRESHOLD,
    DIRECTIONS,
    INJECT_MODES,
    LATTICES,
    THEORETICAL_PC,
    THEORETICAL_PC_BY_COMBO,
    BatchResult,
    PercolationGrid,
    SimResult,
    batch_percolation_probability,
    encode_edges,
    lattice_layout,
    scan_curve,
)
from .spec import build_spec

SPEC = register(build_spec())

__all__ = [
    "SPEC",
    "THEORETICAL_PC",
    "THEORETICAL_PC_BY_COMBO",
    "DEFAULT_THRESHOLD",
    "CRITERIA",
    "CRITERION_NAMES",
    "DEFAULT_CRITERION",
    "LATTICES",
    "DIRECTIONS",
    "INJECT_MODES",
    "PercolationGrid",
    "SimResult",
    "BatchResult",
    "batch_percolation_probability",
    "scan_curve",
    "encode_edges",
    "lattice_layout",
]
