# -*- coding: utf-8 -*-
"""线性变换实验室的交互式 Tk 画布。"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Any, Mapping, Optional, Tuple

import numpy as np

from prismath.ui.tk.kit import ChartSpec, ChartViewBase, register_view


@register_view("linear_transform")
class LinearTransformView(ChartViewBase):
    ANIMATED = False
    HINTS = "拖动画布上的粉色向量    1 应用变换"
    INTRO_STATUS = "就绪：拖动粉色向量，观察矩阵如何改变它。"
    FALLBACK_ACCENT = "#7c3aed"
    EXPLAIN = ("灰色是原网格，紫色是变换后网格。i、j 是基向量；粉色箭头可以直接拖动。\n"
               "det(M) 的绝对值表示面积缩放倍数，det(M)<0 表示方向翻转。")
    RESULT_ROWS = (("预设", "modeLabel"), ("矩阵", "matrixText"), ("向量 →", "vectorText"),
                   ("行列式", "determinant"), ("面积倍数", "areaScale"), ("方向", "orientation"))
    ROW_SOURCES = {"modeLabel": "modeLabel", "matrixText": "matrixText", "vectorText": "vectorText",
                   "determinant": "determinant", "areaScale": "areaScale", "orientation": "orientation"}
    RESULT_FORMATS = {"determinant": "{:.3f}", "areaScale": "{:.3f}"}
    CHART_SPECS = {"linear-transform": ChartSpec(kind="text", title="线性变换实验室")}

    def _after_build(self) -> None:
        self.canvas.bind("<Button-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.root.after(80, lambda: self.run_action("apply") if self._alive else None)

    def _payload_with(self, x: float, y: float) -> None:
        if "vector_x" in self.param_vars:
            self.param_vars["vector_x"].set(float(x))
            self.param_vars["vector_y"].set(float(y))
        try:
            payload = self.spec.run("apply", self.current_params(), {})
        except Exception as exc:
            self.var_status.set(f"向量更新失败：{exc}")
            return
        self._redraw_payload(payload)
        self.var_status.set(f"向量 = ({x:.2f}, {y:.2f})；拖动粉色箭头继续探索。")

    def _geometry(self, payload: Mapping[str, Any]) -> Tuple[float, float, float, float, float]:
        extent = max(float(payload.get("extent") or 3.0), 1.0)
        width, height = max(self.canvas.winfo_width(), 300), max(self.canvas.winfo_height(), 240)
        left, top, right, bottom = 42.0, 26.0, 24.0, 34.0
        scale = min((width-left-right)/(2*extent), (height-top-bottom)/(2*extent))
        return extent, scale, left + (width-left-right)/2, top + (height-top-bottom)/2, top

    def _to_math(self, event_x: float, event_y: float, payload: Mapping[str, Any]) -> Tuple[float, float]:
        extent, scale, ox, oy, _ = self._geometry(payload)
        return ((event_x - ox)/scale, (oy - event_y)/scale)

    def _drag_start(self, event: tk.Event) -> None:
        if self._last:
            self._drag_move(event)

    def _drag_move(self, event: tk.Event) -> None:
        if not self._last:
            return
        x, y = self._to_math(event.x, event.y, self._last)
        extent = float(self._last.get("extent") or 3.0)
        if -extent * 1.2 <= x <= extent * 1.2 and -extent * 1.2 <= y <= extent * 1.2:
            self._payload_with(max(-4.0, min(4.0, x)), max(-4.0, min(4.0, y)))

    def _draw(self, spec: ChartSpec, payload: Mapping[str, Any], reveal: Optional[int] = None) -> None:
        self.canvas.delete("all")
        extent, scale, ox, oy, top = self._geometry(payload)
        width, height = max(self.canvas.winfo_width(), 300), max(self.canvas.winfo_height(), 240)
        matrix = np.asarray(payload.get("matrix") or np.eye(2), dtype=float)

        def screen(point):
            return ox + float(point[0]) * scale, oy - float(point[1]) * scale

        self.canvas.create_text(12, 10, anchor="nw",
                                text=f"{payload.get('modeLabel', '')} · M = "
                                     f"[[{matrix[0,0]:.2f}, {matrix[0,1]:.2f}], "
                                     f"[{matrix[1,0]:.2f}, {matrix[1,1]:.2f}]]",
                                fill="#475569", font=("Segoe UI", 10))
        self.canvas.create_line(ox, top, ox, height-28, fill="#cbd5e1")
        self.canvas.create_line(30, oy, width-20, oy, fill="#cbd5e1")
        for line in payload.get("grid") or []:
            p0, p1 = line["original"]
            q0, q1 = line["transformed"]
            a, b, c, d = (*screen(p0), *screen(p1))
            self.canvas.create_line(a, b, c, d, fill="#e2e8f0", dash=(2, 4))
            a, b, c, d = (*screen(q0), *screen(q1))
            self.canvas.create_line(a, b, c, d, fill="#ddd6fe", width=1)

        origin = screen((0, 0))
        basis = (matrix @ np.eye(2)).T
        for idx, vec in enumerate(((1.0, 0.0), (0.0, 1.0))):
            end = screen(basis[idx])
            self.canvas.create_line(*origin, *end, fill=("#2563eb", "#059669")[idx], width=3, arrow=tk.LAST)
            self.canvas.create_text(end[0]+8, end[1], text=("i'", "j'")[idx], fill=("#2563eb", "#059669")[idx])
        vec0 = screen(payload.get("vector") or (0, 0))
        vec1 = screen(payload.get("transformedVector") or (0, 0))
        self.canvas.create_line(*origin, *vec0, fill="#94a3b8", width=2, dash=(5, 3), arrow=tk.LAST)
        self.canvas.create_line(*origin, *vec1, fill="#db2777", width=4, arrow=tk.LAST)
        self.canvas.create_oval(vec1[0]-6, vec1[1]-6, vec1[0]+6, vec1[1]+6, fill="#db2777", outline="white", width=2)
        self.canvas.create_text(vec1[0]+10, vec1[1]-12, anchor="w", text="M v", fill="#be185d", font=("Segoe UI", 10, "bold"))

    def _fill_rows(self, payload: Mapping[str, Any], drawn: Optional[int] = None) -> None:
        matrix = np.asarray(payload.get("matrix") or np.eye(2), dtype=float)
        payload = dict(payload)
        payload["matrixText"] = f"[{matrix[0,0]:.2f} {matrix[0,1]:.2f}; {matrix[1,0]:.2f} {matrix[1,1]:.2f}]"
        v = payload.get("vector") or (0, 0)
        w = payload.get("transformedVector") or (0, 0)
        payload["vectorText"] = f"({v[0]:.2f}, {v[1]:.2f}) → ({w[0]:.2f}, {w[1]:.2f})"
        super()._fill_rows(payload, drawn)
