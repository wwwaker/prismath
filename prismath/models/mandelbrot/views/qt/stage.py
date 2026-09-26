# -*- coding: utf-8 -*-
"""Mandelbrot 连续场舞台。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from prismath.ui.qt.stages.base import ResultStage

class MandelbrotStage(ResultStage):
    """Mandelbrot 的轻量 QImage 画布。"""

    def paintEvent(self, event) -> None:  # noqa: N802
        values = self.payload.get("values")
        if not values:
            return super().paintEvent(event)
        rows = int(self.payload.get("rows", 0))
        cols = int(self.payload.get("cols", 0))
        if rows <= 0 or cols <= 0:
            # JSON 数据契约中的 values 是行优先的一维数组；兼容未来传入的二维值。
            rows = len(values)
            cols = len(values[0]) if rows and isinstance(values[0], (list, tuple)) else len(values)
        if not rows or not cols:
            return super().paintEvent(event)
        image = QImage(cols, rows, QImage.Format_RGB32)
        nested = bool(values and isinstance(values[0], (list, tuple)))
        for row in range(rows):
            line = values[row] if nested else values[row * cols:(row + 1) * cols]
            for col, level in enumerate(line[:cols]):
                value = int(level)
                if value <= 0:
                    color = QColor("#17212b")
                else:
                    hue = int((value / 63.0) * 300 + 20) % 360
                    color = QColor.fromHsv(hue, 175, 235)
                image.setPixelColor(col, row, color)
        painter = QPainter(self)
        painter.drawImage(self.rect(), image)
        painter.setPen(QPen(QColor("#f8f5ed"), 1))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(18, 24, "Mandelbrot · 颜色表示逃逸速度 · 拖动与缩放可在后续迭代加入")
        painter.end()


