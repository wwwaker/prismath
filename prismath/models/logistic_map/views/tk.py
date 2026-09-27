# -*- coding: utf-8 -*-
"""Logistic Map 的声明式曲线 / 分岔图视图。"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

from prismath.ui.tk.kit import ChartSpec, ChartViewBase, register_view


@register_view("logistic_map")
class LogisticMapView(ChartViewBase):
    """参数和结果面板由通用骨架提供，画布只声明两种图。"""

    HINTS = "1 查看轨道（固定 r）    2 生成分岔图（总览）    空格 播放 / 暂停曲线动画"
    INTRO_STATUS = "就绪：先看分岔总览；需要研究单个 r 时再查看轨道。"
    FALLBACK_ACCENT = "#7c3aed"
    EXPLAIN = (
        "怎么玩：\n"
        "· **查看轨道**固定 r，先丢弃初值造成的瞬态，再显示 xₙ 的连续变化；首屏示例 r=3.2 是周期 2，\n"
        "· **生成分岔图**扫描 r，每个 r 保留末尾若干个状态。固定点是一条线，"
        "周期 2 / 4 会分裂成多条线，混沌区会变成一片点云；\n"
        "· Lyapunov 指数小于 0 通常表示稳定，超过 0 表示对初值敏感；\n"
        "· 增大 r 采样数和每个 r 的保留点数会让分岔图更细，也会增加计算和绘制时间。"
    )

    RESULT_ROWS: Tuple[Tuple[str, str], ...] = (
        ("图表", "mode"),
        ("控制参数", "r"),
        ("初值 x₀", "x0"),
        ("采样点数", "samples"),
        ("丢弃瞬态", "discard"),
        ("Lyapunov 指数", "lyapunov"),
        ("计算耗时", "elapsed"),
    )
    ROW_SOURCES: Mapping[str, str] = {
        "mode": "mode", "r": "rLabel", "x0": "x0", "samples": "sampleCount",
        "discard": "discard",
        "lyapunov": "lyapunov", "elapsed": "elapsedMs",
    }
    RESULT_FORMATS: Mapping[str, str] = {
        "r": "{:.4f}", "x0": "{:.4f}", "lyapunov": "{:.5f}", "elapsed": "{:.1f} ms",
    }

    CHART_SPECS = {
        "logistic-orbit": ChartSpec(
            kind="series", title="Logistic Map 轨道",
            caption="固定 r = {r:.4f} · Lyapunov = {lyapunov:.4f}",
            records="records", x_field="step", y_fields=("x",),
            x_label="迭代步 n →", y_label="xₙ", ylim=(0.0, 1.0),
            color="#7c3aed", grid_color="#cbd5e1", animate=True, limit=1200,
        ),
        "logistic-bifurcation": ChartSpec(
            kind="segments", title="Logistic Map 分岔图",
            caption="每列表示一个 r 的长期状态 · r ∈ [{rMin:.3f}, {rMax:.3f}] · {rSamples} 个 r",
            x="rs", y="xs", theta="thetas", length="length",
            # 只显示本次扫描的范围，避免默认 r_min=2.5 时左侧出现大块空白。
            xlim=None, ylim=(0.0, 1.0), grid=0.25,
            x_label="控制参数 r →", y_label="长期状态 x",
            color="#7c3aed", grid_color="#cbd5e1", limit=48_000,
        ),
    }

    def _after_build(self) -> None:
        # 首屏先展示完整结构。单个 r 的轨道仍由「查看轨道」动作负责，避免
        # 用户第一次打开就面对一张难以解释的长序列图。
        self.root.after(80, lambda: self.run_action("bifurcation") if self._alive else None)

    def _badge_for(self, payload: Mapping[str, Any],
                   values: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
        if payload.get("view") == "logistic-bifurcation":
            return ("结构总览 · 固定点 → 倍周期 → 混沌", "ok")

        exponent = values.get("lyapunov")
        if isinstance(exponent, (int, float)):
            if exponent > 0.02:
                return ("混沌区 · 对初值敏感", "bad")
            if exponent < -0.02:
                return ("稳定轨道 · 周期或固定点", "ok")
        return ("临界区域 · 对参数较敏感", "no")
