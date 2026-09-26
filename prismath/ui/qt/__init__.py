# -*- coding: utf-8 -*-
"""PySide6 桌面后端。

Qt 后端和模型内核运行在同一个 Python 进程中；它不启动浏览器，也不把计算
拆成独立的前后端服务。模型视图只依赖 ``ModelSpec`` 的数据级契约，因此新模型
可以先用通用结果页接入，再逐步添加专用画布。
"""

from __future__ import annotations

from typing import Any, Optional

from ...spec import ModelSpec

__all__ = ["launch"]


def launch(spec: Optional[ModelSpec] = None, args: Any = None) -> int:
    """打开 Qt 桌面窗口，并在窗口关闭后返回 Qt 的退出码。"""
    from .app import launch_app

    return launch_app(spec)

