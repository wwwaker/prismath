# -*- coding: utf-8 -*-
"""蒲丰投针 Qt 视图入口。"""

from .stage import BuffonNeedleStage


def create_stage(spec):
    return BuffonNeedleStage()


__all__ = ["BuffonNeedleStage", "create_stage"]
