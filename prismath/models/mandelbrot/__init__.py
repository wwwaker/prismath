# -*- coding: utf-8 -*-
"""
Mandelbrot 集模型（分形与自相似）
==================================
对复平面上的每个点 c 迭代 ``z → z² + c``：轨道有界的点组成 Mandelbrot 集，
轨道发散的点则按"第几步逃逸"上色 —— 边界处处自相似，面积却只有 ≈ 1.5066。

* :mod:`prismath.models.mandelbrot.model` —— 纯计算内核（逃逸时间 / 解析子集 / 视图几何）
* :mod:`prismath.models.mandelbrot.spec`  —— 界面元数据与动作处理器

它是本项目第一个**分形 / 连续场**模型：桌面视图继承通用图表骨架 ``ChartViewBase``，
用的是 ``ChartSpec(kind="grid")`` 的**连续场**路径（数值 + 64 级色带 → 图像缓冲），
并把"左键点哪放大哪"接到基类的点击反查钩子上。

导入本包即完成模型注册。
"""

from ...registry import register
from .model import (  # noqa: F401  便于外部直接引用
    AREA_REFERENCE,
    AUTO_ITERATIONS_BASE,
    AUTO_ITERATIONS_SLOPE,
    DEFAULT_ASPECT,
    DEFAULT_CENTER_X,
    DEFAULT_CENTER_Y,
    DEFAULT_COLS,
    DEFAULT_ITERATIONS,
    DEFAULT_PALETTE,
    DEFAULT_PIXELS,
    DEFAULT_ROWS,
    DEFAULT_SPAN,
    ESCAPE_RADIUS,
    INTERIOR_BIG_DISK,
    INTERIOR_BIG_DISK_MAX_X,
    INTERIOR_DISKS,
    LEVELS,
    MAX_ITERATIONS,
    MAX_MAGNIFICATION,
    MAX_PIXELS,
    MAX_SPAN,
    MIN_ITERATIONS,
    MIN_MAGNIFICATION,
    MIN_PIXELS,
    MIN_SPAN,
    PALETTES,
    Mandelbrot,
    MandelbrotField,
    Viewport,
    complex_grid,
    escape_counts,
    in_main_bulb,
    interior_mask,
    iterations_for,
    make_viewport,
    mandelbrot_levels,
    resample_to,
    scan_iterations,
)
from .spec import build_spec

SPEC = register(build_spec())

__all__ = [
    "SPEC",
    "DEFAULT_CENTER_X",
    "DEFAULT_CENTER_Y",
    "DEFAULT_SPAN",
    "DEFAULT_ITERATIONS",
    "DEFAULT_PIXELS",
    "DEFAULT_COLS",
    "DEFAULT_ROWS",
    "DEFAULT_ASPECT",
    "DEFAULT_PALETTE",
    "MIN_ITERATIONS",
    "MAX_ITERATIONS",
    "MIN_PIXELS",
    "MAX_PIXELS",
    "MIN_SPAN",
    "MAX_SPAN",
    "MIN_MAGNIFICATION",
    "MAX_MAGNIFICATION",
    "AUTO_ITERATIONS_BASE",
    "AUTO_ITERATIONS_SLOPE",
    "INTERIOR_DISKS",
    "INTERIOR_BIG_DISK",
    "INTERIOR_BIG_DISK_MAX_X",
    "ESCAPE_RADIUS",
    "LEVELS",
    "PALETTES",
    "AREA_REFERENCE",
    "Viewport",
    "make_viewport",
    "complex_grid",
    "escape_counts",
    "mandelbrot_levels",
    "resample_to",
    "in_main_bulb",
    "interior_mask",
    "iterations_for",
    "MandelbrotField",
    "Mandelbrot",
    "scan_iterations",
]
