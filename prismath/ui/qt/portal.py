# -*- coding: utf-8 -*-
"""模型目录卡片。"""
from typing import Optional, Sequence
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QFrame, QWidget
from ...spec import ModelSpec
class ModelPortal(QWidget):
    """模型目录：纵向卡片，不再用 Tk 的多列入口。"""

    opened = Signal(object)

    def __init__(self, models: Sequence[ModelSpec], parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(38, 30, 38, 38)
        title = QLabel("从一个规则开始。")
        title.setObjectName("pageTitle")
        subtitle = QLabel(f"选择一个数学模型，把参数变成纸面上的变化。共 {len(models)} 个模型。")
        subtitle.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(10)
        for index, spec in enumerate(models, 1):
            card = QFrame()
            card.setObjectName("modelCard")
            row = QHBoxLayout(card)
            row.setContentsMargins(18, 14, 16, 14)
            number = QLabel(f"{index:02d}")
            number.setObjectName("cardNumber")
            icon = QLabel(spec.icon)
            icon.setObjectName("cardIcon")
            copy = QVBoxLayout()
            name = QLabel(spec.name)
            name.setObjectName("cardName")
            detail = QLabel(f"{spec.topic} · {spec.summary}")
            detail.setWordWrap(True)
            detail.setObjectName("muted")
            copy.addWidget(name)
            copy.addWidget(detail)
            row.addWidget(number)
            row.addWidget(icon)
            row.addLayout(copy, 1)
            button = QPushButton("打开  ↗")
            button.setObjectName("accentButton")
            button.clicked.connect(lambda _checked=False, item=spec: self.opened.emit(item))
            row.addWidget(button)
            card.mousePressEvent = lambda event, item=spec: self.opened.emit(item)  # type: ignore[method-assign]
            body_layout.addWidget(card)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        note = QLabel("操作顺序：先观察舞台，再打开控制台；高级实验功能默认收起。")
        note.setObjectName("muted")
        layout.addWidget(note)
