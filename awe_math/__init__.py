# -*- coding: utf-8 -*-
"""
awe_math —— 数学模型可视化工具箱
==================================

设计目标
--------
1. **统一入口**：``python main.py`` 直接打开桌面窗口的「模型列表」入口页，点卡片进入
   某个模型；``--model xxx`` 可跳过列表直达，``--menu`` 保留原来的终端交互选择流程。
2. **模型可插拔**：新增一个数学模型 = 在 ``awe_math/models/`` 下新建一个包，用
   :func:`awe_math.registry.register` 注册 :class:`~awe_math.spec.ModelSpec`；入口页会
   自动出现该模型的卡片，无需改动入口代码。要给它配界面，就在同一个包里加
   ``views/tk.py``（**界面代码跟着模型走**，见 :mod:`awe_math.registry` 的模块说明）。
3. **界面可更换**：同一个模型可挂载不同 UI 后端（桌面窗口 / 终端统计 / 网页），模型只
   负责计算与数据结构，不关心渲染方式。其中网页后端**暂时弃用**，仅 ``--ui web`` 可进入。

目录结构::

    main.py                     统一入口
    awe_math/
        spec.py                 模型元数据规范（参数、动作、视图）
        registry.py             模型注册表 + 「一个模型长什么样」的目录约定
        launcher.py             入口流程：默认桌面窗口 / --menu 终端交互 / --ui 指定后端
        models/                 各数学模型（每个包自带自己的界面）
            _options.py         模型间共用的选项词表
            _geometry.py        模型间共用的格子几何
            percolation/        边渗流：model.py + spec.py + views/tk.py
            site_percolation/   点渗流：同上
        ui/                     界面后端
            tk/                 桌面窗口（默认）：shell / portal（入口页）/ theme / kit（共享骨架）
            web/                现代网页界面（暂时弃用）
"""

__version__ = "2.0.0"
__all__ = ["__version__"]
