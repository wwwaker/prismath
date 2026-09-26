# -*- coding: utf-8 -*-
"""
点渗流模型在各界面后端下的**特化视图**。

约定（所有模型一致）：

* 文件名即界面后端的 key：``tk.py`` 对应 ``--ui tk``，``web.py`` 对应 ``--ui web``；
* Qt 视图放在 ``qt/`` 子包中，由 ``prismath.ui.qt.stages`` 按模型 key 懒加载；
* 模块内用 ``@register_view("<spec.view>")`` 登记自己的视图类；
* **不要在模型的 ``__init__.py`` 里 import 本包**：视图会引入 tkinter / matplotlib 这类
  重型依赖，必须由对应后端在真正启动时按需导入（网页服务、终端模式因此保持无头可用）。
"""
