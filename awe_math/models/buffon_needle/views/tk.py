# -*- coding: utf-8 -*-
"""
蒲丰投针模型 · 桌面视图（Tkinter）
====================================

本模块是**一个非渗流模型的桌面视图**，用的是中间层骨架
:class:`~awe_math.ui.tk.kit.chart.ChartViewBase`（「参数表单 + 通用图表」）：

* 左侧参数栏由 ``spec.params`` **自动生成**，动作按钮由 ``spec.actions`` 自动生成 —— 继承即得；
* 画布怎么画、坐标轴 / 网格 / 参考线怎么摆、进度与**逐帧动画**怎么做，全部由基类负责；
* 本文件只写**声明**：每种动作返回结构的图怎么画 :attr:`CHART_SPECS`，右侧指标行怎么取
  :attr:`RESULT_ROWS` / ``ROW_SOURCES`` / ``RESULT_FORMATS``，再加三个可选小钩子。

因此这里**一行 Tk 绘图代码都没有**（对比：``percolation/views/tk.py`` 用的是渗流专化骨架，
要自己写画布钩子）。新增非渗流模型时照抄本文件即可。

三个可选钩子
------------
* :meth:`BuffonNeedleView._badge_for`：右上角结论徽章（π 估计值 + 误差）；
* :meth:`BuffonNeedleView._partial_rows`：**动态投针**进行中按"已画出的前若干根"给实时指标，
  于是 π 的估计值会随着针一根根落下而变化；
* :meth:`BuffonNeedleView._status_for`：状态栏那句人话。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

from awe_math.ui.tk.kit import (
    NO,
    OK,
    ChartSpec,
    ChartViewBase,
    register_view,
)

from ..model import PI, VIEWPORT_HEIGHT, VIEWPORT_WIDTH, estimate_pi

#: 画布上最多画多少根针（N 很大时全画会拖慢界面；超出部分只统计不绘制）
MAX_DRAW = 3000

#: 配色（与渗流视图同一套思路：基底中性灰，饱和色留给"判定关注的对象"）
COL_LINE = "#334155"      # 平行线
COL_NEEDLE = "#93a1b3"    # 未命中的针
COL_HIT = "#f59e0b"       # 命中的针
COL_PI = "#4ade80"        # 收敛曲线里的 π 参考线

EXPLAIN = (
    "说明：\n"
    "· 平行线是水平线，间距 d = 1；每根针的中心在视口内均匀分布，"
    "倾角 θ 在 [0, π) 上均匀分布；\n"
    "· 针心到最近一条线的距离 ≤ (L/2)·sin θ 时与线相交；\n"
    "· 理论命中概率（L ≤ d）= 2L/(πd)，于是 π ≈ 2LN/(dH)；\n"
    "· 「投针一次」会动态投针：针从零开始逐根出现（左侧「动画间隔」可调速），"
    "指标随针数实时刷新；\n"
    "· 投针越多估计越准（误差 ≈ 1/√N），但这是个随机试验，结果只会「接近」π "
    "而不等于它；命中数为 0 时无法反解 π。\n"
    f"· 投针根数超过 {MAX_DRAW} 时，画布上只绘出前 {MAX_DRAW} 根（统计仍按全部计算）。"
)


@register_view("buffon_needle")
class BuffonNeedleView(ChartViewBase):
    """蒲丰投针的可视化视图（中间层骨架 + 声明式图表）。"""

    HINTS = "空格 播放/暂停    R 重新投针    1/2 也可触发左侧动作"
    INTRO_STATUS = "就绪：点「投针一次」随机投针，用命中率估计 π（π ≈ 2LN/(dH)）。"
    FALLBACK_ACCENT = "#f59e0b"
    EXPLAIN = EXPLAIN

    # ---------------- 右侧指标行（声明即可，不必写刷新代码） ----------------
    RESULT_ROWS: Tuple[Tuple[str, str], ...] = (
        ("投针根数 N", "n"),
        ("命中根数 H", "hits"),
        ("实测命中率", "rate"),
        ("理论命中率 2L/(πd)", "theory"),
        ("π 估计值", "pi"),
        ("绝对误差", "err"),
        ("耗时", "cost"),
    )
    #: 指标行取值来自 payload 的哪个键
    ROW_SOURCES: Mapping[str, str] = {
        "n": "throws", "hits": "hits", "rate": "hitRate", "theory": "theoryRate",
        "pi": "piEstimate", "err": "absError", "cost": "elapsedMs",
    }
    #: 指标行的格式化模板
    RESULT_FORMATS: Mapping[str, str] = {
        "rate": "{:.4f}", "theory": "{:.4f}", "pi": "{:.5f}",
        "err": "{:.5f}", "cost": "{:.1f} ms",
    }

    # ---------------- 图表声明：payload["view"] -> 怎么画 ----------------
    CHART_SPECS: Mapping[str, ChartSpec] = {
        # 投针布局：线段云（中心 + 夹角 + 长度），命中按 0/1 掩码着色
        "buffon-needle": ChartSpec(
            kind="segments",
            title="投针布局",
            caption="L/d = {ratio:.2f} · 投 {throws} 根 · 命中 {hits} 根",
            x="xs", y="ys", theta="thetas", length="length", flag="hitsMask",
            xlim=(0.0, VIEWPORT_WIDTH), ylim=(0.0, VIEWPORT_HEIGHT), grid=1.0,
            color=COL_NEEDLE, flag_color=COL_HIT, grid_color=COL_LINE,
            limit=MAX_DRAW,
            animate=True,                     # 针从零开始逐个出现
        ),
        # 收敛过程：曲线族 + π 参考线
        "buffon-converge": ChartSpec(
            kind="series",
            title="π 的收敛过程",
            records="samples", x_field="throws", y_fields=("estimate",),
            ref=PI, ref_label=f"π = {PI:.4f}",
            x_label="累计投针数 →", y_label="π 估计值",
            color=COL_HIT, ref_color=COL_PI, grid_color=COL_LINE,
            rows={"n": "totalThrows", "hits": "totalHits", "rate": "hitRate",
                  "theory": "theoryRate", "pi": "piEstimate", "err": "absError",
                  "cost": "elapsedMs"},
        ),
    }

    # ==================================================================
    # 钩子一：结论徽章
    # ==================================================================
    def _badge_for(self, payload: Mapping[str, Any],
                   values: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
        pi_hat = values.get("pi")
        if pi_hat is None:
            return "命中为 0，无法估计 π", NO
        err = values.get("err")
        ok = isinstance(err, (int, float)) and err <= 0.1
        return f"π ≈ {float(pi_hat):.4f}（误差 {float(err):.4f}）", OK if ok else NO

    # ==================================================================
    # 钩子二：动画进行中的实时指标（按"已画出的前 drawn 根针"统计）
    # ==================================================================
    def _partial_rows(self, payload: Mapping[str, Any],
                      drawn: int) -> Optional[Mapping[str, Any]]:
        mask = str(payload.get("hitsMask") or "")
        shown = max(0, min(drawn, len(mask)))
        hits = mask.count("1", 0, shown)
        length = float(payload.get("length") or 0.0)
        gap = float(payload.get("gap") or 1.0)
        pi_hat = estimate_pi(length, gap, shown, hits)
        return {
            "n": shown,
            "hits": hits,
            "rate": hits / shown if shown else 0.0,
            "theory": payload.get("theoryRate"),
            "pi": pi_hat,
            "err": None if pi_hat is None else abs(pi_hat - PI),
            "cost": payload.get("elapsedMs"),
        }

    # ==================================================================
    # 钩子三：状态栏文案
    # ==================================================================
    def _status_for(self, payload: Mapping[str, Any], values: Mapping[str, Any],
                    partial: bool) -> Optional[str]:
        if payload.get("view") == "buffon-converge":
            n, hits = values.get("n") or 0, values.get("hits") or 0
            pi_text = self.vals["pi"].get()
            return (f"多组重复完成：累计投针 {n} 根、命中 {hits} 根，π ≈ {pi_text}。")
        if partial:
            return (f"投针中… 已投 {values.get('n')} 根，命中 {values.get('hits')} 根，"
                    f"π 当前估计 {self.vals['pi'].get()}。")
        n, hits = values.get("n") or 0, values.get("hits") or 0
        note = f"（画布只绘出前 {MAX_DRAW} 根）" if n > MAX_DRAW else ""
        if values.get("pi") is None:
            return f"投针完成：{n} 根、命中 {hits} 根{note}；命中率为 0，无法反解 π。"
        return (f"投针完成：{n} 根、命中 {hits} 根"
                f"（{values.get('rate')} vs 理论 {values.get('theory')}）{note}，"
                f"π ≈ {self.vals['pi'].get()}（误差 {self.vals['err'].get()}）。")

    # ==================================================================
    # 首屏与快捷键
    # ==================================================================
    def _after_build(self) -> None:
        self.var_caption.set("投针区（视口 12 × 8 个线距）")
        self._draw_message("点左侧「投针一次」开始")
        actions = tuple(getattr(self.spec, "actions", ()) or ())
        if actions:      # 进来先自动投一次，用户立刻能看到动态投针
            self._first_job = self.root.after(60, lambda: self.run_action(actions[0].key))

    def on_key(self, key: str) -> None:
        """``R`` 重新投针；其余（空格播放/暂停、数字键触发动作）交给基类。"""
        if key.lower() == "r":
            actions = tuple(getattr(self.spec, "actions", ()) or ())
            if actions:
                self.run_action(actions[0].key)
            return
        super().on_key(key)
