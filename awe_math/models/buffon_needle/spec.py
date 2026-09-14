# -*- coding: utf-8 -*-
"""
蒲丰投针模型 —— 界面元数据与动作处理器
========================================

本文件是「模型」与「界面」之间的唯一桥梁：

* :data:`PARAMS` 描述可调参数（针长/线距、投针根数、重复组数、随机种子），
  桌面 / 网页 / 终端三种界面都据此生成控件（桌面侧栏由 ``kit/form.py`` 自动生成）；
* :func:`handle` 处理界面发来的动作请求（投针一次、多组重复估计），返回 JSON 可序列化的结果；
* :func:`_cli` 是终端模式的入口。

算法本身在 :mod:`~awe_math.models.buffon_needle.model` 中，与本文件完全解耦。

它是本项目第一个**非渗流**模型：``spec.view`` 是 ``"buffon_needle"``，对应的桌面视图
（``views/tk.py``）继承的是**通用骨架** :class:`~awe_math.ui.tk.kit.base.ModelViewBase`
而不是渗流专用的 ``PercolationViewBase``。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from ...spec import ActionSpec, ModelSpec, ParamSpec
from .model import (
    DEFAULT_RATIO,
    DEFAULT_REPEATS,
    DEFAULT_THROWS,
    MAX_RATIO,
    MIN_RATIO,
    PI,
    BuffonNeedle,
    encode_needles,
)

# ----------------------------------------------------------------------
# 可调参数（桌面侧栏按 group 自动分组生成控件）
# ----------------------------------------------------------------------
PARAMS = (
    ParamSpec(
        key="ratio", label="针长 / 线距 (L/d)", kind="float", default=DEFAULT_RATIO,
        min=MIN_RATIO, max=MAX_RATIO, step=0.05, group="几何",
        hint="L ≤ d 时经典结论才成立：命中概率 = 2L/(πd)，于是 π ≈ 2LN/(dH)。",
    ),
    ParamSpec(
        key="throws", label="投针根数 N", kind="int", default=DEFAULT_THROWS,
        min=50, max=20000, step=50, group="几何",
        hint="一次投掷多少根针。估计误差大致按 1/√N 缩小；命中数为 0 时无法反解 π。",
    ),
    ParamSpec(
        key="repeats", label="重复组数", kind="int", default=DEFAULT_REPEATS,
        min=2, max=200, step=1, group="收敛",
        hint="「多组重复估计」做多少组独立实验，用来观察估计值的波动（组间标准误）。",
    ),
    ParamSpec(
        key="seed", label="随机种子（-1 表示随机）", kind="int", default=-1,
        min=-1, max=2147483647, step=1, group="随机性",
        hint="取 ≥0 时同一种子可以复现完全相同的投针序列。",
    ),
)

# ----------------------------------------------------------------------
# 动作
# ----------------------------------------------------------------------
ACTIONS = (
    ActionSpec("throw", "投针一次", mode="once", kind="primary",
               hint="随机投 N 根针，画出布局并按命中率估计 π"),
    ActionSpec("converge", "多组重复估计", mode="once", kind="default",
               hint="重复若干组独立实验，观察 π 的估计值随样本量收敛"),
)


# ----------------------------------------------------------------------
# 参数校正
# ----------------------------------------------------------------------
def _resolve_ratio(value: Any) -> float:
    """把界面传来的 L/d 比值夹到经典公式成立的范围内。"""
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return DEFAULT_RATIO
    return min(MAX_RATIO, max(MIN_RATIO, ratio))


def _resolve_throws(value: Any) -> int:
    try:
        count = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_THROWS
    return max(1, min(200000, count))


def _resolve_repeats(value: Any) -> int:
    try:
        groups = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_REPEATS
    return max(1, min(10000, groups))


def _resolve_seed(value: Any) -> Optional[int]:
    """把界面传来的种子转成 ``random`` 可用的形式：-1 表示随机。"""
    try:
        seed = int(float(value))
    except (TypeError, ValueError):
        return None
    return None if seed < 0 else seed


# ----------------------------------------------------------------------
# 动作处理器
# ----------------------------------------------------------------------
def _handle_throw(params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """投针一次：返回绘制布局与统计所需的全部数据。"""
    model = BuffonNeedle(
        ratio=_resolve_ratio(params.get("ratio")),
        throws=_resolve_throws(params.get("throws")),
        rng=_resolve_seed(params.get("seed")),
    )
    res = model.throw()
    pi_hat = res.pi_estimate
    return {
        "view": "buffon-needle",
        "ratio": res.ratio,
        "length": res.length,
        "gap": res.gap,
        "width": res.width,
        "height": res.height,
        "piTrue": PI,
        "throws": res.throws,
        "hits": res.hits,
        "hitRate": res.hit_rate,
        "theoryRate": res.theory_rate,
        "piEstimate": pi_hat,
        "absError": res.abs_error,
        "relError": res.rel_error,
        "elapsedMs": res.elapsed * 1000.0,
        # 几何用「坐标数组 + 0/1 掩码」压缩传输，前端解析只需一次遍历
        **encode_needles(res),
    }


def _handle_converge(params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """多组重复估计：返回每个样本点的累计估计值，用于画收敛过程。"""
    model = BuffonNeedle(
        ratio=_resolve_ratio(params.get("ratio")),
        throws=_resolve_throws(params.get("throws")),
        rng=_resolve_seed(params.get("seed")),
    )
    res = model.converge(repeats=_resolve_repeats(params.get("repeats")))
    return {
        "view": "buffon-converge",
        "ratio": res.ratio,
        "length": res.length,
        "gap": res.gap,
        "piTrue": PI,
        "repeats": res.repeats,
        "throwsPerGroup": res.throws_per_group,
        "totalThrows": res.total_throws,
        "totalHits": res.total_hits,
        "hitRate": res.hit_rate,
        "theoryRate": res.theory_rate,
        "piEstimate": res.pi_estimate,
        "absError": res.abs_error,
        "meanEstimate": res.mean_estimate,
        "stderr": res.stderr,
        "samples": [
            {"throws": n, "hits": h, "estimate": e}
            for n, h, e in res.samples
        ],
        "elapsedMs": res.elapsed * 1000.0,
    }


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """动作分发入口，由 :class:`~awe_math.spec.ModelSpec` 调用。"""
    if action == "throw":
        return _handle_throw(params, payload)
    if action == "converge":
        return _handle_converge(params, payload)
    raise ValueError(f"蒲丰投针模型不支持的动作：{action}")


# ----------------------------------------------------------------------
# 终端模式
# ----------------------------------------------------------------------
#: ``--scan`` 模式下逐级放大的投针数（观察估计值收敛）
_SCAN_SIZES = (100, 200, 500, 1000, 2000, 5000, 10000)


def _cli(args) -> int:
    """命令行模式：投针一次，或（``--scan``）逐级放大投针数观察收敛。

    本模型可用的命令行参数（沿用统一入口的参数名）：
    ``--p`` 表示「针长 / 线距」比值（默认 0.8）、``--trials`` 表示投针根数、
    ``--seed`` 为随机种子、``--scan`` 切换为收敛扫描。
    """
    ratio = _resolve_ratio(getattr(args, "p", None))
    throws = _resolve_throws(getattr(args, "trials", DEFAULT_THROWS))
    seed = _resolve_seed(getattr(args, "seed", -1))
    model = BuffonNeedle(ratio=ratio, throws=throws, rng=seed)

    header = (f"蒲丰投针 | L/d = {ratio:.2f}（针长 {model.length:.2f}，线距 {model.gap:.2f}）"
              f" | 理论命中率 2L/(πd) = {model.theory_rate:.4f}")
    print("=" * 78)
    if getattr(args, "scan", False):
        print(f"收敛扫描 | {header}")
        print("=" * 78)
        print(f"{'投针数 N':>10} | {'命中数 H':>10} | {'实测命中率':>12} | "
              f"{'π 估计':>10} | {'误差':>10}")
        print("-" * 78)
        for count in _SCAN_SIZES:
            res = model.throw(count)
            pi_hat = res.pi_estimate
            shown = "—" if pi_hat is None else f"{pi_hat:.4f}"
            err = "—" if res.abs_error is None else f"{res.abs_error:.4f}"
            print(f"{res.throws:>10} | {res.hits:>10} | {res.hit_rate:>12.4f} | "
                  f"{shown:>10} | {err:>10}")
        print("-" * 78)
        print("提示：针随机地落在平面上，「针与线相交」的概率 = 2L/(πd)，"
              "于是 π ≈ 2LN/(dH)；")
        print("      误差大致按 1/√N 缩小；命中数为 0 时无法反解 π。")
        return 0

    print(f"投针一次 | {header}")
    print("=" * 78)
    res = model.throw()
    pi_hat = res.pi_estimate
    print(f"投出 {res.throws} 根针，命中 {res.hits} 根（{res.hit_rate:.4f}"
          f" vs 理论 {res.theory_rate:.4f}）")
    if pi_hat is None:
        print("本次没有命中任何一条线，无法反解 π（请增大投针根数或换随机种子）。")
    else:
        print(f"π ≈ 2LN/(dH) = {pi_hat:.6f}（真值 {PI:.6f}，"
              f"绝对误差 {res.abs_error:.6f}，相对误差 {res.rel_error:.2%}）")
    print(f"耗时 {res.elapsed * 1000:.1f} ms")
    print("-" * 78)

    conv = model.converge(repeats=DEFAULT_REPEATS)
    total = conv.total_throws
    final = conv.pi_estimate
    print(f"多组重复 | {conv.repeats} 组 × {conv.throws_per_group} 根 = {total} 根，"
          f"累计命中 {conv.total_hits}（{conv.hit_rate:.4f}）")
    if final is not None:
        mean = conv.mean_estimate
        print(f"累计估计 π ≈ {final:.6f}（误差 {conv.abs_error:.6f}）"
              + (f"，组间均值 {mean:.4f} ± {conv.stderr:.4f}"
                 if mean is not None else ""))
    print("=" * 78)
    return 0


def build_spec() -> ModelSpec:
    """构造并返回蒲丰投针模型的元数据。"""
    return ModelSpec(
        key="buffon_needle",
        name="蒲丰投针模型",
        topic="概率与统计",
        summary="在间距为 d 的平行线上随机投 N 根长 L 的针，"
                "用命中频率反解 π：L ≤ d 时命中概率 = 2L/(πd)，故 π ≈ 2LN/(dH)。",
        description=(
            "在一组间距为 d 的平行线上随机投 N 根长度为 L（L ≤ d）的针。\n\n"
            "**一根针是否与线相交**：只有「针心到最近一条线的距离」与「针的倾斜程度」"
            "共同决定 —— 距离 ≤ (L/2)·sin θ 时才相交。于是\n\n"
            "    命中概率 P = 2L / (π d)（要求 L ≤ d），\n\n"
            "把频率 H/N 当作概率解出来，就得到 π 的估计\n\n"
            "    π ≈ 2 L N / (d H)。\n\n"
            "这就是蒲丰投针：**用随机试验去求一个确定性的几何常数**。它与渗流模型同属"
            "「量变引起质变」之外的另一类蒙特卡洛思想 —— 样本越多估计越准，误差大致按 "
            "1/√N 缩小，但永远不会精确等于 π。\n\n"
            "界面上的两个动作：\n\n"
            "1. **投针一次**：投出 N 根针并画出布局（命中为橙色、未命中为灰色），"
            "右侧给出命中率、理论命中率与 π 的估计值；\n"
            "2. **多组重复估计**：重复若干组独立实验，画出估计值随累计样本量向 π 收敛的"
            "过程，并给出组间均值与标准误。\n\n"
            "注意：L > d 时经典结论不再成立（命中概率不再是 2L/(πd)），因此本模型把 "
            "L/d 限制在 [0.05, 1]；命中数为 0 时无法反解 π。"
        ),
        params=PARAMS,
        actions=ACTIONS,
        view="buffon_needle",
        accent="#f59e0b",
        icon="π",
        handler=handle,
        cli=_cli,
        highlights=("随机投针估计 π：π ≈ 2LN/(dH)",
                    "L ≤ d 时命中概率 = 2L/(πd)",
                    "投针越多越准，误差 ≈ 1/√N"),
        order=10,
    )
