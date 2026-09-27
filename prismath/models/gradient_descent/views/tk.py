# -*- coding: utf-8 -*-
"""梯度下降实验室的函数曲线 + 路径动画。"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from prismath.ui.tk.kit import ChartSpec, ChartViewBase, register_view


@register_view("gradient_descent")
class GradientDescentView(ChartViewBase):
    ANIM_STEPS = 80
    SPEED_DEFAULT = 36
    HINTS = "1 开始下降    空格 播放 / 暂停    ⏭ 单步看梯度"
    INTRO_STATUS = "就绪：选择函数、初始位置和学习率，观察点如何走向谷底。"
    FALLBACK_ACCENT = "#2563eb"
    EXPLAIN = ("蓝线是函数，橙色折线是优化路径，当前点旁标出梯度。\n"
               "现在可试 sin 波纹、三势阱、高阶多项式和光滑绝对值函数；"
               "学习率控制每一步的长度。")
    RESULT_ROWS = (("函数", "functionLabel"), ("当前 x", "currentX"),
                   ("函数值", "currentValue"), ("梯度", "currentGradient"),
                   ("目标位置", "minimumX"), ("学习率", "rate"))
    ROW_SOURCES = {key: key for _label, key in RESULT_ROWS}
    RESULT_FORMATS = {key: "{:.4f}" for key in ("currentX", "currentValue", "currentGradient", "minimumX", "rate")}
    CHART_SPECS = {"gradient-descent": ChartSpec(kind="series", title="梯度下降 · 一步一步走向谷底",
                                                   records="records", x_field="x", y_fields=("y",),
                                                   animate=True, limit=501)}

    def _after_build(self) -> None:
        self.root.after(80, lambda: self.run_action("run") if self._alive else None)

    def _draw(self, spec: ChartSpec, payload: Mapping[str, Any], reveal: Optional[int] = None) -> None:
        self.canvas.delete("all")
        curve, records = payload.get("curve") or [], payload.get("records") or []
        if not curve or not records:
            self._draw_message("没有可绘制的下降路径")
            return
        shown = len(records) if reveal is None else max(1, min(int(reveal), len(records)))
        xs = [float(row["x"]) for row in curve]
        ys = [float(row["y"]) for row in curve]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        pad = max((ymax-ymin)*0.1, 0.5)
        ymin, ymax = ymin-pad, ymax+pad
        width, height = max(self.canvas.winfo_width(), 320), max(self.canvas.winfo_height(), 240)
        left, top, right, bottom = 52.0, 30.0, 26.0, 44.0
        sx, sy = (width-left-right)/(xmax-xmin), (height-top-bottom)/(ymax-ymin)
        def screen(row):
            return left + (float(row["x"])-xmin)*sx, top + (ymax-float(row["y"])) * sy
        self.canvas.create_line(left, top+sy*ymax, width-right, top+sy*ymax, fill="#cbd5e1")
        self.canvas.create_text(12, 10, anchor="nw", text=(f"{payload.get('functionLabel', '')} · "
                         f"学习率 {payload.get('rate', 0):.3f}"), fill="#475569", font=("Segoe UI", 10))
        curve_points = [screen(row) for row in curve]
        self.canvas.create_line(*[v for point in curve_points for v in point], fill="#2563eb", width=2)
        trail = [screen(row) for row in records[:shown]]
        if len(trail) > 1:
            self.canvas.create_line(*[v for point in trail for v in point], fill="#f97316", width=3)
        current = trail[-1]
        self.canvas.create_oval(current[0]-5, current[1]-5, current[0]+5, current[1]+5, fill="#f97316", outline="white", width=2)
        row = records[shown-1]
        self.canvas.create_text(current[0]+10, current[1]-12, anchor="w",
                                text=f"∇f={float(row.get('gradient', 0)):.3f}", fill="#c2410c")
        self.canvas.create_text(width-right, height-18, anchor="e", text="x", fill="#64748b")
        self.canvas.create_text(left-10, top, anchor="e", text="f(x)", fill="#64748b")

    def _partial_rows(self, payload: Mapping[str, Any], drawn: int):
        records = payload.get("records") or []
        if not records:
            return None
        row = records[max(0, min(drawn-1, len(records)-1))]
        values = self._row_values(payload)
        values.update({"currentX": row.get("x"), "currentValue": row.get("y"), "currentGradient": row.get("gradient")})
        return values

    def _row_values(self, payload: Mapping[str, Any]):
        values = super()._row_values(payload)
        records = payload.get("records") or []
        if records:
            row = records[-1]
            values.update({"currentX": row.get("x"), "currentValue": row.get("y"), "currentGradient": row.get("gradient")})
        return values

    def _status_for(self, payload: Mapping[str, Any], values: Mapping[str, Any], partial: bool) -> Optional[str]:
        if partial:
            return f"第 {self._reveal} 步：x={float(values.get('currentX') or 0):.3f}，梯度={float(values.get('currentGradient') or 0):.3f}。"
        return "已完成：梯度接近 0 时，当前位置就是一个局部极小值。"
