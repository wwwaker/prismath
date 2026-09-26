# -*- coding: utf-8 -*-
"""生命游戏 Qt 视图入口。"""

from .stage import LifeGameStage


def create_stage(spec):
    return LifeGameStage()


__all__ = ["LifeGameStage", "create_stage"]
