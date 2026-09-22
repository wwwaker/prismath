# -*- coding: utf-8 -*-
"""
左侧控制栏 mixin
================

把「参数 / 高级选项 / 操作 / 批量统计 / 曲线扫描」五张卡片 + 停止按钮搭出来。
卡片内容由基类提供的 ``var_*``（Tk 变量）与 ``_on_*``（事件处理）驱动，模型差异只体现在
:class:`~prismath.ui.tk.views.common.Terms` 的用词（如「流通概率 p」/「占据密度 p」）与
子类给出的 ``INJECT_CHOICES`` 上。

参数一多侧栏就会比窗口还高，此时 ``pack`` 会直接不显示装不下的控件（按钮会「凭空消失」），
因此整栏放在 :class:`~prismath.ui.tk.theme.ScrollArea` 里。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Tuple

from ..theme import FAINT, FONT_SM, ScrollArea
from .common import MAX_SIZE, THRESHOLD_CHOICES
from .protocols import ViewContract

__all__ = ["SidebarMixin"]


class SidebarMixin(ViewContract):
    """左侧控制栏（卡片族）。"""

    # ------------------------------------------------------------------
    # 骨架
    # ------------------------------------------------------------------
    def _build_sidebar(self) -> None:
        area = ScrollArea(self.host, width=306)
        area.outer.grid(row=0, column=0, sticky="ns", padx=(14, 7), pady=12)
        side = area.inner

        self._build_param_card(side)
        self._build_advanced_card(side)
        self._build_action_card(side)
        self._build_batch_card(side)
        self._build_scan_card(side)

        self.btn_stop = ttk.Button(
            side, text="■ 停止后台任务", style="Danger.TButton",
            command=self.stop_work, state="disabled",
        )
        self.btn_stop.pack(fill="x", pady=(2, 0))
        area.bind_wheel()           # 滚轮滚动 + 下拉框弹出列表配色

    @staticmethod
    def _card(parent: tk.Widget, title: str) -> ttk.LabelFrame:
        """造一张侧栏卡片（统一样式与间距）。"""
        card = ttk.LabelFrame(
            parent, text=f" {title} ", style="Card.TLabelframe",
            padding=(12, 8, 12, 10),
        )
        card.pack(fill="x", pady=(0, 6))
        return card

    def _build_param_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "参数")

        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=self._terms.p_label, style="Card.TLabel").pack(side="left")
        self.lbl_p = ttk.Label(
            head, text=f"p = {self.var_p.get():.2f}", style="MonoAccent.TLabel",
        )
        self.lbl_p.pack(side="right")

        p_low, p_high = self.spec_bounds("p", 0.0, 1.0)
        self.scale_p = ttk.Scale(
            card, from_=p_low, to=p_high, variable=self.var_p,
            command=self._on_p_change,
        )
        self.scale_p.pack(fill="x", pady=(4, 8))

        rows_row = ttk.Frame(card, style="Card.TFrame")
        rows_row.pack(fill="x", pady=(0, 6))
        ttk.Label(rows_row, text="行数 n", style="Card.TLabel").pack(side="left")
        rows_low, rows_high = self.spec_bounds("rows", 5, MAX_SIZE)
        spin_rows = ttk.Spinbox(
            rows_row, from_=rows_low, to=rows_high, width=5,
            textvariable=self.var_rows, command=self._on_shape_change,
        )
        spin_rows.pack(side="right")
        spin_rows.bind("<Return>", lambda _e: self._on_shape_change())
        spin_rows.bind("<FocusOut>", lambda _e: self._on_shape_change())

        cols_row = ttk.Frame(card, style="Card.TFrame")
        cols_row.pack(fill="x", pady=(0, 6))
        ttk.Label(cols_row, text="列数 m", style="Card.TLabel").pack(side="left")
        ttk.Label(cols_row, text="≠ 行数 即矩形", style="CardDim.TLabel",
                  font=FONT_SM).pack(side="left", padx=(6, 0))
        cols_low, cols_high = self.spec_bounds("cols", 5, MAX_SIZE)
        spin_cols = ttk.Spinbox(
            cols_row, from_=cols_low, to=cols_high, width=5,
            textvariable=self.var_cols, command=self._on_shape_change,
        )
        spin_cols.pack(side="right")
        spin_cols.bind("<Return>", lambda _e: self._on_shape_change())
        spin_cols.bind("<FocusOut>", lambda _e: self._on_shape_change())

        thr_row = ttk.Frame(card, style="Card.TFrame")
        thr_row.pack(fill="x", pady=(0, 6))
        self.lbl_threshold = ttk.Label(
            thr_row, text="面积判据阈值", style="Card.TLabel",
        )
        self.lbl_threshold.pack(side="left")
        threshold = ttk.Combobox(
            thr_row, width=5, state="readonly", textvariable=self.var_threshold,
            values=self.spec_choices("threshold", THRESHOLD_CHOICES),
        )
        threshold.pack(side="right")
        threshold.bind("<<ComboboxSelected>>", lambda _e: self.regenerate())

        seed_row = ttk.Frame(card, style="Card.TFrame")
        seed_row.pack(fill="x", pady=(0, 6))
        ttk.Label(seed_row, text="统计种子（-1 = 随机）", style="Card.TLabel").pack(side="left")
        seed_low, seed_high = self.spec_bounds("seed", -1, 2147483647)
        ttk.Spinbox(
            seed_row, from_=seed_low, to=seed_high, width=11, textvariable=self.var_seed,
        ).pack(side="right")

        speed_row = ttk.Frame(card, style="Card.TFrame")
        speed_row.pack(fill="x")
        ttk.Label(speed_row, text="动画间隔", style="Card.TLabel").pack(side="left")
        speed = ttk.Scale(speed_row, from_=1, to=200, length=130,
                          command=self._on_speed_change)
        speed.set(self.var_speed.get())
        speed.pack(side="right", pady=(0, 2))

    def _on_speed_change(self, value: str) -> None:
        try:
            self.var_speed.set(max(1, min(200, int(round(float(value))))))
        except (TypeError, ValueError):
            pass

    # ------------------------------------------------------------------
    # 高级选项
    # ------------------------------------------------------------------
    @staticmethod
    def _option_row(parent: tk.Misc, title: str, var: tk.StringVar,
                    values: Tuple[str, ...], command) -> None:
        """一行「标题 + 只读下拉框」（中文标签较长，所以下拉框占满整行）。"""
        ttk.Label(parent, text=title, style="Card.TLabel").pack(anchor="w")
        combo = ttk.Combobox(
            parent, state="readonly", textvariable=var, values=values, font=FONT_SM,
        )
        combo.pack(fill="x", pady=(2, 6))
        combo.bind("<<ComboboxSelected>>", lambda _e: command())

    def _build_advanced_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "高级选项")

        # 判据放最前面：它决定「什么算成功」，也就决定 p_c 是否有意义
        self._option_row(card, "成功判据", self.var_criterion,
                         tuple(self.CRITERION_CHOICES), self._on_criterion_change)
        self._option_row(card, "格子类型", self.var_lattice,
                         tuple(self.LATTICE_CHOICES), self._on_lattice_change)
        self._option_row(card, "方向模式", self.var_direction,
                         tuple(self.DIRECTION_CHOICES), self._on_direction_change)
        self._option_row(card, self._terms.inject_label, self.var_inject,
                         tuple(self.INJECT_CHOICES), self._on_inject_change)

        self.lbl_pc = ttk.Label(
            card, text="", style="CardDim.TLabel",
            wraplength=252, justify="left", font=FONT_SM,
        )
        self.lbl_pc.pack(anchor="w")
        self._update_pc_label()

    # ------------------------------------------------------------------
    # 操作 / 批量统计 / 曲线扫描
    # ------------------------------------------------------------------
    def _build_action_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "操作")
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        self.btn_anim = ttk.Button(
            card, text="▶ 播放动画", style=self._accent_btn,
            command=self.start_animation,
        )
        self.btn_anim.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self.btn_regen = ttk.Button(card, text="↻ 重新生成", command=self.regenerate)
        self.btn_instant = ttk.Button(card, text="⤓ 直接看结果", command=self.show_result_instant)
        self.btn_regen.grid(row=1, column=0, sticky="ew", padx=(0, 4))
        self.btn_instant.grid(row=1, column=1, sticky="ew", padx=(4, 0))

    def _build_batch_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "批量统计")

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="实验次数 N", style="Card.TLabel").pack(side="left")
        ttk.Combobox(
            row, width=8, textvariable=self.var_trials,
            values=self.spec_choices("trials", ("100", "500", "1000", "5000", "10000")),
        ).pack(side="right")

        self.btn_batch = ttk.Button(
            card, text="开始批量统计", command=self.start_batch_statistics,
        )
        self.btn_batch.pack(fill="x")

    def _build_scan_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "曲线扫描")

        row1 = ttk.Frame(card, style="Card.TFrame")
        row1.pack(fill="x", pady=(0, 6))
        ttk.Label(row1, text="曲线每点次数", style="Card.TLabel").pack(side="left")
        # 每点次数的候选来自 spec（choice 型参数），值域取其最小 / 最大
        scan_choices = self.spec_choices("scanTrials", ())
        if scan_choices:
            scan_nums = sorted(int(float(c)) for c in scan_choices)
            trial_low, trial_high = scan_nums[0], scan_nums[-1]
        else:
            trial_low, trial_high = 20, 5000
        ttk.Spinbox(
            row1, from_=trial_low, to=trial_high, increment=20, width=7,
            textvariable=self.var_scan_trials,
        ).pack(side="right")

        row2 = ttk.Frame(card, style="Card.TFrame")
        row2.pack(fill="x", pady=(0, 6))
        ttk.Label(row2, text="p 扫描步进", style="Card.TLabel").pack(side="left")
        ttk.Combobox(
            row2, width=6, textvariable=self.var_scan_step,
            values=self.spec_choices("scanStep", ("0.02", "0.05", "0.1")),
        ).pack(side="right")

        self.btn_scan = ttk.Button(card, text="▶ 绘制曲线", command=self.start_scan)
        self.btn_scan.pack(fill="x")

        self._action_buttons = [
            self.btn_regen,
            self.btn_anim,
            self.btn_instant,
            self.btn_batch,
            self.btn_scan,
        ]
