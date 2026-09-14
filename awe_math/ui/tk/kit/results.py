# -*- coding: utf-8 -*-
"""
右侧结果面板 mixin：单次结果 / 批量统计 / P(p) 曲线
===================================================

三个标签页的骨架、指标行的填值、历史记录表与 matplotlib 曲线都放在这里。

* 指标行的**行标题**由子类的 ``STAT_ROWS`` 给出（数据表），行**数值**由基类按归一化结果
  :class:`~awe_math.ui.tk.views.common.ActiveView` 统一填写；只有真正模型特有的几行
  （边渗流的「流通边 / 总边数、注水点、浸润节点数」，点渗流的
  「占据格数量、注水点、蔓延格数」）交给子类的
  :meth:`ResultPanelMixin._fill_extra_rows`。
* 「什么算成功」由判据决定：贯通 / 起点 / 面积三种判据下，结论徽章、历史表列名与提示
  都会改变（见 :meth:`ResultPanelMixin._update_result_labels`）。

matplotlib 是**可选依赖**：没装时曲线页显示一行提示，其余功能照常。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, List, Optional, Sequence

from ..theme import (
    ACCENT,
    BORDER,
    DANGER,
    DIM,
    FAINT,
    FONT_BADGE,
    FONT_BOLD,
    FONT_SM,
    PANEL,
    PANEL_2,
    TEXT,
    WARN,
)
from .common import (
    BG_CANVAS,
    BADGE_BAD_BG,
    BADGE_BAD_FG,
    BADGE_NO_BG,
    BADGE_NO_FG,
    BADGE_OK_BG,
    BADGE_OK_FG,
    TREE_NO,
    TREE_OK,
    ActiveView,
    half_crossing,
    label as choice_label,
)

__all__ = ["ResultPanelMixin", "HAS_MPL"]

# ----------------------------------------------------------------------
# matplotlib 为可选依赖：只有曲线页需要它
# ----------------------------------------------------------------------
try:
    import matplotlib

    matplotlib.use("TkAgg")
    # 中文显示：Windows 优先使用微软雅黑 / 黑体
    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
        "Noto Sans CJK SC",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False

    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure

    HAS_MPL = True
except Exception as _exc:  # pragma: no cover - 环境缺库时降级
    HAS_MPL = False
    _MPL_ERROR = str(_exc)


class ResultPanelMixin:
    """右侧三标签页结果面板 + 指标刷新 + 曲线绘制。"""

    # ==================================================================
    # 骨架
    # ==================================================================
    def _build_right(self) -> None:
        self.notebook = ttk.Notebook(self.host, width=412)
        self.notebook.grid(row=0, column=2, sticky="nsew", padx=(7, 14), pady=12)

        self.tab_single = ttk.Frame(self.notebook, style="Panel.TFrame", padding=12)
        self.tab_batch = ttk.Frame(self.notebook, style="Panel.TFrame", padding=12)
        self.tab_curve = ttk.Frame(self.notebook, style="Panel.TFrame", padding=8)
        self.notebook.add(self.tab_single, text=" 单次结果 ")
        self.notebook.add(self.tab_batch, text=" 批量统计 ")
        self.notebook.add(self.tab_curve, text=" P(p) 曲线 ")

        self._build_single_tab()
        self._build_batch_tab()
        self._build_curve_tab()

    def _add_stat_row(self, parent: tk.Misc, row: int, label: str, var: tk.StringVar,
                      key: Optional[str] = None) -> None:
        """一行「标题 + 数值」；``key`` 非空时登记进 ``_stat_labels`` 供按判据改标题。"""
        lbl = ttk.Label(parent, text=label, style="CardDim.TLabel", width=14, anchor="w")
        lbl.grid(row=row, column=0, sticky="w", pady=4)
        if key is not None:
            self._stat_labels[key] = lbl
        ttk.Label(parent, textvariable=var, style="Mono.TLabel", anchor="w").grid(
            row=row, column=1, sticky="w", pady=4
        )

    # ------------------------------------------------------------------
    # 单次结果
    # ------------------------------------------------------------------
    def _build_single_tab(self) -> None:
        tab = self.tab_single
        tab.columnconfigure(1, weight=1)

        self.badge = tk.Label(
            tab, text="— 等待计算 —", bg=PANEL_2, fg=FAINT,
            font=FONT_BADGE, pady=12,
        )
        self.badge.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))

        rows = self.STAT_ROWS
        for i, (label, key) in enumerate(rows, start=1):
            self._add_stat_row(tab, i, label, self.vals[key])

        sep_row = len(rows) + 1
        ttk.Separator(tab, orient="horizontal").grid(
            row=sep_row, column=0, columnspan=2, sticky="ew", pady=10
        )
        ttk.Label(
            tab,
            style="CardDim.TLabel",
            wraplength=350,
            justify="left",
            font=FONT_SM,
            text=self.EXPLAIN,
        ).grid(row=sep_row + 1, column=0, columnspan=2, sticky="w")

    # ------------------------------------------------------------------
    # 批量统计
    # ------------------------------------------------------------------
    def _build_batch_tab(self) -> None:
        tab = self.tab_batch
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        info = ttk.LabelFrame(
            tab, text=" 最近一次批量统计 ", style="Card.TLabelframe",
            padding=(14, 10, 14, 12),
        )
        info.grid(row=0, column=0, columnspan=2, sticky="ew")
        info.columnconfigure(1, weight=1)
        rows = [
            ("统计所用 p", "b_p"),
            ("实验次数 N", "b_trials"),
            ("成功次数", "b_success"),
            ("成功概率", "b_prob"),
            (f"{self._terms.mean_short}比例", "b_mean"),
            ("标准误", "b_err"),
            ("总耗时", "b_time"),
        ]
        for i, (label, key) in enumerate(rows):
            self._add_stat_row(info, i, label, self.vals[key], key=key)

        head = ttk.Frame(tab, style="Panel.TFrame")
        head.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        ttk.Label(head, text="历史记录", style="Card.TLabel", font=FONT_BOLD).pack(side="left")
        ttk.Button(head, text="清空", width=6, command=self._clear_history).pack(side="right")

        cols = ("p", "shape", "trials", "success", "prob", "mean", "time")
        self.tree = ttk.Treeview(tab, columns=cols, show="headings", height=10)
        for col, text, width in zip(
            cols,
            ("概率 p", "形状", "次数", "成功", "成功概率", "平均比例", "耗时(s)"),
            (46, 62, 46, 46, 52, 66, 50),
        ):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="center")
        self.tree.grid(row=2, column=0, sticky="nsew")
        self.tree.tag_configure("ok", foreground=TREE_OK)
        self.tree.tag_configure("no", foreground=TREE_NO)

        bar = ttk.Scrollbar(tab, orient="vertical", command=self.tree.yview)
        bar.grid(row=2, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=bar.set)

    def _insert_history(self, res, tag: str) -> None:
        """往历史表插一行（最新的在最前面，最多保留 300 行）。"""
        self.tree.insert(
            "", 0,
            values=(
                f"{res.p:.2f}",
                f"{res.rows}×{res.cols}",
                res.trials,
                res.success,
                f"{res.probability:.4f}",
                f"{res.mean_ratio:.3f}",
                f"{res.elapsed:.2f}",
            ),
            tags=(tag,),
        )
        if len(self.tree.get_children()) > 300:
            self.tree.delete(self.tree.get_children()[-1])

    def _clear_history(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    # ------------------------------------------------------------------
    # P(p) 曲线
    # ------------------------------------------------------------------
    def _build_curve_tab(self) -> None:
        tab = self.tab_curve
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        if not HAS_MPL:
            ttk.Label(
                tab,
                text="未检测到 matplotlib，无法绘制曲线。\n可执行 pip install matplotlib 后重试。",
                style="Danger.TLabel",
                justify="left",
            ).grid(row=0, column=0, sticky="nw", padx=10, pady=10)
            self.figure = None
            self.ax = None
            self.figure_canvas = None
            return

        self.figure = Figure(figsize=(4.3, 3.4), dpi=100, facecolor=PANEL)
        self.ax = self.figure.add_subplot(111)
        self.figure_canvas = FigureCanvasTkAgg(self.figure, master=tab)
        self.figure_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar = NavigationToolbar2Tk(self.figure_canvas, tab, pack_toolbar=False)
        toolbar.update()
        toolbar.configure(bg=PANEL)
        for child in toolbar.winfo_children():
            try:
                child.configure(bg=PANEL)
            except tk.TclError:
                pass
        toolbar.grid(row=1, column=0, sticky="ew")

    def _style_ax(self) -> None:
        """把坐标轴刷成暗色（clear 之后需要重新设置）。"""
        if self.ax is None:
            return
        ax = self.ax
        ax.set_facecolor(PANEL)
        for spine in ax.spines.values():
            spine.set_color(BORDER)
        ax.tick_params(colors=DIM)
        ax.xaxis.label.set_color(DIM)
        ax.yaxis.label.set_color(DIM)

    def _redraw_curve(self) -> None:
        """重画 P(p) 曲线：成功概率 + 平均活动比例，并标出本次曲线的 1/2 交点。"""
        if not HAS_MPL or self.ax is None or self.figure_canvas is None:
            return
        terms = self._terms
        ax = self.ax
        ax.clear()

        if not self._scan_results:
            ax.text(
                0.5, 0.5,
                "点击左侧「绘制曲线」开始扫描",
                transform=ax.transAxes, ha="center", va="center",
                color=FAINT, fontsize=10,
            )
            ax.set_xticks([])
            ax.set_yticks([])
        else:
            xs = [r.p for r in self._scan_results]
            prob = [r.probability * 100.0 for r in self._scan_results]
            ratio = [r.mean_ratio * 100.0 for r in self._scan_results]
            span = self._scan_criterion == "span"
            ax.plot(
                xs, prob, "-o", color=ACCENT, lw=1.8, ms=3.4,
                mfc=BG_CANVAS, mec=TEXT, mew=0.8,
                label="成功概率 (%)",
            )
            ax.plot(
                xs, ratio, "--", color="#7dd3fc", lw=1.5,
                label=terms.curve_ratio_label,
            )
            # p_c 只属于贯通判据：面积判据下这条线画出来只会误导
            pc = self._scan_pc if span else None
            if pc is not None:
                kind = "估计" if self.model.pc_is_estimate else "阈值"
                ax.axvline(
                    pc, color=DANGER, ls="--", lw=1.3,
                    label=f"{kind} p_c = {pc:.4f}",
                )
            ax.set_xlabel(terms.curve_x_label, fontsize=9)
            ax.set_ylabel("百分比 (%)", fontsize=9)
            ax.set_xlim(0, 1)
            ax.set_ylim(-3, 103)
            ax.grid(color="#22303f", lw=0.8, ls=":")
            ax.tick_params(labelsize=8)
            ax.legend(
                loc="upper left", fontsize=8,
                facecolor=PANEL_2, edgecolor=BORDER, labelcolor=TEXT,
            )
            rows, trials = self._scan_meta
            cols = self._scan_cols or rows
            lattice_name = choice_label(self.LATTICE_CHOICES, self._scan_lattice)
            direction_name = choice_label(self.DIRECTION_CHOICES, self._scan_direction)
            rule = {
                "span": "贯通判据",
                "origin": "起点判据",
                "area": f"面积判据 ≥ {self._scan_threshold:.0%}",
            }[self._scan_criterion]
            inject_name = choice_label(self.INJECT_CHOICES, self._scan_inject)
            title = (f"P(p) 曲线（{lattice_name} {rows}×{cols} · {direction_name} · "
                     f"注水 {inject_name} · {rule}，每点 {trials} 次）")
            # 把「本次曲线自己的 1/2 交点」标出来：它随长宽比移动，理论 p_c 不会动
            cross = half_crossing([(p, v / 100.0) for p, v in zip(xs, prob)])
            if cross is not None:
                pc_note = (f" = {pc:.4f}）" if pc is not None else " 未知）")
                title += (f"\n1/2 交点 = {cross:.3f}（有限尺寸 + 长宽比决定；理论 p_c"
                          + pc_note)
            ax.set_title(title, fontsize=9, color=TEXT)
            if pc is not None and prob and max(prob) >= 100 and min(prob) <= 0:
                ax.annotate(
                    "相变：量变引起质变",
                    xy=(pc, 50), xytext=(pc + 0.06, 22),
                    fontsize=8, color=WARN,
                    arrowprops=dict(arrowstyle="->", color=WARN, lw=1),
                )
            elif not span:
                note = ("起点判据：交点高于 p_c —— 还要看注水点是否落在纵贯簇里；"
                        "注水方式选「顶端整行」时才等于 p_c"
                        if self._scan_criterion == "origin" else
                        "面积判据：曲线交点随「比例 / 网格尺寸 / 注水方式」变化，不是 p_c")
                ax.text(
                    0.03, 0.03, note,
                    transform=ax.transAxes, ha="left", va="bottom",
                    fontsize=7.5, color=WARN,
                )

        self._style_ax()
        self.figure_canvas.draw_idle()

    # ==================================================================
    # 指标刷新
    # ==================================================================
    def _update_result_labels(self) -> None:
        """按当前模型状态与（可能尚未算完的）结果刷新单次结果面板。"""
        model = self.model
        res = self.result
        self.vals["p"].set(f"{model.p:.2f}")
        self.vals["size"].set(self._size_text(model))

        if res is None:
            self._fill_extra_rows(None)
            for key in ("ratio", "depth", "cost"):
                self.vals[key].set("-")
            self._refresh_spanning_row(None)
            self.badge.configure(text="— 等待计算 —", bg=PANEL_2, fg=FAINT)
            return

        view = self._active_view()
        shown = min(self._shown_layers, view.depth)
        self._fill_extra_rows(view)
        shown_ratio = len(self._active_set) / view.total if view.total else 0.0
        self.vals["ratio"].set(
            f"{shown_ratio:.1%}（{view.ratio_note}动画 {shown}/{view.depth} 层）"
        )
        self.vals["depth"].set(f"{shown} / {view.depth} 层")
        self.vals["cost"].set(f"{view.elapsed * 1000:.1f} ms")
        self._refresh_spanning_row(view)
        self._update_badge(view, shown)

    def _refresh_spanning_row(self, view: Optional[ActiveView]) -> None:
        """「纵贯簇」是区域本身的性质（与注水点无关），没有结果时也显示。"""
        nodes = self.model.spanning_nodes()
        unit = self._terms.unit
        if not nodes:
            self.vals["spanning"].set("无")
            return
        total = self.model.node_count
        if total:
            value = f"{len(nodes)} {unit}（{len(nodes) / total:.1%}）"
        else:
            value = f"{len(nodes)} {unit}"
        if view is not None:
            value += "·水在簇内" if view.origin_in_spanning else "·水在簇外"
        self.vals["spanning"].set(value)

    def _update_badge(self, view: ActiveView, shown: int) -> None:
        """顶部结论徽章：按判据给出「这一次算不算成功」的一句话。"""
        terms = self._terms
        unit = terms.unit
        if not view.has_source:
            self.badge.configure(
                text=terms.no_source_badge, bg=BADGE_BAD_BG, fg=BADGE_BAD_FG)
        elif shown < view.depth:
            self.badge.configure(text=terms.progress_badge, bg=PANEL_2, fg=WARN)
        elif view.criterion == "span":
            # 贯通判据：结论看整片区域有没有纵贯簇，活动面积只是附带信息
            if view.spans:
                self.badge.configure(
                    text=f"✔ 存在纵贯簇（{view.spanning_count} {unit}，"
                         f"{terms.active_verb} {view.active_ratio:.1%}）",
                    bg=BADGE_OK_BG, fg=BADGE_OK_FG)
            else:
                self.badge.configure(
                    text=f"✘ 没有纵贯簇（{terms.active_verb} {view.active_ratio:.1%}）",
                    bg=BADGE_NO_BG, fg=BADGE_NO_FG)
        elif view.criterion == "origin":
            # 起点判据：最容易困惑的一档 —— 区域有纵贯簇，但注水点在簇外
            if view.origin_spans:
                self.badge.configure(
                    text=f"✔ 起点纵贯（{terms.active_verb} {view.active_ratio:.1%}）",
                    bg=BADGE_OK_BG, fg=BADGE_OK_FG)
            elif view.spans:
                self.badge.configure(
                    text=f"✘ 起点在纵贯簇外（簇 {view.spanning_count} {unit}）",
                    bg=BADGE_NO_BG, fg=BADGE_NO_FG)
            else:
                self.badge.configure(
                    text=f"✘ 起点未纵贯（{terms.active_verb} {view.active_ratio:.1%}）",
                    bg=BADGE_NO_BG, fg=BADGE_NO_FG)
        elif view.engulfed:
            self.badge.configure(
                text=f"✔ 面积达标 {view.active_ratio:.1%}（≥{view.threshold:.0%}）",
                bg=BADGE_OK_BG, fg=BADGE_OK_FG)
        else:
            self.badge.configure(
                text=f"✘ 面积不足 {view.active_ratio:.1%}（<{view.threshold:.0%}）",
                bg=BADGE_NO_BG, fg=BADGE_NO_FG)

    # ------------------------------------------------------------------
    # 交给子类的两处模型差异
    # ------------------------------------------------------------------
    def _fill_extra_rows(self, view: Optional[ActiveView]) -> None:
        """填写模型特有的指标行（子类实现；``view`` 为 None 表示还没有结果）。"""
        raise NotImplementedError

    def _size_text(self, model: Any) -> str:
        """「格子 / 规模」行的文本（子类可覆盖以追加注水方式等信息）。"""
        terms = self._terms
        return (f"{model.lattice_name} {model.rows}×{model.cols}"
                f"（{model.node_count} {terms.unit}）")
