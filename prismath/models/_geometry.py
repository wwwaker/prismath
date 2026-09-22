# -*- coding: utf-8 -*-
"""
模型间共用的几何小工具
========================

以 ``_`` 开头，因此 :func:`prismath.registry.load_models` 扫描模型包时会跳过它（它不是
模型，只是共用函数）。

这里放的是**与具体模型无关、但被多个模型共用**的几何：格子类型（方格网 / 三角网）决定了
每个格点在图纸上的单位坐标，界面层按同一套坐标等比缩放即可绘制；三角网与方格网的差异只
在"奇数行右移半格、行距 √3/2"，写成一份就不会在两个模型里各写一遍。

界面层可以直接用（例如桌面视图的画布布局），这属于"向下依赖共用件"，与依赖 ``_options``
的选项词表同理。
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

__all__ = ["lattice_layout"]


def lattice_layout(rows: int, cols: Optional[int] = None,
                   lattice: str = "square") -> List[Tuple[float, float]]:
    """返回每个格点的**单位坐标**（供界面层等比缩放后绘制）。

    * 方格网：``x = c``、``y = r``，行距 1；
    * 三角网：奇数行右移半格、行距 ``√3 / 2``，恰好铺成等边三角形。

    返回列表的下标即格点索引（``row * cols + col``）。
    """
    columns = int(cols) if cols is not None else int(rows)
    row_h = 1.0 if lattice == "square" else math.sqrt(3.0) / 2.0
    half = 0.0 if lattice == "square" else 0.5
    pts: List[Tuple[float, float]] = []
    for r in range(int(rows)):
        shift = half * (r % 2)
        for c in range(columns):
            pts.append((c + shift, r * row_h))
    return pts
