# -*- coding: utf-8 -*-
"""Fourier Epicycles 的嵌套圆、向量链和轨迹 Tk 视图。"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any, Mapping, Optional, Tuple

import numpy as np

from ..model import MAX_FRAMES
from prismath.ui.tk.kit import ChartSpec, ChartViewBase, register_view
from prismath.ui.tk.theme import DIM, FAINT, FONT_SM


@register_view("fourier_epicycles")
class FourierEpicyclesView(ChartViewBase):
    # Fourier 轨迹本身已经按用户设置的帧数采样；每个定时器 tick 只推进一帧，
    # 不再沿用通用图表的 48 步抽样（否则 36000 帧会一次跳过数百帧）。
    ANIM_STEPS = MAX_FRAMES
    SPEED_MIN = 0
    SPEED_DEFAULT = 18
    ALLOW_ZERO_ANIM_DELAY = True
    LOOP_ANIMATION = True
    MAX_TRAIL_RENDER_POINTS = 1600
    HINTS = "1 绘制旋转矢量    2 重新播放轨迹    空格 播放 / 暂停"
    INTRO_STATUS = "就绪：用一串旋转向量重绘轮廓。"
    FALLBACK_ACCENT = "#db2777"
    EXPLAIN = (
        "每个圆对应一个傅里叶系数：半径是振幅，旋转速度是频率，初始角度是相位。\n"
        "圆心从上一个向量末端开始，最后一个端点就是画笔。\n"
        "减少旋转向量数可以看清原理，增加数量会恢复更多轮廓细节。"
    )
    RESULT_ROWS: Tuple[Tuple[str, str], ...] = (
        ("曲线", "shape"), ("旋转向量", "terms"), ("轮廓采样", "samples"),
        ("动画帧数", "frames"), ("截断误差", "rmse"), ("计算耗时", "elapsed"),
    )
    ROW_SOURCES: Mapping[str, str] = {
        "shape": "shapeLabel", "terms": "terms", "samples": "samples",
        "frames": "frames", "rmse": "rmse", "elapsed": "elapsedMs",
    }
    RESULT_FORMATS: Mapping[str, str] = {
        "rmse": "{:.5f}", "elapsed": "{:.1f} ms",
    }
    CHART_SPECS = {
        "fourier-epicycle": ChartSpec(
            kind="series", title="Fourier Epicycles · 旋转矢量绘图",
            records="records", x_field="step", y_fields=("x",),
            animate=True, limit=MAX_FRAMES,
        ),
    }
    COLORS = ("#db2777", "#7c3aed", "#2563eb", "#0891b2", "#059669", "#d97706")

    def _setup_state(self) -> None:
        super()._setup_state()
        self._last_payload: Optional[Mapping[str, Any]] = None

    def _after_build(self) -> None:
        self.root.after(80, lambda: self.run_action("draw") if self._alive else None)

    def _build_extra_cards(self, parent: tk.Widget) -> None:
        card = self._card(parent, "图片轮廓")
        ttk.Button(card, text="▣ 选择图片轮廓", command=self._choose_image).pack(fill="x")
        ttk.Button(card, text="✎ 手绘轮廓", command=self._open_manual_editor).pack(
            fill="x", pady=(5, 0))
        ttk.Label(
            card,
            text="选择 PNG/JPG 后会自动切换到“图片轮廓”。优先用 OpenCV GrabCut；"
                 "没有 OpenCV 时使用 Pillow/NumPy 的主体分割回退。",
            style="CardDim.TLabel", font=FONT_SM, wraplength=252, justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def _open_manual_editor(self) -> None:
        """打开轻量手绘板，把用户拖出的有序点列送入同一套 DFT 内核。"""
        window = tk.Toplevel(self.root)
        window.title("手绘轮廓")
        window.transient(self.root)
        window.geometry("680x560")
        window.minsize(420, 360)
        window.configure(bg="#f8fafc")
        ttk.Label(window, text="按住鼠标左键沿轮廓拖动，完成后点击“使用此轮廓”。",
                  style="CardDim.TLabel").pack(anchor="w", padx=14, pady=(12, 6))
        canvas = tk.Canvas(window, bg="white", highlightthickness=1,
                           highlightbackground="#cbd5e1")
        canvas.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        points = []
        state = {"last": None}

        def begin(event):
            state["last"] = (event.x, event.y)
            points.append(state["last"])

        def move(event):
            previous = state.get("last")
            current = (event.x, event.y)
            if previous is None:
                begin(event)
                return
            if abs(current[0] - previous[0]) + abs(current[1] - previous[1]) >= 2:
                canvas.create_line(previous[0], previous[1], current[0], current[1],
                                   fill="#db2777", width=2, capstyle=tk.ROUND)
                points.append(current)
                state["last"] = current

        def clear():
            points.clear()
            state["last"] = None
            canvas.delete("all")

        def use_points():
            if len(points) < 8:
                self.var_status.set("手绘轮廓至少需要 8 个点。")
                return
            # 画布坐标转成数学坐标；analyze_points 会再次居中和归一化。
            raw = np.asarray([(x, -y) for x, y in points], dtype=float)
            window.destroy()
            self._show_manual_result(raw)

        buttons = ttk.Frame(window)
        buttons.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(buttons, text="清空", command=clear).pack(side="left")
        ttk.Button(buttons, text="使用此轮廓", command=use_points).pack(side="right")
        canvas.bind("<Button-1>", begin)
        canvas.bind("<B1-Motion>", move)

    def _show_manual_result(self, points: np.ndarray) -> None:
        from ..spec import payload_for_points
        try:
            payload = payload_for_points(points, self.current_params())
        except Exception as exc:
            self.var_status.set(f"手绘轮廓无效：{exc}")
            return
        self._render_result(payload)

    def _choose_image(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要提取轮廓的图片",
            filetypes=(("图片", "*.png *.jpg *.jpeg *.bmp *.webp"), ("所有文件", "*.*")),
        )
        if not path:
            return
        shape_var = self.param_vars.get("shape")
        image_var = self.param_vars.get("image_path")
        if shape_var is not None:
            shape_var.set("image")
        if image_var is not None:
            image_var.set(path)
        self._on_param_change("image_path")
        self.run_action("draw")

    def _primitive_count(self, spec: ChartSpec, payload: Mapping[str, Any]) -> int:
        # ChartViewBase 的内置种类没有“旋转矢量动画”，这里把每一帧轨迹当作
        # 一个可播放图元；实际绘制仍由本视图的 _draw 完成。
        if spec.kind in {"fourier-epicycle", "fourier"}:
            return len(payload.get("trajectory") or [])
        return super()._primitive_count(spec, payload)

    @staticmethod
    def _bounds(payload: Mapping[str, Any]) -> float:
        target = np.asarray(payload.get("target") or [], dtype=float)
        radius_sum = float(payload.get("radiusSum") or 0.0)
        extent = max(float(np.max(np.abs(target))) if target.size else 1.0,
                     radius_sum, 0.8)
        return extent * 1.12

    def _draw(self, spec: ChartSpec, payload: Mapping[str, Any],
              reveal: Optional[int] = None) -> None:
        self._last_payload = payload
        self.canvas.delete("all")
        target = np.asarray(payload.get("target") or [], dtype=float).reshape(-1, 2)
        trajectory = np.asarray(payload.get("trajectory") or [], dtype=float).reshape(-1, 2)
        harmonics = payload.get("harmonics") or []
        if target.size == 0 or trajectory.size == 0 or not harmonics:
            self._draw_message("没有可绘制的傅里叶轮廓。")
            return
        shown = trajectory.shape[0] if reveal is None else max(1, min(int(reveal), trajectory.shape[0]))
        current_index = shown - 1
        current_t = current_index / max(trajectory.shape[0], 1)
        extent = self._bounds(payload)
        width = max(self.canvas.winfo_width(), 260)
        height = max(self.canvas.winfo_height(), 220)
        left, right, top, bottom = 58.0, 24.0, 48.0, 52.0
        plot_w, plot_h = max(10.0, width - left - right), max(10.0, height - top - bottom)
        scale = min(plot_w, plot_h) / (2.0 * extent)
        ox, oy = left + plot_w / 2.0, top + plot_h / 2.0

        def screen(point: complex) -> Tuple[float, float]:
            return ox + point.real * scale, oy - point.imag * scale

        self.canvas.create_text(12, 12, anchor="nw",
                                text=f"{payload.get('shapeLabel', '')} · "
                                     f"{payload.get('terms', 0)} 个旋转向量 · 帧 {shown}/{trajectory.shape[0]}",
                                fill=DIM, font=FONT_SM)
        self.canvas.create_line(ox, top, ox, top + plot_h, fill="#e2e8f0", dash=(1, 5))
        self.canvas.create_line(left, oy, left + plot_w, oy, fill="#e2e8f0", dash=(1, 5))
        self.canvas.create_rectangle(left, top, left + plot_w, top + plot_h, outline="#cbd5e1")
        self.canvas.create_text(ox + plot_w / 2.0, top + plot_h + 28, anchor="n",
                                text="x", fill=FAINT, font=FONT_SM)
        self.canvas.create_text(left - 12, top + 4, anchor="e", text="y", fill=FAINT, font=FONT_SM)

        # 原始轮廓是浅灰参考线，末端已经走过的近似路径用强调色。
        target_points = [screen(complex(x, y)) for x, y in target]
        target_points.append(target_points[0])
        self.canvas.create_line(*[v for point in target_points for v in point],
                                fill="#cbd5e1", width=1, dash=(2, 3), tags="target")
        # 36000 个计算帧不必每帧都把 36000 个 Canvas 顶点重建一遍；轨迹仍按
        # 全精度计算，显示时只做像素级抽样，并强制保留当前画笔端点。
        trail = trajectory[:shown]
        if trail.shape[0] > self.MAX_TRAIL_RENDER_POINTS:
            indices = np.linspace(0, trail.shape[0] - 1,
                                  self.MAX_TRAIL_RENDER_POINTS, dtype=int)
            trail = trail[indices]
        trail_points = [screen(complex(x, y)) for x, y in trail]
        if len(trail_points) >= 2:
            self.canvas.create_line(*[v for point in trail_points for v in point],
                                    fill="#be185d", width=2, tags="trail")

        vectors = np.array([
            complex(item["real"], item["imag"])
            * np.exp(2j * np.pi * float(item["frequency"]) * current_t)
            for item in harmonics
        ])
        chain = np.concatenate(([0j], np.cumsum(vectors)))
        for index, vector in enumerate(vectors):
            start, end = screen(chain[index]), screen(chain[index + 1])
            radius = abs(vector) * scale
            if radius >= 2.0:
                self.canvas.create_oval(start[0] - radius, start[1] - radius,
                                        start[0] + radius, start[1] + radius,
                                        outline=self.COLORS[index % len(self.COLORS)],
                                        width=1, tags="epicycle")
            self.canvas.create_line(start[0], start[1], end[0], end[1],
                                    fill=self.COLORS[index % len(self.COLORS)], width=2,
                                    arrow=tk.LAST, tags="vector")
        pen = screen(complex(*trajectory[current_index]))
        self.canvas.create_oval(pen[0] - 4, pen[1] - 4, pen[0] + 4, pen[1] + 4,
                                fill="#be185d", outline="", tags="pen")

    def _badge_for(self, payload: Mapping[str, Any],
                   values: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
        error = float(payload.get("rmse") or 0.0)
        if error < 0.03:
            return "轮廓还原度高", "ok"
        if error < 0.12:
            return "低频近似 · 细节被平滑", "no"
        return "向量较少 · 可增加数量", "bad"

    def _status_for(self, payload: Mapping[str, Any], values: Mapping[str, Any],
                    partial: bool) -> Optional[str]:
        if partial:
            return "正在播放：末端画笔沿傅里叶近似轮廓移动。"
        return "灰色虚线是目标轮廓，粉色轨迹是旋转向量末端已经画过的路径。"
