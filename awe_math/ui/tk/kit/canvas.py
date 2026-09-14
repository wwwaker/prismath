# -*- coding: utf-8 -*-
"""
中央画布 mixin：底图 / 逐层动画 / 图例 / 结论
=============================================

画布的**骨架**是共用的（缩放、重绘调度、动画分帧、结论文字、点击命中、图例排版），
只有三处必须由子类实现——它们确实是画法不同：

* :meth:`CanvasMixin._draw_base`：边渗流画「全部边 + 节点」，点渗流画「邻接连线 + 占据格/空位」；
* :meth:`CanvasMixin._apply_active`：把一批单元标记为已活动，并给路径上色（描边细节不同）；
* :meth:`CanvasMixin._layer_color`：逐层的渐变色带（琥珀→红 / 紫→蓝）。

另外 :meth:`CanvasMixin._draw_finish_overlay` 是可选钩子（点渗流用它把注水点圈出来），
:meth:`CanvasMixin._hit_test` 决定「这个位置能不能被指定为注水点」（点渗流的空位不行）。

性能上做了两件事：底图与增量上色分离（动画只做 ``itemconfigure``，不整图重绘），
以及层数过多时每帧多播几层，保证动画总时长可控。
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Sequence, Tuple

from ....models._geometry import lattice_layout      # 两个模型共用的格子几何
from ..theme import BORDER, DIM, FONT_BOLD, FONT_SM, PANEL
from .common import BG_CANVAS, COL_VERDICT_NO, COL_VERDICT_OK, ActiveView

__all__ = ["CanvasMixin"]


class CanvasMixin:
    """中央画布 + 动画 + 图例 + 结论。"""

    #: 图例里圆点的描边色（子类覆盖：边渗流用节点描边、点渗流用格子描边）
    LEGEND_EDGE = "#0a0e13"
    #: 图例里线条的粗细
    LEGEND_LINE_WIDTH = 3
    #: 画布左上角配置说明的颜色
    CAPTION_COLOR = DIM
    #: 画布左下角提示的颜色
    FOOTER_COLOR = DIM

    # ==================================================================
    # 骨架
    # ==================================================================
    def _build_center(self) -> None:
        center = ttk.Frame(self.host, style="Side.TFrame")
        center.grid(row=0, column=1, sticky="nsew", pady=12)
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            center, bg=BG_CANVAS, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        self._build_legend(center).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _build_legend(self, parent: tk.Widget) -> tk.Canvas:
        """底部图例条：条目由子类的 :meth:`_legend_items` 给出。"""
        cv = tk.Canvas(
            parent, height=30, bg=PANEL, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,
        )
        x = 12
        for kind, color, text in self._legend_items():
            if kind == "line":
                cv.create_line(x, 15, x + 20, 15, fill=color, width=self.LEGEND_LINE_WIDTH)
            elif kind == "dash":
                cv.create_line(x, 15, x + 20, 15, fill=color, width=2, dash=(2, 3))
            else:
                cv.create_oval(x + 5, 10, x + 15, 20, fill=color, outline=self.LEGEND_EDGE)
            cv.create_text(x + 25, 15, text=text, anchor="w", fill=DIM, font=FONT_SM)
            x += 25 + len(text) * 13 + 16
        return cv

    def _draw_caption(self) -> None:
        """画布左上角「当前配置」与左下角操作提示（两个模型的骨架一致）。"""
        terms = self._terms
        model = self.model
        self.canvas.create_text(
            10, 8, anchor="nw", fill=self.CAPTION_COLOR, font=FONT_SM,
            text=f"{terms.caption_prefix}{model.direction_name} · {model.inject_name} · "
                 f"{self._criterion_rule()}{terms.caption_suffix}",
        )
        if terms.canvas_footer:
            self.canvas.create_text(
                10, int(self.canvas.winfo_height()) - 8, anchor="sw",
                text=terms.canvas_footer, fill=self.FOOTER_COLOR, font=FONT_SM,
            )

    # ==================================================================
    # 几何
    # ==================================================================
    def _layout_params(self) -> Tuple[float, float, float]:
        """计算画布下每个单元的屏幕坐标，返回 (单元间距, 左上偏移x, 左上偏移y)。

        方格网 / 三角网、方形 / 矩形区域共用同一套缩放逻辑，区别只在单位坐标：
        三角网的奇数行右移半格、行距 √3/2，恰好铺成等边三角形（见 ``lattice_layout``）。
        """
        model = self.model
        width = max(self.canvas.winfo_width(), 60)
        height = max(self.canvas.winfo_height(), 60)
        pad = 24
        units = lattice_layout(model.rows, model.cols, model.lattice)
        span_x = max(u[0] for u in units) or 1.0
        span_y = max(u[1] for u in units) or 1.0
        cell = min(max(width - 2 * pad, 10) / span_x, max(height - 2 * pad, 10) / span_y)
        ox = (width - cell * span_x) / 2.0
        oy = (height - cell * span_y) / 2.0
        self._node_xy = [(ox + ux * cell, oy + uy * cell) for ux, uy in units]
        return cell, ox, oy

    def _canvas_ready(self) -> bool:
        """画布是否仍然可用（视图被销毁后，挂起的回调不应继续画图）。"""
        return self._alive and bool(self.canvas.winfo_exists())

    # ==================================================================
    # 重绘
    # ==================================================================
    def _redraw_grid(self) -> None:
        """整图重绘：底图 + 当前已显示的活动层。"""
        self._redraw_job = None
        if not self._canvas_ready():
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width <= 40 or height <= 40:   # 布局尚未完成，等待 Configure 事件
            return

        self._draw_base()
        self._active_set = set()
        # 结果必须与底图一致，否则只画底图（防止切换尺寸/方向瞬间的越界渲染）
        if (
            self.result is None
            or self._shown_layers <= 0
            or self.result.shape != self.model.shape
        ):
            self._hide_verdict()
            return

        view = self._active_view()
        total = view.depth
        for i in range(min(self._shown_layers, total)):
            batch = view.layers[i]
            self._active_set.update(batch)
            self._apply_active(batch, self._layer_color(i, total))

        if self._shown_layers >= total:
            self._draw_finish_overlay()
            self._show_verdict()

    def _show_verdict(self) -> None:
        """画布底部显示结论（按当前判据给出不同的说法）。"""
        if self.result is None:
            return
        terms = self._terms
        view = self._active_view()
        ratio = view.active_ratio
        if view.criterion == "span":
            ok = view.spans
            text = (f"✔ {terms.arena}存在纵贯簇（顶行 ↔ 底行）"
                    if ok else f"✘ {terms.arena}没有纵贯簇")
            text += f"；{terms.active_phrase} {ratio:.1%}"
        elif view.criterion == "origin":
            ok = view.origin_spans
            if ok:
                text = (f"✔ 起点纵贯：{terms.origin_cluster_phrase}碰到顶行与底行"
                        f"（{terms.active_verb} {ratio:.1%}）")
            elif view.spans:
                text = (f"✘ 起点未纵贯：{terms.arena}有纵贯簇"
                        f"（{view.spanning_count} {terms.unit}，青色），"
                        f"但注水点不在簇内（{terms.active_verb} {ratio:.1%}）")
            else:
                text = (f"✘ 起点未纵贯，{terms.arena}也没有纵贯簇"
                        f"（{terms.active_verb} {ratio:.1%}）")
        else:
            ok = view.engulfed
            text = (f"✔ 面积判据达标：{terms.active_verb} {ratio:.1%}"
                    f"（≥{view.threshold:.0%}）" if ok else
                    f"✘ 面积未达标：{terms.active_verb} {ratio:.1%}"
                    f"（<{view.threshold:.0%}）")
        self.canvas.delete("verdict")
        self.canvas.create_text(
            self.canvas.winfo_width() // 2, self.canvas.winfo_height() - 8,
            anchor="s", text=text, fill=COL_VERDICT_OK if ok else COL_VERDICT_NO,
            font=FONT_BOLD, tags="verdict",
        )

    def _hide_verdict(self) -> None:
        self.canvas.delete("verdict")

    # ==================================================================
    # 生成与显示
    # ==================================================================
    def regenerate(self) -> None:
        """重新随机生成区域，并立即显示出结果（不做动画）。"""
        self._regenerate_job = None
        if not self._canvas_ready():
            return
        terms = self._terms
        self._cancel_animation()
        self._sync_model_params()
        self.model.regenerate()
        self._run_and_show()
        model = self.model
        self.var_status.set(
            f"已重新生成{terms.arena}：{model.lattice_name} {model.rows}×{model.cols}"
            f"（{model.direction_name}），p={model.p:.2f}。"
            f"按空格可播放{terms.process_verb}动画。"
        )

    def _run_and_show(self, origins: Optional[Sequence[int]] = None) -> None:
        """重新算一次过程（渗透 / 蔓延）并刷新画布与指标。"""
        self.result = self._run_once(origins)
        view = self._active_view()
        self._shown_layers = view.depth
        self._active_set = set(view.active)
        self._redraw_grid()
        self._update_result_labels()

    # ==================================================================
    # 动画
    # ==================================================================
    def start_animation(self, origins: Optional[Sequence[int]] = None) -> None:
        """播放逐层动画（``origins`` 省略时按注水方式自动挑选注水点）。

        不重新生成区域：按空格是「重播当前这一次过程」，想换一片区域请点「重新生成」；
        点击画布上的单元则从那个单元开始注水。
        """
        if self._busy:
            return
        terms = self._terms
        self._cancel_animation()
        self._sync_model_params()
        self.result = self._run_once(origins)
        self._shown_layers = 0
        self._active_set = set()
        self._draw_base()
        self._hide_verdict()
        self._update_result_labels()

        if not self._active_view().has_source:
            self.var_status.set(terms.no_source_hint)
            return
        model = self.model
        self.var_status.set(
            f"正在演示{terms.process_verb}过程：{model.lattice_name} "
            f"{model.rows}×{model.cols}，p={model.p:.2f}，"
            f"{model.direction_name} · {model.inject_name}。"
        )
        self._step_animation()

    def _step_animation(self) -> None:
        self._anim_job = None
        if self.result is None:
            return
        if self._drawn_shape[:2] != self.result.shape:
            # 底图已被其它形状重建，当前动画结果作废
            self._cancel_animation()
            return
        view = self._active_view()
        layers = view.layers
        total = view.depth

        if self._shown_layers >= total:
            self._finish_animation()
            return

        # 层数太多时每帧多播几层，保证动画总时长可控（最多约 60 帧）
        per_frame = max(1, math.ceil(total / 60))
        for _ in range(per_frame):
            if self._shown_layers >= total:
                break
            i = self._shown_layers
            batch = [idx for idx in layers[i] if idx not in self._active_set]
            self._active_set.update(batch)
            self._apply_active(batch, self._layer_color(i, total))
            self._shown_layers += 1

        self._update_result_labels()
        delay = max(1, int(self.var_speed.get()))
        self._anim_job = self.root.after(delay, self._step_animation)

    def _finish_animation(self) -> None:
        self._cancel_animation()
        self._redraw_grid()
        self._update_result_labels()
        if self.result is not None:
            terms = self._terms
            view = self._active_view()
            self.var_status.set(
                f"动画结束：{self._verdict_phrase(view)}"
                f"（{terms.cover_phrase} {view.active_ratio:.1%}）。"
                "可点击「开始批量统计」考察该 p 值下的成功概率。"
            )

    def _cancel_animation(self) -> None:
        if self._anim_job is not None:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None

    def show_result_instant(self) -> None:
        """跳过动画，直接显示最终结果。"""
        terms = self._terms
        self._cancel_animation()
        self._sync_model_params()
        self._run_and_show()
        if self.result is None:
            return
        view = self._active_view()
        if not view.has_source:
            self.var_status.set(terms.no_source_hint)
            return
        self.var_status.set(
            f"单次结果：{self._verdict_phrase(view)}，{terms.cover_verb} "
            f"{view.active_count}/{view.total}（{view.active_ratio:.1%}）。"
        )

    # ==================================================================
    # 交互
    # ==================================================================
    def _on_canvas_click(self, event) -> None:
        """点击画布：把最近的单元设为注水点并播放动画。"""
        if not self._node_xy or len(self._node_xy) != self.model.node_count:
            return
        best, best_dist = -1, float("inf")
        for idx, (x, y) in enumerate(self._node_xy):
            dist = (x - event.x) ** 2 + (y - event.y) ** 2
            if dist < best_dist:
                best, best_dist = idx, dist
        if best < 0:
            return
        if self._hit_test(best):
            self.start_animation(origins=[best])
        elif self._terms.reject_hint:
            self.var_status.set(self._terms.reject_hint)

    def _on_canvas_resize(self, _event=None) -> None:
        """画布尺寸变化后重绘（防抖，避免拖动窗口时频繁重绘）。"""
        if self._redraw_job is not None:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(120, self._redraw_grid)

    # ==================================================================
    # 交给子类的钩子
    # ==================================================================
    def _legend_items(self) -> Sequence[Tuple[str, str, str]]:
        """底部图例的条目：``("line" | "dash" | "dot", 颜色, 文字)``。"""
        raise NotImplementedError

    def _draw_base(self) -> None:
        """绘制底层图形（不含活动信息）；完成后应调用 :meth:`_draw_caption`。"""
        raise NotImplementedError

    def _apply_active(self, nodes: Sequence[int], color: str) -> None:
        """把一批单元标记为已活动，并给与已活动相邻的路径上色。"""
        raise NotImplementedError

    def _layer_color(self, layer_index: int, total_layers: int) -> str:
        """第 ``layer_index`` 层的颜色（按层数做渐变）。"""
        raise NotImplementedError

    def _draw_finish_overlay(self) -> None:
        """所有层都显示完之后的可选叠加层（点渗流用它圈出注水点）。"""

    def _hit_test(self, index: int) -> bool:
        """这个位置能否被指定为注水点（点渗流里空位不行）。"""
        return True
