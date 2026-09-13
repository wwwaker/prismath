# -*- coding: utf-8 -*-
"""
模型间的公共选项词表（界面中文标签 -> 模型内部取值）
=====================================================

放在 ``models`` 包根目录、以 ``_`` 开头，因此 :func:`awe_math.registry.load_models`
自动扫描模型包时会跳过它（它不是模型，只是共用词表）。

边渗流与点渗流共用同一套「格子 / 方向」标签，保证界面上两个模型的选项命名一致；
注水（起始）方式的措辞各自贴合模型语义（边渗流说「注水」，点渗流说「占据格」）。
"""

from __future__ import annotations

from typing import Dict

__all__ = [
    "LATTICE_CHOICES",
    "DIRECTION_CHOICES",
    "BOND_INJECT_CHOICES",
    "SITE_INJECT_CHOICES",
    "CRITERION_CHOICES",
    "SITE_CRITERION_CHOICES",
]

#: 格子类型
LATTICE_CHOICES: Dict[str, str] = {
    "方格网（4 邻域）": "square",
    "三角网（6 邻域）": "triangular",
}

#: 方向模式（两个模型通用）
DIRECTION_CHOICES: Dict[str, str] = {
    "无向（四面流动）": "undirected",
    "不允许向上（下/左/右）": "no_up",
    "只允许向下/向右（经典有向渗流）": "down_right",
    "只允许向下/向左（镜像）": "down_left",
}

#: 边渗流的注水方式
BOND_INJECT_CHOICES: Dict[str, str] = {
    "顶端整行注水": "top",
    "中心单点注水": "center",
    "随机单点注水": "random",
}

#: 点渗流的注水（起始）方式
SITE_INJECT_CHOICES: Dict[str, str] = {
    "随机一个占据格": "random",
    "中心附近的占据格": "center",
    "顶端整行占据格": "top",
}

#: 「成功判据」：两个模型共用同一套标签，两种判据回答的是两个不同的问题
#:
#: * ``span``：网格上是否存在纵贯簇（顶行 ↔ 底行）—— 这才是 p_c 的判据；
#: * ``area``：从注水点出发的蔓延/浸润面积是否达到设定比例 —— 没有固定临界值。
CRITERION_CHOICES: Dict[str, str] = {
    "贯通判据：顶行连通到底行（对应 p_c）": "span",
    "面积判据：面积比例 ≥ 阈值（无固定阈值）": "area",
}

#: 旧名（点渗流专用），保留以兼容既有引用
SITE_CRITERION_CHOICES: Dict[str, str] = CRITERION_CHOICES
