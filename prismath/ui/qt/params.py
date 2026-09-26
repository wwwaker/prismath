# -*- coding: utf-8 -*-
"""从 ModelSpec 生成参数控件；不包含任何模型专用判断。"""
from collections import defaultdict
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QSpinBox, QToolButton, QVBoxLayout, QWidget
from ...spec import ModelSpec, ParamSpec
from .widgets import CollapsibleBox
class ParamEditor(QWidget):
    """从 ParamSpec 自动生成基础控件和二次折叠的高级控件。"""

    changed = Signal()

    def __init__(self, spec: ModelSpec, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.spec = spec
        self.widgets: Dict[str, QWidget] = {}
        self._groups: Dict[str, QVBoxLayout] = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        groups: Dict[str, List[ParamSpec]] = defaultdict(list)
        for param in spec.params:
            groups[param.group].append(param)
        for group_name, params in groups.items():
            advanced = group_name in {"高级选项", "批量统计", "曲线扫描"}
            box = CollapsibleBox(group_name, checked=not advanced)
            layout = box.body_layout
            for param in params:
                label = QLabel(param.label)
                editor = self._make_editor(param)
                self.widgets[param.key] = editor
                row = QHBoxLayout()
                row.addWidget(label)
                row.addWidget(editor, 1)
                layout.addLayout(row)
                if param.hint:
                    hint = QLabel(param.hint)
                    hint.setWordWrap(True)
                    hint.setObjectName("hint")
                    layout.addWidget(hint)
            outer.addWidget(box)
        outer.addStretch(1)

    def _make_editor(self, param: ParamSpec) -> QWidget:
        if param.kind == "choice":
            combo = QComboBox()
            combo.addItems([str(item) for item in param.choices])
            if param.default in param.choices:
                combo.setCurrentText(str(param.default))
            combo.currentTextChanged.connect(lambda _value: self.changed.emit())
            return combo
        if param.kind == "bool":
            checkbox = QToolButton(text="开启", checkable=True)
            checkbox.setChecked(bool(param.default))
            checkbox.toggled.connect(lambda _value: self.changed.emit())
            return checkbox
        if param.kind == "int":
            spin = QSpinBox()
            spin.setRange(int(param.min if param.min is not None else -2_000_000_000),
                          int(param.max if param.max is not None else 2_000_000_000))
            spin.setSingleStep(max(1, int(param.step or 1)))
            spin.setValue(int(param.default))
            spin.valueChanged.connect(lambda _value: self.changed.emit())
            return spin
        spin = QDoubleSpinBox()
        spin.setDecimals(5)
        spin.setRange(float(param.min if param.min is not None else -1e9),
                      float(param.max if param.max is not None else 1e9))
        spin.setSingleStep(float(param.step or 0.01))
        spin.setValue(float(param.default))
        spin.valueChanged.connect(lambda _value: self.changed.emit())
        return spin

    def values(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for param in self.spec.params:
            widget = self.widgets[param.key]
            if isinstance(widget, QComboBox):
                result[param.key] = widget.currentText()
            elif isinstance(widget, QSpinBox):
                result[param.key] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                result[param.key] = widget.value()
            elif isinstance(widget, QToolButton):
                result[param.key] = widget.isChecked()
        return result


