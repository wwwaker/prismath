# -*- coding: utf-8 -*-
"""PySide6 后端的稳定导出入口。

具体实现按职责拆在 ``theme``, ``widgets``, ``params``, ``stages``, ``portal``,
``pages`` 和 ``window`` 中；新增模型或视觉范式不需要把代码塞进本文件。
"""
from .window import PrismathWindow, launch_app
from .pages import ModelPage

__all__ = ["PrismathWindow", "ModelPage", "launch_app"]
