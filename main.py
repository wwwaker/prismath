#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
awe_math · 数学模型可视化工具箱 —— 统一入口
=============================================

用法::

    python main.py                                  # 门户：选择模型 → 选择界面
    python main.py --list                           # 列出全部模型与界面后端
    python main.py --model percolation --ui web     # 直接进入渗流模型的网页界面
    python main.py --model percolation --ui tk      # 用桌面窗口打开同一模型
    python main.py --model percolation --ui cli --scan

新增数学模型不需要修改本文件：在 ``awe_math/models/`` 下新建一个包，
在其中调用 :func:`awe_math.registry.register` 注册 ``ModelSpec`` 即可。
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
    from awe_math.launcher import main
except ImportError as exc:  # 通常是装错了目录或缺少包
    print(f"× 无法导入 awe_math 包：{exc}", file=sys.stderr)
    print("  请在项目根目录（含 awe_math/ 与 main.py 的目录）下运行本文件。", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
