# -*- coding: utf-8 -*-
"""
视图公共件：配色常量、术语表、结果归一化与共享小工具
======================================================

边渗流与点渗流两个桌面视图在结构上刻意保持对称，差别集中在三处：

1. **术语不同**（网格/格地、节点/格、浸润/蔓延……）—— 用 :class:`Terms` 一张表描述，
   基类的所有文案都由它拼出来，视图类不必重写方法；
2. **模型结果字段不同**（``SimResult.wet_ratio`` 与 ``SpreadResult.spread_ratio``）——
   用 :class:`ActiveView` 归一化成同一套字段名，基类只认归一化后的名字；
3. **画布画法不同**（边+节点 / 格子+邻接连线）—— 这部分确实无法参数化，交给子类
   override 绘制钩子（见 :mod:`prismath.ui.tk.views.canvas`）。

此外这里放两个视图逐字相同的常量（画布底色、纵贯簇配色、结论色）与纯函数工具。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

__all__ = [
    "MAX_SIZE",
    "THRESHOLD_CHOICES",
    "BG_CANVAS",
    "COL_SPAN_FILL",
    "COL_SPAN_EDGE",
    "COL_VERDICT_OK",
    "COL_VERDICT_NO",
    "BADGE_OK_BG",
    "BADGE_OK_FG",
    "BADGE_NO_BG",
    "BADGE_NO_FG",
    "BADGE_BAD_BG",
    "BADGE_BAD_FG",
    "TREE_OK",
    "TREE_NO",
    "Terms",
    "ActiveView",
    "spec_defaults",
    "pick",
    "label",
    "half_crossing",
    "parse_int",
    "parse_float",
]

#: 行数 / 列数上限（画布要画 rows×cols 个单元，太大就卡了）
MAX_SIZE = 80

#: 「面积判据」阈值下拉框候选项
THRESHOLD_CHOICES = ("0.3", "0.5", "0.7", "0.9")

# ---------------- 两个视图逐字相同的配色（画布与结论） ----------------
BG_CANVAS = "#0c1118"        # 画布底色
COL_SPAN_FILL = "#12433c"    # 纵贯簇（顶行 ↔ 底行连通的簇）的填充
COL_SPAN_EDGE = "#2dd4bf"    # 纵贯簇描边（两个模型一致，便于对照）
COL_VERDICT_OK = "#4ade80"   # 结论「成立」
COL_VERDICT_NO = "#fb7185"   # 结论「不成立」
BADGE_OK_BG, BADGE_OK_FG = "#2b2340", "#c4b5fd"    # 结论徽章：成功
BADGE_NO_BG, BADGE_NO_FG = "#131c28", "#93c5fd"    # 结论徽章：未成功
BADGE_BAD_BG, BADGE_BAD_FG = "#331420", "#fb7185"  # 结论徽章：无法判定（如没有注水点）
TREE_OK, TREE_NO = "#4ade80", "#fb7185"            # 历史记录表格的成功 / 失败行


# ----------------------------------------------------------------------
# 术语表：基类的所有文案都由这张表拼出来
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Terms:
    """一个模型的用词（默认值是边渗流视图的用词，点渗流视图整套覆盖）。"""

    #: 模型对象的名字：「网格」/「格地」
    arena: str = "网格"
    #: 「整张网格」/「整片格地」里的量词
    arena_qty: str = "整张"
    #: 组成的单元：「节点」/「格」
    unit: str = "节点"
    #: 活动过程的名字：「浸润」/「蔓延」（做名词用）
    active_verb: str = "浸润"
    #: p 的界面名：「流通概率 p」/「占据密度 p」
    p_label: str = "流通概率 p"
    #: 注水方式那张下拉框的标题：「注水方式」/「注水（起始）方式」
    inject_label: str = "注水方式"
    #: 结论行里「本次活动了多少」的说法：「本次注水浸润」/「本次蔓延」
    active_phrase: str = "本次注水浸润"
    #: 状态栏里「本次活动了多少」的说法：「本次注水浸润」/「本次蔓延覆盖」
    cover_phrase: str = "本次注水浸润"
    #: 单次结果里「覆盖了 n/m」的动词：「浸润」/「覆盖」
    cover_verb: str = "浸润"
    #: 「注水点的簇」的说法：「注水的这一簇」/「注水点的簇」
    origin_cluster_phrase: str = "注水的这一簇"
    #: 动画 / 批量的过程说法：「渗透」/「蔓延」
    process_verb: str = "渗透"
    #: 结论徽章进行中：「渗透中 …」/「蔓延中 …」
    progress_badge: str = "渗透中 …"
    #: 平均值的简称：「平均浸润」/「平均蔓延」
    mean_short: str = "平均浸润"
    #: 单次实验的量词：「模拟」/「实验」
    trial_word: str = "模拟"
    #: 曲线页里每点实验次数的量词（两个视图都用「实验」）
    curve_trial_word: str = "实验"
    #: 扫描 / 曲线的说法
    scan_verb: str = "正在扫描 p"
    scan_progress: str = "曲线扫描"
    scan_error: str = "曲线扫描失败"
    #: 临界值的说法：「临界值 p_c」/「临界密度 p_c」
    pc_word: str = "临界值"
    #: 曲线坐标轴
    curve_x_label: str = "流通概率 p"
    curve_ratio_label: str = "平均浸润比例 (%)"
    #: 画布左上角的配置说明：前缀 + 后缀
    caption_prefix: str = "▼ "
    caption_suffix: str = "（蓝色描边为注水点）"
    #: 画布左下角的提示（点渗流用来说明「空位不可选」）
    canvas_footer: str = "▲ 底端出口（水从这里流出）；点击节点可指定注水点"
    #: 结论徽章：没有可用的注水点
    no_source_badge: str = "没有可用的注水点"
    #: 无法选定注水点时的提示（点渗流在顶端整行没有占据格时会出现）
    no_source_hint: str = ""
    #: 点击到不可选的位置时的提示
    reject_hint: str = ""


# ----------------------------------------------------------------------
# 结果归一化：两个模型的单次结果字段名不同，基类只认这一套
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class ActiveView:
    """一次「逐层活动」结果（浸润 / 蔓延）的归一化视图。"""

    #: 本次已活动的单元索引
    active: Sequence[int]
    #: 本次已活动的单元数 / 总单元数
    active_count: int
    total: int
    #: 逐层分组，``layers[k]`` 是距注水点 k 步的单元
    layers: Sequence[Sequence[int]]
    #: 本次实际使用的注水点
    sources: Sequence[int]
    #: 整片区域是否存在纵贯簇（与注水点无关）—— 贯通判据问的就是这个
    spans: bool
    #: 从注水点出发的那一簇是否纵贯
    origin_spans: bool
    #: 面积判据是否达标
    engulfed: bool
    #: 纵贯簇的单元数
    spanning_count: int
    #: 注水点是否落在纵贯簇里
    origin_in_spanning: bool
    #: 「是否成功」采用的判据：``span`` / ``origin`` / ``area``
    criterion: str
    #: 面积判据阈值
    threshold: float
    #: 判定耗时（秒）
    elapsed: float
    #: 层数（``len(layers)`` 的语义化别名）
    depth: int
    #: 是否存在可用的注水点（点渗流在「顶端整行一个占据格都没有」时为 False）
    has_source: bool = True
    #: 比例行里模型特有的补充说明（点渗流用来额外报告「簇内 x%」）
    ratio_note: str = ""

    @property
    def active_ratio(self) -> float:
        """已活动单元占全部单元的比例。"""
        return self.active_count / self.total if self.total else 0.0

    @property
    def ok(self) -> bool:
        """按当前判据，「这一次」是否算成功。"""
        if self.criterion == "origin":
            return self.origin_spans
        if self.criterion == "area":
            return self.engulfed
        return self.spans


# ----------------------------------------------------------------------
# 共享工具
# ----------------------------------------------------------------------
def spec_defaults(spec, fallback_p: float) -> Dict[str, Any]:
    """从模型元数据里取出参数默认值；没有 spec 时用该视图的默认值。"""
    if spec is None:
        return {"p": fallback_p, "rows": 30, "cols": 30}
    return {param.key: param.default for param in getattr(spec, "params", ())}


def pick(mapping: Mapping[str, str], value: Any, fallback: str) -> str:
    """界面选项（中文）-> 模型取值；无法识别时回退到 fallback。"""
    return mapping.get(str(value), fallback)


def label(mapping: Mapping[str, str], value: str) -> str:
    """模型取值 -> 界面选项（中文）。"""
    for text, key in mapping.items():
        if key == value:
            return text
    return next(iter(mapping))


def half_crossing(points: Sequence[Tuple[float, float]]) -> Optional[float]:
    """线性插值求曲线与 50% 的交点（扫描范围内跨不过 50% 时返回 None）。

    这个交点是**有限尺寸 + 网格长宽比**一起决定的结果，和理论 p_c（无限大格子、
    只由格子与方向决定）不是一回事：长宽比一变，它就跟着移动
    （例如方格网无向：20×20 约 0.50、20×60 约 0.45、60×20 约 0.54）。
    """
    for (p1, v1), (p2, v2) in zip(points, points[1:]):
        if v1 != v2 and (v1 - 0.5) * (v2 - 0.5) <= 0:
            return p1 + (p2 - p1) * (0.5 - v1) / (v2 - v1)
    return None


def parse_int(text: Any, default: int, low: int = 1, high: int = 10_000_000) -> int:
    """文本框 -> 整数（非法值回退到默认值，并夹在 [low, high] 内）。"""
    try:
        value = int(str(text).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def parse_float(text: Any, default: float, low: float = 0.0, high: float = 1.0) -> float:
    """文本框 -> 浮点数（非法值回退到默认值，并夹在 [low, high] 内）。"""
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))
