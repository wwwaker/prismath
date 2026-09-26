# -*- coding: utf-8 -*-
"""边/点渗流的彩色分层舞台。"""
from typing import Dict, Optional, Tuple, Any
from PySide6.QtCore import QPointF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget
from prismath.ui.qt.stages.base import StageBase
from prismath.ui.qt.theme import MUTED, PAPER_LIGHT

class PercolationStage(StageBase):
    """边/点渗流专用画布，复用 web-demo 的分层思路并改为 Qt 绘制。

    每一层水团使用连续色相（黄 → 青 → 紫 → 红），开放边在被两端浸润后变粗并
    随层变色，因此播放时能直接看到彩色流动路径，而不是只有静态的蓝色覆盖。
    """

    originClicked = Signal(int)
    playChanged = Signal(bool)
    playback = True
    play_label = "▶ 播放浸润"
    pause_label = "⏸ 暂停浸润"
    finish_label = "⏭ 立即完成"

    def __init__(self, site: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.site = site
        self.origin_action = "spread" if site else "generate"
        self.payload: Dict[str, Any] = {}
        self.shown = 0
        self.playing = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(420)
        self.setMouseTracking(True)

    def set_payload(self, payload: Dict[str, Any]) -> None:
        self.stop()
        self.payload = payload or {}
        self.shown = 0
        self.update()

    def play(self) -> None:
        if not self.payload.get("layers"):
            return
        self.playing = not self.playing
        if self.playing:
            self._timer.start(90)
        else:
            self._timer.stop()
        self.playChanged.emit(self.playing)

    def finish(self) -> None:
        self.playing = False
        self._timer.stop()
        self.shown = len(self.payload.get("layers") or [])
        self.update()
        self.playChanged.emit(False)

    def stop(self) -> None:
        self.playing = False
        self._timer.stop()

    def _tick(self) -> None:
        layers = self.payload.get("layers") or []
        self.shown = min(len(layers), self.shown + 1)
        self.update()
        if self.shown >= len(layers):
            self.stop()
            self.playChanged.emit(False)

    def _geometry(self) -> Tuple[float, float, float]:
        rows = max(1, int(self.payload.get("rows", 1)))
        cols = max(1, int(self.payload.get("cols", 1)))
        margin = min(self.width(), self.height()) * 0.12
        cell = min((self.width() - 2 * margin) / max(1, cols - 1),
                   (self.height() - 2 * margin) / max(1, rows - 1))
        ox = (self.width() - cell * (cols - 1)) / 2
        oy = (self.height() - cell * (rows - 1)) / 2
        return cell, ox, oy

    def _point(self, index: int, cell: float, ox: float, oy: float) -> QPointF:
        cols = max(1, int(self.payload.get("cols", 1)))
        row, col = divmod(index, cols)
        # 三角网的奇数行稍微错开，保持和模型几何相同的视觉提示。
        shift = cell * 0.5 if self.payload.get("lattice") == "triangular" and row % 2 else 0.0
        return QPointF(ox + col * cell + shift, oy + row * cell)

    def _wet_layers(self) -> Dict[int, int]:
        result: Dict[int, int] = {}
        for layer, nodes in enumerate((self.payload.get("layers") or [])[:self.shown]):
            for node in nodes:
                result[int(node)] = layer
        return result

    def _open_edge(self, key: str, index: int) -> bool:
        bits = str(self.payload.get(key, ""))
        return index < len(bits) and bits[index] == "1"

    def _wet_color(self, layer: int, total: int) -> QColor:
        hue = int((42 + (layer / max(1, total - 1)) * 285) % 360)
        return QColor.fromHsv(hue, 205, 230)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), PAPER_LIGHT)
        if not self.payload:
            painter.setPen(MUTED)
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect(), Qt.AlignCenter, "等待生成网格…")
            painter.end()
            return
        cell, ox, oy = self._geometry()
        rows = max(1, int(self.payload.get("rows", 1)))
        cols = max(1, int(self.payload.get("cols", 1)))
        layers = self.payload.get("layers") or []
        wet = self._wet_layers()
        total_layers = len(layers)
        # 先画连接，再画节点，确保彩色水路清楚地跨过节点。
        edge_pen = QPen(QColor("#78908d"), max(1.0, cell * 0.08), Qt.SolidLine, Qt.RoundCap)
        blocked_pen = QPen(QColor("#c9bfb1"), max(0.8, cell * 0.045), Qt.DashLine, Qt.RoundCap)
        for row in range(rows):
            for col in range(cols - 1):
                a, b = row * cols + col, row * cols + col + 1
                open_edge = (self._site_open(a, b) if self.site
                             else self._open_edge("h", row * (cols - 1) + col))
                self._draw_connection(painter, a, b, open_edge, wet, total_layers,
                                      edge_pen, blocked_pen, cell, ox, oy)
        if self.payload.get("lattice") != "triangular":
            for row in range(rows - 1):
                for col in range(cols):
                    a, b = row * cols + col, (row + 1) * cols + col
                    open_edge = (self._site_open(a, b) if self.site
                                 else self._open_edge("v", row * cols + col))
                    self._draw_connection(painter, a, b, open_edge, wet, total_layers,
                                          edge_pen, blocked_pen, cell, ox, oy)
        if self.payload.get("lattice") == "triangular":
            for row in range(rows - 1):
                shift = row % 2
                for col in range(cols):
                    a = row * cols + col
                    left = col - 1 + shift
                    right = col + shift
                    if 0 <= left < cols:
                        b = (row + 1) * cols + left
                        open_edge = (self._site_open(a, b) if self.site
                                     else self._open_edge("dl", row * cols + col))
                        self._draw_connection(painter, a, b, open_edge, wet, total_layers,
                                              edge_pen, blocked_pen, cell, ox, oy)
                    if 0 <= right < cols:
                        b = (row + 1) * cols + right
                        open_edge = (self._site_open(a, b) if self.site
                                     else self._open_edge("dr", row * cols + col))
                        self._draw_connection(painter, a, b, open_edge, wet, total_layers,
                                              edge_pen, blocked_pen, cell, ox, oy)

        radius = max(2.4, min(8.0, cell * 0.17))
        sites = str(self.payload.get("sites", ""))
        for index in range(rows * cols):
            point = self._point(index, cell, ox, oy)
            occupied = (not self.site) or (index < len(sites) and sites[index] == "1")
            if not occupied:
                continue
            if index in wet:
                fill = self._wet_color(wet[index], total_layers)
                outline = QColor("#603c56")
                radius_now = radius + 1.8
            else:
                fill = QColor("#fffdf8") if self.site else QColor("#6f9694")
                outline = QColor("#71918c")
                radius_now = radius
            painter.setBrush(fill)
            painter.setPen(QPen(outline, 1.2))
            painter.drawEllipse(point, radius_now, radius_now)

        # 顶部注水线和底部出口线，形成清晰的阅读方向。
        line_width = max(2.0, cell * 0.1)
        painter.setPen(QPen(QColor("#3e75a1"), line_width))
        painter.drawLine(QPointF(ox - 6, oy - 22), QPointF(ox + cell * (cols - 1) + 6, oy - 22))
        painter.setPen(QPen(QColor("#4c9b6d"), line_width))
        bottom = oy + cell * (rows - 1)
        painter.drawLine(QPointF(ox - 6, bottom + 22), QPointF(ox + cell * (cols - 1) + 6, bottom + 22))
        painter.setPen(MUTED)
        painter.setFont(QFont("Segoe UI", 10))
        text = "播放中 · 彩色浸润层 {}/{}".format(min(self.shown, total_layers), total_layers)
        if self.payload:
            text += "   " + ("已贯通" if self.payload.get("success") else "尚未贯通")
        painter.drawText(18, 24, text)
        painter.end()

    def _draw_connection(self, painter: QPainter, a: int, b: int, open_edge: bool,
                         wet: Dict[int, int], total_layers: int, edge_pen: QPen,
                         blocked_pen: QPen, cell: float, ox: float, oy: float) -> None:
        pa, pb = self._point(a, cell, ox, oy), self._point(b, cell, ox, oy)
        if open_edge and a in wet and b in wet:
            layer = max(wet[a], wet[b])
            painter.setPen(QPen(self._wet_color(layer, total_layers), max(3.0, cell * 0.22),
                                Qt.SolidLine, Qt.RoundCap))
        else:
            painter.setPen(edge_pen if open_edge else blocked_pen)
        painter.drawLine(pa, pb)

    def _site_open(self, a: int, b: int) -> bool:
        sites = str(self.payload.get("sites", ""))
        return (a < len(sites) and b < len(sites)
                and sites[a] == "1" and sites[b] == "1")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or not self.payload:
            return
        cell, ox, oy = self._geometry()
        rows = max(1, int(self.payload.get("rows", 1)))
        cols = max(1, int(self.payload.get("cols", 1)))
        best, distance = -1, float("inf")
        for index in range(rows * cols):
            point = self._point(index, cell, ox, oy)
            current = (point.x() - event.position().x()) ** 2 + (point.y() - event.position().y()) ** 2
            if best < 0 or current < distance:
                best, distance = index, current
        if best >= 0 and distance <= (cell * 0.7) ** 2:
            self.originClicked.emit(best)

