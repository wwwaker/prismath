# -*- coding: utf-8 -*-
"""
点渗流模型 —— 界面元数据与动作处理器
======================================

本文件是「模型」与「界面」之间的唯一桥梁：

* :data:`PARAMS` 描述可调参数，网页/桌面/终端三种界面都据此生成控件；
* :func:`handle` 处理界面发来的动作请求（蔓延一次、批量统计），返回 JSON 可序列化的结果；
* :func:`_cli` 是终端模式的入口。

算法本身在 :mod:`~awe_math.models.site_percolation.model` 中，与本文件完全解耦。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from ...spec import ActionSpec, ModelSpec, ParamSpec
from .._options import (
    DIRECTION_CHOICES,
    LATTICE_CHOICES,
    CRITERION_CHOICES,
    SITE_INJECT_CHOICES,
)
from .model import (
    CRITERIA,
    CRITERION_DESCRIPTIONS,
    DEFAULT_CRITERION,
    DEFAULT_THRESHOLD,
    SitePercolation,
    batch_spread_probability,
    encode_sites,
    scan_curve,
)

# ----------------------------------------------------------------------
# 可调参数（界面自动生成控件，按 group 分组显示）
# ----------------------------------------------------------------------
PARAMS = (
    ParamSpec(
        key="p", label="占据密度 p", kind="float", default=0.6,
        min=0.0, max=1.0, step=0.01, group="格地与占据",
        hint="每个格子被占据（长树）的概率。方格点渗流（无向）临界密度 p_c ≈ 0.5927，"
             "注意这个 p_c 属于「贯通判据」，不属于「面积判据」。",
    ),
    ParamSpec(
        key="rows", label="行数 n", kind="int", default=30,
        min=5, max=80, step=1, group="格地与占据",
        hint="格地行数（格子数 = 行数 × 列数）。行数越大，相变越陡峭。",
    ),
    ParamSpec(
        key="cols", label="列数 m", kind="int", default=30,
        min=5, max=80, step=1, group="格地与占据",
        hint="列数 ≠ 行数 即为矩形格地。临界密度与长宽比无关，只改变有限尺寸下的曲线形状。",
    ),
    ParamSpec(
        key="threshold", label="面积判据阈值", kind="choice", default="0.5",
        choices=("0.3", "0.5", "0.7", "0.9"), group="格地与占据",
        hint="只在「面积判据」下生效：蔓延格数达到总格数的这个比例才算成功。"
             "阈值取得越大，曲线的交点越往高处跑 —— 它不是一个固定的临界值。",
    ),
    ParamSpec(
        key="seed", label="随机种子（-1 表示随机）", kind="int", default=-1,
        min=-1, max=2147483647, step=1, group="格地与占据",
        hint="取 ≥0 时同一种子可以复现完全相同的格地与蔓延过程。",
    ),
    ParamSpec(
        key="criterion", label="成功判据", kind="choice",
        default="贯通判据：顶行连通到底行（对应 p_c）",
        choices=tuple(CRITERION_CHOICES), group="高级选项",
        hint="三种判据回答的是三个不同的问题：\n"
             "· 贯通判据：整片格地是否存在顶行↔底行的纵贯簇 —— 这才是 p_c = 0.5927 的判据，"
             "与注水方式无关；\n"
             "· 起点判据：从注水点出发的那一簇是否纵贯 —— 随注水方式变化，"
             "顶端整行时与贯通判据相同（随机起火常常落在纵贯簇之外）；\n"
             "· 面积判据：蔓延面积达到设定比例 —— 没有固定临界值，交点随比例、网格尺寸、"
             "注水方式一起变。",
    ),
    ParamSpec(
        key="lattice", label="格子类型", kind="choice", default="方格网（4 邻域）",
        choices=tuple(LATTICE_CHOICES), group="高级选项",
        hint="三角网每点有 6 个邻居，无向点渗流临界密度 p_c = 0.5（方格网为 0.5927）。",
    ),
    ParamSpec(
        key="direction", label="方向模式", kind="choice", default="无向（四面流动）",
        choices=tuple(DIRECTION_CHOICES), group="高级选项",
        hint="无向 = 标准点渗流；不允许向上 / 只允许向下向右会提高临界密度。"
             "注意：经典的「火只往上下左右烧」就是无向模式。",
    ),
    ParamSpec(
        key="inject", label="注水（起始）方式", kind="choice", default="随机一个占据格",
        choices=tuple(SITE_INJECT_CHOICES), group="高级选项",
        hint="随机一个占据格 = 经典「随机一棵树起火」；中心附近 / 顶端整行用于对照实验。",
    ),
    ParamSpec(
        key="trials", label="批量统计次数 N", kind="choice", default="1000",
        choices=("100", "500", "1000", "5000"), group="批量统计",
        hint="独立重复实验的次数：每次重新生成格地，统计「当前判据」的成功频率。",
    ),
    ParamSpec(
        key="scanTrials", label="曲线每点次数", kind="choice", default="200",
        choices=("50", "100", "200", "500"), group="曲线扫描",
        hint="密度曲线上每个 p 值做多少次实验。",
    ),
    ParamSpec(
        key="scanStep", label="p 扫描步进", kind="choice", default="0.05",
        choices=("0.02", "0.05", "0.1"), group="曲线扫描",
        hint="步进越小曲线越细腻，计算量也越大。",
    ),
)

# ----------------------------------------------------------------------
# 动作
# ----------------------------------------------------------------------
ACTIONS = (
    ActionSpec("spread", "蔓延一次", mode="once", kind="primary",
               hint="重新生成格地并在注水点开始蔓延，BFS 记录逐层过程"),
    ActionSpec("batch", "批量统计", mode="chunk", kind="default",
               hint="分块执行 N 次独立实验，统计当前判据下的成功频率与平均蔓延比例"),
)


def _pick(mapping: Dict[str, str], value: Any, fallback: str) -> str:
    """把界面上的中文选项翻译成模型内部取值（无法识别时回退）。"""
    return mapping.get(str(value), fallback)


def _resolve_seed(value: Any) -> Optional[int]:
    """把界面传来的种子转成 ``random`` 可用的形式：-1 表示随机。"""
    try:
        seed = int(value)
    except (TypeError, ValueError):
        return None
    return None if seed < 0 else seed


def _resolve_size(raw: Any, default: int) -> int:
    """把界面传来的行/列数转成合法整数。"""
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return default
    return max(2, value)


def _resolve_threshold(value: Any) -> float:
    """把界面传来的阈值字符串转成浮点数（非法时回退到默认值）。"""
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD
    return min(1.0, max(0.05, threshold))


def _options(params: Dict[str, Any]) -> Dict[str, Any]:
    """从界面参数里取出格子/方向/注水/判据选项（含矩形形状）。"""
    return {
        "rows": _resolve_size(params.get("rows"), 30),
        "cols": _resolve_size(params.get("cols"), 30),
        "lattice": _pick(LATTICE_CHOICES, params.get("lattice"), "square"),
        "direction": _pick(DIRECTION_CHOICES, params.get("direction"), "undirected"),
        "inject": _pick(SITE_INJECT_CHOICES, params.get("inject"), "random"),
        "criterion": _pick(CRITERION_CHOICES, params.get("criterion"), DEFAULT_CRITERION),
        "threshold": _resolve_threshold(params.get("threshold")),
    }


def build_grid(params: Dict[str, Any]) -> SitePercolation:
    """由参数构造模型实例 —— **A/B 两套契约共用的唯一构造入口**。

    数据级契约（:func:`handle`）与对象级契约（桌面视图的 ``spec.factory``）都调用它，
    于是"界面参数 -> 模型"的换算只写一份。

    ``params`` 里的 ``lattice`` / ``direction`` / ``inject`` / ``criterion`` 必须是模型
    **内部取值**（界面上的中文标签请先用 :func:`_options` 翻译）；
    ``rng`` 可以是 ``None`` / 种子 / ``random.Random`` 实例（也接受 ``seed``）。
    """
    if "rng" not in params and "seed" in params:
        params = {**params, "rng": _resolve_seed(params.get("seed"))}
    return SitePercolation(
        rows=_resolve_size(params.get("rows"), 30),
        cols=params.get("cols"),
        p=float(params.get("p", 0.6)),
        rng=params.get("rng"),
        lattice=params.get("lattice", "square"),
        direction=params.get("direction", "undirected"),
        inject=params.get("inject", "random"),
        criterion=params.get("criterion", DEFAULT_CRITERION),
        threshold=_resolve_threshold(params.get("threshold")),
    )


def _handle_spread(params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """蔓延一次：返回前端绘制逐层动画所需的全部数据。

    ``payload`` 里可以带上 ``origin``（格子索引），用于「点击格地指定注水点」。
    """
    options = _options(params)
    p = float(params.get("p", 0.6))
    model = build_grid({**options, "p": p, "rng": _resolve_seed(params.get("seed"))})

    origins: Optional[List[int]] = None
    origin = payload.get("origin")
    if origin is not None:
        try:
            index = int(origin)
        except (TypeError, ValueError):
            index = -1
        if 0 <= index < model.node_count and model.is_occupied(index):
            origins = [index]

    result = model.simulate(origins)
    base = {
        "view": "site-percolation",
        "rows": result.rows,
        "cols": result.cols,
        "size": result.rows,          # 兼容旧前端
        "p": p,
        "lattice": model.lattice,
        "direction": model.direction,
        "inject": model.inject,
        "latticeName": model.lattice_name,
        "directionName": model.direction_name,
        "injectName": model.inject_name,
        "criterion": model.criterion,
        "criterionName": model.criterion_name,
        "criterionHint": CRITERION_DESCRIPTIONS[model.criterion],
        "threshold": result.threshold,
        "nodeCount": model.node_count,      # 与边渗流同名，方便前端通用处理
        # 整片格地是否存在纵贯簇（与注水点无关，贯通判据就看这个）
        "spans": result.spans,
        # 从注水点出发的簇是否纵贯（起点判据看这个）
        "originSpans": result.origin_spans,
        "spanningCount": result.spanning_count,
        "spanningRatio": result.spanning_ratio,
        "spanningNodes": result.spanning_nodes,
        "originInSpanning": result.origin_in_spanning,
        "theoreticalPc": model.theoretical_pc,
        "pcApplies": model.pc_applies,
        "pcIsEstimate": model.pc_is_estimate,
        "pcLabel": model.pc_label,
        # 格地用 0/1 字符串压缩传输
        "sites": encode_sites(model),
    }

    if not result.has_source:
        return {**base, "empty": True, "origins": [], "spread": [], "layers": []}

    return {
        **base,
        "empty": False,
        "origins": result.origins,
        "origin": result.origins[0],
        "spread": result.spread,
        "layers": result.layers,
        "occupiedCount": result.occupied_count,
        "occupiedRatio": result.occupied_ratio,
        "spreadCount": result.spread_count,
        "spreadRatio": result.spread_ratio,
        "clusterRatio": result.cluster_ratio,
        "depth": result.depth,
        "engulfed": result.engulfed,
        "success": result.success,
        "reachedBottom": result.reached_bottom,
        "elapsedMs": result.elapsed * 1000.0,
    }


def _handle_batch(params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """执行一小批独立实验（分块），由前端循环累加得到总频率。

    ``payload`` 可覆盖 ``trials``（本块次数）、``seed``（本块种子）与 ``p``
    （曲线扫描时逐点变化），从而让一次统计既能显示进度、又完全可复现。
    """
    merged = dict(params)
    for key in ("rows", "cols", "lattice", "direction", "inject", "criterion", "threshold"):
        if key in payload:
            merged[key] = payload[key]
    options = _options(merged)
    p = float(payload.get("p", params["p"]))
    trials = max(1, int(payload.get("trials", params["trials"])))
    seed = _resolve_seed(payload.get("seed", params.get("seed")))

    result = batch_spread_probability(
        p=p, trials=trials, rng=seed, **options
    )
    return {
        "p": p,
        "rows": result.rows,
        "cols": result.cols,
        "size": result.rows,
        "threshold": result.threshold,
        "criterion": result.criterion,
        "criterionName": result.criterion_name,
        "criterionHint": CRITERION_DESCRIPTIONS[result.criterion],
        "pcApplies": result.criterion == "span",
        "lattice": result.lattice,
        "direction": result.direction,
        "inject": result.inject,
        "trials": result.trials,
        "success": result.success,
        "probability": result.probability,
        "meanRatio": result.mean_ratio,
        "stderr": result.stderr,
        "elapsedMs": result.elapsed * 1000.0,
    }


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """动作分发入口，由 :class:`~awe_math.spec.ModelSpec` 调用。"""
    if action == "spread":
        return _handle_spread(params, payload)
    if action == "batch":
        return _handle_batch(params, payload)
    raise ValueError(f"点渗流模型不支持的动作：{action}")


# ----------------------------------------------------------------------
# 终端模式
# ----------------------------------------------------------------------
def _cli(args) -> int:
    """命令行模式：单次蔓延 + 批量统计，或扫描「密度 -> 蔓延概率」曲线。"""
    rows = max(2, min(400, int(getattr(args, "size", 40))))
    cols = getattr(args, "cols", None)
    cols = rows if cols is None else max(2, min(400, int(cols)))
    trials = max(1, int(getattr(args, "trials", 1000)))
    raw_p = getattr(args, "p", None)
    p = 0.6 if raw_p is None else float(raw_p)

    lattice = getattr(args, "lattice", None)
    if lattice not in LATTICE_CHOICES.values():
        lattice = "square"
    direction = getattr(args, "direction", None)
    if direction not in DIRECTION_CHOICES.values():
        direction = "no_up" if getattr(args, "directed", False) else "undirected"
    inject = getattr(args, "inject", None)
    if inject not in SITE_INJECT_CHOICES.values():
        inject = "random"
    criterion = getattr(args, "criterion", None)
    if criterion not in CRITERIA:
        criterion = DEFAULT_CRITERION
    threshold = _resolve_threshold(getattr(args, "threshold", None))

    options = {"lattice": lattice, "direction": direction, "inject": inject,
               "criterion": criterion}
    shape = f"{rows}×{cols}" if rows != cols else f"{rows}×{rows}"
    probe = build_grid({"rows": rows, "cols": cols, "p": p, **options})
    # 判据名称由下一行的 rule 给出，这里只放临界值说明，避免「判据：… | 判据：…」重复
    header = (f"{probe.lattice_name} {shape} | {probe.direction_name} | "
              f"注水：{probe.inject_name} | {probe.pc_label}")
    if criterion == "span":
        rule = "贯通判据：整片格地是否存在纵贯簇"
    elif criterion == "origin":
        rule = "起点判据：从注水点出发的簇是否纵贯顶底"
    else:
        rule = f"面积判据：蔓延比例 ≥ {threshold:.0%}"

    if getattr(args, "scan", False):
        step = float(getattr(args, "step", 0.05))
        p_values: List[float] = []
        k = 0
        while k * step <= 1.0 + 1e-9:
            p_values.append(round(k * step, 3))
            k += 1

        print("=" * 78)
        print(f"点渗流密度扫描 | {header}")
        print(f"每点 {trials} 次实验 | {rule}")
        print("=" * 78)
        print(f"{'占据密度 p':>10} | {'成功概率':>12} | {'平均蔓延比例':>12} | 分布")
        print("-" * 78)

        def on_point(done: int, total: int, res) -> None:
            bar = "█" * int(round(res.mean_ratio * 26))
            print(f"{res.p:>10.2f} | {res.probability:>12.4f} | "
                  f"{res.mean_ratio:>12.4f} | {bar}")
            sys.stdout.flush()

        scan_curve(p_values, rows=rows, cols=cols, trials=trials,
                   rng=_resolve_seed(getattr(args, "seed", -1)),
                   threshold=threshold, progress=on_point, **options)
        print("-" * 78)
        if criterion == "span":
            print("提示：成功概率 = 1/2 的交点即临界密度 p_c（p 越过它，纵贯簇出现 —— 相变）。")
        elif criterion == "origin":
            print("提示：起点判据的交点高于 p_c —— 它额外要求「起点落在纵贯簇里」；")
            print("      注水方式选「顶端整行」时它与贯通判据完全相同。")
        else:
            print("提示：面积判据的交点不是固定临界值，它随所设比例、网格尺寸、注水方式变化；")
            print("      只有「贯通判据」的交点才等于 p_c。")
        return 0

    model = build_grid({"rows": rows, "cols": cols, "p": p, "threshold": threshold,
                        "rng": _resolve_seed(getattr(args, "seed", -1)), **options})
    single = model.simulate()
    print("=" * 78)
    print(f"单次蔓延 | {header}")
    print(f"占据格 {model.occupied_count()}/{model.node_count}"
          f"（实测密度 {model.occupied_ratio():.3f}）| {rule}")
    rows_out = [divmod(i, model.cols) for i in single.origins[:4]]
    if not single.has_source:
        print("没有可用的注水点（顶端整行注水时该行可能一个占据格都没有）。")
    else:
        print(f"注水点 (行, 列) = {rows_out}{' …' if len(single.origins) > 4 else ''}")
        print(f"蔓延格数 {single.spread_count}/{single.node_count}"
              f"（{single.spread_ratio:.1%}），蔓延 {single.depth} 层，"
              f"耗时 {single.elapsed * 1000:.1f} ms")
    bottom = "已到达底端" if single.reached_bottom else "未到达底端"
    if criterion == "span":
        verdict = "存在纵贯簇 ✔" if single.spans else "没有纵贯簇 ✘"
        print(f"整片格地是否存在纵贯簇（顶行 ↔ 底行）：{verdict}"
              f"（纵贯簇 {single.spanning_count} 格，{single.spanning_ratio:.1%}）；"
              f"本次蔓延{bottom}。")
    elif criterion == "origin":
        verdict = "纵贯 ✔" if single.origin_spans else "未纵贯 ✘"
        note = "" if single.spans else "（格地上本来就没有纵贯簇）"
        inside = "在簇内" if single.origin_in_spanning else "在簇外"
        print(f"从注水点出发的簇是否纵贯顶行与底行：{verdict}{note}；"
              f"注水点{inside}；本次蔓延{bottom}。")
    else:
        verdict = f"达到 ≥{threshold:.0%} ✔" if single.engulfed else f"不足 {threshold:.0%} ✘"
        print(f"本次蔓延比例 {single.spread_ratio:.1%}，{verdict}；{bottom}。")

    res = batch_spread_probability(
        rows=rows, cols=cols, p=p, trials=trials,
        rng=_resolve_seed(getattr(args, "seed", -1)), threshold=threshold, **options,
    )
    print("-" * 78)
    print(f"批量统计 | 独立实验 {res.trials} 次 | {rule} 命中 {res.success} 次")
    print(f"该密度下「{res.criterion_name}」的成功概率 ≈ {res.probability:.4f} "
          f"± {res.stderr:.4f}，平均蔓延比例 {res.mean_ratio:.1%}"
          f"（耗时 {res.elapsed:.2f} s）")
    print("=" * 78)
    return 0


def build_spec() -> ModelSpec:
    """构造并返回点渗流模型的元数据。"""
    return ModelSpec(
        key="site_percolation",
        name="点渗流模型",
        topic="量变引起质变",
        summary="每格以概率 p 被占据，从注水点沿相邻占据格蔓延："
                "密度越过临界值后出现纵贯整片格地的巨簇，一次偶然的起因就能烧成一片。"
                "三种判据要分清：贯通（对 p_c = 0.5927）、起点纵贯（随注水方式变化）、"
                "面积比例（无固定阈值）。",
        description=(
            "把格地看成 rows × cols 的方格：每格以概率 p 独立地被占据（其余为空位），"
            "只有相邻的占据格之间才连通。从注水点出发蔓延，最终蔓延范围就是包含注水点的"
            "那个连通簇 —— 抽象地说，这就是「随机一棵树起火，火只沿上下左右烧，"
            "最终烧掉多大面积」的问题。\n\n"
            "**先分清三种「成功」的标准，它们的临界值完全不是一回事：**\n\n"
            "1. 贯通判据（默认）：整片格地上是否存在从顶行连通到底行的**纵贯簇**。"
            "二维方格点渗流（无向）的理论临界密度 p_c ≈ 0.5927 说的就是这个相变，"
            "所以它的「成功概率 = 1/2」交点落在 p_c 上，且与注水方式无关。"
            "（注意它高于方格网**边**渗流的 0.5 —— 随机的是格子而不是边；"
            "三角网点渗流 p_c = 0.5。）\n\n"
            "2. 起点判据：**从注水点出发的那一簇**是否纵贯（碰到顶行与底行）。"
            "它与贯通判据的唯一差别是「还要求注水点落在纵贯簇里」：顶端整行注水时"
            "两者完全相同，随机 / 中心单点注水时交点明显更高 —— 格地上明明有纵贯簇，"
            "一次随机起火却可能烧在簇外，只覆盖很小一片。\n\n"
            "3. 面积判据：从注水点出发的蔓延面积达到设定比例。它回答的是「一次起因"
            "能烧掉多大面积」，**没有固定的临界密度**：比例定得越大交点越高，"
            "单点注水还会额外要求「起点恰好落在巨簇里」，网格尺寸也会影响它。\n\n"
            "后两种判据的交点都**不是** p_c（把它们的交点当成 p_c 是常见误解）；"
            "方向模式会改变临界值（只允许向下/向右的有向点渗流临界密度更高）；"
            "而矩形长宽比与注水点位置都不改变临界值，只影响有限尺寸下的曲线形状"
            "—— 这些结论都只在贯通判据下成立。"
        ),
        params=PARAMS,
        actions=ACTIONS,
        view="site_percolation",
        accent="#a78bfa",
        icon="▦",
        handler=handle,
        cli=_cli,
        # 对象级契约：桌面视图直接渲染、后台批量统计 / 曲线扫描都复用它，
        # 于是「界面参数 -> 模型」与「批量/扫描函数」不必在视图里再写一遍
        factory=build_grid,
        batch=batch_spread_probability,
        scan=scan_curve,
        highlights=("三种成功判据：贯通（对 p_c）/ 起点纵贯（随注水方式）/ 面积比例",
                    "方格网 p_c ≈ 0.5927 / 三角网 0.5",
                    "矩形格地 + 四种方向模式 + 三种注水方式"),
        order=20,
    )
