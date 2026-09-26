# -*- coding: utf-8 -*-
"""点渗流 Qt 视图：与边渗流共享绘制基元，但拥有独立的模型适配入口。"""
from .stage import PercolationStage

def create_stage(spec):
    return PercolationStage(site=True)
