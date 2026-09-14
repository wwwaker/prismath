# -*- coding: utf-8 -*-
"""
边渗流模型 · 桌面视图（Tkinter）
================================

本模块是**一个模型的桌面视图**：界面骨架、卡片、动画、后台任务全部来自
:class:`~awe_math.ui.tk.kit.base.PercolationViewBase`，这里只写「边渗流与点渗流
不一样的地方」——术语、配色、画布画法与几行指标。

渲染与计算共用同一份模型代码（:mod:`awe_math.models.percolation.model`），网页界面
另有一套 Canvas 实现。

界面构成（与点渗流视图结构一致）
--------------------------------
* 左侧控制栏：流通概率 p、区域尺寸、面积判据阈值、成功判据、格子类型、方向模式、
  注水方式、动画速度、批量统计与曲线扫描参数、各类按钮；
* 中央画布：绘制全部边与节点（流通边灰白实线、阻断边暗色虚线），并以逐层动画展示水的
  渗透过程（浸润节点按层数着色），**点击节点可指定注水点**。方格网与三角网共用同一套
  绘制逻辑，差别只在于节点的单位坐标与边表；
* 右侧面板（三个标签页）：单次结果 / 批量统计 / P(p) 曲线。

配色分工（与点渗流视图一致）：**基底走中性灰，饱和颜色留给判据关注的对象** ——
纵贯簇用青色（簇内节点与簇内流通边都变青，连成一条贯通路线），浸润路径用琥珀→红，
注水点蓝色描边、底端出口绿色描边。灰白的流通边与暗色虚线化的阻断边只靠明度、虚实与
粗细区分，避免跟青色纵贯簇抢眼。

新增模型请照抄本文件的结构：新建 ``awe_math/models/<模型包>/views/tk.py``，写一份术语表 +
一份指标行 + 几个画布钩子，用 :func:`~awe_math.ui.tk.kit.register_view` 登记
（名字与 ``spec.view`` 一致）即可，不必改动任何已有文件。
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Dict, Optional, Sequence, Tuple, cast

from awe_math.ui.tk.kit import (  # 桌面界面工具箱（共享骨架，与模型无关）
    BG_CANVAS,
    COL_SPAN_EDGE,
    COL_SPAN_FILL,
    ActiveView,
    PercolationViewBase,
    Terms,
    register_view,
)
from awe_math.ui.tk.theme import ACCENT, lerp_color

from ..._options import BOND_INJECT_CHOICES
from ..model import (
    PercolationGrid,
    SimResult,
    batch_percolation_probability,
    scan_curve,
)

# ----------------------------------------------------------------------
# 画布配色
#
# 分工（与点渗流视图一致）：**基底用中性灰、判据关注的对象用青色**。
# 流通边原本是青蓝 #2fa9c9，与纵贯簇的青绿 #2dd4bf 色相相邻、明度也接近，
# 屏幕上分不清「哪些是普通流通边、哪些属于纵贯簇」，所以流通边改成灰白，
# 只靠明度与虚线/粗细区分流通/阻断，把饱和的青色全部让给纵贯簇。
# ----------------------------------------------------------------------
COL_BLOCKED = "#2a333f"     # 阻断边（更暗：与灰白流通边拉开明度差）
COL_OPEN = "#93a1b3"        # 流通边（灰白：不跟青色纵贯簇抢眼）
COL_WET_EDGE = "#ffb703"    # 已被水浸透的流通边
COL_NODE = "#5b6878"        # 未浸润节点
COL_NODE_EDGE = "#0a0e13"   # 节点描边
COL_TOP = "#4dabf7"         # 注水点
COL_BOTTOM = "#51cf66"      # 底端出口
COL_WET_FROM = (255, 222, 118)   # 早层浸润色（黄）
COL_WET_TO = (255, 74, 92)       # 深层浸润色（红）

#: 边渗流视图的用词（基类的全部文案由它拼出）
TERMS = Terms(
    arena="网格",
    arena_qty="整张",
    unit="节点",
    active_verb="浸润",
    p_label="流通概率 p",
    active_phrase="本次注水浸润",
    cover_phrase="本次注水浸润",
    cover_verb="浸润",
    origin_cluster_phrase="注水的这一簇",
    process_verb="渗透",
    progress_badge="渗透中 …",
    mean_short="平均浸润",
    trial_word="模拟",
    scan_verb="正在扫描 p",
    scan_error="曲线扫描失败",
    curve_x_label="流通概率 p",
    curve_ratio_label="平均浸润比例 (%)",
    caption_prefix="▼ ",
    caption_suffix="（蓝色描边为注水点）",
    canvas_footer="▲ 底端出口（水从这里流出）；点击节点可指定注水点",
)

#: 单次结果页的指标行
STAT_ROWS: Tuple[Tuple[str, str], ...] = (
    ("流通概率 p", "p"),
    ("格子 / 规模", "size"),
    ("流通边 / 总边数", "edges"),
    ("注水点", "origins"),
    ("浸润节点数", "wet"),
    ("浸润比例", "ratio"),
    ("纵贯簇", "spanning"),
    ("渗透层数", "depth"),
    ("判定耗时", "cost"),
)

#: 单次结果页底部的说明段落
EXPLAIN = (
    "说明：\n"
    "· 每条边以概率 p 独立地流通或阻断，水从注水点沿流通边蔓延；\n"
    "· 青色节点是**纵贯簇**：同时连通顶行与底行的那一串节点。三种判据：\n"
    "  · 贯通判据 = 网格上有没有纵贯簇 —— p_c 说的就是这个相变\n"
    "    （方格网 0.5、三角网 ≈ 0.3473、有向 ≈ 0.6447），与注水方式无关；\n"
    "  · 起点判据 = 你这次注水的那一簇是否纵贯 —— 随机/中心注水经常\n"
    "    落在簇外，所以交点高于 p_c（顶端整行注水时两者相同）；\n"
    "  · 面积判据 = 浸润面积达到设定比例 —— 没有固定临界值，交点随\n"
    "    比例、网格尺寸、注水方式一起漂移；\n"
    "· 只有贯通判据的 1/2 交点等于 p_c；点击节点可指定注水点。"
)

#: 切换判据时的状态栏文案
CRITERION_STATUS: Dict[str, str] = {
    "span": (
        "已切换为「贯通判据」：判定**整张网格**上是否存在顶行↔底行的纵贯簇"
        "（青色节点）。它的成功概率 = 1/2 交点就是临界值 p_c"
        "（方格网无向 = 1/2），且与注水方式无关。"
    ),
    "origin": (
        "已切换为「起点判据」：判定**从注水点出发的那一簇**是否纵贯（碰到顶行"
        "与底行）。它与贯通判据的差别是「还要求注水点落在纵贯簇里」，"
        "所以交点高于 p_c —— 随机注水常常落在簇外。"
    ),
    "area": (
        "已切换为「面积判据」：判定浸润面积是否达到设定比例。"
        "注意它没有固定的临界值 —— 交点随比例、网格尺寸、注水方式一起变，"
        "不要把它当成 p_c。"
    ),
}

#: 切换注水方式时的状态栏文案（``{inject}`` 会被替换成当前的注水方式名）
INJECT_STATUS: Dict[str, str] = {
    "span": (
        "注水方式：{inject}。贯通判据只看整张网格有没有纵贯簇，与注水位置无关 —— "
        "它只影响单次动画的起点。"
    ),
    "origin": (
        "注水方式：{inject}。起点判据下注水位置影响很大 —— 顶端整行一定在纵贯簇上，"
        "随机/中心单点则可能落在簇外（只浸透一小片）。"
    ),
    "area": (
        "注水方式：{inject}。面积判据下起始位置影响很大：单点注水额外要求"
        "「起点落在巨簇里」，所以曲线整体比顶端整行注水更平缓。"
    ),
}


@register_view("percolation")
class PercolationApp(PercolationViewBase):
    """边渗流模型的可视化视图（由 :class:`~awe_math.ui.tk.shell.DesktopShell` 放入窗口中部）。"""

    # ---------------- 界面文案与数据 ----------------
    HINTS = "空格 播放动画    R 重新生成    点击网格可指定注水点"
    TERMS = TERMS
    STAT_ROWS = STAT_ROWS
    EXPLAIN = EXPLAIN
    CRITERION_STATUS = CRITERION_STATUS
    INJECT_STATUS = INJECT_STATUS
    INJECT_CHOICES = BOND_INJECT_CHOICES
    DEFAULT_P = 0.5
    DEFAULT_INJECT = "top"
    FALLBACK_ACCENT = ACCENT
    INTRO_STATUS = "就绪：拖动滑块调整 p，程序会自动重绘网格。"

    # ---------------- 画布配色 ----------------
    LEGEND_EDGE = COL_NODE_EDGE
    LEGEND_LINE_WIDTH = 3
    CAPTION_COLOR = COL_TOP
    FOOTER_COLOR = COL_BOTTOM

    # ==================================================================
    # 模型适配
    # ==================================================================
    def _create_model(self, **kwargs) -> PercolationGrid:
        return PercolationGrid(**kwargs)

    def _model_functions(self):
        return batch_percolation_probability, scan_curve

    def _active_view(self) -> ActiveView:
        """把 :class:`SimResult` 归一化成界面统一使用的 :class:`ActiveView`。"""
        res = cast(SimResult, self.result)
        return ActiveView(
            active=res.wet,
            active_count=res.wet_count,
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
        )

    # ==================================================================
    # 画布（三处画法确实与点渗流不同）
    # ==================================================================
    def _legend_items(self) -> Sequence[Tuple[str, str, str]]:
        return (
            ("line", COL_OPEN, "流通边"),
            ("dash", COL_BLOCKED, "阻断边"),
            ("dot", COL_SPAN_FILL, "纵贯簇"),
            ("dot", COL_NODE, "未浸润节点"),
            ("dot", lerp_color(COL_WET_FROM, COL_WET_TO, 0.5), "已浸润节点"),
            ("dot", COL_TOP, "注水点"),
            ("dot", COL_BOTTOM, "底端出口"),
        )

    def _draw_base(self) -> None:
        """绘制底层网格：所有边 + 所有节点（不含量变信息）。"""
        cv = self.canvas
        cv.delete("all")
        model = self.model
        cell, _ox, _oy = self._layout_params()
        self._cell = cell
        # 记录底图对应的形状 / 格子 / 方向，供增量上色时校验
        self._drawn_shape = (model.rows, model.cols, model.lattice, model.direction)

        radius = max(1.2, min(5.0, cell * 0.17))
        lw_open = max(1.0, min(2.8, cell * 0.16))
        lw_block = max(0.6, min(1.5, cell * 0.08))

        xy = self._node_xy
        self._node_items = [None] * model.node_count
        #: 边 -> 画布元素；键是 (较小的节点索引, 较大的节点索引)
        self._edge_items = {}
        # 纵贯簇单独上色：判据问的就是「有没有这么一串节点纵贯顶底」，
        # 不画出来的话，「判定贯通 + 浸润面积很小」会显得莫名其妙
        spanning = set(model.spanning_nodes())

        for a, b in model.iter_all_edges():
            x1, y1 = xy[a]
            x2, y2 = xy[b]
            if model.is_open(a, b):
                # 纵贯簇内部的流通边跟着簇一起变青：整条贯通路线连成一条青色路径
                color = (COL_SPAN_EDGE if (a in spanning and b in spanning)
                         else COL_OPEN)
                item = cv.create_line(x1, y1, x2, y2, fill=color, width=lw_open)
            else:
                item = cv.create_line(x1, y1, x2, y2, fill=COL_BLOCKED,
                                      width=lw_block, dash=(2, 3))
            self._edge_items[(a, b)] = item

        # 注水点优先取「本次实际使用」的（点击网格指定后与 inject 的默认选择不同）；
        # 形状不一致时说明结果属于上一张网格，退回按注水方式现算
        if (self.result is not None and self.result.origins
                and self.result.shape == model.shape):
            sources = set(self.result.origins)
        else:
            sources = set(model.source_nodes())
        last_row_start = (model.rows - 1) * model.cols
        for idx, (x, y) in enumerate(xy):
            # 描边表达「角色」（注水点蓝、底端出口绿），填充表达「是否在纵贯簇里」，
            # 两者叠加正好说明「这个簇是否既碰顶又碰底」
            if idx in sources:
                outline, ow = COL_TOP, 1.6
            elif idx >= last_row_start:
                outline, ow = COL_BOTTOM, 1.6
            elif idx in spanning:
                outline, ow = COL_SPAN_EDGE, 1.2
            else:
                outline, ow = COL_NODE_EDGE, 1
            fill = COL_SPAN_FILL if idx in spanning else COL_NODE
            self._node_items[idx] = cv.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill=fill, outline=outline, width=ow,
            )

        self._draw_caption()

    def _apply_active(self, nodes: Sequence[int], color: str) -> None:
        """把一批节点标记为已浸润，并高亮它与已浸润邻居之间的流通边。

        注意：节点索引必须与当前底图一致（形状 / 格子 / 方向变了就画不出来），
        因此这里先校验 ``_drawn_shape``。
        """
        cv = self.canvas
        model = self.model
        if self._drawn_shape != (model.rows, model.cols, model.lattice, model.direction):
            return
        node_items = self._node_items
        edges = self._edge_items
        lw = max(2.0, min(4.2, self._cell * 0.26))

        for idx in nodes:
            item = node_items[idx]
            if item is not None:
                cv.itemconfigure(item, fill=color)
            # 找已经浸润的邻居给这条边染色。必须用 traversable_neighbors 而不是
            # neighbors：后者只给「出边」，有向模式下从后来浸润的节点看前一个节点是
            # 「逆方向」的，那条边就漏色了（三角网 + 方向限制时最明显）。
            for nb in model.traversable_neighbors(idx):
                if nb not in self._active_set:
                    continue
                it = edges.get((idx, nb) if idx < nb else (nb, idx))
                if it is not None:
                    cv.itemconfigure(it, fill=COL_WET_EDGE, width=lw, dash=())

    def _layer_color(self, layer_index: int, total_layers: int) -> str:
        """按渗透层数做颜色渐变：越晚到达的节点越红。"""
        if total_layers <= 1:
            t = 0.0
        else:
            t = layer_index / (total_layers - 1)
        return lerp_color(COL_WET_FROM, COL_WET_TO, t)

    # ==================================================================
    # 指标（模型特有的三行）
    # ==================================================================
    def _fill_extra_rows(self, view: Optional[ActiveView]) -> None:
        model = self.model
        res = self.result
        if res is None:
            self.vals["edges"].set(f"- / {model.total_edge_count()}")
            for key in ("origins", "wet"):
                self.vals[key].set("-")
            return
        self.vals["edges"].set(
            f"{res.open_edge_count} / {res.total_edge_count}"
            f"（实测比例 {res.open_ratio:.3f}）"
        )
        self.vals["origins"].set(
            f"{len(res.origins)} 个（{model.inject_name}）" if res.origins else "-"
        )
        ratio = len(self._active_set) / res.node_count if res.node_count else 0.0
        self.vals["wet"].set(f"{len(self._active_set)} / {res.node_count}（{ratio:.1%}）")

    def _size_text(self, model: Any) -> str:
        """「格子 / 规模」行：附上注水方式（点渗流视图没有这一项）。"""
        return (f"{model.lattice_name} {model.rows}×{model.cols}"
                f"（{model.node_count} 节点，{model.inject_name}）")

    # ==================================================================
    # 兼容旧名（重构前这个方法叫 regenerate_grid）
    # ==================================================================
    def regenerate_grid(self) -> None:
        """重新随机生成网格（等价于 :meth:`regenerate`，保留旧名以兼容既有调用）。"""
        self.regenerate()
