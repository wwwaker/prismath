# -*- coding: utf-8 -*-
"""运行时依赖自检
=================

本项目的数值内核全部基于 ``numpy`` 向量化（见 README 的「依赖规则」），因此 numpy 是
**必需依赖**。缺少它时，模型包会在导入期抛 ``ModuleNotFoundError`` —— 那时调用栈已经
很深（``load_models`` → 模型包 → ``import numpy``），用户看到的是 ImportError 堆栈，
而不是"我该装什么"。本模块把这件事**提前到入口**：

* :func:`missing_required`：轻量探测缺了哪些必需依赖；
* :func:`dependency_hint`：给出可直接打印的提示文本（依赖齐全时返回 ``None``）；
* :func:`exit_if_missing`：缺依赖时打印提示并以退出码 1 结束，依赖齐全时**零输出**。

为什么用 ``importlib.util.find_spec`` 探测，而不是直接 ``import numpy``
------------------------------------------------------------------------
1. 启动更快：不必真的加载 numpy（它是重型包）；
2. 语义更准：只回答"装没装"这一个问题。若 numpy 装了但二进制不兼容（版本 / ABI 问题），
   那属于 numpy 自己的报错，由它抛出原始异常比这里误报成"没装"更有助于排查。

探测本身遇到异常时按"存在"处理（fail-open），同样是为了不产生误导性结论。
"""

from __future__ import annotations

import importlib.util
import sys
from typing import List, Optional

__all__ = [
    "REQUIRED",
    "INSTALL_HINT",
    "missing_required",
    "dependency_hint",
    "exit_if_missing",
]

#: 必需依赖（必须同时出现在 ``requirements.txt`` 里）。
#: 目前只有 numpy：全部内核都靠它向量化，且不再维护"标准库回退"实现。
REQUIRED = ("numpy",)

#: 安装提示（口径与 README / requirements.txt 保持一致）
INSTALL_HINT = "pip install -r requirements.txt"


def _present(name: str) -> bool:
    """该模块是否可被导入（只做定位探测，不执行 import）。"""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        # find_spec 在「父包不存在」「sys.modules 里存在 __spec__ = None 的占位」等
        # 情形下会抛异常。此时按"存在"处理，把真正的判断交给 import 语句本身。
        return True


def missing_required() -> List[str]:
    """返回缺失的必需依赖名；依赖齐全时返回空列表。"""
    return [name for name in REQUIRED if not _present(name)]


def dependency_hint() -> Optional[str]:
    """缺必需依赖时返回一段可直接打印的提示文本；依赖齐全时返回 ``None``。"""
    missing = missing_required()
    if not missing:
        return None
    return (
        f"× 缺少必需依赖：{'、'.join(missing)}\n"
        f"  本项目的数值内核全部基于 numpy 向量化（元胞自动机演化、渗流单遍扫描、\n"
        f"  蒙特卡洛批量采样、多体积分），所以必须先安装依赖：\n"
        f"\n"
        f"      {INSTALL_HINT}\n"
        f"\n"
        f"  请在**项目根目录**（含 requirements.txt 与 main.py 的那一层）执行。"
    )


def exit_if_missing() -> None:
    """缺必需依赖时打印友好提示并 ``SystemExit(1)``；依赖齐全时什么都不做。"""
    message = dependency_hint()
    if message is not None:
        print(message, file=sys.stderr)
        raise SystemExit(1)
