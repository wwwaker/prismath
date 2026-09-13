# -*- coding: utf-8 -*-
"""
awe_math —— 数学模型可视化工具箱
==================================

设计目标
--------
1. **统一入口**：``python main.py`` 打开门户，先选择数学模型，再进入对应界面。
2. **模型可插拔**：新增一个数学模型 = 在 ``awe_math/models/`` 下新建一个包，
   用 :func:`awe_math.registry.register` 注册 :class:`~awe_math.spec.ModelSpec`，
   门户会自动出现该模型的卡片，无需改动入口代码。
3. **界面可更换**：同一模型可挂载不同 UI 后端（现代网页界面 / 桌面窗口 / 终端），
   模型只负责计算与数据结构，不关心渲染方式。

目录结构::

    main.py                     统一入口
    awe_math/
        spec.py                 模型元数据规范（参数、动作、视图）
        registry.py             模型注册表
        launcher.py             门户：选模型 → 选界面
        models/                 各数学模型的实现
            percolation/        方格网渗流模型
        ui/                     界面后端
            web/                现代网页界面（Canvas + HTTP，标准库实现）
            tk/                 桌面窗口（Tkinter）
"""

__version__ = "2.0.0"
__all__ = ["__version__"]
