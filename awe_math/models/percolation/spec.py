# -*- coding: utf-8 -*-
"""
边渗流模型 —— 界面元数据与动作处理器
======================================

本文件是「模型」与「界面」之间的唯一桥梁：

* :data:`PARAMS` 描述可调参数，网页/桌面/终端三种界面都据此生成控件；
* :func:`handle` 处理界面发来的动作请求（生成网格、批量统计），返回 JSON 可序列化的结果；
* :func:`_cli` 是终端模式的入口。

算法本身在 :mod:`~awe_math.models.percolation.model` 中，与本文件完全解耦。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from ...spec import ActionSpec, CliArgs, ModelSpec, ParamSpec
from .._cli import GRID_CLI_OPTIONS
from .._options import (
    CRITERION_CHOICES,
    DIRECTION_CHOICES,
    LATTICE_CHOICES,
)
from .._options import BOND_INJECT_CHOICES as INJECT_CHOICES
from .model import (
    CRITERIA,
    CRITERION_DESCRIPTIONS,
    DEFAULT_CRITERION,
    DEFAULT_THRESHOLD,
    PercolationGrid,
    batch_percolation_probability,
    encode_edges,
    scan_curve,
)

# ----------------------------------------------------------------------
# 可调参数（界面自动生成控件，按 group 分组显示）
# ----------------------------------------------------------------------
PARAMS = (
    ParamSpec(
        key="p", label="流通概率 p", kind="float", default=0.5,
        min=0.0, max=1.0, step=0.01, group="网格与边缘",
        hint="每条边独立流通的概率。p 越过临界值附近会发生相变。",
    ),
    ParamSpec(
        key="rows", label="行数 n", kind="int", default=30,
        min=5, max=80, step=1, group="网格与边缘",
        hint="网格行数（节点数 = 行数 × 列数）。行数越大，相变越陡峭。",
    ),
    ParamSpec(
        key="cols", label="列数 m", kind="int", default=30,
        min=5, max=80, step=1, group="网格与边缘",
        hint="列数 ≠ 行数 即为矩形网格。临界值与长宽比无关，只改变有限尺寸下的曲线形状。",
    ),
    ParamSpec(
        key="threshold", label="面积判据阈值", kind="choice", default="0.5",
        choices=("0.3", "0.5", "0.7", "0.9"), group="网格与边缘",
        hint="只在「面积判据」下生效：浸润节点数达到总节点数的这个比例才算成功。"
             "阈值取得越大，曲线的交点越往高处跑 —— 它不是一个固定的临界值。",
    ),
    ParamSpec(
        key="seed", label="随机种子（-1 表示随机）", kind="int", default=-1,
        min=-1, max=2147483647, step=1, group="网格与边缘",
        hint="取 ≥0 时同一种子可以复现完全相同的网格与统计结果。",
    ),
    ParamSpec(
        key="criterion", label="成功判据", kind="choice",
        default="贯通判据：顶行连通到底行（对应 p_c）",
        choices=tuple(CRITERION_CHOICES), group="高级选项",
        hint="三种判据回答的是三个不同的问题：\n"
             "· 贯通判据：整张网格是否存在顶行↔底行的纵贯簇 —— 这才是 p_c 的判据，"
             "与注水方式无关；\n"
             "· 起点判据：从注水点出发的那一簇是否纵贯 —— 随注水方式变化，"
             "顶端整行时与贯通判据相同；\n"
             "· 面积判据：浸润面积达到设定比例 —— 没有固定临界值，交点随比例、网格尺寸、"
             "注水方式一起变。",
    ),
    ParamSpec(
        key="lattice", label="格子类型", kind="choice", default="方格网（4 邻域）",
        choices=tuple(LATTICE_CHOICES), group="高级选项",
        hint="三角网每点有 6 个邻居、连接更密，无向键渗流临界值 p_c ≈ 0.3473（方格网为 0.5）。",
    ),
    ParamSpec(
        key="direction", label="方向模式", kind="choice", default="无向（四面流动）",
        choices=tuple(DIRECTION_CHOICES), group="高级选项",
        hint="无向 = 标准渗流；不允许向上 = 半有向；只允许向下/向右 = 经典有向渗流。"
             "方向模式会真正改变临界值，与注水点位置无关。",
    ),
    ParamSpec(
        key="inject", label="注水方式", kind="choice", default="顶端整行注水",
        choices=tuple(INJECT_CHOICES), group="高级选项",
        hint="顶端整行 = 经典渗流实验（判定横贯）；中心单点 / 随机单点 = 观察一个水团"
             "能否长到底端。贯通判据下三种注水方式的统计结果相同（判据只看整张网格），"
             "面积判据下差别很大。",
    ),
    ParamSpec(
        key="trials", label="批量统计次数 N", kind="choice", default="1000",
        choices=("100", "500", "1000", "5000", "10000"), group="批量统计",
        hint="独立重复实验的次数：每次重新生成网格，统计「当前判据」的成功频率。",
    ),
    ParamSpec(
        key="scanTrials", label="曲线每点次数", kind="choice", default="200",
        choices=("50", "100", "200", "500", "1000"), group="曲线扫描",
        hint="概率曲线上每个 p 值模拟多少次。",
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
    ActionSpec("generate", "生成并绘制网格", mode="once", kind="primary",
               hint="随机生成一次网格，并计算水的渗透过程"),
    ActionSpec("batch", "批量统计", mode="chunk", kind="default",
               hint="分块执行 N 次独立模拟，便于显示进度与随时中断"),
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


def _grid_options(params: Dict[str, Any]) -> Dict[str, Any]:
    """从界面参数里取出与网格相关的选项（含矩形、格子、方向、注水、判据）。"""
    return {
        "lattice": _pick(LATTICE_CHOICES, params.get("lattice"), "square"),
        "direction": _pick(DIRECTION_CHOICES, params.get("direction"), "undirected"),
        "inject": _pick(INJECT_CHOICES, params.get("inject"), "top"),
        "criterion": _pick(CRITERION_CHOICES, params.get("criterion"), DEFAULT_CRITERION),
        "threshold": _resolve_threshold(params.get("threshold")),
    }


def build_grid(params: Dict[str, Any]) -> PercolationGrid:
    """由参数构造模型实例 —— **A/B 两套契约共用的唯一构造入口**。

    数据级契约（:func:`handle`）与对象级契约（桌面视图的 ``spec.factory``）都调用它，
    于是"界面参数 -> 模型"的换算只写一份。

    ``params`` 里的 ``lattice`` / ``direction`` / ``inject`` / ``criterion`` 必须是模型
    **内部取值**（界面上的中文标签请先用 :func:`_grid_options` 翻译）；
    ``rng`` 可以是 ``None`` / 种子 / ``random.Random`` 实例（也接受 ``seed``）。
    """
    if "rng" not in params and "seed" in params:
        params = {**params, "rng": _resolve_seed(params.get("seed"))}
    return PercolationGrid(
        rows=_resolve_size(params.get("rows"), 30),
        cols=params.get("cols"),
        p=float(params.get("p", 0.5)),
        rng=params.get("rng"),
        lattice=params.get("lattice", "square"),
        direction=params.get("direction", "undirected"),
        inject=params.get("inject", "top"),
        criterion=params.get("criterion", DEFAULT_CRITERION),
        threshold=_resolve_threshold(params.get("threshold")),
    )


def _handle_generate(params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """生成一次网格并完成渗流模拟，返回前端绘图所需的全部数据。

    ``payload`` 里可以带上 ``origin``（节点索引），用于「点击网格指定注水点」。
    """
    rows = _resolve_size(params.get("rows"), 30)
    cols = _resolve_size(params.get("cols"), rows)
    p = float(params.get("p", 0.5))
    options = _grid_options(params)

    grid = build_grid({"rows": rows, "cols": cols, "p": p,
                       "rng": _resolve_seed(params.get("seed")), **options})

    origins: Optional[List[int]] = None
    origin = payload.get("origin")
    if origin is not None:
        try:
            index = int(origin)
        except (TypeError, ValueError):
            index = -1
        if 0 <= index < grid.node_count:
            origins = [index]
    result = grid.simulate(origins)

    return {
        "view": "percolation-grid",
        "rows": rows,
        "cols": cols,
        "size": rows,                 # 兼容旧前端（方格网时 size 即边长）
        "p": p,
        **options,
        "latticeName": grid.lattice_name,
        "directionName": grid.direction_name,
        "injectName": grid.inject_name,
        "criterionName": grid.criterion_name,
        "criterionHint": CRITERION_DESCRIPTIONS[grid.criterion],
        "percolates": result.percolates,
        # 整张网格是否存在纵贯簇（与注水点无关，贯通判据就看这个）
        "spans": result.spans,
        # 从注水点出发的簇是否纵贯（起点判据看这个）
        "originSpans": result.origin_spans,
        "spanningCount": result.spanning_count,
        "spanningRatio": result.spanning_ratio,
        "spanningNodes": result.spanning_nodes,
        "originInSpanning": result.origin_in_spanning,
        "success": result.success,
        "engulfed": result.engulfed,
        "nodeCount": result.node_count,
        "totalEdges": result.total_edge_count,
        "openEdges": result.open_edge_count,
        "openRatio": result.open_ratio,
        "wetCount": result.wet_count,
        "wetRatio": result.wet_ratio,
        "depth": result.depth,
        "elapsedMs": result.elapsed * 1000.0,
        # 阈值信息：pcIsEstimate 为真时前端可标注「估计值」，pcApplies 为假时不要画 p_c
        "theoreticalPc": grid.theoretical_pc,
        "pcApplies": grid.pc_applies,
        "pcIsEstimate": grid.pc_is_estimate,
        "pcLabel": grid.pc_label,
        # 本次实际使用的注水点（点击网格时会变成点击的那个节点）
        "origins": result.origins,
        "sources": result.origins,
        # 边用 0/1 字符串压缩传输（方格网 h/v，三角网 h/dl/dr）；layers 用于逐层播放
        **encode_edges(grid),
        "layers": result.layers,
    }


def _handle_batch(params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """执行一小批独立模拟（分块），由前端循环累加得到总的成功频率。

    ``payload`` 可覆盖 ``trials``（本块次数）、``seed``（本块种子）与 ``p``
    （曲线扫描时逐点变化），以及 ``lattice`` / ``direction`` / ``inject`` /
    ``criterion`` / ``threshold``，从而让一次统计既能显示进度、又完全可复现。
    """
    rows = _resolve_size(payload.get("rows", params.get("rows")), 40)
    cols = _resolve_size(payload.get("cols", params.get("cols")), rows)
    p = float(payload.get("p", params["p"]))
    trials = max(1, int(payload.get("trials", params["trials"])))
    seed = _resolve_seed(payload.get("seed", params.get("seed")))
    merged = dict(params)
    merged.update({
        k: payload[k]
        for k in ("lattice", "direction", "inject", "criterion", "threshold")
        if k in payload
    })
    options = _grid_options(merged)

    result = batch_percolation_probability(
        rows=rows, cols=cols, p=p, trials=trials, rng=seed, **options
    )
    return {
        "p": p,
        "rows": result.rows,
        "cols": result.cols,
        "size": result.rows,
        "criterion": result.criterion,
        "criterionName": result.criterion_name,
        "criterionHint": CRITERION_DESCRIPTIONS[result.criterion],
        "pcApplies": result.criterion == "span",
        "threshold": result.threshold,
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
    if action == "generate":
        return _handle_generate(params, payload)
    if action == "batch":
        return _handle_batch(params, payload)
    raise ValueError(f"边渗流模型不支持的动作：{action}")


# ----------------------------------------------------------------------
# 终端模式
# ----------------------------------------------------------------------
def _cli(raw_args) -> int:
    """命令行统计模式：单点估计或扫描 P(p) 曲线。

    取值统一走 :class:`~awe_math.spec.CliArgs`：名字与默认值都来自
    :data:`~awe_math.models._cli.GRID_CLI_OPTIONS` 的声明，不再手写魔法字符串。
    """
    args = CliArgs(raw_args, GRID_CLI_OPTIONS)
    rows = max(2, min(400, int(args.rows)))
    cols = getattr(args, "cols", None)
    cols = rows if cols is None else max(2, min(400, int(cols)))
    trials = max(1, int(args.trials))
    raw_p = getattr(args, "p", None)
    p = 0.5 if raw_p is None else float(raw_p)

    lattice = getattr(args, "lattice", None)
    if lattice not in LATTICE_CHOICES.values():
        lattice = "square"
    direction = getattr(args, "direction", None)
    if direction not in DIRECTION_CHOICES.values():
        # 兼容旧的 --directed 开关
        direction = "no_up" if getattr(args, "directed", False) else "undirected"
    inject = getattr(args, "inject", None)
    if inject not in INJECT_CHOICES.values():
        inject = "top"
    criterion = getattr(args, "criterion", None)
    if criterion not in CRITERIA:
        criterion = DEFAULT_CRITERION
    threshold = _resolve_threshold(getattr(args, "threshold", None))

    options = {"lattice": lattice, "direction": direction, "inject": inject,
               "criterion": criterion, "threshold": threshold}
    shape = f"{rows}×{cols}" if rows != cols else f"{rows}×{rows}"
    grid = build_grid({"rows": rows, "cols": cols, "p": p, **options})
    # 判据名称由下一行的 rule 给出，这里只放临界值说明，避免「判据：… | 判据：…」重复
    header = (f"{grid.lattice_name} {shape} | {grid.direction_name} | "
              f"注水：{grid.inject_name} | {grid.pc_label}")
    if criterion == "span":
        rule = "贯通判据：整张网格是否存在纵贯簇"
    elif criterion == "origin":
        rule = "起点判据：从注水点出发的簇是否纵贯顶底"
    else:
        rule = f"面积判据：浸润比例 ≥ {threshold:.0%}"

    if getattr(args, "scan", False):
        step = float(args.step)
        p_values: List[float] = []
        k = 0
        while k * step <= 1.0 + 1e-9:
            p_values.append(round(k * step, 3))
            k += 1

        print("=" * 78)
        print(f"边渗流概率扫描 | {header}")
        print(f"每点 {trials} 次模拟 | {rule}")
        print("=" * 78)
        print(f"{'流通概率 p':>10} | {'成功概率':>12} | {'平均浸润比例':>12} | 分布")
        print("-" * 78)

        def on_point(done: int, total: int, res) -> None:
            bar = "█" * int(round(res.mean_ratio * 26))
            print(f"{res.p:>10.2f} | {res.probability:>12.4f} | "
                  f"{res.mean_ratio:>12.4f} | {bar}")
            sys.stdout.flush()

        scan_curve(p_values, rows=rows, cols=cols, trials=trials,
                   rng=_resolve_seed(getattr(args, "seed", -1)),
                   progress=on_point, **options)
        print("-" * 78)
        if criterion == "span":
            print("提示：成功概率 = 1/2 的交点即临界值 p_c（p 越过它，纵贯簇出现 —— 相变）。")
        elif criterion == "origin":
            print("提示：起点判据的交点高于 p_c —— 它额外要求「注水点落在纵贯簇里」；")
            print("      注水方式选「顶端整行」时它与贯通判据完全相同。")
        else:
            print("提示：面积判据的交点不是固定临界值，它随所设比例、网格尺寸、注水方式变化；")
            print("      只有「贯通判据」的交点才等于 p_c。")
        return 0

    seed = _resolve_seed(getattr(args, "seed", -1))
    grid = build_grid({"rows": rows, "cols": cols, "p": p, "rng": seed, **options})
    single = grid.simulate()
    print("=" * 78)
    print(f"单次模拟 | {header}")
    print(f"流通边 {single.open_edge_count}/{single.total_edge_count}"
          f"（实测比例 {single.open_ratio:.3f}）| {rule}")
    print(f"浸润节点 {single.wet_count}/{single.node_count}（{single.wet_ratio:.1%}），"
          f"蔓延 {single.depth} 层")
    bottom = "已到达底端" if single.percolates else "未到达底端"
    if criterion == "span":
        verdict = "存在纵贯簇 ✔" if single.spans else "没有纵贯簇 ✘"
        print(f"整张网格是否存在纵贯簇（顶行 ↔ 底行）：{verdict}"
              f"（纵贯簇 {single.spanning_count} 节点，{single.spanning_ratio:.1%}）；"
              f"本次注水{bottom}。")
    elif criterion == "origin":
        verdict = "纵贯 ✔" if single.origin_spans else "未纵贯 ✘"
        note = "" if single.spans else "（网格上本来就没有纵贯簇）"
        inside = "在簇内" if single.origin_in_spanning else "在簇外"
        print(f"从注水点出发的那一簇是否纵贯顶行与底行：{verdict}{note}；"
              f"注水点{inside}；本次注水{bottom}。")
    else:
        verdict = f"达到 ≥{threshold:.0%} ✔" if single.engulfed else f"不足 {threshold:.0%} ✘"
        print(f"本次浸润比例 {single.wet_ratio:.1%}，{verdict}；本次注水{bottom}。")

    res = batch_percolation_probability(
        rows=rows, cols=cols, p=p, trials=trials,
        rng=None if seed is None else seed + 1, **options,
    )
    print("-" * 78)
    print(f"批量统计 | 独立模拟 {res.trials} 次 | {rule} 命中 {res.success} 次")
    print(f"该 p 值下「{res.criterion_name}」的成功概率 ≈ {res.probability:.4f} "
          f"± {res.stderr:.4f}，平均浸润比例 {res.mean_ratio:.1%}"
          f"（耗时 {res.elapsed:.2f} s）")
    print("=" * 78)
    return 0


def build_spec() -> ModelSpec:
    """构造并返回边渗流模型的元数据。"""
    return ModelSpec(
        key="percolation",
        name="边渗流模型",
        topic="量变引起质变",
        summary="每条边以概率 p 随机连通，看水能否从注水点渗到底端；"
                "支持方格网/三角网、方形/矩形网格、四种方向模式、三种注水方式与三种成功判据。",
        description=(
            "在 rows × cols 的格子上，每条边以概率 p 独立地设为「流通」或「阻断」，"
            "水从注水点出发沿流通边蔓延。\n\n"
            "**先分清三种「成功」的标准，它们的临界值完全不是一回事：**\n\n"
            "1. 贯通判据（默认）：整张网格上是否存在从顶行连通到底行的**纵贯簇**，"
            "也就是「顶端整行注水能否流到底端」。方格网（4 邻域）无向键渗流 p_c = 1/2、"
            "三角网（6 邻域）p_c = 2·sin(π/18) ≈ 0.3473、只允许向下/向右的经典有向渗流"
            "p_c ≈ 0.6447（文献值），说的都是这个相变，所以它的「成功概率 = 1/2」交点"
            "落在 p_c 上，且与注水方式无关。\n\n"
            "2. 起点判据：**从注水点出发的那一簇**是否纵贯（同时碰到顶行与底行）。"
            "它与贯通判据的唯一差别是「还要求注水点落在纵贯簇里」：顶端整行注水时两者"
            "完全相同，中心 / 随机单点注水时交点明显更高 —— 网格上明明有纵贯簇，"
            "水从一个随机节点注入却可能根本没接上，只浸透一小片。\n\n"
            "3. 面积判据：从注水点出发的浸润面积达到设定比例。它回答的是「一次注水能浸透"
            "多大范围」，**没有固定的临界值**：比例定得越大交点越高，单点注水还会额外要求"
            "「起点恰好落在巨簇里」，网格尺寸也会影响它。\n\n"
            "后两种判据的交点都**不是** p_c（把它们的交点当成 p_c 是常见误解）。"
            "另外：p_c 只取决于格子的连接结构与方向模式，与网格是正方形还是矩形、"
            "以及注水点在顶端整行、中心还是随机位置都无关 —— 后两者只改变有限尺寸下"
            "曲线的形状与陡峭程度（矩形网格与单点注水的曲线更缓、饱和更慢）。"
            "这些结论都只在贯通判据下成立。"
        ),
        params=PARAMS,
        actions=ACTIONS,
        view="percolation",
        accent="#38bdf8",
        icon="≋",
        handler=handle,
        cli=_cli,
        # 终端命令行参数（与点渗流共用同一套声明；入口会汇总所有模型的声明）
        cli_options=GRID_CLI_OPTIONS,
        # 对象级契约：桌面视图直接渲染、后台批量统计 / 曲线扫描都复用它，
        # 于是「界面参数 -> 模型」与「批量/扫描函数」不必在视图里再写一遍
        factory=build_grid,
        batch=batch_percolation_probability,
        scan=scan_curve,
        highlights=("三种成功判据：贯通（对 p_c）/ 起点纵贯（随注水方式）/ 面积比例",
                    "方格网 0.5 / 三角网 0.3473 / 有向 0.6447",
                    "矩形网格 + 四种方向模式 + 三种注水方式"),
        order=10,          # 同主题内先展示边渗流，再展示点渗流
    )
