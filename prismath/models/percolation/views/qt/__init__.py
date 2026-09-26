# -*- coding: utf-8 -*-
"""边渗流 Qt 视图：模型拥有自己的舞台入口，外框由 ui/qt 提供。"""
from .stage import PercolationStage

def create_stage(spec):
    return PercolationStage(site=False)
