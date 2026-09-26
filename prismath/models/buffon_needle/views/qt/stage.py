# -*- coding: utf-8 -*-
"""蒲丰投针的几何画布与收敛曲线。"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from prismath.ui.qt.stages.base import StageBase
from prismath.ui.qt.theme import GRID, INK, MUTED, PAPER_LIGHT


class BuffonNeedleStage(StageBase):
    """同时支持 ``buffon-needle`` 几何结果和 ``buffon-converge`` 曲线结果。"""

    def __init__(self, parent: Optional[Any] = None):
        super().__init__(parent)
        self.setMinimumHeight(380)

    def _paper(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), PAPER_LIGHT)
        painter.setPen(QPen(GRID, 1))
        for x in range(0, self.width(), 24):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 24):
            painter.drawLine(0, y, self.width(), y)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paper(painter)
        view = str(self.payload.get("view", ""))
        if view == "buffon-needle":
            self._paint_throw(painter)
        elif view == "buffon-converge":
            self._paint_convergence(painter)
        else:
            painter.setPen(MUTED)
            painter.drawText(self.rect(), Qt.AlignCenter, "等待投针实验…")
        painter.end()

    def _plot_rect(self) -> QRectF:
        return QRectF(34, 48, max(10, self.width() - 68), max(10, self.height() - 78))

    def _paint_throw(self, painter: QPainter) -> None:
        payload = self.payload
        plot = self._plot_rect()
        width = max(1e-9, float(payload.get("width", 12.0)))
        height = max(1e-9, float(payload.get("height", 8.0)))
        sx = plot.width() / width
        sy = plot.height() / height
        def point(x: float, y: float) -> QPointF:
            return QPointF(plot.left() + x * sx, plot.bottom() - y * sy)

        gap = max(1e-9, float(payload.get("gap", 1.0)))
        painter.setPen(QPen(QColor("#78908d"), 1.5))
        line = 0.0
        while line <= height + gap * 0.5:
            p1, p2 = point(0, line), point(width, line)
            painter.drawLine(p1, p2)
            line += gap

        xs = list(payload.get("xs") or [])
        ys = list(payload.get("ys") or [])
        thetas = list(payload.get("thetas") or [])
        mask = str(payload.get("hitsMask", ""))
        length = float(payload.get("length", 0.8))
        count = min(len(xs), len(ys), len(thetas))
        # 十万根针仍能返回统计结果，但画布只抽样显示，保持交互流畅。
        stride = max(1, math.ceil(count / 2600))
        half = length / 2.0
        for index in range(0, count, stride):
            x, y, theta = float(xs[index]), float(ys[index]), float(thetas[index])
            dx, dy = half * math.cos(theta), half * math.sin(theta)
            a, b = point(x - dx, y - dy), point(x + dx, y + dy)
            hit = index < len(mask) and mask[index] == "1"
            color = QColor("#e76f51") if hit else QColor("#718096")
            painter.setPen(QPen(color, 1.8 if hit else 1.1, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(a, b)

        painter.setPen(INK)
        painter.setFont(QFont("Segoe UI", 12, QFont.DemiBold))
        painter.drawText(18, 26, "蒲丰投针 · 命中橙红，未命中灰蓝")
        painter.setFont(QFont("Segoe UI", 10))
        hit = payload.get("hits", 0)
        throws = payload.get("throws", 0)
        estimate = payload.get("piEstimate")
        estimate_text = "—" if estimate is None else f"{float(estimate):.5f}"
        details = (f"命中 {hit}/{throws}   实测 {float(payload.get('hitRate', 0.0)):.4f}   "
                   f"理论 {float(payload.get('theoryRate', 0.0)):.4f}   π ≈ {estimate_text}")
        painter.setPen(MUTED)
        painter.drawText(18, self.height() - 18, details)

    def _paint_convergence(self, painter: QPainter) -> None:
        plot = self._plot_rect()
        samples = list(self.payload.get("samples") or [])
        values = [(float(item.get("throws", 0)), item.get("estimate"))
                  for item in samples if isinstance(item, dict) and item.get("estimate") is not None]
        painter.setPen(INK)
        painter.setFont(QFont("Segoe UI", 12, QFont.DemiBold))
        painter.drawText(18, 26, "蒲丰投针 · π 估计收敛")
        painter.setPen(QPen(QColor("#ad5c34"), 1.5, Qt.DashLine))
        pi_true = float(self.payload.get("piTrue", math.pi))
        low, high = self._y_range(values, pi_true)
        def sx(value: float) -> float:
            x0 = values[0][0] if values else 0.0
            x1 = values[-1][0] if values else 1.0
            return plot.left() + (value - x0) / max(1e-9, x1 - x0) * plot.width()
        def sy(value: float) -> float:
            return plot.bottom() - (value - low) / max(1e-9, high - low) * plot.height()
        painter.drawLine(QPointF(plot.left(), sy(pi_true)), QPointF(plot.right(), sy(pi_true)))
        painter.setPen(QPen(QColor("#367b83"), 2.4, Qt.SolidLine, Qt.RoundCap))
        if len(values) >= 2:
            for before, current in zip(values, values[1:]):
                painter.drawLine(QPointF(sx(before[0]), sy(float(before[1]))),
                                 QPointF(sx(current[0]), sy(float(current[1]))))
        elif values:
            painter.drawEllipse(QPointF(sx(values[0][0]), sy(float(values[0][1]))), 3, 3)
        painter.setPen(MUTED)
        painter.setFont(QFont("Segoe UI", 10))
        final = self.payload.get("piEstimate")
        final_text = "—" if final is None else f"{float(final):.5f}"
        painter.drawText(18, self.height() - 18,
                         f"累计 {self.payload.get('totalThrows', 0)} 根 · 最终 π ≈ {final_text} · 红线为 π 真值")

    @staticmethod
    def _y_range(values, true_value: float):
        ys = [float(value) for _x, value in values] + [true_value]
        center = sum(ys) / len(ys) if ys else true_value
        span = max(max(ys) - min(ys), 0.15)
        return center - span * 0.7, center + span * 0.7


__all__ = ["BuffonNeedleStage"]
