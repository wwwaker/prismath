# -*- coding: utf-8 -*-
"""
点渗流模型 · 桌面视图（Tkinter）
================================

与边渗流视图（:mod:`prismath.models.percolation.views.tk`）**结构完全一致**：界面骨架、
卡片、动画、后台任务都由 :class:`~prismath.ui.tk.kit.base.PercolationViewBase` 提供，
这里只写点渗流自己的术语、配色、画布画法与指标行。

渲染与计算共用同一份模型代码（:mod:`prismath.models.site_percolation.model`），
网页界面另有一套 Canvas 实现。

界面构成（与边渗流视图结构一致）
--------------------------------
* 左侧控制栏：占据密度 p、格地尺寸、面积判据阈值、成功判据、格子类型、方向模式、
  注水（起始）方式、动画速度、批量统计与曲线扫描参数、各类按钮；
* 中央画布：绘制相邻可蔓延关系（浅线）与占据格 / 空位，并以逐层动画展示蔓延过程
  （蔓延格按层数着色），**点击占据格可指定注水点**；
* 右侧面板（三个标签页）：单次结果 / 批量统计 / P(p) 曲线。

配色分工（与边渗流视图一致）：**基底走中性灰，饱和颜色留给判据关注的对象** ——
纵贯簇用青色，蔓延路径用紫→蓝渐变，注水点琥珀色描边。

新增模型请照抄本文件的结构：新建 ``prismath/models/<模型包>/views/tk.py``，写一份术语表 +
一份指标行 + 几个画布钩子，用 :func:`~prismath.ui.tk.kit.register_view` 登记
（名字与 ``spec.view`` 一致）即可，不必改动任何已有文件。
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Dict, Iterator, Optional, Sequence, Tuple, cast

from prismath.ui.tk.kit import (  # 桌面界面工具箱（共享骨架，与模型无关）
    BG_CANVAS,
    COL_SPAN_EDGE,
    COL_SPAN_FILL,
    ActiveView,
    PercolationViewBase,
    Terms,
    register_view,
)
from prismath.ui.tk.theme import DIM, FAINT, lerp_color

from ..._options import SITE_INJECT_CHOICES
from ..model import SpreadResult

# ----------------------------------------------------------------------
# 画布配色
# ----------------------------------------------------------------------
COL_GROUND = "#1b2430"      # 相邻格子的连线（可蔓延关系）
COL_EMPTY = "#222b38"       # 空位
COL_SITE = "#5c6b80"        # 被占据但还没蔓延到的格子
COL_SITE_EDGE = "#0a0e13"   # 占据格描边
COL_SEED = "#fbbf24"        # 注水点（起始格）
COL_SPREAD_EDGE = "#a78bfa"  # 蔓延路径

#: 蔓延层的颜色渐变：刚蔓延到偏浅紫，越晚越深
SPREAD_RAMP = [
    (0.00, (196, 181, 253)),
    (0.45, (167, 139, 250)),
    (0.78, (139, 92, 246)),
    (1.00, (59, 130, 246)),
]


def _ramp_color(t: float) -> str:
    """按 0..1 的进度在 :data:`SPREAD_RAMP` 上取色。"""
    value = 0.0 if t < 0 else (1.0 if t > 1 else t)
    for i in range(1, len(SPREAD_RAMP)):
        pos, rgb = SPREAD_RAMP[i]
        if value <= pos:
            p0, c0 = SPREAD_RAMP[i - 1]
            k = (value - p0) / (pos - p0 or 1.0)
            return lerp_color(c0, rgb, k)
    return lerp_color(SPREAD_RAMP[-1][1], SPREAD_RAMP[-1][1], 0.0)


#: 点渗流视图的用词（基类的全部文案由它拼出）
TERMS = Terms(
    arena="格地",
    arena_qty="整片",
    unit="格",
    active_verb="蔓延",
    p_label="占据密度 p",
    inject_label="注水（起始）方式",
    active_phrase="本次蔓延",
    cover_phrase="本次蔓延覆盖",
    cover_verb="覆盖",
    origin_cluster_phrase="注水点的簇",
    process_verb="蔓延",
    progress_badge="蔓延中 …",
    mean_short="平均蔓延",
    trial_word="实验",
    scan_verb="正在扫描占据密度",
    scan_progress="密度扫描",
    scan_error="密度扫描失败",
    pc_word="临界密度",
    curve_x_label="占据密度 p",
    curve_ratio_label="平均蔓延比例 (%)",
    caption_prefix="▦ ",
    caption_suffix="（深色为空位）",
    canvas_footer="点击任意占据格可指定注水点（空位不可选）",
    no_source_hint="没有可用的注水点（顶端整行注水时该行可能一个占据格都没有）。",
    reject_hint="那里是空位（或已超出格地范围），请点击一个占据格。",
)

#: 单次结果页的指标行
STAT_ROWS: Tuple[Tuple[str, str], ...] = (
    ("占据密度 p", "p"),
    ("格子 / 规模", "size"),
    ("占据格数量", "sites"),
    ("注水点", "seeds"),
    ("蔓延格数", "area"),
    ("蔓延比例", "ratio"),
    ("纵贯簇", "spanning"),
    ("蔓延层数", "depth"),
    ("判定耗时", "cost"),
)

#: 单次结果页底部的说明段落
EXPLAIN = (
    "说明：\n"
    "· 每格以概率 p 被占据，相邻占据格之间才连通；蔓延范围 = 包含注水点\n"
    "  的那个连通簇（「随机一棵树起火，火只沿相邻的树烧」）；\n"
    "· 青色格子是**纵贯簇**：同时连通顶行与底行的那个簇。三种判据：\n"
    "  · 贯通判据 = 格地上有没有纵贯簇 —— p_c 说的就是这个相变\n"
    "    （方格网 ≈ 0.5927、三角网 0.5），与注水方式无关；\n"
    "  · 起点判据 = 你这次注水的那一簇是否纵贯 —— 随机/中心起火经常\n"
    "    落在纵贯簇之外，所以交点高于 p_c（顶端整行注水时两者相同）；\n"
    "  · 面积判据 = 蔓延面积达到设定比例 —— 没有固定临界值，交点随\n"
    "    比例、网格尺寸、注水方式一起漂移；\n"
    "· 只有贯通判据的 1/2 交点等于 p_c；点击占据格可指定注水点。"
)

#: 切换判据时的状态栏文案
CRITERION_STATUS: Dict[str, str] = {
    "span": (
        "已切换为「贯通判据」：判定**整片格地**上是否存在顶行↔底行的纵贯簇"
        "（青色格子）。它的成功概率 = 1/2 交点就是临界密度 p_c"
        "（方格网无向 ≈ 0.5927），且与注水方式无关。"
    ),
    "origin": (
        "已切换为「起点判据」：判定**从注水点出发的那一簇**是否纵贯（碰到顶行"
        "与底行）。它与贯通判据的差别是「还要求注水点落在纵贯簇里」，"
        "所以交点高于 p_c —— 随机起火常常烧在簇外。"
    ),
    "area": (
        "已切换为「面积判据」：判定蔓延面积是否达到设定比例。"
        "注意它没有固定的临界值 —— 交点随比例、网格尺寸、注水方式一起变，"
        "不要把它当成 p_c。"
    ),
}

#: 切换注水方式时的状态栏文案（``{inject}`` 会被替换成当前的注水方式名）
INJECT_STATUS: Dict[str, str] = {
    "span": (
        "注水方式：{inject}。贯通判据只看整片格地有没有纵贯簇，与注水位置无关 —— "
        "它只影响单次动画的起点。"
    ),
    "origin": (
        "注水方式：{inject}。起点判据下注水位置影响很大 —— 顶端整行一定在纵贯簇上，"
        "随机/中心单点则可能落在簇外（火很小却仍可能判定成功）。"
    ),
    "area": (
        "注水方式：{inject}。面积判据下起始位置影响很大：单点注水额外要求"
        "「起点落在巨簇里」，所以曲线整体比顶端整行注水更平缓。"
    ),
}


@register_view("site_percolation")
class SitePercolationApp(PercolationViewBase):
    """点渗流模型的可视化视图（由 :class:`~prismath.ui.tk.shell.DesktopShell` 放入窗口中部）。"""

    # ---------------- 界面文案与数据 ----------------
    HINTS = "空格 播放动画    R 重新生成    点击格地可指定注水点"
    TERMS = TERMS
    STAT_ROWS = STAT_ROWS
    EXPLAIN = EXPLAIN
    CRITERION_STATUS = CRITERION_STATUS
    INJECT_STATUS = INJECT_STATUS
    INJECT_CHOICES = SITE_INJECT_CHOICES
    DEFAULT_P = 0.6
    DEFAULT_INJECT = "random"
    FALLBACK_ACCENT = "#a78bfa"
    INTRO_STATUS = "就绪：拖动滑块调整占据密度 p，程序会自动重新生成格地并蔓延。"

    # ---------------- 画布配色 ----------------
    LEGEND_EDGE = COL_SITE_EDGE
    LEGEND_LINE_WIDTH = 2
    CAPTION_COLOR = DIM
    FOOTER_COLOR = FAINT

    # ==================================================================
    # 模型适配（构造与批量 / 扫描都由 spec 的 factory / batch / scan 提供，
    # 这里只需把模型结果归一化成界面统一使用的 ActiveView）
    # ==================================================================
    def _active_view(self) -> ActiveView:
        """把 :class:`SpreadResult` 归一化成界面统一使用的 :class:`ActiveView`。"""
        res = cast(SpreadResult, self.result)
        return ActiveView(
            active=res.spread,
            active_count=res.spread_count,
            total=res.node_count,
            layers=res.layers,
            sources=res.origins,
            spans=res.spans,
            origin_spans=res.origin_spans,
            engulfed=res.engulfed,
            spanning_count=res.spanning_count,
            origin_in_spanning=res.origin_in_spanning,
            criterion=res.criterion,
            threshold=res.threshold,
            elapsed=res.elapsed,
            depth=res.depth,
            has_source=res.has_source,
            # 点渗流额外报告「蔓延格占占据格的比例」，即这个簇的相对大小
            ratio_note=f"簇内 {res.cluster_ratio:.1%}，",
        )

    # ==================================================================
    # 画布（三处画法确实与边渗流不同）
    # ==================================================================
    def _legend_items(self) -> Sequence[Tuple[str, str, str]]:
        return (
            ("dot", COL_SITE, "占据格"),
            ("dot", COL_EMPTY, "空位"),
            ("dot", COL_SPAN_FILL, "纵贯簇"),
            ("dot", _ramp_color(0.5), "已蔓延"),
            ("dot", COL_SEED, "注水点"),
            ("line", COL_GROUND, "相邻可蔓延"),
        )

    def _adjacent_pairs(self, index: int) -> Iterator[int]:
        """几何相邻的格子（不受方向与占据状态限制），供底图画线使用。"""
        model = self.model
        rows, cols = model.rows, model.cols
        r, c = divmod(index, cols)
        if c + 1 < cols:
            yield index + 1
        if c > 0:
            yield index - 1
        if model.lattice == "square":
            if r + 1 < rows:
                yield index + cols
            if r > 0:
                yield index - cols
            return
        shift = r % 2
        if r + 1 < rows:
            for j in (c - 1 + shift, c + shift):
                if 0 <= j < cols:
                    yield r * cols + cols + j
        if r > 0:
            pshift = (r - 1) % 2
            for k in (c + 1 - pshift, c - pshift):
                if 0 <= k < cols:
                    yield (r - 1) * cols + k

    def _draw_base(self) -> None:
        """绘制底层格地：可蔓延关系（浅线）+ 占据格 / 空位。"""
        cv = self.canvas
        cv.delete("all")
        model = self.model
        cell, _ox, _oy = self._layout_params()
        self._cell = cell
        # 记录底图对应的形状 / 格子 / 方向，供增量上色时校验
        self._drawn_shape = (model.rows, model.cols, model.lattice, model.direction)

        radius = max(1.2, min(5.0, cell * 0.30))
        xy = self._node_xy
        self._node_items = [None] * model.node_count
        self._edge_items = {}

        # 相邻格子的可蔓延关系（画在最下层，作为格点提示）
        for idx in range(model.node_count):
            for nb in self._adjacent_pairs(idx):
                key = (idx, nb) if idx < nb else (nb, idx)
                if key in self._edge_items:
                    continue
                x1, y1 = xy[idx]
                x2, y2 = xy[nb]
                self._edge_items[key] = cv.create_line(
                    x1, y1, x2, y2, fill=COL_GROUND, width=1
                )

        # 占据格与空位
        occupied = model.occupied
        cols = model.cols
        # 纵贯簇单独上色：判据问的就是「有没有这么一片格子纵贯顶底」，
        # 不画出来的话，「判定贯通 + 蔓延面积很小」会显得莫名其妙
        spanning = set(model.spanning_nodes())
        for idx, (x, y) in enumerate(xy):
            if not occupied[idx // cols][idx % cols]:
                outline, ow, fill = "", 0, COL_EMPTY
            elif idx in spanning:
                outline, ow, fill = COL_SPAN_EDGE, 1, COL_SPAN_FILL
            else:
                outline, ow, fill = COL_SITE_EDGE, 1, COL_SITE
            self._node_items[idx] = cv.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill=fill, outline=outline, width=ow,
            )

        self._draw_caption()

    def _apply_active(self, nodes: Sequence[int], color: str) -> None:
        """把一批格子标记为已蔓延，并高亮它与已蔓延邻居之间的路径。"""
        cv = self.canvas
        model = self.model
        if self._drawn_shape != (model.rows, model.cols, model.lattice, model.direction):
            return
        node_items = self._node_items
        edges = self._edge_items
        lw = max(1.6, min(3.6, self._cell * 0.22))

        for idx in nodes:
            item = node_items[idx]
            if item is not None:
                cv.itemconfigure(item, fill=color, outline=COL_SITE_EDGE, width=1)
            # 找已经蔓延到的邻居给这条边染色。必须用 traversable_neighbors 而不是
            # neighbors：后者只给「出边」，有向模式下从后来蔓延到的格子看前一个格子是
            # 「逆方向」的，那条边就漏色了（三角网 + 方向限制时最明显）。
            for nb in model.traversable_neighbors(idx):
                if nb not in self._active_set:
                    continue
                it = edges.get((idx, nb) if idx < nb else (nb, idx))
                if it is not None:
                    cv.itemconfigure(it, fill=COL_SPREAD_EDGE, width=lw)

    def _layer_color(self, layer_index: int, total_layers: int) -> str:
        """按蔓延层数做颜色渐变：刚蔓延到偏浅紫，越晚越深。"""
        t = 0.0 if total_layers <= 1 else layer_index / (total_layers - 1)
        return _ramp_color(t)

    def _draw_finish_overlay(self) -> None:
        """所有层都显示完之后，把注水点圈出来（画在最上层）。"""
        if self.result is None:
            return
        for origin in self.result.origins[:64]:      # 顶端整行注水时可能有很多点
            if not 0 <= origin < len(self._node_xy):
                continue
            x, y = self._node_xy[origin]
            r = max(3.0, min(9.0, self._cell * 0.42))
            self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                outline=COL_SEED, width=2, tags="seed",
            )

    def _hit_test(self, index: int) -> bool:
        """只有占据格才能被指定为注水点。"""
        return self.model.is_occupied(index)

    # ==================================================================
    # 指标（模型特有的三行）
    # ==================================================================
    def _fill_extra_rows(self, view: Optional[ActiveView]) -> None:
        model = self.model
        res = self.result
        if res is None:
            for key in ("sites", "seeds", "area"):
                self.vals[key].set("-")
            return
        self.vals["sites"].set(
            f"{res.occupied_count} / {res.node_count}（{res.occupied_ratio:.1%}）"
        )
        self.vals["seeds"].set(
            "-" if not res.has_source else f"{len(res.origins)} 个（{model.inject_name}）"
        )
        self.vals["area"].set(f"{len(self._active_set)} / {res.node_count} 格")

    def _size_text(self, model: Any) -> str:
        """「格子 / 规模」行：只报规模（蔓延范围取决于占据格，见「蔓延格数」）。"""
        return (f"{model.lattice_name} {model.rows}×{model.cols}"
                f"（{model.node_count} 格）")

    # ==================================================================
    # 兼容旧名（重构前这些方法叫 regenerate_sites / start_spread）
    # ==================================================================
    def regenerate_sites(self) -> None:
        """重新随机生成格地（等价于 :meth:`regenerate`，保留旧名以兼容既有调用）。"""
        self.regenerate()

    def start_spread(self, origins: Optional[Sequence[int]] = None) -> None:
        """播放蔓延动画（等价于 :meth:`start_animation`，保留旧名以兼容既有调用）。"""
        self.start_animation(origins)
