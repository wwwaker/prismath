# -*- coding: utf-8 -*-
"""与模型无关的 Qt 画布与折叠控件。"""
from typing import Any, Dict, Optional
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QToolButton, QVBoxLayout, QWidget, QSizePolicy
from .theme import GRID, GRID_MAJOR, INK, MUTED, PAPER, PAPER_LIGHT
class PaperSurface(QWidget):
    """带淡色数学稿纸网格的背景。"""

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), PAPER)
        step = 24
        major = 120
        painter.setPen(QPen(GRID, 1))
        for x in range(0, self.width(), step):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            painter.drawLine(0, y, self.width(), y)
        painter.setPen(QPen(GRID_MAJOR, 1))
        for x in range(0, self.width(), major):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), major):
            painter.drawLine(0, y, self.width(), y)
        painter.end()


class CollapsibleBox(QFrame):
    """可折叠面板，参数组和高级功能都用它。"""

    toggled = Signal(bool)

    def __init__(self, title: str, *, checked: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("collapsibleBox")
        self.button = QToolButton(text=title, checkable=True, checked=checked)
        self.button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.button.clicked.connect(self._set_open)
        self.body = QWidget()
        self.body.setVisible(checked)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 4, 12, 12)
        self.body_layout.setSpacing(8)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.button)
        layout.addWidget(self.body)

    def _set_open(self, opened: bool) -> None:
        self.button.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)
        self.body.setVisible(opened)
        self.toggled.emit(opened)


class ResultStage(QWidget):
    """通用结果画布：让没有专用 Qt 画布的模型也有清晰的反馈。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.payload: Dict[str, Any] = {}
        self.setMinimumHeight(360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_payload(self, payload: Dict[str, Any]) -> None:
        self.payload = payload or {}
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), PAPER_LIGHT)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(GRID, 1))
        for x in range(0, self.width(), 24):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 24):
            painter.drawLine(0, y, self.width(), y)
        title = str(self.payload.get("view", "等待实验"))
        painter.setPen(INK)
        painter.setFont(QFont("Segoe UI", 18, QFont.DemiBold))
        painter.drawText(QRectF(28, 28, self.width() - 56, 32), title)
        painter.setFont(QFont("Segoe UI", 11))
        painter.setPen(MUTED)
        values = [(str(k), str(v)) for k, v in self.payload.items()
                  if k not in {"values", "cells", "frames", "layers", "h", "v", "dl", "dr", "sites"}]
        y = 86
        for key, value in values[:12]:
            painter.setPen(QColor("#8b6b55"))
            painter.drawText(30, y, f"{key}")
            painter.setPen(INK)
            painter.drawText(200, y, value[:90])
            y += 25
        painter.end()



