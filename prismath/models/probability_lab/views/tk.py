# -*- coding: utf-8 -*-
"""概率实验室：LLN 曲线、CLT 直方图和 Galton board 的交互画布。"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Any, Mapping, Optional

import numpy as np

from prismath.ui.tk.kit import ChartSpec, ChartViewBase, register_view


@register_view("probability_lab")
class ProbabilityLabView(ChartViewBase):
    ANIM_STEPS = 110
    SPEED_DEFAULT = 24
    HINTS = "1 开始实验    空格 播放 / 暂停    ⏭ 单步观察"
    INTRO_STATUS = "就绪：选择一个概率实验，调整样本量后开始。"
    FALLBACK_ACCENT = "#0f766e"
    EXPLAIN = ("大数定理：一次实验的平均值随样本变多而靠近理论均值。\n"
               "中心极限定理：许多样本平均值组成近似钟形。\n"
               "高尔顿钉板：每次左右选择叠加后，最终高度呈二项分布。")
    RESULT_ROWS = (("实验", "experimentLabel"), ("随机变量", "distributionLabel"),
                   ("样本数", "sampleCount"), ("理论均值", "targetMean"),
                   ("当前均值", "observed"), ("与理论差", "absError"),
                   ("标准误", "standardError"))
    ROW_SOURCES = {key: key for _label, key in RESULT_ROWS}
    RESULT_FORMATS = {key: "{:.4f}" for key in ("targetMean", "observed", "absError", "standardError")}
    CHART_SPECS = {
        "probability-lln": ChartSpec(kind="series", title="大数定理 · 平均值正在收敛",
                                      records="records", x_field="step", y_fields=("value",),
                                      animate=True, limit=12000),
        "probability-clt": ChartSpec(kind="bars", title="中心极限定理 · 均值的分布",
                                      values="counts", labels="labels", animate=False),
        "probability-galton": ChartSpec(kind="bars", title="高尔顿钉板 · 二项分布从碰撞中出现",
                                         values="counts", labels="labels", animate=True, limit=5000),
    }

    def _after_build(self) -> None:
        self.root.after(80, lambda: self.run_action("run") if self._alive else None)

    def _primitive_count(self, spec: ChartSpec, payload: Mapping[str, Any]) -> int:
        # 高尔顿图的柱子只有 rows+1 根，但动画时间轴应该是一颗颗小球落下。
        if payload.get("view") == "probability-galton":
            return len(payload.get("finalBins") or [])
        return super()._primitive_count(spec, payload)

    def _draw(self, spec: ChartSpec, payload: Mapping[str, Any], reveal: Optional[int] = None) -> None:
        self.canvas.delete("all")
        view = str(payload.get("view") or "")
        if view == "probability-clt":
            self._draw_clt(payload)
        elif view == "probability-galton":
            self._draw_galton(payload, reveal)
        else:
            self._draw_lln(payload, reveal)

    def _frame(self):
        return max(self.canvas.winfo_width(), 360), max(self.canvas.winfo_height(), 260)

    def _draw_lln(self, payload: Mapping[str, Any], reveal: Optional[int]) -> None:
        records = payload.get("records") or []
        shown = len(records) if reveal is None else max(1, min(int(reveal), len(records)))
        if not records:
            self._draw_message("没有可画的采样")
            return
        values = [float(row["value"]) for row in records[:shown]]
        target = float(payload.get("targetMean") or 0.0)
        low, high = min(values + [target]), max(values + [target])
        margin = max((high-low)*0.18, 0.08)
        low, high = low-margin, high+margin
        width, height = self._frame(); left, top, right, bottom = 62, 34, 24, 46
        plot_w, plot_h = width-left-right, height-top-bottom
        x_max = max(shown, 1)
        def sx(x): return left + (x / x_max) * plot_w
        def sy(y): return top + (high-y)/(high-low)*plot_h
        self.canvas.create_line(left, top, left, top+plot_h, fill="#cbd5e1")
        self.canvas.create_line(left, sy(target), width-right, sy(target), fill="#0f766e", dash=(5, 3))
        self.canvas.create_text(width-right, sy(target)-10, anchor="e", text=f"理论均值 {target:.3f}", fill="#0f766e")
        points = [(sx(i+1), sy(row["value"])) for i, row in enumerate(records[:shown])]
        if len(points) > 1:
            self.canvas.create_line(*[v for p in points for v in p], fill="#14b8a6", width=2)
        x, y = points[-1]
        self.canvas.create_oval(x-5, y-5, x+5, y+5, fill="#0f766e", outline="white", width=2)
        self.canvas.create_text(12, 10, anchor="nw", text="样本平均值 x̄ₙ", fill="#475569", font=("Segoe UI", 10))
        self.canvas.create_text(width-right, height-18, anchor="e", text=f"n = {shown}", fill="#64748b")
        self.canvas.create_text(left-8, top, anchor="e", text=f"{high:.2f}", fill="#64748b")
        self.canvas.create_text(left-8, top+plot_h, anchor="e", text=f"{low:.2f}", fill="#64748b")

    def _draw_clt(self, payload: Mapping[str, Any]) -> None:
        counts = [int(v) for v in payload.get("counts") or []]
        centers = [float(v) for v in payload.get("centers") or []]
        normal = [float(v) for v in payload.get("normal") or []]
        if not counts or not centers:
            self._draw_message("没有可画的直方图")
            return
        width, height = self._frame(); left, top, right, bottom = 60, 36, 24, 52
        plot_w, plot_h = width-left-right, height-top-bottom
        ymax = max(max(counts), 1)
        low, high = centers[0], centers[-1]
        span = max(high-low, 1e-9)
        def sx(x): return left + (x-low)/span*plot_w
        def sy(y): return top + (ymax-y)/ymax*plot_h
        slot = plot_w / max(len(counts), 1)
        for i, count in enumerate(counts):
            x0, x1 = left + i*slot+1, left+(i+1)*slot-1
            self.canvas.create_rectangle(x0, sy(count), x1, top+plot_h, fill="#5eead4", outline="#0f766e")
        normal_points = [(sx(x), sy(y)) for x, y in zip(centers, normal)]
        if len(normal_points) > 1:
            self.canvas.create_line(*[v for p in normal_points for v in p], fill="#f97316", width=3)
        mean = float(payload.get("observed") or 0.0)
        self.canvas.create_line(sx(mean), top, sx(mean), top+plot_h, fill="#0f766e", dash=(5, 3))
        self.canvas.create_text(12, 10, anchor="nw", text=(f"每个均值由 {payload.get('sampleSize', 0)} 个样本组成 · "
                         "橙色是正态近似"), fill="#475569", font=("Segoe UI", 10))
        self.canvas.create_text(left, height-18, anchor="w", text=f"{low:.2f}", fill="#64748b")
        self.canvas.create_text(width-right, height-18, anchor="e", text=f"{high:.2f}", fill="#64748b")

    def _draw_galton(self, payload: Mapping[str, Any], reveal: Optional[int]) -> None:
        """画一个可读的 Galton board，而不是把小球压成一片点云。

        画面分成三层：上方是带阴影的钉板，中间是有槽位的收集盘，下方是
        实测柱状图和二项分布期望曲线。动画时只突出最近几条路径与当前小球，
        已经落下的小球按槽位整齐堆叠，因此每个视觉元素都有明确含义。
        """
        rows = max(4, int(payload.get("rows") or 10))
        final_bins = [int(value) for value in (payload.get("finalBins") or [])]
        total = len(final_bins)
        if reveal is None:
            shown = total
        else:
            shown = max(0, min(int(reveal), total))
        shown_bins = final_bins[:shown]
        counts = np.bincount(np.asarray(shown_bins, dtype=int), minlength=rows + 1)
        expected = np.asarray(payload.get("expectedCounts") or [], dtype=float)
        if expected.size != rows + 1:
            expected = np.asarray([
                total * math.comb(rows, index) / (2.0 ** rows)
                for index in range(rows + 1)
            ], dtype=float)

        width, height = self._frame()
        center = width / 2.0
        board_top = 58.0
        histogram_top = height * 0.72
        board_bottom = histogram_top - 72.0
        peg_top = board_top + 38.0
        peg_bottom = board_bottom - 44.0
        row_step = (peg_bottom - peg_top) / max(rows - 1, 1)
        spacing = min(34.0, max(18.0, (width - 112.0) / (rows + 3.5)))
        board_half = (rows / 2.0 + 1.0) * spacing
        left_edge, right_edge = center - board_half, center + board_half
        tray_top, tray_bottom = board_bottom - 22.0, board_bottom + 35.0

        self.canvas.create_rectangle(16, 38, width - 16, histogram_top - 8,
                                     fill="#f8fafc", outline="#e2e8f0")
        self.canvas.create_text(28, 12, anchor="nw",
                                text=f"高尔顿钉板 · {rows} 层 · 已落下 {shown}/{total} 个小球",
                                fill="#334155", font=("Segoe UI", 11, "bold"))
        self.canvas.create_text(width - 28, 13, anchor="ne",
                                text="每次碰撞：向左或向右，概率各为 1/2",
                                fill="#64748b", font=("Segoe UI", 9))

        # 两侧导轨和入口，先画底色再画钉子，层次会比一堆同色圆点清楚。
        self.canvas.create_line(left_edge, board_top + 8, left_edge + spacing * 0.55,
                                peg_top, fill="#cbd5e1", width=3)
        self.canvas.create_line(right_edge, board_top + 8, right_edge - spacing * 0.55,
                                peg_top, fill="#cbd5e1", width=3)
        self.canvas.create_line(center, board_top + 4, center, peg_top - 7,
                                fill="#f97316", width=3)
        self.canvas.create_oval(center - 7, board_top - 4, center + 7, board_top + 10,
                                fill="#fb923c", outline="#c2410c", width=1)

        # 画钉板的斜向引导线，帮助读者看清每层左右分叉。
        for row in range(rows - 1):
            y0 = peg_top + row * row_step + 8
            y1 = peg_top + (row + 1) * row_step - 8
            for col in range(row + 1):
                x0 = center + (2 * col - row) * spacing / 2.0
                for direction in (-1, 1):
                    x1 = center + (2 * (col + (direction > 0)) - (row + 1)) * spacing / 2.0
                    self.canvas.create_line(x0, y0, x1, y1, fill="#e2e8f0", width=1)

        for row in range(rows):
            y = peg_top + row * row_step
            for col in range(row + 1):
                x = center + (2 * col - row) * spacing / 2.0
                self.canvas.create_oval(x - 6, y - 4, x + 7, y + 8,
                                        fill="#cbd5e1", outline="")
                self.canvas.create_oval(x - 6, y - 6, x + 6, y + 6,
                                        fill="#64748b", outline="#475569", width=1)
                self.canvas.create_oval(x - 3, y - 4, x - 1, y - 2,
                                        fill="#f8fafc", outline="")

        # 收集槽：每个落点都有边界和编号，避免柱状图与钉板混在一起。
        self.canvas.create_rectangle(left_edge + 8, tray_top, right_edge - 8, tray_bottom,
                                     fill="#ecfeff", outline="#99f6e4", width=1)
        for index in range(rows + 2):
            x = center + (index - rows / 2.0 - 0.5) * spacing
            self.canvas.create_line(x, tray_top + 4, x, tray_bottom,
                                    fill="#99f6e4", width=1)
        for index, count in enumerate(counts):
            x = center + (index - rows / 2.0) * spacing
            visible = min(int(count), 14)
            for level in range(visible):
                y = tray_bottom - 7 - level * 7
                self.canvas.create_oval(x - 3.5, y - 3.5, x + 3.5, y + 3.5,
                                        fill="#f97316", outline="#c2410c", width=1)
            if int(count) > visible:
                self.canvas.create_text(x, tray_top + 9, text=f"+{int(count) - visible}",
                                        fill="#c2410c", font=("Segoe UI", 8))
            self.canvas.create_text(x, tray_bottom + 7, text=str(index),
                                    anchor="n", fill="#64748b", font=("Segoe UI", 8))

        # 最近几条真实路径使用浅色，当前小球使用强调色；不会再把 80 条路径全部叠在一起。
        paths = [str(path) for path in (payload.get("paths") or [])]
        path_start = max(0, min(shown - 12, len(paths)))
        path_end = min(shown, len(paths))

        def path_points(path: str):
            points = [(center, board_top + 7)]
            rights = 0
            for row, choice in enumerate(path[:rows]):
                rights += 1 if choice == "R" else 0
                y = peg_top + row * row_step
                x = center + (2 * rights - (row + 1)) * spacing / 2.0
                points.append((x, y))
            final_bin = rights
            points.append((center + (final_bin - rows / 2.0) * spacing, tray_top - 4))
            return points

        for index in range(path_start, path_end):
            points = path_points(paths[index])
            coords = [coordinate for point in points for coordinate in point]
            self.canvas.create_line(*coords, fill="#fdba74", width=2,
                                    capstyle=tk.ROUND, smooth=True)
        if shown > 0 and shown <= len(paths):
            current = path_points(paths[shown - 1])
            coords = [coordinate for point in current for coordinate in point]
            self.canvas.create_line(*coords, fill="#ea580c", width=3,
                                    capstyle=tk.ROUND, smooth=True)
            bx, by = current[-1]
            self.canvas.create_oval(bx - 7, by - 7, bx + 7, by + 7,
                                    fill="#fb923c", outline="#9a3412", width=2)
            self.canvas.create_oval(bx - 3, by - 4, bx - 1, by - 2,
                                    fill="#fff7ed", outline="")

        # 底部统计：实测柱状图 + 二项分布期望线。
        chart_left, chart_right = 56.0, width - 56.0
        chart_top, chart_bottom = histogram_top + 15.0, height - 42.0
        expected_plot = expected * (shown / total) if total else expected
        scale_max = max(float(np.max(counts)) if counts.size else 0.0,
                        float(np.max(expected_plot)) if expected_plot.size else 0.0, 1.0)
        slot = (chart_right - chart_left) / max(rows + 1, 1)
        self.canvas.create_rectangle(chart_left, chart_top, chart_right, chart_bottom,
                                     fill="#ffffff", outline="#e2e8f0")
        for tick in range(1, 4):
            y = chart_bottom - (chart_bottom - chart_top) * tick / 3.0
            value = scale_max * tick / 3.0
            self.canvas.create_line(chart_left, y, chart_right, y,
                                    fill="#f1f5f9", dash=(2, 4))
            self.canvas.create_text(chart_left - 7, y, anchor="e", text=f"{value:.0f}",
                                    fill="#94a3b8", font=("Segoe UI", 8))
        for index, count in enumerate(counts):
            x0 = chart_left + index * slot + slot * 0.14
            x1 = chart_left + (index + 1) * slot - slot * 0.14
            y0 = chart_bottom - float(count) / scale_max * (chart_bottom - chart_top)
            self.canvas.create_rectangle(x0, y0, x1, chart_bottom,
                                         fill="#14b8a6", outline="#0f766e")
            self.canvas.create_text((x0 + x1) / 2.0, chart_bottom + 7,
                                    text=str(index), anchor="n", fill="#64748b",
                                    font=("Segoe UI", 8))
        expected_points = []
        for index, value in enumerate(expected_plot):
            x = chart_left + (index + 0.5) * slot
            y = chart_bottom - float(value) / scale_max * (chart_bottom - chart_top)
            expected_points.append((x, y))
        if len(expected_points) > 1:
            self.canvas.create_line(*[coordinate for point in expected_points for coordinate in point],
                                    fill="#f97316", width=2, dash=(5, 3), smooth=True)
        self.canvas.create_text(chart_left + 8, chart_top + 8, anchor="nw",
                                text="落点分布（绿） · 理论二项分布（橙色虚线）",
                                fill="#0f766e", font=("Segoe UI", 9, "bold"))

    def _row_values(self, payload: Mapping[str, Any]):
        values = super()._row_values(payload)
        if payload.get("view") == "probability-galton":
            values["targetMean"] = payload.get("targetMean", values.get("targetMean"))
        return values

    def _partial_rows(self, payload: Mapping[str, Any], drawn: int):
        values = self._row_values(payload)
        view = payload.get("view")
        if view == "probability-lln":
            records = payload.get("records") or []
            if records:
                row = records[min(max(drawn-1, 0), len(records)-1)]
                values["observed"] = row.get("value")
                values["absError"] = abs(float(row.get("value", 0.0)) - float(payload.get("targetMean", 0.0)))
                values["sampleCount"] = drawn
        elif view == "probability-galton":
            bins = list(payload.get("finalBins") or [])[:drawn]
            if bins:
                values["observed"] = float(np.mean(bins))
                values["absError"] = abs(values["observed"] - float(payload.get("targetMean", 0.0)))
                values["sampleCount"] = drawn
        return values

    def _status_for(self, payload: Mapping[str, Any], values: Mapping[str, Any], partial: bool) -> Optional[str]:
        if partial:
            return f"实验进行中：已完成 {values.get('sampleCount', 0)} 次，当前均值 {float(values.get('observed') or 0):.4f}。"
        view = payload.get("view")
        if view == "probability-clt":
            return "直方图越接近橙色钟形曲线，中心极限定理的近似越明显。"
        if view == "probability-galton":
            return "中间落点最多：许多次左右选择叠加后，二项分布自然出现。"
        return "样本平均值会逐步靠近理论均值；重新运行可用同一种子复现实验。"
