# -*- coding: utf-8 -*-
"""万有引力多星 Qt 视图入口。"""

from .stage import NBodyStage


def create_stage(spec):
    return NBodyStage()


__all__ = ["NBodyStage", "create_stage"]
