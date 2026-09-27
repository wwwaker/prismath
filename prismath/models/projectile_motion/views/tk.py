# -*- coding: utf-8 -*-
"""抛体运动的轨迹动画 Tk 视图。"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

from prismath.ui.tk.kit import ChartSpec, ChartViewBase, register_view


@register_view("projectile_motion")
class ProjectileMotionView(ChartViewBase):
    ANIM_STEPS = 90
    SPEED_DEFAULT = 28
    HINTS = "1 发射    空格 播放 / 暂停    ⏭ 单步观察飞行"
    INTRO_STATUS = "就绪：调好角度与阻力后点击「发射！」。"
    FALLBACK_ACCENT = "#ea580c"
    EXPLAIN = ("灰色虚线：没有空气阻力时的解析轨迹。橙色：数值积分得到的实际轨迹。\n"
               "改变发射角度、初速度和阻力，比较最高点、飞行时间与射程。")
    RESULT_ROWS = (("飞行时间", "flightTime"), ("落点距离", "range"),
                   ("最高点", "maxHeight"), ("理想射程", "idealRange"),
                   ("落地速度", "impactSpeed"), ("阻力系数", "drag"))
    ROW_SOURCES = {key: key for _label, key in RESULT_ROWS}
    RESULT_FORMATS = {key: "{:.2f}" for _label, key in RESULT_ROWS}
    CHART_SPECS = {"projectile-motion": ChartSpec(kind="series", title="抛体运动 · 轨迹动画",
                                                   records="records", x_field="x", y_fields=("y",),
                                                   animate=True, limit=2000)}

    def _after_build(self) -> None:
        self.root.after(80, lambda: self.run_action("simulate") if self._alive else None)

    def _draw(self, spec: ChartSpec, payload: Mapping[str, Any], reveal: Optional[int] = None) -> None:
        self.canvas.delete("all")
        records = payload.get("records") or []
        ideal = payload.get("idealRecords") or []
        if not records:
            self._draw_message("没有可绘制的轨迹")
            return
        shown = len(records) if reveal is None else max(1, min(int(reveal), len(records)))
        all_x = [float(row.get("x", 0.0)) for row in ideal + records]
        all_y = [float(row.get("y", 0.0)) for row in ideal + records]
        xmax, ymax = max(max(all_x), 1.0), max(max(all_y), 1.0)
        width, height = max(self.canvas.winfo_width(), 320), max(self.canvas.winfo_height(), 240)
        left, top, right, bottom = 52.0, 28.0, 24.0, 44.0
        sx, sy = (width-left-right)/xmax, (height-top-bottom)/ymax
        scale = min(sx, sy)
        ox, oy = left, height-bottom
        def screen(row):
            return ox + float(row.get("x", 0.0))*scale, oy - float(row.get("y", 0.0))*scale
        self.canvas.create_line(left, oy, width-right, oy, fill="#94a3b8")
        self.canvas.create_line(left, top, left, oy, fill="#94a3b8")
        self.canvas.create_text(12, 10, anchor="nw", text=(f"v₀={payload.get('speed', 0):.1f}  "
                         f"θ={payload.get('angle', 0):.1f}°  阻力={payload.get('drag', 0):.2f}"),
                                fill="#475569", font=("Segoe UI", 10))
        ideal_points = [screen(row) for row in ideal]
        if len(ideal_points) > 1:
            self.canvas.create_line(*[v for point in ideal_points for v in point], fill="#94a3b8", width=2, dash=(5, 3))
        trail_points = [screen(row) for row in records[:shown]]
        if len(trail_points) > 1:
            self.canvas.create_line(*[v for point in trail_points for v in point], fill="#ea580c", width=3)
        current = trail_points[-1]
        self.canvas.create_oval(current[0]-5, current[1]-5, current[0]+5, current[1]+5, fill="#ea580c", outline="white", width=2)
        peak = max(records, key=lambda row: float(row.get("y", 0.0)))
        px, py = screen(peak)
        self.canvas.create_text(px+8, py-12, anchor="w", text=f"最高点 {peak.get('y', 0):.2f}", fill="#c2410c")
        self.canvas.create_text(width-right, oy+24, anchor="e", text="水平距离 x", fill="#64748b")
        self.canvas.create_text(left-10, top, anchor="e", text="高度 y", fill="#64748b")

    def _status_for(self, payload: Mapping[str, Any], values: Mapping[str, Any], partial: bool) -> Optional[str]:
        if partial:
            return f"飞行中… 已播放 {self._reveal}/{self._anim_target} 个采样点。"
        return (f"落点约 {float(payload.get('range', 0.0)):.2f} m；理想模型会落在 "
                f"{float(payload.get('idealRange', 0.0)):.2f} m。")
