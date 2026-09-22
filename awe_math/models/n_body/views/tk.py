# -*- coding: utf-8 -*-
"""
万有引力多星模型 · 桌面视图（Tkinter）
========================================
这是本项目第一个**连续时间动力学**模型的桌面视图：画布上要看到的是"一簇会动的点 +
它们拖出的轨迹"，而不是网格、曲线或线段云。工具箱现成的五种图元（线段云 / 曲线族 /
柱状 / 栅格 / 文字）都没有覆盖这个范式，所以本视图继承通用图表骨架
:class:`~awe_math.ui.tk.kit.chart.ChartViewBase`（参数表单、动作按钮、侧栏顶部的
「动画 / 播放」卡片、右侧指标行与徽章都由基类给），只把**画布**这一层自己补上：

* 声明一个自己的图种 ``kind="orbits"``，并覆盖 :meth:`NBodyView._draw`；
* 播放（▶ / ⏸ / ⏭）走**自己的循环**（``_tick``），因为它的时间轴来自物理积分，
  而不是"预先算好的一段帧序列" —— 同生命游戏的做法：一边算一边画，不设帧数上限。

界面构成
--------
* **左侧栏顶部**：播放卡片 —— `▶ 播放 / ⏸ 暂停`、`⏭ 下一帧`、`↺ 重置模拟`、动画间隔滑块；
* **左侧栏参数区**：场景 / 积分 / 轨迹 / 随机性四组参数（由 ``spec.params`` 自动生成）；
* **左侧栏底部**：「视图」卡片（缩放 / 平移的说明 + `⌖ 恢复视图`）与
  「星体编辑」卡片（选中哪一颗、质量滑块、◀ / ▶ 轮换）；
* **中央画布**：星体（大小与颜色随质量）+ 轨迹带（按星体着色、末段渐隐）+ 质心十字；
  选中的星体会戴上高亮环并标出质量；
* **右侧面板**：结论徽章 + 指标行（守恒量）+ **能量漂移曲线**（E − E₀ 随 t 的实时曲线
  —— 曲线贴着 0 线振荡、"鼓包"越小，积分器越准）。

画布交互
--------
=========================  ==================================================================
操作                        行为
=========================  ==================================================================
滚轮                        以光标为中心缩放（手动视角）
按住左键拖动空白处          平移视角（右键拖动同样可以，播放中也能用）
点击星体                    选中它（会自动暂停：编辑时会改动物理）
按住左键拖动星体            把它挪到光标处（速度不变）
点击 ◀ / ▶ 或空白处后滚轮    切换 / 缩放，不必非打中一颗正在飞的星
=========================  ==================================================================

四条约定
--------
1. **画面不追逃逸者**：自动视角下半径只增不减，且星多时取半径的 90% 分位数
   （上限为初值的 :data:`CAM_GROW_MAX` 倍）—— 被甩出去的那几颗会飞出视野，但主体始终
   看得清。这正是"星团抛射"该有的样子，而不是让视角被一颗远方的星拖到失焦；
   手动缩放 / 平移之后由你说了算，点 `⌖ 恢复视图` 才回到自动视角；
2. **参数改动分两类**：改场景 / 星体数 / dt / ε / 种子会**重置初值**（它们改变的是
   被积分的物理本身）；改轨迹点数只改画面；改子步数只改动画快慢。改轨迹 / 子步数不打断播放；
3. **编辑星体会重开一段轨迹**：拖动位置或改质量都改变了被积分的系统，所以播放会暂停、
   能量基准 ``E₀`` 重新锚定到"当前状态"、曲线从这一刻重新开始 —— 与生命游戏里
   "涂改会让人口曲线从这一代重来"是同一个道理；
4. **数值爆炸就明说**：近距遭遇把速度打到 inf/NaN 时模型会标记 ``blown_up``，
   播放自动停下、徽章与状态栏提示"减小 dt 或增大 ε"，而不是抛一个 traceback。
"""

from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from awe_math.ui.tk.kit import (
    BAD,
    NO,
    OK,
    BG_CANVAS,
    ChartSpec,
    ChartViewBase,
    register_view,
)
from awe_math.ui.tk.theme import BORDER, DIM, FAINT, FONT_SM, lerp_color

from ..model import SCENARIOS, SCENARIO_LABELS
from ..spec import build_nbody, options_from_ui, snapshot_payload

# ----------------------------------------------------------------------
# 配色与尺寸
# ----------------------------------------------------------------------
#: 星体调色板（星体少时按序号取色，一眼能分清谁是谁）
PALETTE: Tuple[str, ...] = (
    "#fca5a5", "#fdba74", "#fde68a", "#86efac", "#7dd3fc", "#c4b5fd",
    "#f9a8d4", "#a7f3d0", "#93c5fd", "#fcd34d",
)
#: 星体多时按质量上色：轻星偏冷（蓝）、重星偏暖（黄白）
STAR_COLD = (125, 211, 252)          # #7dd3fc
STAR_HOT = (253, 230, 138)           # #fde68a
#: 质心十字
COL_CENTER = "#334155"

#: 质心十字之外的第二种参考色：选中星体的高亮环
COL_SELECT = "#f0abfc"
#: 视角上限：自动视角最多允许放大到初值视野的多少倍（再大就只剩"一颗远星"了）
CAM_GROW_MAX = 5.0
#: 手动缩放的范围（相对于初值视野半径）：下限太小会把整幅画面糊成一坨
CAM_ZOOM_MIN = 0.05
CAM_ZOOM_MAX = 20.0
#: 每条轨迹最多画多少个点（再多就抽样，否则大星团每帧都要画几万段折线）
TRAIL_DRAW_MAX = 240
#: 能量曲线的高度、最多画多少个点、以及最多保留多少个历史点。
#:
#: 历史点数是**滑动窗口**的宽度：保留得越多、横轴显示的时间跨度越长，否则曲线会
#: 越画越密。横轴始终铺满"当前保留下来的这一段"（见 :meth:`_update_energy_curve`），
#: 所以时间再长也不会把曲线挤到右边一角。
CURVE_HEIGHT = 132
CURVE_MAX_POINTS = 400
CURVE_HISTORY_MAX = CURVE_MAX_POINTS * 4
#: 星体编辑的质量范围（滑块按对数映射，于是跨五个数量级也能调得动）
MASS_MIN = 1e-4
MASS_MAX = 5.0
#: 点击"命中"星体的宽容像素：星体本身只有几个像素，不多给一点就点不中
PICK_SLOP = 5.0

EXPLAIN = (
    "怎么玩：\n"
    "· **场景**是初值库：8 字三体（精确周期解，转一圈回到出发点）/ 双星 + 行星 / "
    "太阳 + 四行星 / 随机星团（混沌，会被甩出个别星体）/ 星系盘；\n"
    "· **▶ 播放**逐帧推进（可暂停 / 单步 / 调速）—— 动画间隔只管快慢，"
    "「每帧子步数」才决定一帧推进多少物理时间；\n"
    "· **轨迹**是每颗星的历史位置（「轨迹点数」控制长短）：轨道形状、"
    "双星的抖动、星团的散开，都直接画在尾迹上；\n"
    "· **守恒量**在右侧：能量曲线画的是 E − E₀，贴着 0 线小幅振荡就说明积分器稳，"
    "鼓包越大越说明 dt 该减小；总动量与角动量应当基本不变；\n"
    "· **看细节**：滚轮缩放、按住拖动空白处平移、点 `⌖ 恢复视图` 回到自动视角；\n"
    "· **动手改**：点一下星体即可选中（会自动暂停），拖动它换位置、"
    "拉「星体编辑」里的滑块改质量；改完 E₀ 会重新锚定，曲线从这一刻重画；\n"
    "· **ε = 0 是严格牛顿引力**（8 字三体这类精确解必须用 0）；随机星团建议 ε ≥ 0.1，"
    "否则近距遭遇会让速度发散 —— 那时徽章会提示「数值爆炸」，请减小 dt 或增大 ε；\n"
    "· 混沌场景换个随机种子就会走出一条完全不同的历史：这不是 bug，而是本模型要展示的结论。"
)


@register_view("n_body")
class NBodyView(ChartViewBase):
    """万有引力多星视图（星体 + 轨迹带 + 实时播放 + 缩放 / 平移 / 星体编辑 + 能量漂移曲线）。"""

    HINTS = ("空格 播放/暂停    R 重置模拟    1 开始模拟    "
             "滚轮缩放 · 拖动平移 · 点击星体选中并拖动")
    INTRO_STATUS = "就绪：按 ▶ 播放让星体跑起来（8 字三体会转出一圈闭合的轨道）。"
    FALLBACK_ACCENT = "#c084fc"
    EXPLAIN = EXPLAIN
    #: 默认 40 毫秒/帧（≈25 帧/秒）：既能看清轨道，也不至于慢得无聊
    SPEED_DEFAULT = 40

    # ---------------- 右侧指标行（声明即可，不必写刷新代码） ----------------
    RESULT_ROWS: Tuple[Tuple[str, str], ...] = (
        ("星体数 N", "count"),
        ("仿真步数", "steps"),
        ("仿真时间 t", "time"),
        ("总能量 E", "energy"),
        ("能量相对漂移", "drift"),
        ("全过程最大漂移", "maxDrift"),
        ("总动量 |P|", "momentum"),
        ("角动量 L", "angular"),
        ("逃逸星体", "escaped"),
        ("每帧耗时", "cost"),
    )
    ROW_SOURCES: Mapping[str, str] = {
        "count": "count", "steps": "steps", "time": "time",
        "energy": "energy", "drift": "energyDrift", "maxDrift": "maxDrift",
        "momentum": "momentum", "angular": "angularMomentum",
        "escaped": "escaped", "cost": "costMs",
    }
    RESULT_FORMATS: Mapping[str, str] = {
        "time": "{:.2f}", "energy": "{:.6f}", "drift": "{:.2e}",
        "maxDrift": "{:.2e}", "momentum": "{:.2e}", "angular": "{:.4f}",
        "cost": "{:.2f} ms",
    }

    # ---------------- 图表声明：payload["view"] -> 怎么画 ----------------
    #: ``kind="orbits"`` 是本视图自己声明的图种（见 :meth:`_draw`）：
    #: ``animate=True`` 只是让基类把侧栏顶部的「动画 / 播放」卡片建出来 ——
    #: 时间轴由本视图自己的积分循环驱动，基类的"逐帧显示"在这里用不上。
    CHART_SPECS: Mapping[str, ChartSpec] = {
        "nbody-orbit": ChartSpec(
            kind="orbits",
            title="多星运动",
            caption="{scenarioName} · N = {count} · 第 {steps} 步 · t = {time:.2f}"
                    " · 能量漂移 {energyDrift:.1e}",
            animate=True,
        ),
    }

    # ==================================================================
    # 状态：一个可以被反复推进的模型 + 只增不减的视角
    # ==================================================================
    def _setup_state(self) -> None:
        super()._setup_state()
        self._elapsed_ms = 0.0
        #: 表单还没建好，这里取到的是 spec.params 的默认值（8 字三体）
        self.body = self._new_body()
        self._energy_history: List[Tuple[float, float]] = []
        #: 能量曲线的基准（曲线画的是 E − 这个值）；编辑星体后重新锚定
        self._curve_base = self.body.initial_energy
        #: 视角：中心 + 半径，以及"自动 / 手动"两种模式
        self._cam_center = np.zeros(2)
        self._cam_radius = 1.0
        self._cam_radius0 = 1.0
        self._cam_max = 1.0
        self._cam_manual = False
        #: 选中的星体下标（None = 未选中）与鼠标拖拽状态
        self._selected: Optional[int] = None
        self._drag_mode: Optional[str] = None
        self._drag_moved = False
        self._last_pan: Tuple[int, int] = (0, 0)
        #: 同步质量滑块时置位：避免"程序设置滑块"被当成"用户改质量"
        self._mass_syncing = False
        self._reset_camera()
        self._energy_history.append((self.body.time, self.body.initial_energy))

    def _new_body(self):
        """按界面上的当前参数造模型实例（下拉框给的是中文标签，先翻成内部取值）。"""
        return build_nbody(options_from_ui(self.current_params()))

    def _after_build(self) -> None:
        self._bind_canvas_events()
        self._render_live()
        # 进来就先跑起来：星体不动的话，这个模型什么也说明不了
        self._first_job = self.root.after(80, self.play)

    def _bind_canvas_events(self) -> None:
        """画布上的鼠标交互。

        ``<Button-1>`` / ``<B1-Motion>`` 由基类绑到 :meth:`_on_canvas_click` /
        :meth:`_on_canvas_drag`（本视图覆盖了那两个方法），其余在这里补：
        右键 / 中键平移、滚轮缩放、松开鼠标收尾。
        """
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        for button in ("2", "3"):
            self.canvas.bind(f"<Button-{button}>", self._on_pan_press)
            self.canvas.bind(f"<B{button}-Motion>", self._on_pan_drag)
            self.canvas.bind(f"<ButtonRelease-{button}>", self._on_canvas_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)

    # ==================================================================
    # 视角：自动跟随（只增不减） + 手动缩放 / 平移
    # ==================================================================
    def _body_fit(self) -> Tuple[np.ndarray, float]:
        """星体"主体"的中心与它需要的视野半径。

        星少（≤ 8 颗）时看最大值 —— 每一颗都得看见；星多时改用半径的 90% 分位数：
        随机星团里被抛出的那一两颗会把最大值一路拉大，主体于是缩成一个点。
        """
        center = np.asarray(self.body.center_of_mass(), dtype=float)
        centered = self.body.pos - center
        radius = np.hypot(centered[:, 0], centered[:, 1])
        count = max(self.body.count, 1)
        if count <= 8:
            needed = float(np.max(radius))
        else:
            needed = float(np.quantile(radius, min(0.9, 1.0 - 1.5 / count)))
        if not math.isfinite(needed):
            needed = 1.0
        return center, max(needed * 1.2, 0.6)

    def _reset_camera(self) -> None:
        """回到自动视角：对准星体主体，并记下"初值视野半径"作为缩放的标尺。"""
        center, radius = self._body_fit()
        self._cam_center = np.array(center, dtype=float)
        self._cam_radius = radius
        self._cam_radius0 = radius
        self._cam_max = radius * CAM_GROW_MAX
        self._cam_manual = False

    def _update_camera(self) -> None:
        """自动视角：只增不减地装下主体（视角一晃，轨道就看不清了）。

        手动缩放 / 平移之后不再自动跟随 —— 由用户说了算，直到点 `⌖ 恢复视图`。
        """
        if self._cam_manual:
            return
        centered = self.body.pos - self._cam_center
        radius = np.hypot(centered[:, 0], centered[:, 1])
        count = max(self.body.count, 1)
        if count <= 8:
            needed = float(np.max(radius)) * 1.2
        else:
            quantile = min(0.9, 1.0 - 1.5 / count)
            needed = float(np.quantile(radius, max(0.0, quantile))) * 1.2
        if not math.isfinite(needed):
            return                      # 数值已经发散：视角保持在发散前的状态
        if needed > self._cam_radius:
            self._cam_radius = min(needed, self._cam_max)

    def _fit_camera(self) -> Tuple[float, float, float]:
        """把视角换算成 ``(scale, ox, oy)``：屏幕坐标 = 值 · scale + o。"""
        width = max(self.canvas.winfo_width(), 80)
        height = max(self.canvas.winfo_height(), 80)
        pad = 18.0
        radius = max(self._cam_radius, 1e-9)
        scale = min((width - 2 * pad) / (2 * radius), (height - 2 * pad) / (2 * radius))
        scale = max(scale, 1e-9)
        cx, cy = float(self._cam_center[0]), float(self._cam_center[1])
        return scale, width / 2.0 - cx * scale, height / 2.0 - cy * scale

    def _world_to_screen(self, x: float, y: float) -> Tuple[float, float]:
        """世界坐标 -> 画布像素（与 :meth:`_draw_orbits` 用的是同一套换算）。"""
        scale, ox, oy = self._fit_camera()
        return ox + float(x) * scale, oy + float(y) * scale

    def _screen_to_world(self, px: float, py: float) -> Tuple[float, float]:
        """画布像素 -> 世界坐标（拖动星体、以光标为中心缩放都靠它）。"""
        scale, ox, oy = self._fit_camera()
        return (px - ox) / scale, (py - oy) / scale

    def _pan_by_pixels(self, dx: float, dy: float) -> None:
        """按像素平移视角：手往右拖，画面跟着往右走。"""
        scale, _ox, _oy = self._fit_camera()
        self._cam_center = self._cam_center - np.array([dx / scale, dy / scale])
        self._cam_manual = True

    def _zoom_at(self, px: float, py: float, factor: float) -> None:
        """以光标为中心缩放：让光标下的那个世界点保持在原地。"""
        wx, wy = self._screen_to_world(px, py)
        floor = self._cam_radius0 * CAM_ZOOM_MIN
        ceiling = self._cam_radius0 * CAM_ZOOM_MAX
        radius = min(ceiling, max(floor, self._cam_radius * float(factor)))
        if radius == self._cam_radius:
            return
        self._cam_radius = radius
        self._cam_manual = True
        width = max(self.canvas.winfo_width(), 80)
        height = max(self.canvas.winfo_height(), 80)
        scale, _ox, _oy = self._fit_camera()
        # 要让 sx(wx) = px（sx = (x − cx)·scale + W/2），解得 cx = wx − (px − W/2)/scale
        self._cam_center = np.array([wx - (px - width / 2.0) / scale,
                                     wy - (py - height / 2.0) / scale])

    def _restore_view(self) -> None:
        """`⌖ 恢复视图`：回到自动视角（重新对准星体主体、重新允许自动放大）。"""
        self._reset_camera()
        self._render_live()
        self.var_status.set("已恢复视图：自动跟随星体主体（滚轮缩放 / 拖动平移随时可用）。")

    # ==================================================================
    # 画布交互：缩放 / 平移 / 选中并编辑星体
    # ==================================================================
    def _on_canvas_click(self, event) -> None:
        """左键：点在星体上 = 选中它（接着拖动就是移动它）；点在空白处 = 平移视角。"""
        self._drag_moved = False
        index = self._pick_star(event.x, event.y)
        if index is None:
            self._drag_mode = "pan"
            self._last_pan = (event.x, event.y)
            return
        self._select_star(index)
        self._drag_mode = "star"

    def _on_canvas_drag(self, event) -> None:
        """按住左键拖动：选中的星体跟着光标走；空白处则平移视角。"""
        if self._drag_mode == "star":
            self._move_selected_to(event.x, event.y)
        elif self._drag_mode == "pan":
            self._on_pan_drag(event)

    def _on_canvas_release(self, _event=None) -> None:
        """松开鼠标：只有**真的拖动过**才报"移动了 / 平移了"，纯点击不喧宾夺主。"""
        mode, self._drag_mode = self._drag_mode, None
        moved, self._drag_moved = self._drag_moved, False
        if not moved:
            return
        if mode == "star" and self._selected is not None:
            x, y = self.body.pos[self._selected]
            self.var_status.set(
                f"第 {self._selected + 1} 颗星已移动到 ({x:.2f}, {y:.2f})："
                "能量基准已重新锚定，按 ▶ 从这一状态继续演化。")
        elif mode == "pan":
            self.var_status.set("视角已平移 —— `⌖ 恢复视图` 可以回到自动视角。")

    def _on_pan_press(self, event) -> None:
        """右键 / 中键按下：开始平移（播放中也允许，看轨道时很有用）。"""
        self._drag_mode = "pan"
        self._drag_moved = False
        self._last_pan = (event.x, event.y)

    def _on_pan_drag(self, event) -> None:
        if self._drag_mode != "pan":
            self._drag_mode = "pan"
            self._last_pan = (event.x, event.y)
            return
        dx = event.x - self._last_pan[0]
        dy = event.y - self._last_pan[1]
        self._last_pan = (event.x, event.y)
        if dx or dy:
            self._drag_moved = True
            self._pan_by_pixels(dx, dy)
            self._render_live()

    def _on_wheel(self, event) -> str:
        """滚轮缩放（以光标为中心）。一次滚轮 ``delta`` 是 ±120，用指数保证手感线性。"""
        try:
            delta = int(getattr(event, "delta", 0) or 0)
        except (TypeError, ValueError):
            delta = 0
        if delta:
            self._zoom_at(event.x, event.y, 0.85 ** (delta / 120.0))
            self._render_live()
        return "break"

    # ------------------------------------------------------------------
    # 选中星体
    # ------------------------------------------------------------------
    def _pick_star(self, px: float, py: float) -> Optional[int]:
        """画布像素 -> 星体下标（几像素内算命中）；没打中返回 ``None``（交给平移）。"""
        radius = self._star_radii([float(m) for m in self.body.mass], self.body.count)
        best: Optional[int] = None
        best_distance = 0.0
        for index in range(self.body.count):
            x, y = self._world_to_screen(self.body.pos[index, 0], self.body.pos[index, 1])
            distance = math.hypot(x - px, y - py)
            if distance <= radius[index] + PICK_SLOP and (best is None or distance < best_distance):
                best, best_distance = index, distance
        return best

    def _select_star(self, index: Optional[int]) -> None:
        """选中 / 取消选中某颗星（越界或 ``None`` 都表示取消）。"""
        if index is not None and not 0 <= int(index) < self.body.count:
            index = None
        self._selected = None if index is None else int(index)
        self._refresh_selection_ui()
        self._render_live()
        if self._selected is None:
            self.var_status.set("已取消选中。")
        else:
            self.var_status.set(
                f"已选中第 {self._selected + 1} 颗星（质量 "
                f"{float(self.body.mass[self._selected]):.4g}）：在画布上拖动它换位置，"
                "或用左侧「星体编辑」的滑块改质量。")

    def _cycle_selection(self, step: int) -> None:
        """◀ / ▶：按顺序轮换选中（不必非要点中一颗正在飞的星）。"""
        if self.body.count <= 0:
            return
        if self._selected is None:
            index = 0 if step >= 0 else self.body.count - 1
        else:
            index = (self._selected + step) % self.body.count
        self._select_star(index)

    def _refresh_selection_ui(self) -> None:
        """把"选中了哪一颗 / 它有多重"同步到侧栏卡片（含滑块位置）。"""
        var_selected = getattr(self, "var_selected", None)
        if var_selected is None:            # 卡片还没建好（_setup_state 阶段）
            return
        scale = getattr(self, "scale_mass", None)
        if self._selected is None:
            var_selected.set("未选中（点一下画布上的星体）")
            self.var_mass_edit.set("—")
            if scale is not None:
                self._mass_syncing = True
                scale.state(["disabled"])
                self._mass_syncing = False
            return
        mass = float(self.body.mass[self._selected])
        var_selected.set(f"已选中第 {self._selected + 1} 颗（共 {self.body.count} 颗）")
        self.var_mass_edit.set(f"{mass:.4g}")
        if scale is not None:
            self._mass_syncing = True
            scale.state(["!disabled"])
            scale.set(self._mass_to_scale(mass))
            self._mass_syncing = False

    # ------------------------------------------------------------------
    # 编辑星体：位置（拖动）与质量（滑块）
    # ------------------------------------------------------------------
    def _move_selected_to(self, px: float, py: float) -> None:
        """把选中的星体拖到光标处（速度不变），并重新锚定能量基准。"""
        if self._selected is None:
            return
        self._pause(silent=True)
        wx, wy = self._screen_to_world(px, py)
        self.body.move_star(self._selected, wx, wy)
        self._drag_moved = True
        self._apply_edit()

    def _on_mass_scale(self, value: str) -> None:
        """质量滑块（对数映射）：改的是被积分的物理，所以每改一次都重新锚定基准。"""
        if self._mass_syncing or self._selected is None:
            return
        try:
            mass = self._scale_to_mass(float(value))
        except (TypeError, ValueError):
            return
        self._pause(silent=True)
        self.body.set_mass(self._selected, mass)
        self._apply_edit(f"已把第 {self._selected + 1} 颗星的质量改为 {mass:.4g}。")

    def _apply_edit(self, status: Optional[str] = None) -> None:
        """星体被改过之后：重锚能量基准、曲线从这一刻重画、重绘画面。

        为什么要重锚：能量漂移是"相对初值"的量，初值被改过之后旧的 E₀ 就不再属于
        这条轨迹了 —— 不重锚的话右侧会显示一个巨大的假漂移。
        """
        self.body.rebase()
        self._curve_base = self.body.initial_energy
        self._energy_history = [(self.body.time, self.body.total_energy())]
        self._refresh_selection_ui()
        self._render_live()
        if status:
            self.var_status.set(status)

    @staticmethod
    def _mass_to_scale(mass: float) -> float:
        """质量 -> 滑块位置 ``[0, 1]``（对数映射，跨五个数量级也好调）。"""
        low, high = math.log(MASS_MIN), math.log(MASS_MAX)
        value = min(high, max(low, math.log(max(MASS_MIN, float(mass)))))
        return (value - low) / (high - low)

    @staticmethod
    def _scale_to_mass(position: float) -> float:
        """滑块位置 ``[0, 1]`` -> 质量（与 :meth:`_mass_to_scale` 互逆）。"""
        low, high = math.log(MASS_MIN), math.log(MASS_MAX)
        value = min(1.0, max(0.0, float(position)))
        return math.exp(low + (high - low) * value)

    # ==================================================================
    # 播放：一边积分一边画（不预设帧数上限）
    # ==================================================================
    def play(self) -> None:
        """▶ 开始（或继续）播放：逐帧推进积分，直到你按暂停（或数值爆炸）。"""
        if self._anim_job is not None:
            return
        if self.body.blown_up:
            self.var_status.set("数值已发散：按「↺ 重置模拟」回到初值，"
                                "并减小 dt 或增大 ε。")
            return
        self.var_playing.set(True)
        self._sync_player_buttons()
        self._tick()

    def _tick(self) -> None:
        """播放循环的一步：推进一帧 -> 刷新画面 -> 排下一次。"""
        self._anim_job = None
        if not self._alive:
            return
        self._step_once()
        if self.body.blown_up:
            self._pause(blown=True)
            return
        delay = max(1, min(self.SPEED_MAX, int(self.var_speed.get())))
        self._anim_job = self.root.after(delay, self._tick)

    def _step_once(self) -> None:
        """推进一帧（``substeps`` 个子步），刷新画面与曲线。"""
        subs = int(self.param_value("substeps") or 1)
        started = time.perf_counter()
        self.body.advance(subs)
        self._elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._energy_history.append((self.body.time, self.body.total_energy()))
        if len(self._energy_history) > CURVE_HISTORY_MAX:
            del self._energy_history[0:len(self._energy_history) - CURVE_HISTORY_MAX]
        self._update_camera()
        self._render_live()

    def _pause(self, blown: bool = False, silent: bool = False) -> None:
        """暂停播放。``blown=True`` 表示"数值爆炸自动停"，``silent=True`` 表示不写状态栏。"""
        self._cancel_animation()
        self.var_playing.set(False)
        self._sync_player_buttons()
        if silent:
            return
        if blown:
            self.var_status.set(
                "⚠ 数值爆炸：近距遭遇把速度打到了 inf/NaN —— "
                "请减小 dt、增大软化半径 ε，或换一个随机种子（按 ↺ 重置重来）。"
            )
        else:
            self.var_status.set(f"已暂停在第 {self.body.steps} 步（t = {self.body.time:.2f}）："
                                "可调参数、看曲线，或按 ▶ 继续。")

    def _toggle_pause(self) -> None:
        """▶ / ⏸：多星模型是"实时积分"，没有预定的帧数上限。"""
        if self._anim_job is not None or self.var_playing.get():
            self._pause()
        else:
            self.play()

    def _next_frame(self) -> None:
        """⏭ 单步：前进恰好一帧（暂停状态下逐步细看）。"""
        self._pause(silent=True)
        if self.body.blown_up:
            self.var_status.set("数值已发散：按「↺ 重置模拟」回到初值。")
            return
        self._step_once()

    def _sync_player_buttons(self) -> None:
        """按钮文字：播放中「⏸ 暂停」，暂停后「▶ 继续」，还没走过「▶ 播放」。"""
        btn = getattr(self, "btn_pause", None)
        if btn is None:
            return
        if self.var_playing.get() or self._anim_job is not None:
            btn.configure(text="⏸ 暂停")
        elif self.body.steps > 0:
            btn.configure(text="▶ 继续")
        else:
            btn.configure(text="▶ 播放")

    def _speed_hint(self) -> str:
        """「动画间隔」滑块说明：这里的时间轴来自物理积分，不是预先算好的帧序列。"""
        return ("越小越流畅：每一帧推进「每帧子步数」个子步，间隔即相邻两帧之间的停顿。"
                "想细看某一段就用「⏸ 暂停」+「⏭ 下一帧」。")

    # ==================================================================
    # 侧栏：播放卡片里的「重置模拟」
    # ==================================================================
    def _build_player_extra(self, parent: tk.Widget) -> None:
        self.btn_reset = ttk.Button(parent, text="↺ 重置模拟", command=self.reset_simulation)
        self.btn_reset.pack(fill="x", pady=(0, 6))
        self._action_buttons.append(self.btn_reset)

    # ==================================================================
    # 侧栏底部：「视图」与「星体编辑」两张卡片
    # ==================================================================
    def _build_extra_cards(self, parent: tk.Widget) -> None:
        view_card = self._card(parent, "视图")
        ttk.Button(view_card, text="⌖ 恢复视图", command=self._restore_view).pack(fill="x")
        ttk.Label(view_card,
                  text="滚轮缩放；按住左键拖动空白处平移（右键 / 中键同样可以，"
                       "播放中也生效）；点击星体选中后可直接拖动它。",
                  style="CardDim.TLabel", font=FONT_SM, wraplength=252,
                  justify="left").pack(anchor="w", pady=(6, 0))

        card = self._card(parent, "星体编辑")
        self.var_selected = tk.StringVar(value="未选中（点一下画布上的星体）")
        ttk.Label(card, textvariable=self.var_selected, style="Card.TLabel",
                  wraplength=252, justify="left").pack(anchor="w")
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 0))
        for text, step in (("◀ 上一颗", -1), ("下一颗 ▶", 1)):
            ttk.Button(row, text=text, command=lambda s=step: self._cycle_selection(s)).pack(
                side="left", expand=True, fill="x", padx=(0, 6) if step < 0 else (0, 0))

        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x", pady=(8, 0))
        ttk.Label(head, text="质量 m（对数滑块）", style="Card.TLabel").pack(side="left")
        self.var_mass_edit = tk.StringVar(value="—")
        ttk.Label(head, textvariable=self.var_mass_edit,
                  style="MonoAccent.TLabel").pack(side="right")
        self.scale_mass = ttk.Scale(card, from_=0.0, to=1.0, length=200,
                                    command=self._on_mass_scale, state="disabled")
        self.scale_mass.pack(fill="x", pady=(2, 0))
        ttk.Button(card, text="✕ 取消选中",
                   command=lambda: self._select_star(None)).pack(fill="x", pady=(6, 0))
        ttk.Label(card,
                  text="拖动位置或改质量都会暂停播放，并把能量基准 E₀ 重新锚定到当前状态"
                       "（曲线从这一刻重画）。",
                  style="CardDim.TLabel", font=FONT_SM, wraplength=252,
                  justify="left").pack(anchor="w", pady=(6, 0))

    # ==================================================================
    # 右侧：能量漂移曲线（面板，不是另一个动作）
    # ==================================================================
    def _build_right_extra(self, panel: tk.Widget, row: int) -> int:
        ttk.Separator(panel, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(10, 6))
        ttk.Label(panel, text="能量漂移 E − E₀（贴着 0 线 = 守恒）",
                  style="CardDim.TLabel").grid(
            row=row + 1, column=0, columnspan=2, sticky="w")
        self.curve = tk.Canvas(
            panel, height=CURVE_HEIGHT, bg=BG_CANVAS, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,
        )
        self.curve.grid(row=row + 2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        return row + 3

    def _fill_rows(self, payload: Mapping[str, Any],
                   drawn: Optional[int] = None) -> None:
        """指标行 + 徽章 + 状态栏由基类刷新；这里顺带把能量曲线画到当前时刻。"""
        super()._fill_rows(payload, drawn)
        self._update_energy_curve()

    def _update_energy_curve(self) -> None:
        """画「E − E₀」随时间的曲线：贴着 0 线小幅振荡 = 积分器稳，鼓包越大越说明 dt 该减小。

        横轴**铺满当前保留下来的那一段历史**（滑动窗口）：模拟时间再长，曲线也不会被
        挤到右边一角、左边留一片空白；而每帧只保留固定条数的历史点，所以曲线也不会
        越画越密 —— 想看更长的一段，把「轨迹点数」调大即可。
        """
        canvas = getattr(self, "curve", None)
        if canvas is None:
            return
        history = self._energy_history
        width = max(canvas.winfo_width(), 160)
        height = max(canvas.winfo_height(), 90)
        left, top, right, bottom = 54.0, 12.0, 12.0, 20.0
        plot_w = max(width - left - right, 10.0)
        plot_h = max(height - top - bottom, 10.0)
        canvas.delete("all")
        canvas.create_line(left, top, left, top + plot_h, fill=COL_CENTER)
        canvas.create_line(left, top + plot_h, left + plot_w, top + plot_h, fill=COL_CENTER)
        if len(history) < 2:
            canvas.create_text(left + 6, top + 4, anchor="nw", fill=FAINT, font=FONT_SM,
                               text="按 ▶ 播放后，这里会画出能量漂移 E − E₀ 随时间的曲线")
            return

        # 采样：点数再多也只画 CURVE_MAX_POINTS 个（否则每帧都要遍历整条历史）
        stride = max(1, len(history) // CURVE_MAX_POINTS)
        points = history[::stride]
        if points[-1] != history[-1]:
            points = points + [history[-1]]
        # 数值发散后能量会变成 inf/NaN：这种点画不出来，直接过滤掉
        points = [point for point in points
                  if math.isfinite(point[0]) and math.isfinite(point[1])]
        if len(points) < 2:
            canvas.create_text(left + 6, top + 4, anchor="nw", fill=FAINT, font=FONT_SM,
                               text="能量已发散（inf / NaN）—— 请减小 dt 或增大 ε")
            return

        # 纵轴画"漂移"而不是"总能量"本身：总能量是 -1.2871xx 这种数，
        # 上下两个刻度印出来一模一样、什么也说明不了；漂移则一眼能读出误差的量级。
        base = self._curve_base
        times = [point[0] for point in points]
        drift = [point[1] - base for point in points]
        t0, t1 = times[0], times[-1]
        span_t = (t1 - t0) or 1.0
        low, high = min(drift), max(drift)
        span = high - low
        if span <= 0.0:                     # 全程一动不动（刚锚定基准时就是这样）
            span = max(abs(high), 1e-12) * 1e-2
        low, high = low - span * 0.25, high + span * 0.25

        def sx(moment: float) -> float:
            return left + (moment - t0) / span_t * plot_w

        def sy(value: float) -> float:
            return top + (high - value) / (high - low) * plot_h

        # E₀ 基准线：漂移 0，曲线离它多远就是误差多大
        canvas.create_line(left, sy(0.0), left + plot_w, sy(0.0), fill=DIM, dash=(4, 3))
        coords: List[float] = []
        for moment, value in zip(times, drift):
            coords.extend((sx(moment), sy(value)))
        canvas.create_line(*coords, fill="#4ade80", width=2)
        canvas.create_oval(sx(t1) - 3, sy(drift[-1]) - 3,
                           sx(t1) + 3, sy(drift[-1]) + 3, fill="#4ade80", outline="")
        # 刻度：上下限（漂移量级）、当前值、以及横轴两端的时间 ——
        # 横轴标注的是"这一段窗口的起止时刻"，滑动时它会一起往前走
        canvas.create_text(left - 6, top, anchor="ne", text=f"{high:+.1e}",
                           fill=DIM, font=FONT_SM)
        canvas.create_text(left - 6, top + plot_h, anchor="se", text=f"{low:+.1e}",
                           fill=DIM, font=FONT_SM)
        canvas.create_text(left + plot_w - 4, top + 4, anchor="ne",
                           text=f"当前 {drift[-1]:+.1e}", fill="#4ade80", font=FONT_SM)
        canvas.create_text(left, top + plot_h + 10, anchor="w",
                           text=f"t = {t0:.1f}", fill=DIM, font=FONT_SM)
        canvas.create_text(left + plot_w, top + plot_h + 10, anchor="e",
                           text=f"t = {t1:.1f}", fill=DIM, font=FONT_SM)

    # ==================================================================
    # 重置与参数
    # ==================================================================
    def reset_simulation(self) -> None:
        """回到初值重来（按当前参数重建模型、重定视角、清空曲线与选中）。"""
        self._cancel_animation()
        self.var_playing.set(False)
        self._drag_mode = None
        self.body = self._new_body()
        self._curve_base = self.body.initial_energy
        self._energy_history = [(self.body.time, self.body.total_energy())]
        self._reset_camera()
        if self._selected is not None and self._selected >= self.body.count:
            self._selected = None            # 星体数变少了：原来的下标已经不存在
        self._refresh_selection_ui()
        self._render_live()
        self._sync_player_buttons()
        self.var_status.set(
            f"已重置：{SCENARIO_LABELS.get(self.body.scenario, self.body.label)}，"
            f"N = {self.body.count}，dt = {self.body.dt:g}，ε = {self.body.softening:g}"
            " —— 按 ▶ 播放。"
        )

    def _on_param_change(self, key: str) -> None:
        """场景 / 星体数 / dt / ε / 种子改的是**被积分的物理**，必须重置；
        轨迹与子步数只影响画面与节奏，不打断播放。"""
        super()._on_param_change(key)
        if key == "scenario":
            self._sync_scenario_softening()
        if key in ("scenario", "stars", "dt", "softening", "seed"):
            # 滑块拖动会连续触发：防抖一下，别让每一像素都重建 + 重画一次
            self._debounce_reset()
        elif key == "trail":
            self.body.trail_len = int(self.param_value("trail") or 0)
            self._render_live()
            self.var_status.set(f"轨迹长度已改为 {self.body.trail_len} 点。")

    def _debounce_reset(self, delay: int = 140) -> None:
        """延迟一小会儿再重置（同一段时间内的多次改动只重置一次）。"""
        if self._regenerate_job is not None:
            self.root.after_cancel(self._regenerate_job)
        self._regenerate_job = self.root.after(delay, self._after_reset)

    def _after_reset(self) -> None:
        self._regenerate_job = None
        self.reset_simulation()

    def _sync_scenario_softening(self) -> None:
        """切换场景时把「软化半径」换成该场景的推荐值（精确解场景是 0）。"""
        params = options_from_ui(self.current_params())
        scenario = params["scenario"]
        recommended = SCENARIOS[scenario].softening
        var = self.param_vars.get("softening")
        if var is not None:
            var.set(recommended)
        self._refresh_param_label("softening")

    def run_action(self, key: str) -> None:
        """「开始模拟」在桌面上就是"重置 + 播放"，与 ▶ 一致。"""
        if key == "simulate":
            self.reset_simulation()
            self.play()
            return
        super().run_action(key)

    # ==================================================================
    # 画布：自己的图种 kind="orbits"
    # ==================================================================
    def _draw(self, spec: ChartSpec, payload: Mapping[str, Any],
              reveal: Optional[int] = None) -> None:
        """``kind="orbits"`` 走本视图的绘制；其余图种交回基类（保持骨架的通用性）。"""
        if spec.kind == "orbits":
            self._draw_orbits(spec, payload)
            self._draw_overlay(spec, None, self._caption(spec, payload))
            return
        super()._draw(spec, payload, reveal)

    def _draw_orbits(self, spec: ChartSpec, payload: Mapping[str, Any]) -> None:
        """画一帧多星画面：轨迹带（暗） -> 星体（亮） -> 质心十字。"""
        canvas = self.canvas
        canvas.delete("all")
        self._forget_grid()
        positions = list(payload.get("positions") or [])
        masses = [float(m) for m in (payload.get("masses") or [])]
        count = int(payload.get("count") or (len(positions) // 2))
        if count <= 0 or len(positions) < 2 * count:
            self._draw_message("没有可画的星体（数据为空）")
            return
        if not all(math.isfinite(value) for value in positions[: 2 * count]):
            # 数值爆炸后位置会变成 inf/NaN：画不出来，但必须给一句人话
            self._draw_message("数值已发散（inf / NaN）\n"
                               "按「↺ 重置模拟」回到初值，并减小 dt 或增大软化半径 ε")
            return

        scale, ox, oy = self._fit_camera()
        colors = self._star_colors(masses, count)
        radii = self._star_radii(masses, count)

        # ---- 轨迹带：每颗星一条折线，颜色是它的暗色版本（选中的那条用原色加粗） ----
        selected = self._selected if (self._selected is not None
                                      and 0 <= self._selected < count) else None
        trail = self.body.trail_array()
        if trail.size and trail.shape[0] >= 2:
            frames = trail.shape[0]
            step = max(1, frames // TRAIL_DRAW_MAX)
            path = trail[::step]
            for index in range(count):
                xs = path[:, index, 0] * scale + ox
                ys = path[:, index, 1] * scale + oy
                if xs.size < 2:
                    continue
                coords: List[float] = []
                for x, y in zip(xs, ys):
                    coords.extend((float(x), float(y)))
                # 尾迹末端接上当前位置，避免"抽样后轨迹与星体断开"
                coords.extend((float(ox + positions[2 * index] * scale),
                               float(oy + positions[2 * index + 1] * scale)))
                if index == selected:
                    canvas.create_line(*coords, fill=colors[index], width=2, smooth=False)
                else:
                    canvas.create_line(*coords, fill=self._trail_color(colors[index]),
                                       width=1, smooth=False)

        # ---- 质心十字（用来看清轨道是绕谁转的） ----
        cx, cy = float(self._cam_center[0]) * scale + ox, float(self._cam_center[1]) * scale + oy
        canvas.create_line(cx - 7, cy, cx + 7, cy, fill=COL_CENTER)
        canvas.create_line(cx, cy - 7, cx, cy + 7, fill=COL_CENTER)

        # ---- 星体 ----
        for index in range(count):
            x = ox + positions[2 * index] * scale
            y = oy + positions[2 * index + 1] * scale
            radius = radii[index]
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius,
                               fill=colors[index], outline="")

        # ---- 选中的星体：高亮环 + 质量标注（拖它之前先让人看清选中的是谁） ----
        if selected is not None:
            x = ox + positions[2 * selected] * scale
            y = oy + positions[2 * selected + 1] * scale
            ring = radii[selected] + 5.0
            canvas.create_oval(x - ring, y - ring, x + ring, y + ring,
                               outline=COL_SELECT, width=2)
            mass = float(masses[selected]) if selected < len(masses) else 0.0
            canvas.create_text(x + ring + 4, y, anchor="w", fill=COL_SELECT, font=FONT_SM,
                               text=f"#{selected + 1}  m={mass:.3g}")

    @staticmethod
    def _star_colors(masses: Sequence[float], count: int) -> List[str]:
        """星体颜色：数量少时按序号取调色板（分得清谁是谁），多时按质量冷暖渐变。"""
        if not masses or count <= len(PALETTE):
            return [PALETTE[index % len(PALETTE)] for index in range(count)]
        low, high = min(masses), max(masses)
        span = (high - low) or 1.0
        return [lerp_color(STAR_COLD, STAR_HOT, (m - low) / span) for m in masses]

    @staticmethod
    def _star_radii(masses: Sequence[float], count: int) -> List[float]:
        """星体半径：随质量的立方根变化（体积正比质量），并夹在 [2.5, 8] 像素。"""
        if not masses:
            return [3.0] * count
        heaviest = max(max(masses), 1e-12)
        radius: List[float] = []
        for mass in masses:
            ratio = max(float(mass), 0.0) / heaviest
            radius.append(min(8.0, max(2.5, 2.5 + 4.5 * ratio ** (1.0 / 3.0))))
        return radius

    @staticmethod
    def _trail_color(color: str) -> str:
        """把星体颜色压暗成轨迹色（画布底色方向的插值）。"""
        text = color.lstrip("#")
        rgb = (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
        return lerp_color(rgb, (12, 17, 24), 0.55)

    # ==================================================================
    # 渲染：模型 -> payload -> 画布
    # ==================================================================
    def _extent(self) -> Tuple[float, float, float, float]:
        """当前视角对应的包围盒（写进 payload，让这份数据自己说清坐标系）。"""
        cx, cy = float(self._cam_center[0]), float(self._cam_center[1])
        radius = float(self._cam_radius)
        return (cx - radius, cx + radius, cy - radius, cy + radius)

    def _render_live(self) -> None:
        """把当前这一帧画出来（含轨迹与曲线）。"""
        spec = self.CHART_SPECS.get("nbody-orbit")
        if spec is None:
            return
        self._chart = spec
        self._last = snapshot_payload(self.body, extent=self._extent(),
                                      cost_ms=self._elapsed_ms)
        self._draw(spec, self._last)
        self._fill_rows(self._last)

    # ==================================================================
    # 钩子：徽章 / 状态栏
    # ==================================================================
    def _badge_for(self, payload: Mapping[str, Any],
                   values: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
        if payload.get("blownUp"):
            return "数值爆炸：减小 dt 或增大 ε", BAD
        escaped = int(payload.get("escaped") or 0)
        drift = payload.get("energyDrift")
        drift_text = "—" if drift is None else f"{abs(float(drift)):.1e}"
        conserved = drift is not None and abs(float(drift)) < 1e-3
        level = OK if conserved else NO
        if escaped > 0:
            return f"{escaped} 颗已逃逸（混沌）· 能量漂移 {drift_text}", level
        return (f"能量漂移 {drift_text}"
                + ("（守恒）" if conserved else "（偏大：减小 dt 或增大 ε）")), level

    def _status_for(self, payload: Mapping[str, Any], values: Mapping[str, Any],
                    partial: bool) -> Optional[str]:
        if payload.get("blownUp"):
            return "数值爆炸：请减小 dt、增大 ε，或换一个随机种子（按 ↺ 重置重来）。"
        name = payload.get("scenarioName") or ""
        steps = payload.get("steps") or 0
        time_now = payload.get("time")
        if self.var_playing.get() or self._anim_job is not None:
            return (f"模拟中… {name}：第 {steps} 步（t = {float(time_now or 0):.2f}），"
                    f"逃逸 {payload.get('escaped') or 0} 颗。空格可暂停。")
        if not steps:
            return f"就绪：{name} —— 按 ▶ 播放开始积分。"
        return (f"已暂停在第 {steps} 步（t = {float(time_now or 0):.2f}）："
                f"总能量 {self.vals['energy'].get()}，漂移 {self.vals['drift'].get()}。")

    # ==================================================================
    # 快捷键
    # ==================================================================
    def on_key(self, key: str) -> None:
        """``R`` 重置模拟；其余（空格播放/暂停、数字键触发动作）交给基类。"""
        if key.lower() == "r":
            self.reset_simulation()
            return
        super().on_key(key)

    # ==================================================================
    # 生命周期
    # ==================================================================
    def shutdown(self) -> None:
        self._cancel_animation()
        super().shutdown()
