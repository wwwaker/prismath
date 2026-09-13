# -*- coding: utf-8 -*-
"""
点渗流模型（量变引起质变）
============================

* :mod:`awe_math.models.site_percolation.model` —— 纯计算内核（随机占据 + BFS 蔓延）
* :mod:`awe_math.models.site_percolation.spec`  —— 界面元数据与动作处理器

它同时是「森林火灾」的抽象：占据格 = 树、空位 = 空地、蔓延范围 = 一次火灾的过火面积。

导入本包即完成模型注册。
"""

from ...registry import register
from .model import (  # noqa: F401  便于外部直接引用
    CRITERIA,
    CRITERION_NAMES,
    DEFAULT_CRITERION,
    DEFAULT_THRESHOLD,
    THEORETICAL_PC,
    SitePercolation,
    SpreadBatchResult,
    SpreadResult,
    batch_spread_probability,
    encode_sites,
    scan_curve,
)
from .spec import build_spec

SPEC = register(build_spec())

__all__ = [
    "SPEC",
    "THEORETICAL_PC",
    "DEFAULT_THRESHOLD",
    "CRITERIA",
    "CRITERION_NAMES",
    "DEFAULT_CRITERION",
    "SitePercolation",
    "SpreadResult",
    "SpreadBatchResult",
    "batch_spread_probability",
    "scan_curve",
    "encode_sites",
]
