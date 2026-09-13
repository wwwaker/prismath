# -*- coding: utf-8 -*-
"""
方格网渗流模型 —— 界面元数据与动作处理器
==========================================

本文件是「模型」与「界面」之间的唯一桥梁：

* :data:`PARAMS` 描述可调参数，网页/桌面/终端三种界面都据此生成控件；
* :func:`handle` 处理界面发来的动作请求（生成网格、批量统计），返回 JSON 可序列化的结果；
* :func:`_cli` 是终端模式的入口。

算法本身在 :mod:`~awe_math.models.percolation.model` 中，与本文件完全解耦。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from ...spec import ActionSpec, ModelSpec, ParamSpec
from .model import (
    THEORETICAL_PC,
    PercolationGrid,
    batch_percolation_probability,
    encode_edges,
)

# ----------------------------------------------------------------------
# 可调参数（界面自动生成控件，按 group 分组显示）
# ----------------------------------------------------------------------
PARAMS = (
    ParamSpec(
        key="p", label="流通概率 p", kind="float", default=0.5,
        min=0.0, max=1.0, step=0.01, group="网格与边缘",
        hint="每条边独立流通的概率。p 在 0.5 附近会发生相变。",
    ),
    ParamSpec(
        key="size", label="网格尺寸 n", kind="int", default=30,
        min=5, max=60, step=1, unit="×n", group="网格与边缘",
        hint="节点数 n²，边数 2n(n-1)。尺寸越大，相变越陡峭。",
    ),
    ParamSpec(
        key="directed", label="有向渗流（水不能向上）", kind="bool", default=False,
        group="网格与边缘",
        hint="关闭 = 标准无向渗流（推荐）；开启 = 只能向下/左/右，用于对比实验。",
    ),
    ParamSpec(
        key="seed", label="随机种子（-1 表示随机）", kind="int", default=-1,
        min=-1, max=2147483647, step=1, group="网格与边缘",
        hint="取 ≥0 时同一种子可以复现完全相同的网格与统计结果。",
    ),
    ParamSpec(
        key="trials", label="批量统计次数 N", kind="choice", default="1000",
        choices=("100", "500", "1000", "5000", "10000"), group="批量统计",
        hint="独立重复实验的次数，次数越多渗流概率估计越准。",
    ),
    ParamSpec(
        key="scanTrials", label="曲线每点次数", kind="choice", default="200",
        choices=("50", "100", "200", "500", "1000"), group="曲线扫描",
        hint="P(p) 曲线上每个 p 值模拟多少次。",
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


def _resolve_seed(value: Any) -> Optional[int]:
    """把界面传来的种子转成 ``random`` 可用的形式：-1 表示随机。"""
    try:
        seed = int(value)
    except (TypeError, ValueError):
        return None
    return None if seed < 0 else seed


def _handle_generate(params: Dict[str, Any]) -> Dict[str, Any]:
    """生成一次网格并完成渗流模拟，返回前端绘图所需的全部数据。"""
    size = int(params["size"])
    p = float(params["p"])
    directed = bool(params["directed"])

    grid = PercolationGrid(size=size, p=p, rng=_resolve_seed(params.get("seed")), directed=directed)
    result = grid.simulate()
    h_edges, v_edges = encode_edges(grid)

    return {
        "view": "percolation-grid",
        "size": size,
        "p": p,
        "directed": directed,
        "percolates": result.percolates,
        "nodeCount": result.node_count,
        "totalEdges": result.total_edge_count,
        "openEdges": result.open_edge_count,
        "openRatio": result.open_ratio,
        "wetCount": result.wet_count,
        "wetRatio": result.wet_ratio,
        "depth": result.depth,
        "elapsedMs": result.elapsed * 1000.0,
        "theoreticalPc": THEORETICAL_PC,
        # 边用 0/1 字符串压缩传输；layers 用于逐层播放渗透动画
        "h": h_edges,
        "v": v_edges,
        "layers": result.layers,
    }


def _handle_batch(params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """执行一小批独立模拟（分块），由前端循环累加得到总的渗流频率。

    ``payload`` 可覆盖 ``trials``（本块次数）、``seed``（本块种子）与 ``p``
    （曲线扫描时逐点变化），从而让一次统计既能显示进度、又完全可复现。
    """
    size = int(payload.get("size", params["size"]))
    p = float(payload.get("p", params["p"]))
    directed = bool(payload.get("directed", params["directed"]))
    trials = max(1, int(payload.get("trials", params["trials"])))
    seed = _resolve_seed(payload.get("seed", params.get("seed")))

    result = batch_percolation_probability(
        size=size, p=p, trials=trials, rng=seed, directed=directed
    )
    return {
        "p": p,
        "size": size,
        "trials": result.trials,
        "success": result.success,
        "probability": result.probability,
        "stderr": result.stderr,
        "elapsedMs": result.elapsed * 1000.0,
    }


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """动作分发入口，由 :class:`~awe_math.spec.ModelSpec` 调用。"""
    if action == "generate":
        return _handle_generate(params)
    if action == "batch":
        return _handle_batch(params, payload)
    raise ValueError(f"渗流模型不支持的动作：{action}")


# ----------------------------------------------------------------------
# 终端模式
# ----------------------------------------------------------------------
def _cli(args) -> int:
    """命令行统计模式：单点估计或扫描 P(p) 曲线。"""
    size = max(2, min(200, int(getattr(args, "size", 40))))
    trials = max(1, int(getattr(args, "trials", 1000)))
    p = float(getattr(args, "p", 0.5))
    directed = bool(getattr(args, "directed", False))
    seed = getattr(args, "seed", -1)
    rng = None if int(seed) < 0 else int(seed)
    mode = "有向渗流（只向下/左/右）" if directed else "标准无向渗流"

    if getattr(args, "scan", False):
        step = float(getattr(args, "step", 0.05))
        p_values: List[float] = []
        k = 0
        while k * step <= 1.0 + 1e-9:
            p_values.append(round(k * step, 3))
            k += 1

        print("=" * 70)
        print(f"渗流概率扫描 | 网格 {size}×{size} | 每点 {trials} 次 | {mode}")
        print(f"理论临界值 p_c = {THEORETICAL_PC}（二维方格网键渗流）")
        print("=" * 70)
        print(f"{'概率 p':>8} | {'渗流概率':>10} | {'成功/次数':>15} | 分布")
        print("-" * 70)

        from .model import scan_curve

        def on_point(done: int, total: int, res) -> None:
            bar = "█" * int(round(res.probability * 26))
            print(f"{res.p:>8.2f} | {res.probability:>10.4f} | "
                  f"{res.success:>6}/{res.trials:<8} | {bar}")
            sys.stdout.flush()

        scan_curve(p_values, size=size, trials=trials, rng=rng,
                   directed=directed, progress=on_point)
        print("-" * 70)
        print("提示：p 越过 p_c 之后渗流概率迅速由 0 跃升到 1，即相变现象。")
        return 0

    grid = PercolationGrid(size=size, p=p, rng=rng, directed=directed)
    single = grid.simulate()
    print("=" * 70)
    print(f"单次模拟 | 网格 {size}×{size} | p = {p:.2f} | {mode}")
    print(f"流通边 {single.open_edge_count}/{single.total_edge_count}"
          f"（实测比例 {single.open_ratio:.3f}）")
    print(f"浸润节点 {single.wet_count}/{single.node_count}（{single.wet_ratio:.1%}），"
          f"渗透 {single.depth} 层")
    print(f"是否渗流出水：{'是 ✔' if single.percolates else '否 ✘'}")

    res = batch_percolation_probability(size=size, p=p, trials=trials,
                                        rng=None if rng is None else rng + 1,
                                        directed=directed)
    print("-" * 70)
    print(f"批量统计 | 独立模拟 {res.trials} 次 | 成功 {res.success} 次")
    print(f"该 p 值下的渗流概率 ≈ {res.probability:.4f} ± {res.stderr:.4f}"
          f"（耗时 {res.elapsed:.2f} s）")
    print("=" * 70)
    return 0


def build_spec() -> ModelSpec:
    """构造并返回渗流模型的元数据。"""
    return ModelSpec(
        key="percolation",
        name="方格网渗流",
        topic="量变引起质变",
        summary="每条边以概率 p 随机连通，看水能否从顶端渗到底端，"
                "并统计渗流出水概率随 p 变化的相变曲线。",
        description=(
            "在 n×n 的方格网上，每条边以概率 p 独立地设为「流通」或「阻断」，"
            "水从顶端整行同时注入，沿流通边向各方向蔓延（标准无向渗流）；"
            "只要有一个底端节点与顶端连通，就认为本次「渗流出水」。\n\n"
            "二维方格网键渗流的理论临界概率 p_c = 1/2：p 略小于它时几乎不可能贯通，"
            "略大于它时几乎必然贯通，在 p_c 附近发生相变 —— 这正是「量变引起质变」。"
        ),
        params=PARAMS,
        actions=ACTIONS,
        view="percolation",
        accent="#38bdf8",
        icon="≋",
        handler=handle,
        cli=_cli,
        highlights=("标准无向边渗流模型", "并查集判定 + 多源 BFS 分层", "p_c = 0.5 的相变现象"),
    )
