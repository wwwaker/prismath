# -*- coding: utf-8 -*-
"""
蒲丰投针模型在各界面后端下的**特化视图**。

约定（所有模型一致）：

* 文件名即界面后端的 key：``tk.py`` 对应 ``--ui tk``；
* 模块内用 ``@register_view("buffon_needle")`` 登记自己的视图类；
* **不要在模型的 ``__init__.py`` 里 import 本包**：视图会引入 tkinter 这类重型依赖，
  必须由对应后端在真正启动时按需导入（终端模式因此保持无头可用）。

与渗流模型不同，本模型的桌面视图继承的是**通用图表骨架**
:class:`~awe_math.ui.tk.kit.chart.ChartViewBase`——参数表单、动作按钮、画布、坐标轴、
逐帧动画与右侧指标行都由基类负责，这里只写 ``CHART_SPECS`` / ``RESULT_ROWS`` 这类声明。
"""
