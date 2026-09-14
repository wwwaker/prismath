# -*- coding: utf-8 -*-
"""
成功判据策略
=============

「什么算成功」由判据决定，而判据会牵动界面上一大堆东西：结论徽章、画布结论行、统计行标题、
历史表列名、曲线页的说明与 p_c 参考线…… 以前这些分支以 ``if criterion == "span" ...`` 的
形式散落在 :mod:`~awe_math.ui.tk.kit.results` 与 :mod:`~awe_math.ui.tk.kit.canvas` 里，于是
「新增一种判据」就得回头改工具箱。

本模块把每种判据收成一个 :class:`Criterion` **策略对象**：判据 -> (短名、统计词、徽章文案、
结论文案、曲线标注、是否对应 p_c、批量统计的补充说明)。工具箱只按策略对象取文案与判定结果，
**不再认识任何具体判据**；模型要加自己的判据时，往
:attr:`~awe_math.ui.tk.kit.base.PercolationViewBase.CRITERIA` 里加一条即可。

三个内置判据（``span`` / ``origin`` / ``area``）的文案与判定逻辑与重构前逐字一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple

from .common import ActiveView, Terms

__all__ = ["Criterion", "DEFAULT_CRITERIA", "LEVELS", "OK", "NO", "BAD"]

#: 徽章等级：成立 / 不成立 / 无法判定
OK, NO, BAD = "ok", "no", "bad"
LEVELS = (OK, NO, BAD)

#: ``badge`` 的签名：``(归一化结果, 术语表) -> (文案, 等级)``
BadgeFn = Callable[[ActiveView, Terms], Tuple[str, str]]
#: ``verdict`` 的签名：``(归一化结果, 术语表) -> (文案, 是否成立)``
VerdictFn = Callable[[ActiveView, Terms], Tuple[str, bool]]
#: ``rule`` 的签名：``(模型, 术语表) -> 状态栏短句``
RuleFn = Callable[[Any, Terms], str]
#: ``batch_tail`` 的签名：``(批量结果, 模型, 术语表) -> 补充说明``
TailFn = Callable[[Any, Any, Terms], str]


@dataclass(frozen=True)
class Criterion:
    """一种「成功判据」的全部界面语义。"""

    key: str
    #: 短名（历史表列名与图表用），例如「贯通」
    short: str
    #: 统计行标题的词干（后接「次数」「概率」），例如「存在纵贯簇」
    head: str
    #: 该判据的 1/2 交点是否等于 p_c（只有贯通判据为真）
    pc_applies: bool
    #: 面积阈值是否在该判据下生效（只有面积判据为真）
    uses_threshold: bool
    #: 状态栏 / 画布标题里的短句
    rule: RuleFn
    #: 结论徽章：``(view, terms) -> (文案, 等级)``
    badge: BadgeFn
    #: 画布结论行：``(view, terms) -> (文案, 是否成立)``
    verdict: VerdictFn
    #: 批量统计结论的补充说明
    batch_tail: TailFn
    #: 曲线页标题里的判据名（面积判据会由工具箱补上阈值）
    curve_label: str
    #: 曲线页在「交点不是 p_c」时的提示（贯通判据为空）
    curve_note: str = ""


# ----------------------------------------------------------------------
# 贯通判据：整片区域是否存在顶行 ↔ 底行的纵贯簇（p_c 所对应的判据）
# ----------------------------------------------------------------------
def _badge_span(view: ActiveView, terms: Terms) -> Tuple[str, str]:
    if view.spans:
        return (f"✔ 存在纵贯簇（{view.spanning_count} {terms.unit}，"
                f"{terms.active_verb} {view.active_ratio:.1%}）", OK)
    return f"✘ 没有纵贯簇（{terms.active_verb} {view.active_ratio:.1%}）", NO


def _verdict_span(view: ActiveView, terms: Terms) -> Tuple[str, bool]:
    ok = view.spans
    text = (f"✔ {terms.arena}存在纵贯簇（顶行 ↔ 底行）" if ok
            else f"✘ {terms.arena}没有纵贯簇")
    return text + f"；{terms.active_phrase} {view.active_ratio:.1%}", ok


def _rule_span(model: Any, terms: Terms) -> str:
    return f"判据 贯通（{terms.arena}有无纵贯簇）"


def _tail_span(res: Any, model: Any, terms: Terms) -> str:
    pc = getattr(model, "theoretical_pc", None)
    return (f"贯通判据下，成功概率 ≈ 1/2 的位置就是{terms.pc_word} p_c"
            + (f" = {pc:.4f}。" if pc is not None else "（该组合暂无已知值）。"))


# ----------------------------------------------------------------------
# 起点判据：从注水点出发的那一簇是否纵贯（随注水方式变化）
# ----------------------------------------------------------------------
def _badge_origin(view: ActiveView, terms: Terms) -> Tuple[str, str]:
    if view.origin_spans:
        return f"✔ 起点纵贯（{terms.active_verb} {view.active_ratio:.1%}）", OK
    if view.spans:
        return f"✘ 起点在纵贯簇外（簇 {view.spanning_count} {terms.unit}）", NO
    return f"✘ 起点未纵贯（{terms.active_verb} {view.active_ratio:.1%}）", NO


def _verdict_origin(view: ActiveView, terms: Terms) -> Tuple[str, bool]:
    ok = view.origin_spans
    if ok:
        text = (f"✔ 起点纵贯：{terms.origin_cluster_phrase}碰到顶行与底行"
                f"（{terms.active_verb} {view.active_ratio:.1%}）")
    elif view.spans:
        text = (f"✘ 起点未纵贯：{terms.arena}有纵贯簇"
                f"（{view.spanning_count} {terms.unit}，青色），"
                f"但注水点不在簇内（{terms.active_verb} {view.active_ratio:.1%}）")
    else:
        text = (f"✘ 起点未纵贯，{terms.arena}也没有纵贯簇"
                f"（{terms.active_verb} {view.active_ratio:.1%}）")
    return text, ok


def _rule_origin(model: Any, terms: Terms) -> str:
    return "判据 起点纵贯（注水点的簇碰顶又碰底）"


def _tail_origin(res: Any, model: Any, terms: Terms) -> str:
    return ("起点判据下，1/2 交点高于 p_c —— 它还额外要求"
            "「注水点落在纵贯簇里」；注水方式选「顶端整行」时才等于 p_c。")


# ----------------------------------------------------------------------
# 面积判据：活动面积达到设定比例（没有固定临界值）
# ----------------------------------------------------------------------
def _badge_area(view: ActiveView, terms: Terms) -> Tuple[str, str]:
    if view.engulfed:
        return f"✔ 面积达标 {view.active_ratio:.1%}（≥{view.threshold:.0%}）", OK
    return f"✘ 面积不足 {view.active_ratio:.1%}（<{view.threshold:.0%}）", NO


def _verdict_area(view: ActiveView, terms: Terms) -> Tuple[str, bool]:
    ok = view.engulfed
    if ok:
        text = (f"✔ 面积判据达标：{terms.active_verb} {view.active_ratio:.1%}"
                f"（≥{view.threshold:.0%}）")
    else:
        text = (f"✘ 面积未达标：{terms.active_verb} {view.active_ratio:.1%}"
                f"（<{view.threshold:.0%}）")
    return text, ok


def _rule_area(model: Any, terms: Terms) -> str:
    return f"判据 面积 ≥ {model.threshold:.0%}"


def _tail_area(res: Any, model: Any, terms: Terms) -> str:
    return ("面积判据下这个概率随所设比例变化，其 1/2 交点不是 p_c"
            "（想量 p_c 请把判据切到「贯通判据」）。")


#: 渗流类模型的三个内置判据（键与 ``_options.CRITERION_CHOICES`` 的取值一致）
DEFAULT_CRITERIA: Dict[str, Criterion] = {
    "span": Criterion(
        key="span", short="贯通", head="存在纵贯簇",
        pc_applies=True, uses_threshold=False,
        rule=_rule_span, badge=_badge_span, verdict=_verdict_span,
        batch_tail=_tail_span,
        curve_label="贯通判据", curve_note="",
    ),
    "origin": Criterion(
        key="origin", short="起点", head="起点纵贯",
        pc_applies=False, uses_threshold=False,
        rule=_rule_origin, badge=_badge_origin, verdict=_verdict_origin,
        batch_tail=_tail_origin,
        curve_label="起点判据",
        curve_note=("起点判据：交点高于 p_c —— 还要看注水点是否落在纵贯簇里；"
                    "注水方式选「顶端整行」时才等于 p_c"),
    ),
    "area": Criterion(
        key="area", short="面积", head="面积达标",
        pc_applies=False, uses_threshold=True,
        rule=_rule_area, badge=_badge_area, verdict=_verdict_area,
        batch_tail=_tail_area,
        curve_label="面积判据",
        curve_note="面积判据：曲线交点随「比例 / 网格尺寸 / 注水方式」变化，不是 p_c",
    ),
}
