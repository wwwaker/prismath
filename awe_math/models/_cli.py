# -*- coding: utf-8 -*-
"""
渗流类模型共用的命令行选项
============================

两个渗流模型（边渗流 / 点渗流）在终端里的参数完全一样，所以把 :class:`~awe_math.spec.CliOption`
声明放在这里共用；**非渗流模型不引用本文件**，而是声明自己的一套（例如蒲丰投针的
``--ratio`` / ``--throws``）。

放在 ``models`` 包根目录、以 ``_`` 开头，因此 :func:`awe_math.registry.load_models`
自动扫描模型包时会跳过它（它不是模型，只是共用词表）。

入口 :func:`awe_math.launcher.build_parser` 会把各模型声明的选项汇总成一个解析器：
同一组选项串只登记一次，所以这里声明一遍、两个模型各自引用即可。
"""

from __future__ import annotations

from typing import Tuple

from ..spec import CliOption

__all__ = ["GRID_CLI_OPTIONS"]

#: 渗流类模型（边渗流 / 点渗流）共用的命令行选项
GRID_CLI_OPTIONS: Tuple[CliOption, ...] = (
    CliOption(
        ("--p",), kind="float",
        help="概率参数：边渗流 = 流通概率、点渗流 = 占据密度；省略则用模型默认值",
    ),
    CliOption(
        # dest 显式写死：`--size` 只是兼容别名，属性名始终是 rows
        # （否则调换选项顺序会让 dest 变 size，_cli 取值就会静默落回默认值）
        ("--rows", "--size"), dest="rows", kind="int", default=40,
        help="行数（方格网时即边长），默认 40",
    ),
    CliOption(
        ("--cols",), kind="int",
        help="列数；与行数不同即为矩形网格，省略则与行数相同",
    ),
    CliOption(
        ("--lattice",), kind="choice", choices=("square", "triangular"),
        help="格子类型：square 方格网（4 邻域）/ triangular 三角网（6 邻域）",
    ),
    CliOption(
        ("--direction",), kind="choice",
        choices=("undirected", "no_up", "down_right", "down_left"),
        help="方向模式：无向 / 不允许向上 / 只允许向下向右 / 只允许向下向左",
    ),
    CliOption(
        ("--inject",), kind="choice", choices=("top", "center", "random"),
        help="注水（起始）方式：顶端整行 / 中心 / 随机单点",
    ),
    CliOption(
        ("--criterion",), kind="choice", choices=("span", "origin", "area"),
        help="成功判据：span 贯通（对应 p_c）/ origin 起点纵贯 / area 面积比例",
    ),
    CliOption(
        ("--threshold",), kind="choice", choices=("0.3", "0.5", "0.7", "0.9"),
        help="（判据 = area 时）面积比例阈值，默认 0.5",
    ),
    CliOption(
        ("--trials",), kind="int", default=1000,
        help="统计次数，默认 1000",
    ),
    CliOption(
        ("--scan",), kind="flag",
        help="扫描：渗流模型扫 p 曲线、投针模型逐级放大投针数（不开窗口）",
    ),
    CliOption(
        ("--step",), kind="float", default=0.05,
        help="p 扫描步长，默认 0.05",
    ),
    CliOption(
        ("--directed",), kind="flag",
        help="（旧选项）等价于 --direction no_up",
    ),
)
