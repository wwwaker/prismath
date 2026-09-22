# -*- coding: utf-8 -*-
"""
模型元数据规范
===============

任何数学模型只需要提供一份 :class:`ModelSpec`，界面层就能自动生成控件：
参数（滑块 / 开关 / 下拉框）、动作按钮、结果视图。

模型与界面之间的两套契约（都写在同一个 ``ModelSpec`` 里，共用同一份 ``model.py``）
-------------------------------------------------------------------------------

**数据级契约**（所有后端都用，尤其是网页 / 通用视图 / 终端）：

* ``spec.params`` 描述可调参数，界面据此生成表单；
* ``spec.handler(action, params, payload) -> dict`` 负责计算，返回可 JSON 序列化的结果。

**对象级契约**（桌面后端画布 / 动画需要模型对象时用，可选）：

* ``spec.factory(params) -> model``：由（**内部取值**的）参数构造模型实例；
* ``spec.batch`` / ``spec.scan``：批量统计 / 曲线扫描函数（签名见
  :class:`~prismath.ui.tk.kit.protocols.BatchRunner`）。

桌面骨架 :class:`~prismath.ui.tk.kit.base.PercolationViewBase` 默认就用这三项来驱动模型
（``_create_model`` 走 ``factory``、``_model_functions`` 走 ``batch``/``scan``），
于是**同一份"参数 -> 模型"的胶水只写一处**，不会再在 ``handler`` 与 ``views/tk.py`` 里
各写一遍。两者当然都只调用 ``model.py`` 里的纯计算，所以逻辑本身也不会分叉。

**命令行参数同样归模型所有**（终端后端）：

* ``spec.cli_options`` 用 :class:`CliOption` 声明本模型需要的选项（名字 / 类型 / 默认值 /
  候选项 / 帮助）；入口 :func:`prismath.launcher.build_parser` 把**所有模型**的声明汇总成
  一个解析器（同一组选项串只登记一次，多模型共用的会在帮助里标注），于是非渗流模型也能
  用贴合自己语义的 ``--ratio`` / ``--throws``，不必借 ``--p`` / ``--trials`` 当别名；
* ``spec.cli`` 里用 :class:`CliArgs` 按**声明**取值（``args.rows``），不要手写
  ``getattr(args, "rows", 40)`` 这类魔法字符串 —— 声明一改，取值就会静默落回默认值。

模型的 ``view`` 字段决定前端用哪个渲染器（例如 ``"percolation"`` 会画网格动画，
未知取值则退化为“参数表单 + JSON 结果”的通用视图）。渲染器本身按**后端**组织、按
**模型**落位：共享骨架在 ``prismath/ui/<后端>/``，某个模型的渲染器写在模型自己的包里
（``prismath/models/<模型包>/views/<后端>.py``），由后端按约定懒加载——
详见 :mod:`prismath.registry` 的模块说明。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

__all__ = [
    "ParamSpec",
    "ActionSpec",
    "CliOption",
    "CliArgs",
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
class CliOption:
    """一个命令行选项的**声明**（入口据此生成 ``argparse`` 参数）。

    模型用 :attr:`ModelSpec.cli_options` 声明自己需要的命令行参数；入口
    :func:`prismath.launcher.build_parser` 会把**所有模型**声明的选项汇总进同一个解析器
    （同一组选项串只登记一次），于是**非渗流模型也能用自己的参数名**
    （例如 ``--ratio`` / ``--throws``），不必再借 ``--p`` / ``--trials`` 当别名。

    不属于当前模型的选项会被解析器接受但忽略——这是"一个入口、多个模型"的代价，
    换来的是每个模型的参数名都能贴合自己的语义。
    """

    flags: Tuple[str, ...]          # 形如 ("--rows", "--size")；dest 默认取第一个长选项
    help: str = ""
    kind: str = "str"               # str | int | float | choice | flag
    default: Any = None
    choices: Tuple[str, ...] = ()
    dest: str = ""                  # 显式指定属性名（一般不用）

    @property
    def key(self) -> str:
        """``argparse`` 命名空间里的属性名。"""
        if self.dest:
            return self.dest
        for flag in self.flags:
            if flag.startswith("--"):
                return flag[2:].replace("-", "_")
        return self.flags[0].lstrip("-").replace("-", "_")

    def to_argparse(self) -> Dict[str, Any]:
        """转成 ``add_argument`` 的关键字参数。"""
        kwargs: Dict[str, Any] = {"help": self.help}
        if self.dest:
            kwargs["dest"] = self.dest
        if self.kind == "flag":
            kwargs["action"] = "store_true"
            kwargs["default"] = bool(self.default)
            return kwargs
        if self.kind == "int":
            kwargs["type"] = int
        elif self.kind == "float":
            kwargs["type"] = float
        elif self.kind == "choice":
            kwargs["choices"] = tuple(self.choices)
        if self.default is not None:
            kwargs["default"] = self.default
        return kwargs


class CliArgs:
    """``argparse`` 解析结果 + 模型声明的 ``cli_options``：**按声明取值**。

    ``argparse`` 的属性名由选项串推导（``--rows`` → ``rows``）。若在 ``_cli`` 里手写
    ``getattr(args, "rows", 40)``，一旦声明改成 ``("--size", "--rows")``（属性名变 ``size``）
    或调换了顺序，取值会**静默**落回默认值 —— 没有任何东西会拦住它。用本封装后，"名字"与
    "默认值"都来自同一声明，声明里没有的名字会退化为普通属性访问（通常当场
    ``AttributeError``，而不是悄悄用上默认值）::

        def _cli(raw_args) -> int:
            args = CliArgs(raw_args, GRID_CLI_OPTIONS)
            rows = args.rows            # 名字 / 默认值都来自声明
    """

    __slots__ = ("_args", "_options")

    def __init__(self, args: Any, options: Sequence["CliOption"]) -> None:
        object.__setattr__(self, "_args", args)
        object.__setattr__(self, "_options", {option.key: option for option in options})

    @property
    def raw(self) -> Any:
        """底层的 ``argparse.Namespace``（要取没被模型声明的通用选项时用）。"""
        return object.__getattribute__(self, "_args")

    def __getattr__(self, name: str) -> Any:
        options = object.__getattribute__(self, "_options")
        args = object.__getattribute__(self, "_args")
        option = options.get(name)
        if option is None:                  # 未声明：按普通属性取（缺失即 AttributeError）
            return getattr(args, name)
        return getattr(args, option.key, option.default)

    def __contains__(self, name: str) -> bool:
        return name in object.__getattribute__(self, "_options")


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
    #: 终端模式的命令行选项（见 :class:`CliOption`；入口会把所有模型的声明汇总起来）
    cli_options: Tuple[CliOption, ...] = ()
    # ---- 对象级契约（可选）：桌面后端要对象 / 后台任务时用，见模块说明 ----
    #: 由（模型内部取值的）参数构造模型实例；桌面视图渲染需要模型对象时用它
    factory: Optional[Callable[[Dict[str, Any]], Any]] = None
    #: 批量统计函数（签名见 ``ui/tk/kit/protocols.BatchRunner``）
    batch: Optional[Callable[..., Any]] = None
    #: 曲线扫描函数（签名见 ``ui/tk/kit/protocols.ScanRunner``）
    scan: Optional[Callable[..., Any]] = None
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
