# -*- coding: utf-8 -*-
"""万有引力多星的轨道舞台与回放播放器。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from prismath.ui.qt.stages.base import StageBase
from prismath.ui.qt.theme import GRID, INK, MUTED, PAPER_LIGHT


class NBodyStage(StageBase):
    playback = True
    play_label = "▶ 播放"
    pause_label = "⏸ 暂停"
    finish_label = "⏭ 最后一帧"

    _palette = ("#e76f51", "#f4a261", "#e9c46a", "#2a9d8f", "#457b9d",
                "#7b61a8", "#d46a9a", "#5aa897")

    def __init__(self, parent: Optional[Any] = None):
        super().__init__(parent)
        self.playing = False
        self.frame_index = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(420)

    def set_payload(self, payload: Dict[str, Any]) -> None:
        self.stop()
        super().set_payload(payload)
        self.frame_index = 0
        self.update()

    def play(self) -> None:
        frames = self._frames()
        if len(frames) <= 1:
            return
        self.playing = not self.playing
        if self.playing:
            self._timer.start(55)
        else:
            self._timer.stop()
        self.update()

    def finish(self) -> None:
        self.playing = False
        self._timer.stop()
        self.frame_index = max(0, len(self._frames()) - 1)
        self.update()

    def step(self) -> None:
        frames = self._frames()
        if frames:
            self.frame_index = min(len(frames) - 1, self.frame_index + 1)
            self.update()

    def stop(self) -> None:
        self.playing = False
        self._timer.stop()

    def _tick(self) -> None:
        frames = self._frames()
        if not frames or self.frame_index >= len(frames) - 1:
            self.stop()
            self.update()
            return
        self.frame_index += 1
        self.update()

    def _frames(self):
        frames = self.payload.get("frames") or []
        if frames:
            return frames
        current = self.payload.get("positions")
        return [current] if current else []

    def _extent(self) -> Tuple[float, float, float, float]:
        extent = self.payload.get("extent") or [-1, 1, -1, 1]
        try:
            x0, x1, y0, y1 = [float(value) for value in extent[:4]]
        except (TypeError, ValueError):
            return -1.0, 1.0, -1.0, 1.0
        if x1 <= x0:
            x0, x1 = x0 - 1, x1 + 1
        if y1 <= y0:
            y0, y1 = y0 - 1, y1 + 1
        pad_x, pad_y = (x1 - x0) * 0.08, (y1 - y0) * 0.08
        return x0 - pad_x, x1 + pad_x, y0 - pad_y, y1 + pad_y

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), PAPER_LIGHT)
        frames = self._frames()
        if not frames:
            painter.setPen(MUTED)
            painter.drawText(self.rect(), Qt.AlignCenter, "等待模拟结果…")
            painter.end()
            return
        x0, x1, y0, y1 = self._extent()
        left, top, right, bottom = 38.0, 48.0, self.width() - 28.0, self.height() - 42.0
        def map_point(x: float, y: float) -> QPointF:
            return QPointF(left + (x - x0) / (x1 - x0) * max(1.0, right - left),
                           bottom - (y - y0) / (y1 - y0) * max(1.0, bottom - top))

        painter.setPen(QPen(GRID, 1))
        for fraction in range(1, 10):
            x = left + (right - left) * fraction / 10.0
            y = top + (bottom - top) * fraction / 10.0
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
            painter.drawLine(QPointF(left, y), QPointF(right, y))

        index = min(self.frame_index, len(frames) - 1)
        current = self._decode(frames[index])
        count = max(1, int(self.payload.get("count", len(current))))
        masses = list(self.payload.get("masses") or [])
        # 轨迹尾迹：按星体抽样绘制，避免大帧数导致重绘卡顿。
        first = max(0, index - 70)
        for star in range(min(count, len(current))):
            points = []
            stride = max(1, (index - first) // 45)
            for frame in frames[first:index + 1:stride]:
                values = self._decode(frame)
                if star < len(values):
                    points.append(map_point(*values[star]))
            if len(points) >= 2:
                painter.setPen(QPen(QColor(self._palette[star % len(self._palette)]), 1.2,
                                    Qt.SolidLine, Qt.RoundCap))
                for before, after in zip(points, points[1:]):
                    painter.drawLine(before, after)

        heaviest = max([float(value) for value in masses] or [1.0])
        for star, (x, y) in enumerate(current):
            mass = float(masses[star]) if star < len(masses) else 1.0
            radius = 3.8 + 7.0 * min(1.0, max(0.0, mass / heaviest)) ** 0.35
            color = QColor(self._palette[star % len(self._palette)])
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#5b4636"), 1.0))
            painter.drawEllipse(map_point(x, y), radius, radius)

        painter.setPen(INK)
        painter.setFont(QFont("Segoe UI", 12, QFont.DemiBold))
        painter.drawText(18, 26, "万有引力 · 多星轨道")
        painter.setPen(MUTED)
        painter.setFont(QFont("Segoe UI", 10))
        status = "数值爆炸：请减小 dt 或增大 ε" if self.payload.get("blownUp") else str(self.payload.get("scenarioName", "模拟完成"))
        drift = float(self.payload.get("energyDrift", 0.0))
        painter.drawText(18, self.height() - 17,
                         f"{status} · t = {float(self.payload.get('time', 0.0)):.2f} · "
                         f"能量漂移 {drift:.2e} · 帧 {index + 1}/{len(frames)}")
        painter.end()

    @staticmethod
    def _decode(frame: Sequence[Any]):
        values = [float(value) for value in frame]
        return [(values[pos], values[pos + 1]) for pos in range(0, len(values) - 1, 2)]


__all__ = ["NBodyStage"]
