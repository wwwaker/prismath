# -*- coding: utf-8 -*-
"""Hénon Map：复用表单和结果面板，局部提供笛卡尔散点与短轨道绘制。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Mapping, Optional, Tuple

import numpy as np

from prismath.ui.tk.kit import ChartSpec, ChartViewBase, register_view
from prismath.ui.tk.theme import DIM, FONT_SM


@register_view("henon_map")
class HenonMapView(ChartViewBase):
    HINTS = "1 查看相图    2 查看时间轨道    R 恢复经典参数"
    INTRO_STATUS = "正在生成经典吸引子，每个点代表一次迭代后的 (x, y)。"
    FALLBACK_ACCENT = "#0891b2"
    ANIMATED = False
    ORBIT_WINDOW = 80
    EXPLAIN = (
        "两条递推规则：\n"
        "xₙ₊₁ = 1 − a·xₙ² + yₙ\n"
        "yₙ₊₁ = b·xₙ\n\n"
        "相图：每个点代表一次状态，横轴为 x、纵轴为 y。"
        "经典参数下形成反复折叠的带状吸引子。\n\n"
        "先切换「稳定点」作对照，再恢复「经典混沌」。"
        "时间图只显示最后 80 步，用两种颜色区分 x 和 y。\n\n"
        "Lyapunov 指数按完整采样估计：正值提示初值敏感，负值提示收缩。"
        "部分参数或初值会让轨道超出计算范围。"
    )
    RESULT_ROWS = (
        ("图表", "mode"), ("非线性参数 a", "a"), ("反馈参数 b", "b"),
        ("采样点数", "samples"), ("丢弃瞬态", "discard"),
        ("Lyapunov 估计", "lyapunov"), ("计算耗时", "elapsed"),
    )
    ROW_SOURCES = {
        "samples": "sampleCount", "lyapunov": "lyapunovText", "elapsed": "elapsedMs",
    }
    RESULT_FORMATS = {"a": "{:.4f}", "b": "{:.4f}", "elapsed": "{:.1f} ms"}
    CHART_SPECS = {
        "henon-attractor": ChartSpec(kind="henon-phase", title="Hénon Map · 相平面"),
        "henon-orbit": ChartSpec(kind="henon-time", title="Hénon Map · 时间轨道"),
    }

    def _setup_state(self) -> None:
        super()._setup_state()
        self._phase_image: Optional[tk.PhotoImage] = None

    def _build_top_cards(self, parent: tk.Widget) -> None:
        card = self._card(parent, "快速体验")
        for label, stable in (("经典混沌（恢复默认）", False), ("稳定点 · 对照实验", True)):
            ttk.Button(card, text=label, command=lambda s=stable: self._preset(s)).pack(
                fill="x", pady=(0, 4))

    def _preset(self, stable: bool) -> None:
        for param in self.spec.params:
            self.param_vars[param.key].set(0.2 if stable and param.key == "a" else param.default)
            self._refresh_param_label(param.key)
        self.run_action("attractor")

    def _after_build(self) -> None:
        self._draw_message("正在生成 Hénon 吸引子…")
        self._first_job = self.root.after(80, lambda: self.run_action("attractor"))

    def run_action(self, key: str) -> None:
        if self._first_job is not None:
            self.root.after_cancel(self._first_job)
            self._first_job = None
        super().run_action(key)

    def on_key(self, key: str) -> None:
        if key.lower() == "r":
            self._preset(False)
        else:
            super().on_key(key)

    @staticmethod
    def _bounds(values: np.ndarray) -> Tuple[float, float]:
        lo, hi = float(values.min()), float(values.max())
        pad = max((hi - lo) * 0.06, 0.1)
        return lo - pad, hi + pad

    def _draw(self, spec: ChartSpec, payload: Mapping[str, Any],
              reveal: Optional[int] = None) -> None:
        self.canvas.delete("all")
        self._phase_image = None
        if payload.get("stoppedStep") is not None:
            self._draw_message(
                f"轨道在第 {payload['stoppedStep']} 步超出计算范围，已停止。\n\n"
                "部分参数和初值会产生发散轨道。\n"
                "点击左上角「经典混沌」可恢复可观察的吸引子。")
            return
        values = np.column_stack((payload["xs"], payload["ys"]))
        if not len(values):
            self._draw_message("没有可绘制的轨道。")
            return
        phase = payload["view"] == "henon-attractor"
        if phase:
            xlim, ylim = self._bounds(values[:, 0]), self._bounds(values[:, 1])
            caption = f"每个点 = 一次状态 (x, y) · 共 {len(values):,} 点"
        else:
            values = values[-self.ORBIT_WINDOW:]
            end = payload["discard"] + payload["sampleCount"]
            steps = np.arange(end - len(values) + 1, end + 1)
            xlim, ylim = (float(steps[0]), float(steps[-1])), self._bounds(values)
            caption = f"最后 {len(values)} 个连续状态 · 第 {steps[0]}–{steps[-1]} 步"
        self.canvas.create_text(16, 14, anchor="nw", text=caption, fill=DIM, font=FONT_SM)
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        left, top = 66, 74
        plot_w, plot_h = max(10, width - left - 24), max(10, height - top - 56)
        xspan, yspan = xlim[1] - xlim[0], ylim[1] - ylim[0]

        def sx(x):
            return left + (x - xlim[0]) / xspan * plot_w

        def sy(y):
            return top + (ylim[1] - y) / yspan * plot_h

        if phase:
            # 按当前画布像素直接成图，避免 2 万个独立 Tk 图元拖慢缩放。
            rgb = np.full((plot_h + 1, plot_w + 1, 3), 255, dtype=np.uint8)
            px = np.clip(np.rint(sx(values[:, 0]) - left).astype(int), 0, plot_w)
            py = np.clip(np.rint(sy(values[:, 1]) - top).astype(int), 0, plot_h)
            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                rgb[np.minimum(py + dy, plot_h), np.minimum(px + dx, plot_w)] = (8, 145, 178)
            ppm = b"P6 %d %d 255\n" % (plot_w + 1, plot_h + 1) + rgb.tobytes()
            self._phase_image = tk.PhotoImage(master=self.canvas, data=ppm, format="PPM")
            self.canvas.create_image(left, top, anchor="nw", image=self._phase_image, tags="henon-points")
        # 刻度覆盖整个数据范围；y 轴采用数学中向上增大的方向。
        for fraction in np.linspace(0.0, 1.0, 5):
            px, py = left + fraction * plot_w, top + fraction * plot_h
            self.canvas.create_line(left, py, left + plot_w, py, fill="#e2e8f0", dash=(1, 5))
            self.canvas.create_text(left - 8, py, anchor="e", font=FONT_SM, fill=DIM,
                                    text=f"{ylim[1] - fraction * yspan:.2f}")
            tick = xlim[0] + fraction * xspan
            self.canvas.create_text(px, top + plot_h + 10, anchor="n", font=FONT_SM, fill=DIM,
                                    text=f"{tick:.2f}" if phase else f"{tick:.0f}")
        self.canvas.create_rectangle(left, top, left + plot_w, top + plot_h, outline="#cbd5e1")
        self.canvas.create_text(left, top - 14, anchor="sw", text="yₙ" if phase else "状态值",
                                fill=DIM, font=FONT_SM)
        self.canvas.create_text(left + plot_w / 2, top + plot_h + 34, anchor="n",
                                text="xₙ →" if phase else "迭代步 n →", fill=DIM, font=FONT_SM)
        if not phase:
            for column, label, color in ((0, "xₙ", "#0891b2"), (1, "yₙ", "#c2410c")):
                coords = np.column_stack((sx(steps), sy(values[:, column]))).ravel().tolist()
                self.canvas.create_line(*coords, fill=color, width=1.5, tags=f"henon-series-{column}")
                for px, py in zip(coords[::2], coords[1::2]):
                    self.canvas.create_oval(px - 2, py - 2, px + 2, py + 2, fill=color, outline="")
                self.canvas.create_text(left + 80 + column * 70, top - 14, anchor="sw",
                                        text=f"● {label}", fill=color, font=FONT_SM)
        elif float(np.max(np.ptp(values, axis=0))) < 1e-7:
            # 稳定点的数千个样本重叠在一个像素上，标注它以免看起来像空图。
            x, y = values[-1]
            px, py = sx(x), sy(y)
            self.canvas.create_oval(px - 5, py - 5, px + 5, py + 5,
                                    fill="#0891b2", outline="", tags="henon-fixed-point")
            self.canvas.create_text(px, py - 14, anchor="s", font=FONT_SM, fill=DIM,
                                    text=f"收敛到固定点\n({x:.4f}, {y:.4f})")

    def _badge_for(self, payload: Mapping[str, Any],
                   values: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
        if payload.get("stoppedStep") is not None:
            return "超出计算范围 · 已停止", "bad"
        exponent = payload.get("lyapunov")
        if exponent is not None and exponent > 0.02:
            return "对初值敏感 · 混沌迹象", "no"
        if (exponent is not None and exponent < -0.02) or payload.get("lyapunovText") == "−∞":
            return "稳定收缩 · 固定点或周期", "ok"
        return "接近临界 · 可增加采样", "no"

    def _status_for(self, payload: Mapping[str, Any], values: Mapping[str, Any],
                    partial: bool) -> Optional[str]:
        if payload.get("stoppedStep") is not None:
            return "轨道超出计算范围；点击「经典混沌」恢复默认参数。"
        return "计算完成：相图观察长期结构，时间轨道观察最后 80 步；指数由完整采样估计。"
