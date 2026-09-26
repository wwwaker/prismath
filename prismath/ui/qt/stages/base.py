# -*- coding: utf-8 -*-
"""视觉舞台的最小协议和通用结果舞台。"""
from typing import Any, Dict, Optional
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget
from ..theme import GRID, GRID_MAJOR, INK, MUTED, PAPER, PAPER_LIGHT

class StageBase(QWidget):
    """所有模型舞台共享的 payload 接口。"""
    playback = False
    origin_action = ""
    # 播放控件的文字由舞台声明，页面只负责连接通用动作。
    play_label = "▶ 播放"
    pause_label = "⏸ 暂停"
    finish_label = "⏭ 完成"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.payload: Dict[str, Any] = {}
    def set_payload(self, payload: Dict[str, Any]) -> None:
        self.payload = payload or {}
        self.update()

    def action_payload(self) -> Dict[str, Any]:
        """返回舞台产生的可选动作输入（默认没有额外输入）。"""
        return {}

class ResultStage(StageBase):
    """没有专用舞台的模型使用的通用结果画布。"""
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), PAPER_LIGHT)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(GRID, 1))
        for x in range(0, self.width(), 24): painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 24): painter.drawLine(0, y, self.width(), y)
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
            painter.setPen(QColor("#8b6b55")); painter.drawText(30, y, key)
            painter.setPen(INK); painter.drawText(200, y, value[:90]); y += 25
        painter.end()
