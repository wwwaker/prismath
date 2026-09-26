# -*- coding: utf-8 -*-
"""
prismath —— 数学模型可视化工具箱
==================================

设计目标
--------
1. **统一入口**：``python main.py`` 直接打开 Qt 桌面窗口的「模型列表」入口页，点卡片进入
   某个模型；``--model xxx`` 可跳过列表直达，``--menu`` 保留原来的终端交互选择流程。
2. **模型可插拔**：新增一个数学模型 = 在 ``prismath/models/`` 下新建一个包，用
   :func:`prismath.registry.register` 注册 :class:`~prismath.spec.ModelSpec`；入口页会
   自动出现该模型的卡片，无需改动入口代码。要给它配界面，就在同一个包里加
   ``views/tk.py``（**界面代码跟着模型走**，见 :mod:`prismath.registry` 的模块说明）。
3. **界面可更换**：同一个模型可挂载不同 UI 后端（Qt 桌面窗口 / Tk 兼容窗口 / 终端统计），
   模型只负责计算与数据结构，不关心渲染方式。项目默认不启动浏览器网页界面。

依赖：``numpy`` 是**必需**依赖（全部数值内核都用它向量化），``matplotlib`` 可选（只有曲线页
需要），tkinter 随 Python 自带。安装：``pip install -r requirements.txt``。

目录结构::

    main.py                     统一入口
    requirements.txt            依赖声明：numpy（必需）/ matplotlib（可选）
    README.md                   面向使用者：入口用法、当前模型、界面后端、扩展指南
    docs/                       架构与 UI 评审文档（面向开发者：分层 / 机制 / 风险 / 路线）
    tests/                      回归网：金样本 + 单元测试 + 微基准
    prismath/
        spec.py                 模型元数据规范（参数 / 动作 / CLI 选项 / 视图）
        registry.py             模型注册表 + 「一个模型长什么样」的目录约定
        launcher.py             入口流程：默认桌面窗口 / --menu 终端交互 / --ui 指定后端
        models/                 各数学模型（每个包自带自己的界面）
            _options.py         模型间共用的选项词表
            _geometry.py        模型间共用的格子几何
            _cli.py             渗流类模型共用的命令行选项声明
            buffon_needle/      蒲丰投针：非渗流，声明式 segments / series 图元
            life_game/          生命游戏：栅格类，grid 图元 + 时间轴播放 + 点击涂改
            n_body/             万有引力多星：连续时间动力学，自带图种 orbits
            percolation/        边渗流
            site_percolation/   点渗流（结构与边渗流对称）
    ui/                     界面后端
            qt/                 默认桌面窗口：稿纸背景 / 折叠控制台 / 渗流彩色画布
            tk/                 兼容桌面窗口：shell / portal / theme / kit
            web/                历史资源（不在入口注册）
"""

__version__ = "2.0.0"
__all__ = ["__version__"]
