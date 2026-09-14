# -*- coding: utf-8 -*-
"""
模型元数据规范
===============

任何数学模型只需要提供一份 :class:`ModelSpec`，界面层就能自动生成控件：
参数（滑块 / 开关 / 下拉框）、动作按钮、结果视图。

模型与界面之间的约定只有两条：

* ``spec.params`` 描述可调参数，界面据此生成表单；
* ``spec.handler(action, params, payload) -> dict`` 负责计算，返回可 JSON 序列化的结果。

模型的 ``view`` 字段决定前端用哪个渲染器（例如 ``"percolation"`` 会画网格动画，
未知取值则退化为“参数表单 + JSON 结果”的通用视图）。渲染器本身按**后端**组织、按
**模型**落位：共享骨架在 ``awe_math/ui/<后端>/``，某个模型的渲染器写在模型自己的包里
（``awe_math/models/<模型包>/views/<后端>.py``），由后端按约定懒加载——
详见 :mod:`awe_math.registry` 的模块说明。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

__all__ = [
    "ParamSpec",
    "ActionSpec",
    "ModelSpec",
    "normalize_params",
]


@dataclass(frozen=True)
class ParamSpec:
    """一个可调参数的描述。"""

    key: str
    label: str
    kind: str = "float"            # float | int | bool | choice
    default: Any = 0.0
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    choices: Tuple[str, ...] = ()  # kind == "choice" 时的候选项（字符串）
    unit: str = ""
    hint: str = ""
    group: str = "参数"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "default": self.default,
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "choices": list(self.choices),
            "unit": self.unit,
            "hint": self.hint,
            "group": self.group,
        }


@dataclass(frozen=True)
class ActionSpec:
    """一个可执行动作的描述（界面上的按钮）。"""

    key: str
    label: str
    mode: str = "once"      # once = 一次调用返回全部结果；chunk = 分块循环、可显示进度
    kind: str = "default"   # primary | default | ghost
    hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "mode": self.mode,
            "kind": self.kind,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class ModelSpec:
    """一个数学模型的完整描述。"""

    key: str                     # 唯一标识，如 "percolation"
    name: str                    # 展示名称
    topic: str                   # 所属主题，门户按主题分组
    summary: str                 # 一句话简介（门户卡片）
    description: str = ""        # 详细说明（模型页）
    params: Tuple[ParamSpec, ...] = ()
    actions: Tuple[ActionSpec, ...] = ()
    view: str = "generic"        # 前端渲染器标识
    accent: str = "#38bdf8"      # 主题色（门户卡片与按钮）
    icon: str = "◆"
    handler: Optional[Callable[[str, Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None
    cli: Optional[Callable[[Any], int]] = None   # 终端模式的入口（可省略）
    highlights: Tuple[str, ...] = ()             # 门户卡片上的要点
    order: int = 100                             # 同主题内的展示顺序（越小越靠前）

    def to_dict(self) -> Dict[str, Any]:
        """转成可 JSON 序列化的字典（不含函数，供界面层使用）。"""
        return {
            "key": self.key,
            "name": self.name,
            "topic": self.topic,
            "summary": self.summary,
            "description": self.description,
            "params": [p.to_dict() for p in self.params],
            "actions": [a.to_dict() for a in self.actions],
            "view": self.view,
            "accent": self.accent,
            "icon": self.icon,
            "highlights": list(self.highlights),
        }

    def run(self, action: str, params: Optional[Dict[str, Any]] = None,
            payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """按规范化的参数执行动作，返回结果字典。"""
        if self.handler is None:
            raise RuntimeError(f"模型 {self.key} 未提供 handler")
        return self.handler(action, normalize_params(self, params or {}), payload or {})


def normalize_params(spec: ModelSpec, raw: Dict[str, Any]) -> Dict[str, Any]:
    """把界面传来的原始参数校正为规范类型（缺失/非法时回退到默认值）。"""
    out: Dict[str, Any] = {}
    for param in spec.params:
        value = raw.get(param.key, param.default)
        try:
            if param.kind == "int":
                value = int(float(value))
            elif param.kind == "float":
                value = float(value)
            elif param.kind == "bool":
                if isinstance(value, str):
                    value = value.strip().lower() in ("1", "true", "yes", "on", "是")
                else:
                    value = bool(value)
            elif param.kind == "choice":
                text = str(value)
                value = text if text in param.choices else str(param.default)
        except (TypeError, ValueError):
            value = param.default

        if param.kind in ("int", "float"):
            if param.min is not None:
                value = max(param.min, value)
            if param.max is not None:
                value = min(param.max, value)
            value = int(value) if param.kind == "int" else float(value)

        out[param.key] = value
    return out
