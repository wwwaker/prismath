# -*- coding: utf-8 -*-
"""
桌面界面工具箱：与模型无关的共享骨架 + 视图注册表
=================================================

本包只提供「桌面界面」本身——窗口三栏布局、卡片族、画布与逐层动画、后台统计、曲线，
以及术语表 / 结果归一化等公共件。**它不认识任何具体模型**：具体模型的桌面视图放在模型
自己的包里，按约定发现：

    awe_math/models/<模型包>/views/tk.py     # 模块内 @register_view("<spec.view>")

于是「模型」是唯一需要维护的单元：新增模型 = 新增一个目录；删除模型时它的界面代码
跟着一起走；而新增界面后端时，``ui/`` 下加一套骨架即可，不必回头改模型。

为什么用约定而不是中心清单
--------------------------
* **零中心清单**：没有任何文件需要手写"模型 → 视图"的映射，也就不会"忘了登记"；
* **懒加载**：只有在桌面后端真正启动时（:func:`discover_views`）才会去 import 模型包里的
  ``views/tk.py``，因此网页服务、终端模式等无头场景**不会**被引入 tkinter / matplotlib；
* **优雅降级**：模型没写桌面视图（或该后端没有对应文件）时，外壳自动回落到
  :class:`~awe_math.ui.tk.shell.FallbackView`，模型依然可用。

本包对外的主要 API
------------------
* 视图注册：:func:`register_view`、:func:`view_for`、:func:`registered_views`
* 视图基类：:class:`~awe_math.ui.tk.kit.base.PercolationViewBase`（骨架与钩子契约）
* 公共件：:class:`~awe_math.ui.tk.kit.common.Terms`（术语表）、
  :class:`~awe_math.ui.tk.kit.common.ActiveView`（结果归一化）与共用配色常量。
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Callable, Dict, List, Optional, Type

from .base import ModelViewBase, PercolationViewBase
from .canvas import CanvasMixin
from .common import (  # noqa: F401  供模型视图直接取用
    BADGE_BAD_BG,
    BADGE_BAD_FG,
    BADGE_NO_BG,
    BADGE_NO_FG,
    BADGE_OK_BG,
    BADGE_OK_FG,
    BG_CANVAS,
    COL_SPAN_EDGE,
    COL_SPAN_FILL,
    COL_VERDICT_NO,
    COL_VERDICT_OK,
    MAX_SIZE,
    THRESHOLD_CHOICES,
    TREE_NO,
    TREE_OK,
    ActiveView,
    Terms,
)
from .controls import SidebarMixin
from .criteria import DEFAULT_CRITERIA, Criterion
from .form import ParamFormMixin, iter_param_groups
from .jobs import JobsMixin
from .protocols import (
    BatchResultLike,
    BatchRunner,
    PercolationModel,
    ScanRunner,
    SimResultLike,
    ViewContract,
)
from .results import ResultPanelMixin

__all__ = [
    # 注册表
    "register_view",
    "view_for",
    "registered_views",
    "discover_views",
    # 骨架
    "ModelViewBase",
    "PercolationViewBase",
    "CanvasMixin",
    "SidebarMixin",
    "ResultPanelMixin",
    "JobsMixin",
    "ParamFormMixin",
    "iter_param_groups",
    # 契约
    "PercolationModel",
    "SimResultLike",
    "BatchResultLike",
    "BatchRunner",
    "ScanRunner",
    "ViewContract",
    # 判据策略
    "Criterion",
    "DEFAULT_CRITERIA",
    # 公共件
    "Terms",
    "ActiveView",
    "MAX_SIZE",
    "THRESHOLD_CHOICES",
    "BG_CANVAS",
    "COL_SPAN_FILL",
    "COL_SPAN_EDGE",
    "COL_VERDICT_OK",
    "COL_VERDICT_NO",
    "BADGE_OK_BG",
    "BADGE_OK_FG",
    "BADGE_NO_BG",
    "BADGE_NO_FG",
    "BADGE_BAD_BG",
    "BADGE_BAD_FG",
    "TREE_OK",
    "TREE_NO",
    # 约定
    "VIEW_MODULE_TPL",
]

#: 模型包里桌面视图模块的路径模板（约定；文件名即界面后端的 key）
VIEW_MODULE_TPL = "awe_math.models.{package}.views.tk"

#: ``view 名 -> 视图类``，由 :func:`register_view` 在模块导入时填充
_REGISTRY: Dict[str, type] = {}
_discovered = False


def register_view(key: str) -> Callable[[Type], Type]:
    """类装饰器：把视图类登记到 ``spec.view == key`` 的模型名下。

    用法（写在 ``models/<模型>/views/tk.py`` 里）::

        @register_view("buffon_needle")
        class BuffonNeedleApp(PercolationViewBase):
            ...
    """

    def deco(cls: Type) -> Type:
        _REGISTRY[key] = cls
        return cls

    return deco


def discover_views() -> Dict[str, type]:
    """按约定导入各模型包里的桌面视图，触发注册（只做一次，且只在桌面后端启动时发生）。

    遍历 ``awe_math.models`` 下的所有模型包，尝试导入 ``<包>.views.tk``；没有这个模块
    （该模型没有桌面视图）时跳过，由外壳回落到通用视图。
    """
    global _discovered
    if _discovered:
        return dict(_REGISTRY)
    # 先置位：视图模块之间互相 import 时不会递归扫描
    _discovered = True

    models_pkg = importlib.import_module("awe_math.models")
    for module in pkgutil.iter_modules(models_pkg.__path__):
        if module.name.startswith("_"):
            continue
        try:
            importlib.import_module(VIEW_MODULE_TPL.format(package=module.name))
        except ModuleNotFoundError:
            # 该模型没有桌面视图（也可能是可选依赖缺失）——交给 FallbackView
            continue
    return dict(_REGISTRY)


def registered_views() -> Dict[str, type]:
    """所有已注册的 ``view 名 -> 视图类``（对外只读副本）。"""
    discover_views()
    return dict(_REGISTRY)


def view_for(key: Optional[str]) -> Optional[type]:
    """按 ``spec.view`` 取视图类；没有专用视图时返回 ``None``（由外壳回落）。"""
    if not key:
        return None
    discover_views()
    return _REGISTRY.get(str(key))


def view_names() -> List[str]:
    """已注册的 view 名（按名称排序，供调试与文档使用）。"""
    discover_views()
    return sorted(_REGISTRY)
