# -*- coding: utf-8 -*-
"""
Mandelbrot 集模型在各界面后端下的**特化视图**。

约定（所有模型一致）：

* 文件名即界面后端的 key：``tk.py`` 对应 ``--ui tk``；
* 模块内用 ``@register_view("mandelbrot")`` 登记自己的视图类；
* **不要在模型的 ``__init__.py`` 里 import 本包**：视图会引入 tkinter 这类重型依赖，
  必须由对应后端在真正启动时按需导入（终端模式因此保持无头可用）。

本模型的桌面视图继承**通用图表骨架** :class:`~prismath.ui.tk.kit.chart.ChartViewBase`，
用 ``ChartSpec(kind="grid")`` 的连续场路径出图（数值 + 色带 → 图像缓冲），
并在基类的"点击反查"钩子上实现"点哪放大哪"。
"""
