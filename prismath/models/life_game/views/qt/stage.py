# -*- coding: utf-8 -*-
"""生命游戏的栅格舞台与帧播放器。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import QTimer, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from prismath.ui.qt.stages.base import StageBase
from prismath.ui.qt.theme import GRID, INK, MUTED, PAPER_LIGHT


class LifeGameStage(StageBase):
    edited = Signal(str)
    playback = True
    play_label = "▶ 播放"
    pause_label = "⏸ 暂停"
    finish_label = "⏭ 最后一代"

    def __init__(self, parent: Optional[Any] = None):
        super().__init__(parent)
        self.playing = False
        self.frame_index = 0
        self._edited_cells: Optional[str] = None
        self._painting = False
        self._paint_alive = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(420)

    def set_payload(self, payload: Dict[str, Any]) -> None:
        self.stop()
        super().set_payload(payload)
        self.frame_index = 0
        self._edited_cells = None
        self.update()

    def action_payload(self) -> Dict[str, Any]:
        return {"cells": self._edited_cells} if self._edited_cells else {}

    def play(self) -> None:
        frames = self.payload.get("frames") or []
        if len(frames) <= 1:
            return
        self.playing = not self.playing
        if self.playing:
            self._timer.start(110)
        else:
            self._timer.stop()
        self.update()

    def finish(self) -> None:
        frames = self.payload.get("frames") or []
        self.playing = False
        self._timer.stop()
        self.frame_index = max(0, len(frames) - 1)
        self.update()

    def step(self) -> None:
        frames = self.payload.get("frames") or []
        if frames:
            self.frame_index = min(len(frames) - 1, self.frame_index + 1)
            self.update()

    def stop(self) -> None:
        self.playing = False
        self._timer.stop()

    def _tick(self) -> None:
        frames = self.payload.get("frames") or []
        if not frames or self.frame_index >= len(frames) - 1:
            self.stop()
            self.update()
            return
        self.frame_index += 1
        self.update()

    def _cell_geometry(self):
        rows = max(1, int(self.payload.get("rows", 1)))
        cols = max(1, int(self.payload.get("cols", 1)))
        margin_x, margin_top, margin_bottom = 34.0, 48.0, 38.0
        cell = min((self.width() - 2 * margin_x) / cols,
                   (self.height() - margin_top - margin_bottom) / rows)
        cell = max(1.0, cell)
        board_w, board_h = cell * cols, cell * rows
        left = (self.width() - board_w) / 2.0
        top = margin_top + max(0.0, (self.height() - margin_top - margin_bottom - board_h) / 2.0)
        return rows, cols, cell, left, top

    def _paint_cell(self, event) -> None:
        rows, cols, cell, left, top = self._cell_geometry()
        x, y = event.position().x(), event.position().y()
        col, row = int((x - left) / cell), int((y - top) / cell)
        if not (0 <= row < rows and 0 <= col < cols):
            return
        frames = self.payload.get("frames") or []
        cells = list(str(frames[min(self.frame_index, len(frames) - 1)])
                     if frames else str(self.payload.get("cells", "")))
        index = row * cols + col
        if index >= len(cells):
            cells.extend("0" for _ in range(index + 1 - len(cells)))
        cells[index] = "1" if self._paint_alive else "0"
        encoded = "".join(cells[: rows * cols])
        self._edited_cells = encoded
        self.frame_index = 0
        self.payload["frames"] = [encoded]
        self.payload["cells"] = encoded
        self.payload["frameCount"] = 1
        self.payload["generation"] = 0
        self.payload["population"] = encoded.count("1")
        self.payload["census"] = [{"gen": 0, "population": encoded.count("1"),
                                   "births": 0, "deaths": 0}]
        self.payload["outcomeLabel"] = "待演化"
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or not self.payload:
            return
        rows, cols, cell, left, top = self._cell_geometry()
        x, y = event.position().x(), event.position().y()
        col, row = int((x - left) / cell), int((y - top) / cell)
        if not (0 <= row < rows and 0 <= col < cols):
            return
        frames = self.payload.get("frames") or []
        cells = str(frames[min(self.frame_index, len(frames) - 1)]) if frames else str(self.payload.get("cells", ""))
        index = row * cols + col
        self._paint_alive = not (index < len(cells) and cells[index] == "1")
        self._painting = True
        self._paint_cell(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._painting and event.buttons() & Qt.LeftButton:
            self._paint_cell(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._painting:
            self._painting = False
            if self._edited_cells:
                self.edited.emit(self._edited_cells)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), PAPER_LIGHT)
        rows = max(1, int(self.payload.get("rows", 1)))
        cols = max(1, int(self.payload.get("cols", 1)))
        frames = self.payload.get("frames") or []
        cells = str(frames[min(self.frame_index, len(frames) - 1)]) if frames else str(self.payload.get("cells", ""))
        _rows, _cols, cell, left, top = self._cell_geometry()
        board_w, board_h = cell * cols, cell * rows
        if cell >= 4.0:
            painter.setPen(QPen(GRID, 0.5))
            for row in range(rows + 1):
                y = top + row * cell
                painter.drawLine(left, y, left + board_w, y)
            for col in range(cols + 1):
                x = left + col * cell
                painter.drawLine(x, top, x, top + board_h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#367b83"))
        for index, value in enumerate(cells[:rows * cols]):
            if value != "1":
                continue
            row, col = divmod(index, cols)
            inset = min(1.5, cell * 0.12)
            painter.drawRect(QRectF(left + col * cell + inset, top + row * cell + inset,
                                    max(0.5, cell - inset * 2), max(0.5, cell - inset * 2)))
        painter.setPen(INK)
        painter.setFont(QFont("Segoe UI", 12, QFont.DemiBold))
        painter.drawText(18, 26, "生命游戏 · 栅格演化")
        census = self.payload.get("census") or []
        row = census[min(self.frame_index, len(census) - 1)] if census else {}
        generation = row.get("gen", self.payload.get("generation", 0)) if isinstance(row, dict) else self.payload.get("generation", 0)
        population = row.get("population", self.payload.get("population", 0)) if isinstance(row, dict) else self.payload.get("population", 0)
        label = str(self.payload.get("outcomeLabel", "演化中"))
        painter.setPen(MUTED)
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(18, self.height() - 17,
                         f"第 {generation} 代 · 活细胞 {population} · {label} · "
                         f"帧 {min(self.frame_index + 1, len(frames))}/{len(frames) or 1}")
        painter.end()


__all__ = ["LifeGameStage"]
