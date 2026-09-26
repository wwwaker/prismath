# -*- coding: utf-8 -*-
"""
桌面窗口界面后端（Tkinter 实现）——默认入口。
============================================

* :mod:`~prismath.ui.tk.shell` —— 窗口外壳：顶部模型下拉框 + 「☰ 模型列表」+ 视图切换
* :mod:`~prismath.ui.tk.portal` —— **模型列表入口页**（``python main.py`` 的首屏）
* :mod:`~prismath.ui.tk.theme` —— 浅色纸张主题（配色 / 字体 / ttk 样式）
* :mod:`~prismath.ui.tk.kit` —— 桌面界面工具箱：与模型无关的共享骨架 + 视图注册表

**本包不含任何具体模型的界面代码**：模型的桌面视图放在模型自己的包里
（``prismath/models/<模型包>/views/tk.py``），由 :mod:`~prismath.ui.tk.kit` 的注册表按
约定在启动时懒加载；骨架在
:class:`~prismath.ui.tk.kit.base.PercolationViewBase`，各模型只写自己的术语、配色与
画布画法。这样「新增模型 = 新增一个目录」，删除模型时界面代码跟着一起走。
"""

from .shell import DesktopShell, FallbackView, launch  # noqa: F401

__all__ = ["launch", "DesktopShell", "FallbackView"]
