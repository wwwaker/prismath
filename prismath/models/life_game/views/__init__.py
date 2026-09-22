# -*- coding: utf-8 -*-
"""
生命游戏模型在各界面后端下的**特化视图**。

约定（所有模型一致）：

* 文件名即界面后端的 key：``tk.py`` 对应 ``--ui tk``；
* 模块内用 ``@register_view("life_game")`` 登记自己的视图类；
* **不要在模型的 ``__init__.py`` 里 import 本包**：视图会引入 tkinter 这类重型依赖，
  必须由对应后端在真正启动时按需导入（终端模式因此保持无头可用）。

本视图继承通用图表骨架 :class:`~prismath.ui.tk.kit.chart.ChartViewBase`，并用它新增的
``ChartSpec(kind="grid")`` 画**逐帧栅格**：帧序列按时间轴播放（暂停 / 单步 / 调速由
工具箱的"动画"卡片负责），点击画布把像素反查成格子交给
:meth:`~prismath.ui.tk.kit.chart.ChartViewBase._on_cell_click` —— 于是本文件里只有声明
与四个可选钩子，没有一行 Tk 绘图代码。
"""
