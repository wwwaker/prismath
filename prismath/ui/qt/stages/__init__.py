# -*- coding: utf-8 -*-
"""模型舞台注册表。

新模型可以在此包中新增舞台模块并注册 view key；页面和窗口壳不需要改动。
"""
import importlib
from typing import Callable, Dict
from ....spec import ModelSpec
from .base import ResultStage, StageBase
StageFactory = Callable[[ModelSpec], StageBase]
_FACTORIES: Dict[str, StageFactory] = {}

def register(view: str, factory: StageFactory) -> StageFactory:
    """注册一个模型 view key 对应的 Qt 舞台工厂。"""
    _FACTORIES[view] = factory
    return factory

def create_stage(spec: ModelSpec) -> StageBase:
    """按约定发现 ``models/<key>/views/qt``，再退回通用结果舞台。"""
    factory = _FACTORIES.get(spec.key) or _FACTORIES.get(spec.view)
    if factory is None:
        try:
            module = importlib.import_module(f"prismath.models.{spec.key}.views.qt")
            factory = getattr(module, "create_stage", None)
            if factory is not None:
                _FACTORIES[spec.key] = factory
        except ModuleNotFoundError as exc:
            # 只有“没有这个模型的 qt 包”才回退通用舞台；模型视图自己的依赖错误
            # 必须暴露出来，不能悄悄把专用画布降级成空白结果页。
            expected = f"prismath.models.{spec.key}.views.qt"
            if exc.name not in {expected, f"prismath.models.{spec.key}.views"}:
                raise
            factory = None
    return factory(spec) if factory else ResultStage()

__all__ = ["StageBase", "ResultStage", "register", "create_stage"]
