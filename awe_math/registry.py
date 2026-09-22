# -*- coding: utf-8 -*-
"""
模型注册表
===========

新增模型时只需在自己的包里调用 :func:`register`：

    from ...registry import register

    register(ModelSpec(key="xxx", ...))

:func:`load_models` 会自动导入 ``awe_math.models`` 下的所有子包，
因此新增模型无需修改任何入口代码。

一个模型的完整形态（**界面代码跟着模型走**）
-------------------------------------------
::

    awe_math/models/<模型包>/
        __init__.py        # register(ModelSpec(...))，导入本包即完成注册
        model.py           # 纯计算内核（只依赖标准库 + numpy，不要 import 界面）
        spec.py            # 参数 / 动作 / view="<渲染器名>"
        cli.py             # 可选：终端模式的入口（spec.cli）
        views/
            tk.py          # 可选：桌面视图，@register_view("<spec.view>")
            web.js/.py     # 可选：网页视图 / 该模型的静态资源

界面代码（``views/`` 下）会引入 tkinter / matplotlib 这类重型依赖，因此**不要在
``__init__.py`` 里 import 它**——各界面后端会在自己启动时按需导入。这样无头场景
（网页服务、终端模式）不会被拖进 GUI 依赖。
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, List, Optional

from .spec import ModelSpec

__all__ = ["register", "get", "find", "all_models", "load_models", "ModelNotFound"]

_MODELS: Dict[str, ModelSpec] = {}


class ModelNotFound(LookupError):
    """按名称查找模型失败。"""


def register(spec: ModelSpec) -> ModelSpec:
    """注册一个模型（同名会覆盖，便于开发时热重载）。"""
    _MODELS[spec.key] = spec
    return spec


def get(key: str) -> ModelSpec:
    """按 key 获取模型，未注册时抛出 :class:`ModelNotFound`。"""
    try:
        return _MODELS[key]
    except KeyError as exc:
        raise ModelNotFound(f"未找到模型：{key}") from exc


def find(query: str) -> ModelSpec:
    """按 key、序号（从 1 开始）或名称模糊匹配查找模型。"""
    load_models()
    text = str(query).strip()
    if text in _MODELS:
        return _MODELS[text]

    if text.isdigit():
        index = int(text) - 1
        models = all_models()
        if 0 <= index < len(models):
            return models[index]

    lowered = text.lower()
    for spec in all_models():
        if lowered in spec.key.lower() or lowered in spec.name.lower():
            return spec
    raise ModelNotFound(f"未找到模型：{query}")


def all_models() -> List[ModelSpec]:
    """返回所有已注册模型（按主题、order、名称排序，保证门户展示顺序稳定）。"""
    return sorted(_MODELS.values(), key=lambda s: (s.topic, s.order, s.name))


def load_models(force: bool = False) -> List[ModelSpec]:
    """导入 ``awe_math.models`` 下的所有子包以触发注册。"""
    if not force and _MODELS:
        return all_models()

    package = importlib.import_module("awe_math.models")
    for module in pkgutil.iter_modules(package.__path__):
        if module.name.startswith("_"):
            continue
        importlib.import_module(f"{package.__name__}.{module.name}")
    return all_models()
