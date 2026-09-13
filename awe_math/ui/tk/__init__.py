# -*- coding: utf-8 -*-
"""
桌面窗口界面后端（Tkinter 实现），作为网页界面之外的备选方案。

* :mod:`~awe_math.ui.tk.shell` —— 窗口外壳：顶部模型下拉框 + 视图切换
* :mod:`~awe_math.ui.tk.theme` —— 深色扁平主题（配色 / 字体 / ttk 样式）
* :mod:`~awe_math.ui.tk.app`   —— 边渗流视图（格子随机连通）
* :mod:`~awe_math.ui.tk.site`  —— 点渗流视图（格子随机占据）
"""

from .shell import DesktopShell, FallbackView, launch  # noqa: F401

__all__ = ["launch", "DesktopShell", "FallbackView"]
