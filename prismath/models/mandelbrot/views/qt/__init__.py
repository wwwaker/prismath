# -*- coding: utf-8 -*-
"""Mandelbrot Qt 视图入口。"""
from .stage import MandelbrotStage

def create_stage(spec):
    return MandelbrotStage()
