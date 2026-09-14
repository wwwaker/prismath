# -*- coding: utf-8 -*-
"""
参数表单 mixin：按 ``spec.params`` 自动生成侧栏控件
=====================================================

以前桌面侧栏是**手写**的（p 滑块、行列 Spinbox、判据/格子/方向下拉……都硬编码在代码里），
于是模型在 ``spec.params`` 里改一个取值范围，界面并不会跟着变 —— 同一份参数被写了两遍。

本 mixin 把侧栏参数区改成**由元数据驱动**：遍历 ``spec.params``，按 ``kind`` 生成对应控件，
按 ``group`` 分组成卡片，于是"新增模型"只要写 ``spec.params`` 就能在桌面上拿到一套可用的
参数表单，不必再抄一遍控件代码。

控件映射
--------
====================  ==========================================================
``kind``              控件
====================  ==========================================================
``float``             标题 + 实时数值 + 滑块（范围取 ``min``/``max``，步进取 ``step``）
``int``               标题 + 数字输入框（范围取 ``min``/``max``，步进取 ``step``）
``bool``              复选框
``choice``            只读下拉框（候选取 ``choices``）
====================  ==========================================================

任何控件变动都会回调 :meth:`ParamFormMixin._on_param_change`（子类可覆盖以做实时重绘 / 防抖）。
生成的 Tk 变量同时登记在 :attr:`param_vars`（``key -> Variable``）与
``self.var_<key>``（便于既有代码按名字直接取用）。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import ttk

from ....spec import ParamSpec
from ..theme import FONT_SM

__all__ = ["ParamFormMixin", "iter_param_groups"]


def iter_param_groups(spec) -> List[Tuple[str, List[ParamSpec]]]:
    """把 ``spec.params`` 按 ``group`` 分组（组顺序 = 首次出现顺序，组内保持声明顺序）。"""
    groups: List[Tuple[str, List[ParamSpec]]] = []
    index: Dict[str, int] = {}
    for param in getattr(spec, "params", ()) or ():
        name = param.group or "参数"
        if name not in index:
            index[name] = len(groups)
            groups.append((name, []))
        groups[index[name]][1].append(param)
    return groups


class ParamFormMixin:
    """按 ``spec.params`` 生成参数控件（与 ``SidebarMixin`` 的通用版）。"""

    #: 本 mixin 生成的 Tk 变量：``参数 key -> Variable``
    param_vars: Dict[str, tk.Variable]

    # ------------------------------------------------------------------
    # 变量与取值
    # ------------------------------------------------------------------
    @staticmethod
    def _snake(key: str) -> str:
        """``scanTrials`` -> ``scan_trials``（供 ``self.var_scan_trials`` 这种旧名字取用）。"""
        out: List[str] = []
        for ch in str(key):
            if ch.isupper():
                out.append("_")
                out.append(ch.lower())
            else:
                out.append(ch)
        return "".join(out)

    def _make_param_var(self, param: ParamSpec) -> tk.Variable:
        """按 ``kind`` 造一个初值为 ``default`` 的 Tk 变量。"""
        if param.kind == "int":
            var: tk.Variable = tk.IntVar(value=int(param.default))
        elif param.kind == "float":
            var = tk.DoubleVar(value=float(param.default))
        elif param.kind == "bool":
            var = tk.BooleanVar(value=bool(param.default))
        else:
            var = tk.StringVar(value=str(param.default))
        return var

    def param_value(self, key: str) -> Any:
        """读取某个参数的当前值（变量不存在时回退 ``None``）。"""
        var = getattr(self, "param_vars", {}).get(key)
        if var is None:
            var = getattr(self, f"var_{self._snake(key)}", None)
        if var is None:
            param = self._param_spec(key)
            return param.default if param is not None else None
        try:
            return var.get()
        except tk.TclError:
            return None

    def current_params(self) -> Dict[str, Any]:
        """把全部参数收成一个 ``dict``（可交给 ``spec.run``）。"""
        spec = getattr(self, "spec", None)
        if spec is None:
            return {}
        return {p.key: self.param_value(p.key) for p in getattr(spec, "params", ()) or ()}

    def _param_spec(self, key: str) -> Optional[ParamSpec]:
        """按 key 找到 ``spec`` 里的参数描述（找不到返回 ``None``）。"""
        spec = getattr(self, "spec", None)
        for param in getattr(spec, "params", ()) or ():
            if param.key == key:
                return param
        return None

    # ------------------------------------------------------------------
    # 供"手写侧栏"的渗流视图取用：让控件候选项 / 值域跟 ``spec.params`` 一致
    # ------------------------------------------------------------------
    def spec_choices(self, key: str, fallback: Sequence[str] = ()) -> Tuple[str, ...]:
        """取某个 ``choice`` 参数的候选项；spec 未声明时回退 ``fallback``。"""
        param = self._param_spec(key)
        if param is not None and param.choices:
            return tuple(str(c) for c in param.choices)
        return tuple(str(c) for c in fallback)

    def spec_bounds(self, key: str, low: Any, high: Any) -> Tuple[Any, Any]:
        """取某个数值参数的 ``(min, max)``；spec 未声明时回退 ``(low, high)``。"""
        param = self._param_spec(key)
        if param is None:
            return low, high
        return (low if param.min is None else param.min,
                high if param.max is None else param.max)

    # ------------------------------------------------------------------
    # 表单构建
    # ------------------------------------------------------------------
    def _build_param_cards(
        self,
        parent: tk.Misc,
        *,
        groups: Optional[Iterable[str]] = None,
        skip: Sequence[str] = (),
        show_hints: bool = False,
    ) -> None:
        """按 ``group`` 把参数渲染成一组卡片（``groups`` 非空时只渲染列出的组）。"""
        spec = getattr(self, "spec", None)
        if spec is None:
            return
        if not hasattr(self, "param_vars"):
            self.param_vars = {}

        wanted = None if groups is None else {str(g) for g in groups}
        for name, params in iter_param_groups(spec):
            if wanted is not None and name not in wanted:
                continue
            card = self._card(parent, name)
            for param in params:
                if param.key in skip:
                    continue
                self._add_param_row(card, param, show_hints=show_hints)

    def _add_param_row(self, card: tk.Misc, param: ParamSpec,
                       *, show_hints: bool = False) -> tk.Widget:
        """在卡片里加一行控件，返回值即该控件本身。"""
        var = getattr(self, "param_vars", {}).get(param.key)
        if var is None:
            var = self._make_param_var(param)
            self.param_vars = getattr(self, "param_vars", {})
            self.param_vars[param.key] = var
            # 兼容既有代码惯用的 ``self.var_<name>`` 取法
            setattr(self, f"var_{self._snake(param.key)}", var)

        if param.kind == "bool":
            widget = ttk.Checkbutton(
                card, text=param.label, variable=var, style="Card.TCheckbutton",
                command=lambda k=param.key: self._on_param_change(k),
            )
            widget.pack(anchor="w", pady=(2, 6))
        elif param.kind == "choice":
            widget = self._add_choice_row(card, param, var)
        elif param.kind == "int":
            widget = self._add_int_row(card, param, var)
        else:
            widget = self._add_float_row(card, param, var)

        if show_hints and param.hint:
            ttk.Label(card, text=param.hint, style="CardDim.TLabel",
                      font=FONT_SM, wraplength=252, justify="left").pack(
                anchor="w", pady=(0, 6))
        return widget

    # ------------------------------------------------------------------
    # 各 kind 的控件（子类可覆盖以自定义外观）
    # ------------------------------------------------------------------
    def _add_choice_row(self, card: tk.Misc, param: ParamSpec,
                        var: tk.Variable) -> ttk.Combobox:
        """下拉框：标题在上、只读下拉框占满整行（中文标签较长）。"""
        ttk.Label(card, text=param.label, style="Card.TLabel").pack(anchor="w")
        combo = ttk.Combobox(
            card, state="readonly", textvariable=var,
            values=tuple(param.choices), font=FONT_SM,
        )
        combo.pack(fill="x", pady=(2, 6))
        combo.bind("<<ComboboxSelected>>", lambda _e, k=param.key: self._on_param_change(k))
        return combo

    def _add_int_row(self, card: tk.Misc, param: ParamSpec,
                     var: tk.Variable) -> ttk.Spinbox:
        """整数输入框：标题在左、Spinbox 在右。"""
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text=param.label, style="Card.TLabel").pack(side="left")
        spin = ttk.Spinbox(
            row, width=7, textvariable=var,
            from_=0 if param.min is None else param.min,
            to=10_000_000 if param.max is None else param.max,
            increment=param.step or 1,
            command=lambda k=param.key: self._on_param_change(k),
        )
        spin.pack(side="right")
        spin.bind("<Return>", lambda _e, k=param.key: self._on_param_change(k))
        spin.bind("<FocusOut>", lambda _e, k=param.key: self._on_param_change(k))
        return spin

    def _add_float_row(self, card: tk.Misc, param: ParamSpec,
                       var: tk.Variable) -> ttk.Scale:
        """浮点滑块：标题 + 实时数值在上，滑块占满整行。"""
        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=param.label, style="Card.TLabel").pack(side="left")
        value_label = ttk.Label(head, text=self._format_param(param, var),
                                style="MonoAccent.TLabel")
        value_label.pack(side="right")
        # 记下数值标签，滑块拖动时实时刷新（子类也可取用）
        labels = getattr(self, "_param_value_labels", None)
        if labels is None:
            labels = {}
            self._param_value_labels = labels
        labels[param.key] = value_label

        scale = ttk.Scale(card, from_=0.0 if param.min is None else param.min,
                          to=1.0 if param.max is None else param.max,
                          variable=var,
                          command=lambda _v, k=param.key: self._on_param_change(k))
        scale.pack(fill="x", pady=(4, 8))
        return scale

    def _format_param(self, param: ParamSpec, var: tk.Variable) -> str:
        """浮点参数的右上角数值文本（``0.05`` 保留两位）。"""
        try:
            value = float(var.get())
        except (tk.TclError, TypeError, ValueError):
            value = float(param.default)
        step = param.step or 0.01
        digits = 0 if step >= 1 else (2 if step >= 0.01 else 3)
        return f"{value:.{digits}f}"

    def _refresh_param_label(self, key: str) -> None:
        """刷新浮点参数右上角的数值（子类调用）。"""
        param = self._param_spec(key)
        labels = getattr(self, "_param_value_labels", {})
        if param is None or key not in labels:
            return
        var = self.param_vars.get(key)
        if var is not None:
            labels[key].configure(text=self._format_param(param, var))

    # ------------------------------------------------------------------
    # 变更回调（子类覆盖）
    # ------------------------------------------------------------------
    def _on_param_change(self, key: str) -> None:
        """参数控件变动后的统一回调；默认刷新浮点数值标签，不做别的。

        子类可覆盖：``float`` 参数做防抖重绘、``int`` 参数重建结构、``choice`` 参数切换语义。
        需要"只处理自己关心的键、其余交给默认行为"时记得调用 ``super()._on_param_change(key)``。
        """
        self._refresh_param_label(key)
