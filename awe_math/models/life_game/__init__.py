# -*- coding: utf-8 -*-
"""
生命游戏模型（简单规则与涌现）
================================
每个格子只看周围 8 个邻居，按 ``B3/S23`` 同时更新：活细胞有 2~3 个邻居就存活，
死细胞恰好 3 个邻居则新生。三条局部规则，却能长出滑翔机、振荡子、滑翔机枪 ——
**复杂度可以来自规则本身，而不来自规则的复杂**。

* :mod:`awe_math.models.life_game.model` —— 纯计算内核（演化 / 周期检测 / 图案库 / 密度统计）
* :mod:`awe_math.models.life_game.spec`  —— 界面元数据与动作处理器

它是本项目第一个**栅格类**模型：桌面视图继承通用图表骨架 ``ChartViewBase``，但用的是
``ChartSpec(kind="grid")`` —— 逐帧栅格 + 时间轴播放（可暂停 / 单步）+ 点击涂改，
全部由工具箱提供，``views/tk.py`` 里只写声明与四个可选钩子。

导入本包即完成模型注册。
"""

from ...registry import register
from .model import (  # noqa: F401  便于外部直接引用
    BOUNDARIES,
    BOUNDARY_DEAD,
    BOUNDARY_TORUS,
    DEFAULT_COLS,
    DEFAULT_DENSITY,
    DEFAULT_GENERATIONS,
    DEFAULT_ROWS,
    DEFAULT_RULE,
    MAX_FRAMES,
    MAX_SIZE,
    MIN_SIZE,
    OUTCOME_CYCLE,
    OUTCOME_EXTINCT,
    OUTCOME_LABELS,
    OUTCOME_RUNNING,
    OUTCOME_STATIC,
    PATTERNS,
    PATTERN_LABELS,
    RULES,
    DensityResult,
    LifeBoard,
    LifeRule,
    LifeRun,
    LifeStep,
    encode_cells,
    scan_survival,
)
from .spec import build_spec

SPEC = register(build_spec())

__all__ = [
    "SPEC",
    "DEFAULT_ROWS",
    "DEFAULT_COLS",
    "DEFAULT_DENSITY",
    "DEFAULT_GENERATIONS",
    "DEFAULT_RULE",
    "MIN_SIZE",
    "MAX_SIZE",
    "MAX_FRAMES",
    "BOUNDARIES",
    "BOUNDARY_TORUS",
    "BOUNDARY_DEAD",
    "OUTCOME_RUNNING",
    "OUTCOME_EXTINCT",
    "OUTCOME_STATIC",
    "OUTCOME_CYCLE",
    "OUTCOME_LABELS",
    "RULES",
    "PATTERNS",
    "PATTERN_LABELS",
    "LifeRule",
    "LifeStep",
    "LifeRun",
    "DensityResult",
    "LifeBoard",
    "encode_cells",
    "scan_survival",
]
