# -*- coding: utf-8 -*-
"""
万有引力多星模型（确定性与混沌）
==================================
``N`` 颗星只受万有引力 ``F = G·m₁·m₂/r²``：规则只有一条、完全确定，
却既能给出钟表般精确的周期轨道（8 字三体、行星圆轨道），也能给出不可长期预测的
混沌（一般三体、随机星团）—— **确定性不等于可预测**。

* :mod:`prismath.models.n_body.model` —— 纯计算内核（速度 Verlet 积分 / 场景库 / 守恒量 / dt 扫描）
* :mod:`prismath.models.n_body.spec`  —— 界面元数据与动作处理器

它是本项目第一个**连续时间动力学**模型（此前的模型都是离散步：元胞自动机按"代"、
渗流按"逐层"、投针按"根"）。桌面视图继承通用图表骨架 ``ChartViewBase``，
但画布用的是模型自己的图种 ``kind="orbits"`` —— 星体 + 轨迹带 + 播放控制，
因为"运动的点云"是工具箱现成五种图元（线段云 / 曲线族 / 柱状 / 栅格 / 文字）都没覆盖的范式。

导入本包即完成模型注册。
"""

from ...registry import register
from .model import (  # noqa: F401  便于外部直接引用
    DEFAULT_DT,
    DEFAULT_FRAMES,
    DEFAULT_SEED,
    DEFAULT_SOFTENING,
    DEFAULT_STARS,
    DEFAULT_SUBSTEPS,
    DEFAULT_TRAIL,
    FIGURE_EIGHT_PERIOD,
    GRAVITY,
    MAX_DT,
    MAX_FRAMES,
    MAX_SOFTENING,
    MAX_STARS,
    MAX_SUBSTEPS,
    MAX_TRAIL,
    MIN_DT,
    MIN_MASS,
    MIN_STARS,
    MIN_SUBSTEPS,
    MIN_TRAIL,
    SCENARIO_BINARY,
    SCENARIO_CLUSTER,
    SCENARIO_DISK,
    SCENARIO_FIGURE_EIGHT,
    SCENARIO_LABELS,
    SCENARIO_ORDER,
    SCENARIO_SOLAR,
    SCENARIOS,
    DriftPoint,
    NBody,
    NBodyRun,
    Preset,
    Scenario,
    build_scenario,
    circular_velocity,
    encode_positions,
    scan_drift,
)
from .spec import build_spec

SPEC = register(build_spec())

__all__ = [
    "SPEC",
    "GRAVITY",
    "MIN_MASS",
    "DEFAULT_STARS",
    "MIN_STARS",
    "MAX_STARS",
    "DEFAULT_DT",
    "MIN_DT",
    "MAX_DT",
    "DEFAULT_SUBSTEPS",
    "MIN_SUBSTEPS",
    "MAX_SUBSTEPS",
    "DEFAULT_SOFTENING",
    "MAX_SOFTENING",
    "DEFAULT_TRAIL",
    "MIN_TRAIL",
    "MAX_TRAIL",
    "DEFAULT_FRAMES",
    "MAX_FRAMES",
    "DEFAULT_SEED",
    "FIGURE_EIGHT_PERIOD",
    "SCENARIO_FIGURE_EIGHT",
    "SCENARIO_BINARY",
    "SCENARIO_SOLAR",
    "SCENARIO_CLUSTER",
    "SCENARIO_DISK",
    "SCENARIO_ORDER",
    "SCENARIOS",
    "SCENARIO_LABELS",
    "Scenario",
    "Preset",
    "NBody",
    "NBodyRun",
    "DriftPoint",
    "build_scenario",
    "scan_drift",
    "encode_positions",
    "circular_velocity",
]
