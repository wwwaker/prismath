# -*- coding: utf-8 -*-
"""
蒲丰投针模型 · 桌面视图（Tkinter）
====================================

本模块是**一个非渗流模型的桌面视图**：它继承的是**通用骨架**
:class:`~awe_math.ui.tk.kit.base.ModelViewBase`，而不是渗流专用的 ``PercolationViewBase``。

因为通用骨架已经负责了「与模型无关」的那部分：

* 左侧参数栏由 ``spec.params`` **自动生成**（针长/线距、投针根数、重复组数、随机种子）；
* 动作按钮由 ``spec.actions`` 自动生成（投针一次 / 多组重复估计）；
* 状态栏、进度条、后台任务机制、快捷键与资源释放也都在基类里。

所以本文件只需给出**这个模型特有的四件事**：

1. 中央画布：把投针布局画出来（平行线 + 每根针，命中橙色、未命中灰色）；
2. **动态投针**：新投一次时针「从零开始逐根出现」（帧数固定，用「动画间隔」滑块调速），
   右下角实时显示进度，右侧指标随针数增加而刷新 —— 能直观看到估计值逐渐稳定；
3. 「多组重复估计」时的收敛曲线（估计值 vs 累计投针数，并标出 π 参考线）；
4. 右侧结果面板的指标行（命中率 / 理论命中率 / π 估计 / 误差）。

新增一个非渗流模型时，照抄本文件的结构即可：继承 ``ModelViewBase``，覆盖
``_build_center`` / ``_build_right`` / ``_build_extra_cards`` / ``run_action`` 与
``_render_result``（读取动作返回的字典并画图），其余交给基类。
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional, Tuple

from awe_math.ui.tk.kit import (
    BADGE_NO_BG,
    BADGE_NO_FG,
    BADGE_OK_BG,
    BADGE_OK_FG,
    ModelViewBase,
    register_view,
)
from awe_math.ui.tk.theme import (
    BORDER,
    DIM,
    FAINT,
    FONT_BOLD,
    FONT_SM,
    PANEL_2,
)

from ..model import PI, VIEWPORT_HEIGHT, VIEWPORT_WIDTH, estimate_pi

# ----------------------------------------------------------------------
# 画布配色
# ----------------------------------------------------------------------
COL_BG = "#0c1118"        # 画布底色
COL_LINE = "#334155"      # 平行线（基底走中性灰）
COL_NEEDLE = "#93a1b3"    # 未命中的针
COL_HIT = "#f59e0b"       # 命中的针（饱和色留给"判定关注的对象"）
COL_PI = "#4ade80"        # 收敛曲线里的 π 参考线

#: 画布上最多画多少根针（N 很大时全画会拖慢界面，超出部分只统计不绘制）
MAX_DRAW = 3000
#: 动态投针固定分多少帧（帧数固定，于是「动画间隔」滑块调的就是整段动画的快慢）
ANIM_STEPS = 48
#: 动画间隔（毫秒）的取值范围与默认值
SPEED_MIN, SPEED_MAX, SPEED_DEFAULT = 1, 200, 25

EXPLAIN = (
    "说明：\n"
    "· 平行线是水平线，间距 d = 1；每根针的中心在视口内均匀分布，"
    "倾角 θ 在 [0, π) 上均匀分布；\n"
    "· 针心到最近一条线的距离 ≤ (L/2)·sin θ 时与线相交；\n"
    "· 理论命中概率（L ≤ d）= 2L/(πd)，于是 π ≈ 2LN/(dH)；\n"
    "· 投针越多估计越准（误差 ≈ 1/√N），但这是个随机试验，"
    "结果只会「接近」π 而不等于它；\n"
    "· 命中数为 0 时无法反解 π（此时估不出结果）。"
)


@register_view("buffon_needle")
class BuffonNeedleView(ModelViewBase):
    """蒲丰投针的可视化视图（继承通用骨架，非渗流）。"""

    # ---------------- 界面文案 ----------------
    HINTS = "空格 重播投针动画    R 重新投针    左侧「动画间隔」可调速"
    INTRO_STATUS = "就绪：点「投针一次」随机投针，用命中率估计 π（π ≈ 2LN/(dH)）。"
    FALLBACK_ACCENT = "#f59e0b"

    #: 右侧结果面板的指标行：``((标题, vals 键), ...)``
    RESULT_ROWS: Tuple[Tuple[str, str], ...] = (
        ("投针根数 N", "n"),
        ("命中根数 H", "hits"),
        ("实测命中率", "rate"),
        ("理论命中率 2L/(πd)", "theory"),
        ("π 估计值", "pi"),
        ("绝对误差", "err"),
        ("耗时", "cost"),
    )

    # ==================================================================
    # 状态（基类会在 _build_ui 之前调用）
    # ==================================================================
    def _setup_state(self) -> None:
        self._last: Optional[Dict[str, Any]] = None      # 最近一次动作返回的结果
        self._scale = 1.0
        self._origin: Tuple[float, float] = (0.0, 0.0)
        self._reveal = 0                                 # 当前画布上已出现的针数
        self._anim_target = 0                            # 本次动画要画出的针数
        self.var_speed = tk.IntVar(value=SPEED_DEFAULT)   # 动画间隔（毫秒）
        self.vals: Dict[str, tk.StringVar] = {
            key: tk.StringVar(value="-") for _label, key in self.RESULT_ROWS
        }
        self.var_badge = tk.StringVar(value="")
        self.var_caption = tk.StringVar(value="")

    def _after_build(self) -> None:
        self.var_caption.set("投针区（视口 12 × 8 个线距）")
        self._draw_message("点左侧「投针一次」开始")
        # 首次进来先自动投一次，用户一进来就能看到动态投针
        self._first_job = self.root.after(60, lambda: self.run_action("throw"))

    # ==================================================================
    # 左侧「动画」卡片（通用骨架留的 _build_extra_cards 钩子）
    # ==================================================================
    def _build_extra_cards(self, parent: tk.Widget) -> None:
        card = self._card(parent, "动画")

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="动画间隔（毫秒）", style="Card.TLabel").pack(side="left")
        self.scale_speed = ttk.Scale(
            row, from_=SPEED_MIN, to=SPEED_MAX, length=118,
            command=self._on_speed_change,
        )
        self.scale_speed.set(self.var_speed.get())
        self.scale_speed.pack(side="right", pady=(0, 2))
        ttk.Label(card, text="越小越快：每帧新增的针数固定，间隔越小整段动画越短。",
                  style="CardDim.TLabel", font=FONT_SM, wraplength=252,
                  justify="left").pack(anchor="w", pady=(2, 6))

        self.btn_replay = ttk.Button(card, text="▶ 重播投针动画", command=self._replay)
        self.btn_replay.pack(fill="x", pady=(0, 4))
        self.btn_instant = ttk.Button(card, text="⤓ 直接显示全部", command=self._show_instant)
        self.btn_instant.pack(fill="x")
        self._action_buttons.extend([self.btn_replay, self.btn_instant])

    def _on_speed_change(self, value: str) -> None:
        try:
            speed = int(round(float(value)))
        except (TypeError, ValueError):
            return
        self.var_speed.set(max(SPEED_MIN, min(SPEED_MAX, speed)))

    def _replay(self) -> None:
        """重播最近一次投针的动画。"""
        if self._last is not None and self._last.get("view") != "buffon-converge":
            self._start_animation(self._last)
        else:
            self.var_status.set("还没有可重播的投针结果，先点「投针一次」。")

    def _show_instant(self) -> None:
        """跳过动画，直接显示全部针与最终统计。"""
        if self._last is None or self._last.get("view") == "buffon-converge":
            self.var_status.set("还没有可显示的投针结果，先点「投针一次」。")
            return
        self._cancel_animation()
        self._draw_throw(self._last)
        self._fill_rows(self._last)

    # ==================================================================
    # 中央画布
    # ==================================================================
    def _build_center(self) -> None:
        center = ttk.Frame(self.host, style="Panel.TFrame", padding=12)
        center.grid(row=0, column=1, sticky="nsew", pady=12)
        center.columnconfigure(0, weight=1)
        center.rowconfigure(2, weight=1)

        ttk.Label(center, textvariable=self.var_caption, style="Card.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(center, text="水平平行线间距 d = 1；命中 = 针与某条线相交",
                  style="CardDim.TLabel", font=FONT_SM).grid(
            row=1, column=0, sticky="w", pady=(2, 8))

        self.canvas = tk.Canvas(
            center, bg=COL_BG, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,
        )
        self.canvas.grid(row=2, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._on_resize)

    def _on_resize(self, _event=None) -> None:
        """画布尺寸变化后重绘（防抖，避免拖动窗口时频繁重绘）。"""
        if self._redraw_job is not None:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(120, self._redraw)

    def _redraw(self) -> None:
        """按当前已出现的针数重绘（动画进行中被打断也能接上）。"""
        self._redraw_job = None
        if not (self._alive and self.canvas.winfo_exists()):
            return
        if self._last is None:
            self._draw_message("点左侧「投针一次」开始")
        elif self._last.get("view") == "buffon-converge":
            self._draw_converge(self._last)
        else:
            self._draw_throw_base(self._last)
            self._draw_needles(self._last, 0, self._reveal)

    def _draw_message(self, text: str) -> None:
        """在画布中央显示一段提示文字。"""
        cv = self.canvas
        cv.delete("all")
        cv.create_text(
            max(cv.winfo_width(), 60) // 2, max(cv.winfo_height(), 60) // 2,
            text=text, fill=FAINT, font=FONT_BOLD, justify="center",
            width=max(120, cv.winfo_width() - 40),
        )

    def _draw_throw_base(self, p: Dict[str, Any]) -> bool:
        """画底层：平行线 + 说明文字 + 进度占位；返回是否绘制成功。"""
        cv = self.canvas
        cv.delete("all")
        width = max(cv.winfo_width(), 80)
        height = max(cv.winfo_height(), 80)

        vw = float(p.get("width") or VIEWPORT_WIDTH)
        vh = float(p.get("height") or VIEWPORT_HEIGHT)
        pad = 20.0
        scale = min((width - 2 * pad) / vw, (height - 2 * pad) / vh)
        if scale <= 0:
            return False
        ox = (width - scale * vw) / 2.0
        oy = (height - scale * vh) / 2.0
        self._scale, self._origin = scale, (ox, oy)

        for k in range(int(vh) + 1):                 # 平行线
            y = oy + k * scale
            cv.create_line(pad * 0.4, y, width - pad * 0.4, y, fill=COL_LINE)

        note = (f"L/d = {float(p.get('ratio') or 0):.2f} · 投 {p.get('throws')} 根 · "
                f"命中 {p.get('hits')} 根")
        if int(p.get("throws") or 0) > MAX_DRAW:
            note += f"（图上仅绘出前 {MAX_DRAW} 根）"
        cv.create_text(10, height - 8, anchor="sw", text=note, fill=FAINT, font=FONT_SM)
        cv.create_text(width - 10, height - 8, anchor="se", text="", fill=DIM,
                       font=FONT_SM, tags="progress")
        return True

    def _draw_needles(self, p: Dict[str, Any], start: int, end: int) -> None:
        """画出第 ``[start, end)`` 根针（增量绘制，动画每帧只加一小批）。"""
        cv = self.canvas
        xs: List[float] = list(p.get("xs") or [])
        ys: List[float] = list(p.get("ys") or [])
        thetas: List[float] = list(p.get("thetas") or [])
        mask = str(p.get("hitsMask") or "")
        half = float(p.get("length") or 1.0) / 2.0
        scale = self._scale
        ox, oy = self._origin

        end = min(end, len(xs))
        for i in range(max(0, start), end):
            cx = ox + xs[i] * scale
            cy = oy + ys[i] * scale
            theta = thetas[i]
            dx = half * math.cos(theta) * scale
            dy = half * math.sin(theta) * scale
            hit = i < len(mask) and mask[i] == "1"
            cv.create_line(cx - dx, cy - dy, cx + dx, cy + dy,
                           fill=COL_HIT if hit else COL_NEEDLE,
                           width=2 if hit else 1)

    def _draw_throw(self, p: Dict[str, Any]) -> None:
        """一次性画完整个投针布局（跳过动画时用）。"""
        target = min(int(p.get("throws") or 0), MAX_DRAW)
        if not self._draw_throw_base(p):
            return
        self._draw_needles(p, 0, target)
        self._reveal = target
        self.canvas.itemconfigure("progress", text=f"{target} 根")

    # ------------------------------------------------------------------
    # 动态投针：针从零开始逐批出现
    # ------------------------------------------------------------------
    def _start_animation(self, p: Dict[str, Any]) -> None:
        """开始动态投针：清空画布，让针从零开始逐批出现。"""
        self._cancel_animation()
        self._last = p
        self._anim_target = min(int(p.get("throws") or 0), MAX_DRAW)
        self._reveal = 0
        self._fill_rows(p, reveal=0)
        if not self._draw_throw_base(p) or self._anim_target <= 0:
            self._reveal = self._anim_target
            self._fill_rows(p)
            return
        self._step_animation()

    def _step_animation(self) -> None:
        self._anim_job = None
        p = self._last
        if p is None or not self._alive:
            return
        target = self._anim_target
        if self._reveal >= target:
            self._finish_animation()
            return

        per_frame = max(1, math.ceil(target / ANIM_STEPS))
        start = self._reveal
        end = min(target, start + per_frame)
        self._draw_needles(p, start, end)
        self._reveal = end
        try:
            self.canvas.itemconfigure("progress", text=f"{end}/{target} 根")
        except tk.TclError:      # 画布已被销毁
            return
        self._fill_rows(p, reveal=end)

        delay = max(1, min(SPEED_MAX, int(self.var_speed.get())))
        self._anim_job = self.root.after(delay, self._step_animation)

    def _finish_animation(self) -> None:
        """动画结束：按完整样本给出最终统计。"""
        self._cancel_animation()
        if self._last is not None:
            self._fill_rows(self._last)

    def _cancel_animation(self) -> None:
        if self._anim_job is not None:
            try:
                self.root.after_cancel(self._anim_job)
            except tk.TclError:
                pass
            self._anim_job = None

    # ------------------------------------------------------------------
    # 收敛曲线
    # ------------------------------------------------------------------
    def _draw_converge(self, p: Dict[str, Any]) -> None:
        """画收敛过程：估计值（橙色折线）随累计投针数逼近 π（绿色参考线）。"""
        cv = self.canvas
        cv.delete("all")
        width = max(cv.winfo_width(), 160)
        height = max(cv.winfo_height(), 160)

        samples = p.get("samples") or []
        points: List[Tuple[int, float]] = [
            (int(s["throws"]), float(s["estimate"]))
            for s in samples if s.get("estimate") is not None
        ]
        if len(points) < 2:
            self._draw_message("样本太少，画不出收敛过程（可增大重复组数）")
            return

        left, right, top, bottom = 66.0, 24.0, 26.0, 46.0
        x_max = max(x for x, _ in points) or 1
        ys = [y for _, y in points]
        y_lo = min(min(ys), PI) - 0.15
        y_hi = max(max(ys), PI) + 0.15
        if y_hi - y_lo < 1e-6:
            y_lo, y_hi = PI - 0.5, PI + 0.5
        plot_w = max(width - left - right, 10.0)
        plot_h = max(height - top - bottom, 10.0)

        def sx(x: float) -> float:
            return left + (x / x_max) * plot_w

        def sy(y: float) -> float:
            return top + (y_hi - y) / (y_hi - y_lo) * plot_h

        cv.create_line(left, top, left, top + plot_h, fill=COL_LINE)               # y 轴
        cv.create_line(left, top + plot_h, left + plot_w, top + plot_h, fill=COL_LINE)  # x 轴

        py = sy(PI)                                                                # π 参考线
        cv.create_line(left, py, left + plot_w, py, fill=COL_PI, dash=(4, 3))
        cv.create_text(left + plot_w - 4, py - 10, anchor="e",
                       text=f"π = {PI:.4f}", fill=COL_PI, font=FONT_SM)

        coords: List[float] = []
        for x, y in points:
            coords.extend((sx(x), sy(y)))
        cv.create_line(*coords, fill=COL_HIT, width=2)
        for x, y in points:
            px, py2 = sx(x), sy(y)
            cv.create_oval(px - 2.5, py2 - 2.5, px + 2.5, py2 + 2.5,
                           fill=COL_HIT, outline="")

        cv.create_text(left - 8, sy(y_hi), anchor="e", text=f"{y_hi:.2f}",
                       fill=DIM, font=FONT_SM)
        cv.create_text(left - 8, sy(y_lo), anchor="e", text=f"{y_lo:.2f}",
                       fill=DIM, font=FONT_SM)
        cv.create_text(left, top + plot_h + 12, anchor="w", text="0",
                       fill=DIM, font=FONT_SM)
        cv.create_text(left + plot_w, top + plot_h + 12, anchor="e",
                       text=f"{x_max} 根", fill=DIM, font=FONT_SM)
        cv.create_text(left + plot_w / 2, top + plot_h + 30, anchor="n",
                       text="累计投针数 →", fill=FAINT, font=FONT_SM)
        cv.create_text(left + 6, top + 2, anchor="nw", text="π 估计值",
                       fill=FAINT, font=FONT_SM)

    # ==================================================================
    # 右侧结果面板
    # ==================================================================
    def _build_right(self) -> None:
        panel = ttk.Frame(self.host, style="Panel.TFrame", padding=14)
        panel.grid(row=0, column=2, sticky="nsew", padx=(7, 14), pady=12)
        panel.columnconfigure(1, weight=1)

        self.badge = tk.Label(
            panel, textvariable=self.var_badge, bg=PANEL_2, fg=FAINT,
            font=FONT_BOLD, pady=12, wraplength=300, justify="center",
        )
        self.badge.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        for i, (label, key) in enumerate(self.RESULT_ROWS, start=1):
            ttk.Label(panel, text=label, style="CardDim.TLabel",
                      width=16, anchor="w").grid(row=i, column=0, sticky="w", pady=4)
            ttk.Label(panel, textvariable=self.vals[key], style="Mono.TLabel",
                      anchor="w").grid(row=i, column=1, sticky="w", pady=4)

        row = len(self.RESULT_ROWS) + 1
        ttk.Separator(panel, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(panel, text=EXPLAIN, style="CardDim.TLabel", wraplength=300,
                  justify="left", font=FONT_SM).grid(
            row=row + 1, column=0, columnspan=2, sticky="w")

    # ==================================================================
    # 动作分派：跑模型 -> 动画 / 画图 + 填指标
    # ==================================================================
    def run_action(self, key: str) -> None:
        """用当前参数运行一次动作（覆盖基类：状态栏文案改由结果本身给出）。"""
        if self.spec is None:
            return
        try:
            result = self.spec.run(key, self.current_params(), {})
        except Exception as exc:          # 把模型异常直接展示出来，方便排查
            self._render_result({"error": f"{type(exc).__name__}: {exc}"})
            return
        self._render_result(result)

    def on_key(self, key: str) -> None:
        """空格重播动画，R 重新投针。"""
        k = key.lower()
        if k in (" ", "space"):
            self._replay()
        elif k == "r":
            self.run_action("throw")

    def _render_result(self, payload: Any) -> None:
        """基类的渲染钩子：把动作返回的字典画成图形与指标。"""
        if not isinstance(payload, dict):
            return
        if "error" in payload:
            message = str(payload["error"])
            self._cancel_animation()
            self._draw_message(f"× {message}")
            self.var_status.set(f"运行失败：{message}")
            self.var_badge.set("运行失败")
            self.badge.configure(bg=BADGE_NO_BG, fg=BADGE_NO_FG)
            return

        self._last = payload
        if payload.get("view") == "buffon-converge":
            self._cancel_animation()
            self._draw_converge(payload)
            self._fill_rows(payload)
        else:
            self._start_animation(payload)      # 投针一次 / 动画：逐批出现

    # ==================================================================
    # 指标刷新
    # ==================================================================
    def _fill_rows(self, p: Dict[str, Any], reveal: Optional[int] = None) -> None:
        """刷新右侧指标行、状态栏与结论徽章。

        ``reveal`` 非空表示动画进行中：只按「已出现的前 reveal 根针」统计，
        于是能直观看到 π 的估计值随针数增加而逐渐稳定。
        """
        if p.get("view") == "buffon-converge":
            n = int(p.get("totalThrows") or 0)
            hits = int(p.get("totalHits") or 0)
            groups = int(p.get("repeats") or 0)
            self.var_caption.set(f"收敛过程：{groups} 组 × {p.get('throwsPerGroup')} 根")
            self._set_rows(p, n, hits)
            pi_hat = p.get("piEstimate")
            if pi_hat is None:
                self.var_status.set(f"累计投针 {n} 根命中 {hits}，命中率为 0，无法反解 π。")
            else:
                self.var_status.set(
                    f"多组重复完成：累计 {n} 根命中 {hits}"
                    f"（{float(p.get('hitRate') or 0):.4f}），"
                    f"π ≈ {pi_hat:.5f}（误差 {float(p.get('absError') or 0):.5f}）。")
            return

        total = int(p.get("throws") or 0)
        drawn = min(total, MAX_DRAW)
        if reveal is None:
            self.var_caption.set(
                f"投针布局：L/d = {float(p.get('ratio') or 0):.2f}，共 {total} 根")
            self._set_rows(p, total, int(p.get("hits") or 0))
            self.var_status.set(
                f"投针完成：{total} 根命中 {int(p.get('hits') or 0)}"
                f"（{float(p.get('hitRate') or 0):.4f}，"
                f"理论 {float(p.get('theoryRate') or 0):.4f}），"
                + (f"π ≈ {float(p.get('piEstimate')):.5f}"
                   f"（误差 {float(p.get('absError') or 0):.5f}）。"
                   if p.get("piEstimate") is not None else "命中为 0，无法反解 π。"))
            return

        shown = max(0, min(reveal, drawn))
        mask = str(p.get("hitsMask") or "")
        hits = mask.count("1", 0, shown)
        self.var_caption.set(
            f"动态投针：L/d = {float(p.get('ratio') or 0):.2f}，已投 {shown}/{drawn} 根")
        self._set_rows(p, shown, hits)
        pi_hat = self.vals["pi"].get()
        self.var_status.set(
            f"投针中… {shown}/{drawn} 根，命中 {hits}，π 当前估计 {pi_hat}。")

    def _set_rows(self, p: Dict[str, Any], n: int, hits: int) -> None:
        """按「n 根中命中 hits 根」填写指标行与徽章。"""
        length = float(p.get("length") or 0.0)
        gap = float(p.get("gap") or 1.0)
        theory = float(p.get("theoryRate") or 0.0)
        rate = hits / n if n else 0.0
        pi_hat = estimate_pi(length, gap, n, hits)
        err = None if pi_hat is None else abs(pi_hat - PI)

        self.vals["n"].set(str(n))
        self.vals["hits"].set(str(hits))
        self.vals["rate"].set(f"{rate:.4f}")
        self.vals["theory"].set(f"{theory:.4f}")
        self.vals["pi"].set("—" if pi_hat is None else f"{pi_hat:.5f}")
        self.vals["err"].set("—" if err is None else f"{err:.5f}")
        self.vals["cost"].set(f"{float(p.get('elapsedMs') or 0):.1f} ms")

        if pi_hat is None:
            self.var_badge.set("命中为 0，无法估计 π")
            self.badge.configure(bg=BADGE_NO_BG, fg=BADGE_NO_FG)
            return
        ok = err is not None and err <= 0.1
        self.var_badge.set(f"π ≈ {pi_hat:.4f}（误差 {err:.4f}）")
        self.badge.configure(
            bg=BADGE_OK_BG if ok else BADGE_NO_BG,
            fg=BADGE_OK_FG if ok else BADGE_NO_FG,
        )

    # ==================================================================
    # 生命周期
    # ==================================================================
    def shutdown(self) -> None:
        """视图关闭时停掉动画，再交给基类统一收尾。"""
        self._cancel_animation()
        super().shutdown()
