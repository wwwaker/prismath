# -*- coding: utf-8 -*-
"""
蒲丰投针模型（概率与统计）
============================

在间距为 d 的平行线上随机投 N 根长度为 L（L ≤ d）的针，用命中频率反解 π：
命中概率 P = 2L/(πd)，故 π ≈ 2LN/(dH)。

* :mod:`prismath.models.buffon_needle.model` —— 纯计算内核（投针几何 + Monte Carlo 估计）
* :mod:`prismath.models.buffon_needle.spec`  —— 界面元数据与动作处理器

它是本项目第一个**非渗流**模型：桌面视图继承**通用图表骨架** ``ChartViewBase``（而非
渗流专用的 ``PercolationViewBase``），参数表单由 ``spec.params`` 自动生成，图表只写声明。

导入本包即完成模型注册。
"""

from ...registry import register
from .model import (  # noqa: F401  便于外部直接引用
    DEFAULT_RATIO,
    DEFAULT_REPEATS,
    DEFAULT_THROWS,
    MAX_RATIO,
    MIN_RATIO,
    PI,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
    BuffonNeedle,
    ConvergeResult,
    Needle,
    ThrowResult,
    encode_needles,
    estimate_pi,
)
from .spec import build_spec

SPEC = register(build_spec())

__all__ = [
    "SPEC",
    "PI",
    "DEFAULT_RATIO",
    "DEFAULT_THROWS",
    "DEFAULT_REPEATS",
    "MIN_RATIO",
    "MAX_RATIO",
    "VIEWPORT_WIDTH",
    "VIEWPORT_HEIGHT",
    "Needle",
    "ThrowResult",
    "ConvergeResult",
    "BuffonNeedle",
    "encode_needles",
    "estimate_pi",
]
