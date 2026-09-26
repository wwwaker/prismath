# -*- coding: utf-8 -*-
"""
生命游戏模型 · 桌面视图（Tkinter）
====================================
这是本项目第一个**栅格类模型的桌面视图**，继承通用图表骨架
:class:`~prismath.ui.tk.kit.chart.ChartViewBase`（画布用 ``ChartSpec(kind="grid")``），
但它比其它视图多承担一点"编辑器 / 播放器"的活儿：**棋盘默认是空的，由用户在画布上自己画
开局；按 ▶ 之后一代一代实时演化，不设代数上限。**

界面构成
--------
* **左侧栏顶部**：播放卡片 —— `▶ 播放 / ⏸ 暂停`、`⏭ 下一帧`、`✕ 清空棋盘`、动画间隔滑块
  （播放器是最常用的控件，所以放在最上面，不必先滚过一堆参数）；
* **左侧栏参数区**：棋盘 / 开局 / 演化三组参数；「生成开局」按钮挂在**开局卡片底部** ——
  参数只是"下次生成的配方"，按下按钮才会真的铺到棋盘上；
* **中央画布**：栅格（差分刷新）。**按住左键拖动就是画笔**：按下的那一格决定这一笔是
  「画」还是「擦」，拖动只是把经过的格子设成这个状态，因此按住不动 / 来回蹭都不会反复翻转
  （与参考实现 ``game_of_life.html`` 的手感一致）；
* **右侧面板**：结论徽章 + 指标行 + **实时人口曲线**（随每一代长出来）。

三条约定
--------
1. **播放不设代数上限**：一次一代往下走，直到**消亡 / 静止 / 周期振荡**（由
   :class:`~prismath.models.life_game.model.LifeWatch` 判定）或用户按暂停。
   终端 / 网页那条数据级路径仍按 ``--generations`` 走一段有上限的演化（``spec.handle``）——
   **判定逻辑是同一个 ``LifeWatch``**，所以两条路给出的周期长度不会不一样。
2. **起点是棋盘，不是参数**：播放从棋盘当前状态往下走，手绘的开局、刚涂改的细胞都不会被
   参数重新播种覆盖；改规则 / 边界通过 ``LifeBoard.configure`` 作用在现有棋盘上。
   一旦棋盘被改过（生成 / 清空 / 涂改 / 行列变化），周期检测与人口曲线的历史都**从头开始** ——
   之前的轨迹已经不是现在这条了。
3. **人口曲线是面板，不是另一个动作**：它画的就是视图累积的逐代统计（``live_payload``
   的 ``census``），与屏幕上"第几代"永远一致。
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Mapping, Optional, Tuple

from prismath.ui.tk.kit import (
    BAD,
    NO,
    OK,
    BG_CANVAS,
    ChartSpec,
    ChartViewBase,
    register_view,
)
from prismath.ui.tk.theme import BORDER, DIM, FAINT, FONT_SM

from ..model import (
    MAX_FRAMES,
    OUTCOME_CYCLE,
    OUTCOME_EXTINCT,
    OUTCOME_RUNNING,
    OUTCOME_STATIC,
    LifeWatch,
)
from ..spec import build_board, frame_payload, live_payload, options_from_ui, outcome_text

# ----------------------------------------------------------------------
# 配色与尺寸
# ----------------------------------------------------------------------
#: 活细胞（与模型主题色一致）
COL_ALIVE = "#16a34a"
#: 人口曲线与其坐标轴
COL_CURVE = "#0284c7"
COL_AXIS = "#cbd5e1"
#: 人口曲线的画布高度（宽度跟随右侧面板）
CURVE_HEIGHT = 148
#: 曲线上最多画多少个点（代数再多也只做抽样，避免每帧都遍历整条历史）
CURVE_MAX_POINTS = 320

EXPLAIN = (
    "怎么玩：\n"
    "· **先画开局**：棋盘一开始是空的，按住鼠标左键在画布上拖动即可画细胞；"
    "按下那一格若是死的，这一笔就是「画」，若是活的，这一笔就是「擦」——"
    "所以按住不动、来回蹭都不会反复翻转；\n"
    "· **开局**：图案 / 密度 / 种子只是「配方」，按「生成开局」才会铺到棋盘上"
    "（随机播种按密度撒点，预置图案居中放置）；「清空棋盘」回到全空；\n"
    "· **播放**：`▶ 播放` 从当前棋盘一代一代往下走，**不设代数上限** ——"
    "直到消亡、进入周期，或你按暂停（可「⏭ 下一帧」逐代细看、拖动滑块调速）；\n"
    "· **终局判定**：模型会检测状态重复并给出周期长度：消亡 / 静止（周期 1）/ "
    "周期振荡 / 整体平移（滑翔机每 4 代走一格，环面上周期 = 4 × 边长）；"
    "棋盘状态有限而演化确定，所以迟早会重复，但瞬态可以长得惊人；\n"
    "· 改规则或边界不会清空棋盘；**涂改会把人口曲线从这一代重新开始**"
    "（因为之前那一段属于另一条轨迹了）。"
)


@register_view("life_game")
class LifeView(ChartViewBase):
    """生命游戏的可视化视图（栅格画布 + 手绘开局 + 实时播放 + 人口曲线）。"""

    HINTS = "空格 播放/暂停    R 生成开局    1 开始演化    按住左键拖动可在画布上画细胞"
    INTRO_STATUS = "就绪：按住鼠标在画布上画几个细胞（或点「生成开局」），然后按 ▶ 播放。"
    FALLBACK_ACCENT = COL_ALIVE
    EXPLAIN = EXPLAIN
    #: 默认 100 毫秒/代（≈10 代/秒）：滑翔机怎么走、振荡子怎么闪，一眼看得清。
    #: 想快就把滑块往左拉（最小 1 毫秒），想细看就用「⏸ 暂停」+「⏭ 下一帧」。
    SPEED_DEFAULT = 100

    # ---------------- 右侧指标行（声明即可，不必写刷新代码） ----------------
    RESULT_ROWS: Tuple[Tuple[str, str], ...] = (
        ("代数", "generation"),
        ("活细胞数", "population"),
        ("存活密度", "density"),
        ("本代新生", "births"),
        ("本代死亡", "deaths"),
        ("终局判定", "outcome"),
        ("演化规则", "rule"),
        ("边界条件", "boundary"),
        ("演化耗时", "cost"),
    )
    ROW_SOURCES: Mapping[str, str] = {
        "generation": "generation", "population": "population", "density": "density",
        "births": "births", "deaths": "deaths", "outcome": "outcomeLabel",
        "rule": "ruleName", "boundary": "boundaryName", "cost": "elapsedMs",
    }
    RESULT_FORMATS: Mapping[str, str] = {
        "density": "{:.3f}", "cost": "{:.1f} ms",
    }

    # ---------------- 图表声明：payload["view"] -> 怎么画 ----------------
    CHART_SPECS: Mapping[str, ChartSpec] = {
        "life-grid": ChartSpec(
            kind="grid",
            title="生命游戏棋盘",
            caption="{boundaryName} · {rule} · 第 {generation} 代 · {outcomeLabel}",
            frames="frames", row_field="rows", col_field="cols",
            colors=("", COL_ALIVE),          # 死格不画（留画布底色），只画活细胞
            gap=1, grid_lines=False,
            clickable=True,                  # 允许按下 / 拖动涂改
            animate=True,                    # 留给无头后端回放 payload 里的 frames
            limit=MAX_FRAMES,
        ),
    }

    # ==================================================================
    # 状态：一个可以随意涂改的棋盘 + 这一条轨迹的判官与统计
    # ==================================================================
    def _setup_state(self) -> None:
        super()._setup_state()
        #: 当前这一笔是"画"还是"擦"（按下时由那一格的状态决定，拖动时沿用）
        self._paint_alive = True
        #: 表单还没建好，这里取到的是 spec.params 的默认值：默认图案是"空白"，所以棋盘是空的
        self.board = self._new_board()
        self._reset_run()

    def _new_board(self):
        """按界面上的当前参数造棋盘（下拉框给的是中文标签，先翻成内部取值）。"""
        return build_board(options_from_ui(self.current_params()))

    def _after_build(self) -> None:
        self._cancel_animation()
        self._render_live()            # 画一张空棋盘（状态栏保持 INTRO_STATUS）

    # ==================================================================
    # 侧栏：播放卡片（顶部）里的「清空棋盘」
    # ==================================================================
    def _build_player_extra(self, parent: tk.Widget) -> None:
        self.btn_clear = ttk.Button(parent, text="✕ 清空棋盘", command=self.clear_board)
        self.btn_clear.pack(fill="x", pady=(0, 6))
        self._action_buttons.append(self.btn_clear)

    # ==================================================================
    # 侧栏：「开局」卡片底部的「生成开局」
    # ==================================================================
    def _param_card_footer(self, card: tk.Widget, group: str) -> None:
        """把「生成开局」挂到「开局」参数卡片底下：参数是配方，按钮才动手。"""
        if group != "开局":
            return
        self.btn_generate = ttk.Button(card, text="🎲 生成开局", command=self.generate_opening)
        self.btn_generate.pack(fill="x", pady=(4, 0))

    # ==================================================================
    # 右侧：实时人口曲线（面板，不是另一个动作）
    # ==================================================================
    def _build_right_extra(self, panel: tk.Widget, row: int) -> int:
        ttk.Separator(panel, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(10, 6))
        ttk.Label(panel, text="人口曲线（活细胞数 / 代数）", style="CardDim.TLabel").grid(
            row=row + 1, column=0, columnspan=2, sticky="w")
        self.curve = tk.Canvas(
            panel, height=CURVE_HEIGHT, bg=BG_CANVAS, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,
        )
        self.curve.grid(row=row + 2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        return row + 3

    def _fill_rows(self, payload: Mapping[str, Any],
                   drawn: Optional[int] = None) -> None:
        """指标行 + 徽章 + 状态栏由基类刷新；这里顺带把人口曲线画到当前代。"""
        super()._fill_rows(payload, drawn)
        self._update_curve(payload)

    def _update_curve(self, payload: Optional[Mapping[str, Any]]) -> None:
        """画人口曲线：数据取 payload 的 ``census``（整条轨迹的逐代统计，已抽样）。"""
        canvas = getattr(self, "curve", None)
        if canvas is None:
            return
        census = list((payload or {}).get("census") or [])
        # 代数再多也只画抽样后的点（否则每帧都要遍历整条历史）；末点总是补上
        stride = max(1, len(census) // CURVE_MAX_POINTS)
        points: List[Tuple[float, float]] = [
            (float(row.get("gen") or 0), float(row.get("population") or 0))
            for row in census[::stride] if isinstance(row, Mapping)
        ]
        last = census[-1] if census and isinstance(census[-1], Mapping) else None
        if last is not None:
            newest = (float(last.get("gen") or 0), float(last.get("population") or 0))
            if not points or points[-1][0] != newest[0]:
                points.append(newest)

        width = max(canvas.winfo_width(), 160)
        height = max(canvas.winfo_height(), 90)
        left, top, right, bottom = 42.0, 12.0, 12.0, 20.0
        plot_w = max(width - left - right, 10.0)
        plot_h = max(height - top - bottom, 10.0)

        canvas.delete("all")
        canvas.create_line(left, top, left, top + plot_h, fill=COL_AXIS)
        canvas.create_line(left, top + plot_h, left + plot_w, top + plot_h, fill=COL_AXIS)
        if len(points) < 2:
            canvas.create_text(left + 6, top + 4, anchor="nw", fill=FAINT, font=FONT_SM,
                               text="按 ▶ 播放后，这里会画出活细胞数随代数变化")
            return

        x_max = max(x for x, _y in points) or 1.0
        y_max = max(y for _x, y in points) or 1.0

        def sx(value: float) -> float:
            return left + (value / x_max) * plot_w

        def sy(value: float) -> float:
            return top + plot_h - (value / y_max) * plot_h

        coords: List[float] = []
        for x, y in points:
            coords.extend((sx(x), sy(y)))
        canvas.create_line(*coords, fill=COL_CURVE, width=2)
        last_x, last_y = points[-1]
        canvas.create_oval(sx(last_x) - 3, sy(last_y) - 3,
                           sx(last_x) + 3, sy(last_y) + 3, fill=COL_CURVE, outline="")
        canvas.create_text(left - 6, top, anchor="ne", text=f"{y_max:.0f}",
                           fill=DIM, font=FONT_SM)
        canvas.create_text(left, top + plot_h + 10, anchor="w", text="0",
                           fill=DIM, font=FONT_SM)
        canvas.create_text(left + plot_w, top + plot_h + 10, anchor="e",
                           text=f"{x_max:.0f} 代", fill=DIM, font=FONT_SM)

    # ==================================================================
    # 播放：一代一代往下走，不设代数上限
    # ==================================================================
    def _reset_run(self) -> None:
        """重开一条轨迹的统计（生成 / 清空 / 涂改 / 改行列之后都要调用）。

        周期检测"见过哪些状态"与人口曲线的历史都只对**同一条轨迹**有意义：
        棋盘一旦被改过，之前那一段就不再是现在这条轨迹了。
        """
        self._watch = LifeWatch(self.board)
        self._census: List[Dict[str, int]] = [{
            "gen": self.board.generation, "population": self.board.population,
            "births": 0, "deaths": 0,
        }]
        self._started = time.perf_counter()

    def _elapsed(self) -> float:
        return time.perf_counter() - self._started

    def _render_live(self) -> None:
        """把当前棋盘与到这一代为止的统计画出来（栅格走差分刷新）。"""
        spec = self.CHART_SPECS.get("life-grid")
        if spec is None:
            return
        self._chart = spec
        self._last = live_payload(self.board, self._census, self._watch, self._elapsed())
        self._draw(spec, self._last)
        self._fill_rows(self._last)

    def _repaint(self, status: Optional[str] = None) -> None:
        """按当前棋盘重画（连同到这一代为止的人口曲线），可选地改写状态栏。"""
        self._stop_playback()
        self._render_live()
        self._sync_player_buttons()
        if status:
            self.var_status.set(status)

    def _stop_playback(self) -> None:
        """停掉播放循环（不改棋盘状态）。"""
        self._cancel_animation()
        self.var_playing.set(False)

    def play(self) -> None:
        """▶ 开始（或继续）播放：逐代演化，直到消亡 / 进入周期，或你按暂停。

        已经收敛（周期振荡 / 静止）也允许继续播 —— 结论一直挂在右侧徽章上，不会丢；
        只是"刚收敛的那一代"会自动停下来报一次结论（见 :meth:`_step_board`）。
        """
        if self._anim_job is not None:
            return
        if self.board.population == 0:
            self._repaint("棋盘是空的：先按住鼠标画几个细胞，或点「生成开局」。")
            return
        self.var_playing.set(True)
        self._sync_player_buttons()
        self._tick()

    def _tick(self) -> None:
        """播放循环的一步：演化一代 -> 刷新 -> 排下一次。"""
        self._anim_job = None
        if not self._alive:
            return
        if self._step_board() is not None:      # 这一代收敛了：自动停下来
            return
        delay = max(1, min(self.SPEED_MAX, int(self.var_speed.get())))
        self._anim_job = self.root.after(delay, self._tick)

    def _step_board(self) -> Optional[str]:
        """演化一代、刷新画面与曲线；**刚收敛的那一代**自动暂停并返回结局（否则 None）。

        只在"刚收敛"时停：否则按 ▶ 让一个已经进入周期的棋盘继续走，会被每一代都打断一次。
        """
        step = self.board.step()
        self._census.append({"gen": step.generation, "population": step.population,
                             "births": step.births, "deaths": step.deaths})
        was_settled = self._watch.settled
        outcome = self._watch.observe(self.board, step)
        self._render_live()
        if outcome != OUTCOME_RUNNING and not was_settled:
            self._pause(settled=True)
            return outcome
        return None

    def _pause(self, settled: bool = False, silent: bool = False) -> None:
        """暂停播放。``settled=True`` 表示"收敛了自动停"，``silent=True`` 表示不写状态栏。"""
        self._cancel_animation()
        self.var_playing.set(False)
        self._sync_player_buttons()
        if silent:
            return
        if settled:
            self.var_status.set(
                f"{self._watch.label}："
                + outcome_text(self._watch.outcome, self._watch.period,
                               self._watch.period_start, self.board.generation,
                               self.board.population)
            )
        else:
            self.var_status.set(f"已暂停在第 {self.board.generation} 代："
                                "可在画布上涂改，或按 ▶ 继续演化。")

    def _toggle_pause(self) -> None:
        """▶ / ⏸：生命游戏是"实时逐代演化"，没有预定的代数上限。"""
        if self._anim_job is not None or self.var_playing.get():
            self._pause()
        else:
            self.play()

    def _next_frame(self) -> None:
        """⏭ 单步：前进恰好一代（已经进入周期的棋盘也能一代一代看下去）。"""
        self._pause(silent=True)
        if self.board.population == 0:
            self.var_status.set("棋盘是空的：先按住鼠标画几个细胞，或点「生成开局」。")
            return
        self._step_board()

    def _sync_player_buttons(self) -> None:
        """按钮文字：播放中「⏸ 暂停」，暂停后「▶ 继续」，还没走过「▶ 播放」。"""
        btn = getattr(self, "btn_pause", None)
        if btn is None:
            return
        if self.var_playing.get() or self._anim_job is not None:
            btn.configure(text="⏸ 暂停")
        elif self.board.generation > 0 or self._watch.settled:
            btn.configure(text="▶ 继续")
        else:
            btn.configure(text="▶ 播放")

    # ==================================================================
    # 棋盘操作：生成 / 清空 / 涂改
    # ==================================================================
    def generate_opening(self) -> None:
        """按「开局」参数重新生成棋盘（图案 / 密度 / 种子在这里才真正生效）。"""
        self._stop_playback()
        self.board = self._new_board()
        self._reset_run()
        self._repaint(
            f"已生成开局：{self.board.pattern_name}"
            f"（{self.board.rows}×{self.board.cols}，{self.board.boundary_name}，"
            f"{self.board.rule_name}）—— 按 ▶ 播放，或继续涂改。"
        )

    def clear_board(self) -> None:
        """清空棋盘（尺寸 / 规则 / 边界都保留），方便重新画。"""
        self._stop_playback()
        self.board.clear()
        self._reset_run()
        self._repaint("已清空棋盘：按住左键在画布上拖动即可画细胞。")

    def _apply_evolution_params(self) -> None:
        """把界面上的规则 / 边界同步进棋盘（保留棋盘上的细胞）。"""
        params = options_from_ui(self.current_params())
        self.board.configure(rule=params["rule"], boundary=params["boundary"],
                             density=params["density"])

    def _load_frame(self, text: str, index: int, payload: Mapping[str, Any]) -> None:
        """用某一帧的 0/1 掩码覆盖棋盘内容（连同这一帧对应的代数）。"""
        rows = int(payload.get("rows") or self.board.rows)
        cols = int(payload.get("cols") or self.board.cols)
        if self.board.shape != (rows, cols):
            self.board.resize(rows, cols)
        self.board.load(text)
        census = payload.get("census") or []
        if index < len(census) and isinstance(census[index], Mapping):
            generation = census[index].get("gen")
            if generation is not None:
                self.board.generation = int(generation)

    # ==================================================================
    # 参数与动作
    # ==================================================================
    def _on_param_change(self, key: str) -> None:
        """行列变了必须重排棋盘；规则 / 边界作用在现有棋盘上；图案 / 密度等「生成开局」才生效。"""
        super()._on_param_change(key)
        if key in ("rows", "cols"):
            self._stop_playback()
            self.board.resize(int(self.param_value("rows") or self.board.rows),
                              int(self.param_value("cols") or self.board.cols))
            self._reset_run()
            self._repaint(
                f"棋盘已改为 {self.board.rows}×{self.board.cols}"
                "（几何变了，内容会按当前图案重排——直接画或点「生成开局」都行）。"
            )
        elif key in ("rule", "boundary"):
            self._stop_playback()
            self._apply_evolution_params()
            self._reset_run()
            self._repaint(
                f"已切换为 {self.board.rule_name} · {self.board.boundary_name}"
                "（棋盘上的细胞保留，直接播放即可）。"
            )

    def run_action(self, key: str) -> None:
        """「开始演化」在桌面上就是"从当前棋盘接着播"，与 ▶ 完全一致。"""
        if key == "evolve":
            self.play()
            return
        super().run_action(key)

    # ==================================================================
    # 钩子：徽章 / 状态栏 / 画布涂改
    # ==================================================================
    def _badge_for(self, payload: Mapping[str, Any],
                   values: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
        if not isinstance(payload, dict):
            return None
        generation = int(payload.get("generation") or 0)
        if generation <= 0 and not int(payload.get("population") or 0):
            return "空白棋盘：按住鼠标画几个细胞", NO
        outcome = payload.get("outcome")
        label = str(payload.get("outcomeLabel") or "—")
        if outcome == OUTCOME_EXTINCT:
            return f"{label}（活细胞归零）", BAD
        if outcome in (OUTCOME_STATIC, OUTCOME_CYCLE):
            return label, OK
        return f"{label}（第 {generation} 代）", NO

    def _status_for(self, payload: Mapping[str, Any], values: Mapping[str, Any],
                    partial: bool) -> Optional[str]:
        """播放中给一句"此刻怎么样"，停着的时候给结局那句话。"""
        if self.var_playing.get() or self._anim_job is not None:
            return (f"播放中… 第 {payload.get('generation')} 代：活细胞 "
                    f"{payload.get('population')} 个，本代新生 {payload.get('births')}、"
                    f"死亡 {payload.get('deaths')}。空格可暂停，暂停后可在画布上接着涂改。")
        return str(payload.get("outcomeText") or "点「▶ 播放」开始演化。")

    def _on_cell_click(self, row: int, col: int, start: bool) -> Optional[Mapping[str, Any]]:
        """按下 / 拖动：**一次拖画算一笔**（手感对齐参考实现 ``game_of_life.html``）。

        * 按下（``start=True``）：看这一格现在是死是活 —— 死就整笔画"活"，活就整笔擦"死"；
        * 拖动（``start=False``）：把经过的格子**设成**这一笔的状态（而不是翻转），
          所以按住不动、或在同几格上来回蹭，都不会反复翻转、画面也不乱跳；
        * 状态没变的格子直接返回 ``None``（不重绘），于是拖动时只画真正变化的格子。
        """
        payload = self._last
        if not isinstance(payload, dict) or payload.get("view") != "life-grid":
            return None
        index = row * self.board.cols + col
        if not (0 <= index < self.board.node_count):
            return None

        if start:
            self._pause(silent=True)          # 编辑时就停下来：免得"改的是哪一代"说不清
            self._paint_alive = not self.board.is_alive(index)
            # 棋盘被改过 -> 之前那条轨迹的历史与周期检测都作废，从这一代重新开始
            self._reset_run()
            action = "画细胞" if self._paint_alive else "擦除细胞"
            self.var_status.set(f"{action}：按住左键拖动即可连续涂改；"
                                "按 ▶ 从这一代继续演化（人口曲线会从这一代重新画）。")

        if self.board.is_alive(index) == self._paint_alive:
            return None                           # 已经是这个状态，不必重绘
        self.board.set_cell(index, self._paint_alive)
        return frame_payload(self.board)

    # ==================================================================
    # 快捷键
    # ==================================================================
    def on_key(self, key: str) -> None:
        """``R`` 生成开局；其余（空格播放/暂停、数字键触发动作）交给基类。"""
        if key.lower() == "r":
            self.generate_opening()
            return
        super().on_key(key)
