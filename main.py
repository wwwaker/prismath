#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
prismath · 数学模型可视化工具箱 —— 统一入口
=============================================

用法::

    python main.py                                  # 默认：桌面窗口的「模型列表」入口页
    python main.py --model percolation              # 跳过列表，直接进这个模型的窗口
    python main.py --list                           # 列出全部模型与界面后端
    python main.py --menu                           # 终端交互模式（选模型 → 选界面）
    python main.py --model percolation --ui cli --scan   # 终端里跑统计 / 扫描曲线
    python main.py --ui web                         # 网页界面（暂时弃用，需显式指定）

新增数学模型不需要修改本文件：在 ``prismath/models/`` 下新建一个包，
在其中调用 :func:`prismath.registry.register` 注册 ``ModelSpec`` 即可；
若要给模型配桌面界面，再在同一个包里加 ``views/tk.py``（见
:mod:`prismath.registry` 的模块说明）。
"""

from __future__ import annotations

import os
import sys

# Windows 控制台默认使用 GBK，切到 UTF-8 才能正常显示中文与特殊符号
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from prismath.launcher import main
except ImportError as exc:  # 通常是装错了目录或缺少包
    print(f"× 无法导入 prismath 包：{exc}", file=sys.stderr)
    print("  请在项目根目录（含 prismath/ 与 main.py 的目录）下运行本文件。", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
