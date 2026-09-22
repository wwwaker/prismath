# -*- coding: utf-8 -*-
"""
生命游戏模型 —— 界面元数据与动作处理器
========================================

本文件是「模型」与「界面」之间的唯一桥梁：

* :data:`PARAMS` 描述可调参数（棋盘 / 开局 / 演化），桌面侧栏由 ``kit/form.py`` 自动生成
  （``spec.params`` 驱动），网页 / 终端同样据此生成控件；
* :func:`handle` 处理界面发来的动作请求（演化 N 代、人口曲线），返回 **JSON 可序列化** 的结果；
* :func:`build_board` 是「界面参数 -> 模型实例」的**唯一构造入口**，数据级契约与对象级契约
  共用它（与渗流模型的 ``build_grid`` 同理）；
* :func:`frame_payload` 把"当前棋盘"包成一份**单帧 payload** —— 桌面视图的点击涂画用它，
  于是 payload 的形状只有一个真相源；
* :func:`_cli` 是终端模式的入口（含 ``--scan`` 密度扫描）。

算法本身在 :mod:`~awe_math.models.life_game.model` 中，与本文件完全解耦。

返回结构（``payload["view"]``）
------------------------------
``life-grid``  逐帧的栅格：``frames``（0/1 掩码序列）+ ``census``（同长的逐代统计，
               含活细胞数 / 新生 / 死亡）。桌面视图按帧播放（``ChartSpec(kind="grid")``，
               **每一帧恰好一代**），右侧那条约有人口曲线画的是同一份 ``census``。

``frames`` 与 ``census`` 严格同长、结局判定逐代精确；代数超过 400 时按 ``stride`` 抽样
（见 :data:`~awe_math.models.life_game.model.MAX_FRAMES`），这样"通用视图 / 网页"也吃得下。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

from ...spec import ActionSpec, CliArgs, CliOption, ModelSpec, ParamSpec
from .model import (
    BOUNDARIES,
    BOUNDARY_DEAD,
    BOUNDARY_TORUS,
    DEFAULT_COLS,
    DEFAULT_DENSITY,
    DEFAULT_GENERATIONS,
    DEFAULT_ROWS,
    DEFAULT_RULE,
    MAX_SIZE,
    MIN_SIZE,
    OUTCOME_CYCLE,
    OUTCOME_EXTINCT,
    OUTCOME_LABELS,
    OUTCOME_RUNNING,
    OUTCOME_STATIC,
    PATTERNS,
    PATTERN_BLANK,
    PATTERN_LABELS,
    RULES,
    DensityResult,
    LifeBoard,
    LifeRun,
    LifeWatch,
    encode_cells,
    scan_survival,
)

# ----------------------------------------------------------------------
# 界面选项词表（中文标签 -> 模型内部取值）
#
# 与渗流模型同样的做法：下拉框显示中文，交给模型的一律是内部取值；终端里直接用内部取值。
# 放在本文件里而不是 ``models/_options.py`` —— 这些选项只有生命游戏用（那份共用词表
# 是渗流两个模型之间的共用件）。
# ----------------------------------------------------------------------
#: 边界条件
BOUNDARY_CHOICES: Dict[str, str] = {
    "环面（上下左右相连）": BOUNDARY_TORUS,
    "死边界（越界视为死细胞）": BOUNDARY_DEAD,
}

#: 演化规则
RULE_CHOICES: Dict[str, str] = {label: key for key, label in RULES.items()}

#: 开局图案（空白手绘 + 随机播种 + 预置图案）
#: 顺序即下拉框顺序：**空白排第一**，因为默认玩法是自己画开局（生成只发生在按下
#: 「生成开局」时 —— 见 :func:`build_board` 与桌面视图的 ``_generate``）。
PATTERN_CHOICES: Dict[str, str] = {
    label: key for key, label in PATTERN_LABELS.items()
}

# ----------------------------------------------------------------------
# 可调参数（桌面侧栏按 group 自动分组生成控件）
# ----------------------------------------------------------------------
PARAMS = (
    ParamSpec(
        key="rows", label="行数 n", kind="int", default=DEFAULT_ROWS,
        min=MIN_SIZE, max=MAX_SIZE, step=1, group="棋盘",
        hint="棋盘行数（格子数 = 行数 × 列数）。行列越多，涌现出的结构越丰富，"
             "播放也越吃 CPU（50×50 每代约 0.5 ms、120×120 约 3 ms）。",
    ),
    ParamSpec(
        key="cols", label="列数 m", kind="int", default=DEFAULT_COLS,
        min=MIN_SIZE, max=MAX_SIZE, step=1, group="棋盘",
        hint="列数 ≠ 行数 即为矩形棋盘（例如 120×24 像一条走廊，长条上更容易看清滑翔机）。",
    ),
    ParamSpec(
        key="boundary", label="边界条件", kind="choice", default="环面（上下左右相连）",
        choices=tuple(BOUNDARY_CHOICES), group="棋盘",
        hint="环面：上下相连、左右相连，没有「边缘」，滑翔机会绕一圈回来；\n"
             "死边界：棋盘之外一律算死细胞，图案会在边缘撞死。",
    ),
    ParamSpec(
        key="pattern", label="开局图案", kind="choice", default="空白（自己绘制）",
        choices=tuple(PATTERN_CHOICES), group="开局",
        hint="默认「空白」：棋盘一开始是空的，自己用鼠标在画布上画开局（按住拖动即可）。\n"
             "选好图案后按下面的「生成开局」才会铺上去：随机播种按密度撒点，"
             "其余把预置图案居中放置 —— 用来一眼看清「局部规则如何长出会走路、"
             "会振荡、会自我复制的结构」。",
    ),
    ParamSpec(
        key="density", label="初始存活密度", kind="float", default=DEFAULT_DENSITY,
        min=0.02, max=0.95, step=0.01, group="开局",
        hint="「生成开局」随机播种时的存活概率（图案 = 随机播种时才用得上）。"
             "太低会很快消亡，太高会迅速僵化成静止块 / 短周期；"
             "中间一段（约 0.2–0.4）最容易长出长时间活跃的结构。",
    ),
    ParamSpec(
        key="seed", label="随机种子（-1 表示随机）", kind="int", default=-1,
        min=-1, max=2147483647, step=1, group="开局",
        hint="「生成开局」用的随机种子；取 ≥0 时同一种子可以复现完全相同的开局。",
    ),
    ParamSpec(
        key="rule", label="演化规则", kind="choice",
        default=next(iter(RULE_CHOICES)), choices=tuple(RULE_CHOICES), group="演化",
        hint="规则串 ``B<新生>/S<存活>`` 读作「死细胞恰好这些邻居数就新生、"
             "活细胞恰好这些邻居数就存活」。标准生命游戏是 B3/S23；"
             "HighLife 多了「死细胞 6 邻居也新生」，因此存在会自我复制的结构。",
    ),
)

# ----------------------------------------------------------------------
# 动作
# ----------------------------------------------------------------------
ACTIONS = (
    ActionSpec("evolve", "开始演化", mode="once", kind="primary",
               hint="从**当前棋盘**往下演化：界面上一代一代实时播放（可暂停 / 单步 / 调速），"
                    "一直演到消亡或进入周期；终端 / 网页则用它按 --generations 出一次结果"),
)


# ----------------------------------------------------------------------
# 参数校正
# ----------------------------------------------------------------------
def _pick(mapping: Dict[str, str], value: Any, fallback: str) -> str:
    """把界面上的中文选项翻译成模型内部取值。

    两种写法都要认：**中文标签**（界面表单直接给出的就是它）与**已经是内部取值**的字符串
    （分块动作的 payload 会把上一次结果的字段回传，那些字段存的就是内部取值）。
    早先只查 ``mapping.get(value)``，于是"回传内部取值"会被当成无法识别而落到 fallback ——
    本模块的 ``options_from_ui`` 契约明确写着"参数必须是内部取值"，所以那等于静默改参数。
    """
    text = str(value)
    if text in mapping:
        return mapping[text]
    if text in mapping.values():
        return text
    return fallback


def _resolve_size(raw: Any, default: int) -> int:
    """把界面传来的行 / 列数夹到合法范围。"""
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return default
    return max(MIN_SIZE, min(MAX_SIZE, value))


def _resolve_density(raw: Any) -> float:
    """把界面传来的密度夹到 ``[0.02, 0.95]``。"""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_DENSITY
    return min(0.95, max(0.02, value))


def _resolve_generations(raw: Any) -> int:
    """把界面传来的代数夹到 ``[10, 5000]``。"""
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return DEFAULT_GENERATIONS
    return max(10, min(5000, value))


def _resolve_seed(value: Any) -> Optional[int]:
    """把界面传来的种子转成内核可用的形式（``None | int``）：-1 表示随机。

    内核的随机源是 ``numpy.random.default_rng``，它只接受 ``None`` / 整数 /
    ``Generator`` —— 传字符串或 ``random.Random`` 会直接抛异常，所以这里必须落成整数。
    """
    try:
        seed = int(float(value))
    except (TypeError, ValueError):
        return None
    return None if seed < 0 else seed


def options_from_ui(params: Dict[str, Any]) -> Dict[str, Any]:
    """把**界面参数**（下拉框给的是中文标签）翻成模型内部取值并夹到合法范围。

    返回的字典可以直接交给 :func:`build_board`。界面（桌面侧栏 / 网页表单）走这一条路；
    终端直接用内部取值，不必经过本函数。
    """
    return {
        "rows": _resolve_size(params.get("rows"), DEFAULT_ROWS),
        "cols": _resolve_size(params.get("cols"), DEFAULT_COLS),
        "boundary": _pick(BOUNDARY_CHOICES, params.get("boundary"), BOUNDARY_TORUS),
        "pattern": _pick(PATTERN_CHOICES, params.get("pattern"), "random"),
        "rule": _pick(RULE_CHOICES, params.get("rule"), DEFAULT_RULE),
        "density": _resolve_density(params.get("density")),
        "generations": _resolve_generations(params.get("generations")),
        "seed": params.get("seed"),
    }


# ----------------------------------------------------------------------
# 唯一构造入口（数据级 + 对象级共用）
# ----------------------------------------------------------------------
def build_board(params: Dict[str, Any]) -> LifeBoard:
    """由**内部取值**构造棋盘 —— **两套契约共用的唯一构造入口**。

    与渗流模型的 ``build_grid`` 同一约定：``params`` 里的 ``boundary`` / ``pattern`` /
    ``rule`` 必须是模型内部取值（``"torus"`` / ``"glider"`` / ``"B3/S23"``）；
    界面上的中文标签请先过 :func:`options_from_ui`。
    ``rng`` 可以是 ``None`` / 种子 / ``random.Random`` 实例（也接受 ``seed``）。

    数据级契约（:func:`handle`）与对象级契约（桌面视图的 ``spec.factory``、点击涂画后的重绘）
    都调用它，于是"参数 -> 模型"的换算只写一份。
    """
    if "rng" not in params and "seed" in params:
        params = {**params, "rng": _resolve_seed(params.get("seed"))}
    boundary = params.get("boundary")
    pattern = str(params.get("pattern") or PATTERN_BLANK)
    rule = params.get("rule")
    known = pattern in PATTERNS or pattern in ("random", PATTERN_BLANK)
    return LifeBoard(
        rows=_resolve_size(params.get("rows"), DEFAULT_ROWS),
        cols=_resolve_size(params.get("cols"), DEFAULT_COLS),
        rule=rule if rule in RULES else DEFAULT_RULE,
        boundary=boundary if boundary in BOUNDARIES else BOUNDARY_TORUS,
        density=_resolve_density(params.get("density")),
        rng=params.get("rng"),
        pattern=pattern if known else PATTERN_BLANK,
    )


def run_board(params: Dict[str, Any], generations: Optional[int] = None,
              progress: Optional[Any] = None, cancel: Optional[Any] = None
              ) -> Tuple[LifeBoard, LifeRun]:
    """由**内部取值**构造棋盘并演化若干代，返回 ``(棋盘, 结果)``。

    终端与桌面视图的后台任务用它（传内部取值）；数据级契约（``handler``）拿到的是界面
    参数，先过 :func:`options_from_ui` 再进来 —— 于是"翻译"只发生在该发生的那一层。
    """
    board = build_board(params)
    total = (_resolve_generations(params.get("generations"))
             if generations is None else int(generations))
    # 连续演化会**原地推进**棋盘，调用方拿到的是末态棋盘（与结果一致）
    run = board.run(total, progress=progress, cancel=cancel)
    return board, run


# ----------------------------------------------------------------------
# payload：返回结构的唯一真相源
# ----------------------------------------------------------------------
def outcome_text(outcome: str, period: int = 0, period_start: int = 0,
                 generation: int = 0, population: int = 0) -> str:
    """把结局说成一句话（这是模型最有价值的输出之一）。

    按字段而不是按 :class:`~awe_math.models.life_game.model.LifeRun` 取参：
    "跑完一段"（``run``）与"实时播放到某一代"（``LifeWatch``）都要说这句话。
    """
    if outcome == OUTCOME_EXTINCT:
        return f"第 {generation} 代全部死亡（一个活细胞都不剩）。"
    if outcome == OUTCOME_STATIC:
        return (f"第 {period_start} 代起状态不再改变（静止物），"
                f"棋盘上留下 {population} 个活细胞。")
    if outcome == OUTCOME_CYCLE:
        return (f"第 {period_start} 代起以周期 {period} 重复"
                f"（第 {generation} 代确认重复）——振荡子，或整体平移的图案"
                f"（滑翔机在环面上的周期是 4 × 边长）。")
    return (f"演化到第 {generation} 代仍未重复（环面上状态有限，"
            f"所以迟早会进入周期，只是这段「瞬态」可能长得出人意料）。")


def _census_rows(run: LifeRun) -> List[Dict[str, int]]:
    """人口曲线数据（每帧一条，与 ``frames`` 严格对齐）。"""
    return run.census_series()


def payload_for(board: LifeBoard, run: LifeRun) -> Dict[str, Any]:
    """把一次演化包成界面用的 payload（唯一的返回结构：``life-grid`` 逐帧栅格）。

    ``frames`` 与 ``census`` 严格同长：画布按帧播放，右侧人口曲线按同一份 ``census``
    随帧增长，于是"屏幕上第几代"与"曲线画到第几个点"永远一致。
    """
    last = run.census[-1] if run.census else (0, 0, 0, 0)
    payload: Dict[str, Any] = {
        "view": "life-grid",
        "rows": board.rows,
        "cols": board.cols,
        "generation": run.stop_generation,
        "population": run.population,
        "density": run.density_now,
        "births": last[2],
        "deaths": last[3],
        "rule": run.rule,
        "ruleName": board.rule_name,
        "boundary": run.boundary,
        "boundaryName": board.boundary_name,
        "pattern": run.pattern,
        "patternName": board.pattern_name,
        "densityStart": run.density,
        "outcome": run.outcome,
        "outcomeLabel": run.outcome_label,
        "outcomeText": outcome_text(run.outcome, run.period, run.period_start,
                                    run.stop_generation, run.population),
        "period": run.period,
        "periodStart": run.period_start,
        "generations": run.generations,
        "stride": run.stride,
        "frameCount": run.frame_count,
        "census": _census_rows(run),
        "elapsedMs": run.elapsed * 1000.0,
    }
    payload.update({"frames": run.frames, "cells": run.frames[-1] if run.frames else ""})
    return payload


def live_payload(board: LifeBoard, census: List[Dict[str, int]], watch: LifeWatch,
                 elapsed: float = 0.0) -> Dict[str, Any]:
    """桌面视图**实时播放**用的 payload：单帧栅格 + 到目前为止的逐代统计。

    与 :func:`payload_for` 的结构完全一致（``view`` / ``cells`` / ``census`` / 结局字段），
    只是"帧"只有当前这一代 —— 界面上不预先算好未来，而是一代一代往前走（不设代数上限），
    于是 ``frames`` 退化为单帧，而 ``census`` 是这一整条轨迹的累积（右侧人口曲线画它）。
    """
    last = census[-1] if census else {}
    payload = frame_payload(board)
    payload.update({
        "census": list(census),
        "generation": board.generation,
        "population": board.population,
        "density": board.density_now,
        "births": last.get("births", 0),
        "deaths": last.get("deaths", 0),
        "outcome": watch.outcome,
        "outcomeLabel": watch.label,
        "outcomeText": outcome_text(watch.outcome, watch.period, watch.period_start,
                                    board.generation, board.population),
        "period": watch.period,
        "periodStart": watch.period_start,
        "elapsedMs": elapsed * 1000.0,
    })
    return payload


def frame_payload(board: LifeBoard, view: str = "life-grid",
                  **scalars: Any) -> Dict[str, Any]:
    """把**当前棋盘**包成一份单帧 payload（桌面视图点击涂画后原地重绘用它）。

    这是"编辑之后怎么重画"的唯一真相源：视图不需要知道 payload 有哪些字段，
    只要拿 :func:`build_board` 造出的棋盘改一格，再调用本函数即可。
    """
    cells = board.encode()
    payload: Dict[str, Any] = {
        "view": view,
        "rows": board.rows,
        "cols": board.cols,
        "generation": board.generation,
        "population": board.population,
        "density": board.density_now,
        "births": 0,
        "deaths": 0,
        "rule": board.rule_string,
        "ruleName": board.rule_name,
        "boundary": board.boundary,
        "boundaryName": board.boundary_name,
        "pattern": board.pattern,
        "patternName": board.pattern_name,
        "densityStart": board.density,
        "outcome": OUTCOME_RUNNING,
        "outcomeLabel": OUTCOME_LABELS[OUTCOME_RUNNING],
        "outcomeText": "棋盘已就绪：按 ▶ 播放开始演化，或继续在画布上涂改。",
        "period": 0,
        "periodStart": 0,
        "generations": 0,
        "stride": 1,
        "frameCount": 1,
        "census": [{"gen": board.generation, "population": board.population,
                    "births": 0, "deaths": 0}],
        "elapsedMs": 0.0,
    }
    payload.update(encode_cells(board))
    payload.update({"cells": cells, "frames": [cells]})
    payload.update(scalars)
    return payload


# ----------------------------------------------------------------------
# 动作处理器
# ----------------------------------------------------------------------
def _handle_run(params: Dict[str, Any]) -> Dict[str, Any]:
    """按参数重新播种并演化一次，返回界面用的 payload。

    界面参数在这里翻成内部取值（:func:`options_from_ui`）—— 数据级契约的入参永远是
    "界面上的样子"，而模型只认内部取值。
    """
    board, run = run_board(options_from_ui(params))
    return payload_for(board, run)


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """动作分发入口，由 :class:`~awe_math.spec.ModelSpec` 调用。

    ``payload`` 目前用不上（没有"点击指定起点"这类输入：起点的编辑是纯界面行为，
    由桌面视图直接改棋盘 → :func:`frame_payload`），保留它是为了与统一签名一致。
    """
    if action == "evolve":
        return _handle_run(params)
    raise ValueError(f"生命游戏模型不支持的动作：{action}")


# ----------------------------------------------------------------------
# 终端模式
# ----------------------------------------------------------------------
#: 本模型的终端命令行参数。
#:
#: 尺寸用自己的 ``--cells``（边长），**不复用**渗流的 ``--rows``：两者默认值不同（40 / 50），
#: 而入口是按 flags 合并声明的（同 flags 只登记一次、先声明者胜出），于是"生命游戏的 --rows"
#: 会被静默换成渗流的默认值 40 —— 这正是评审文档里的 R7。语义与默认值**完全一致**的
#: ``--cols`` / ``--scan`` / ``--step`` / ``--trials`` 才共用声明。
LIFE_CLI_OPTIONS: Tuple[CliOption, ...] = (
    CliOption(
        ("--cells",), kind="int", default=DEFAULT_ROWS,
        help=f"棋盘边长（正方形），默认 {DEFAULT_ROWS}",
    ),
    CliOption(
        ("--cols",), kind="int",
        help="列数；与 --cells 不同即为矩形棋盘，省略则与 --cells 相同",
    ),
    CliOption(
        ("--density",), kind="float", default=DEFAULT_DENSITY,
        help=f"随机播种的初始存活密度，默认 {DEFAULT_DENSITY}",
    ),
    CliOption(
        ("--generations",), kind="int", default=DEFAULT_GENERATIONS,
        help=f"演化代数上限，默认 {DEFAULT_GENERATIONS}",
    ),
    CliOption(
        ("--rule",), kind="choice", choices=tuple(RULES),
        help="规则串：B3/S23（标准）/ B36/S23（HighLife）/ B3/S12345（慢生长）",
    ),
    CliOption(
        ("--boundary",), kind="choice", choices=tuple(BOUNDARIES),
        help="边界条件：torus 环面 / dead 死边界",
    ),
    CliOption(
        ("--pattern",), kind="choice",
        choices=(PATTERN_BLANK, "random") + tuple(PATTERNS),
        help="开局图案：random 随机播种（终端默认）/ blank 空白 / "
             + " / ".join(PATTERNS),
    ),
    CliOption(
        ("--trials",), kind="int", default=1000,
        help="统计次数，默认 1000",
    ),
    CliOption(
        ("--scan",), kind="flag",
        help="扫描：渗流模型扫 p 曲线、投针模型逐级放大投针数、生命游戏扫密度（不开窗口）",
    ),
    CliOption(
        ("--step",), kind="float", default=0.05,
        help="密度扫描步长，默认 0.05",
    ),
)


def _ascii_board(cells: str, rows: int, cols: int) -> List[str]:
    """把 0/1 掩码渲染成终端字符画：**两行合成一行**（``▀`` / ``▄`` / ``█`` / 空格）。

    于是 50×50 只占 25 行 × 50 列，120×120 也只占 60 行 —— 终端里能完整看完一张棋盘。
    """
    blocks = []
    for row in range(0, rows, 2):
        line: List[str] = []
        top = row * cols
        bottom = (row + 1) * cols
        for col in range(cols):
            upper = cells[top + col] == "1"
            lower = (cells[bottom + col] == "1") if row + 1 < rows else False
            if upper and lower:
                line.append("█")
            elif upper:
                line.append("▀")
            elif lower:
                line.append("▄")
            else:
                line.append(" ")
        blocks.append("".join(line))
    return blocks


def _cli(raw_args) -> int:
    """终端模式：演化一次（打印终局 + 字符画），或（``--scan``）扫描密度 -> 长期结局。

    取值统一走 :class:`~awe_math.spec.CliArgs`：名字与默认值都来自 :data:`LIFE_CLI_OPTIONS`
    的声明，不手写魔法字符串。
    """
    args = CliArgs(raw_args, LIFE_CLI_OPTIONS)
    rows = _resolve_size(args.cells, DEFAULT_ROWS)
    cols = _resolve_size(getattr(args, "cols", None) or rows, rows)
    density = _resolve_density(args.density)
    generations = _resolve_generations(args.generations)
    rule = args.rule if args.rule in RULES else DEFAULT_RULE
    boundary = args.boundary if args.boundary in BOUNDARIES else BOUNDARY_TORUS
    # 终端是"给参数就出数"的场景：不指定图案时用随机播种（空白棋盘没有任何可统计的东西）
    raw_pattern = getattr(args, "pattern", None)
    known = raw_pattern in PATTERNS or raw_pattern in ("random", PATTERN_BLANK)
    pattern = raw_pattern if known else "random"
    seed = _resolve_seed(getattr(args, "seed", -1))
    trials = max(1, int(args.trials))

    if args.scan:
        step = max(0.01, min(0.5, float(args.step)))
        densities: List[float] = []
        point = step
        while point <= 1.0 + 1e-9:
            densities.append(round(point, 3))
            point += step

        print("=" * 78)
        print(f"生命游戏 · 密度扫描 | {rows}×{cols} 棋盘 | {RULES[rule]} | "
              f"{BOUNDARIES[boundary]} | 每点 {trials} 次 × 最多 {generations} 代")
        print("=" * 78)
        print(f"{'初始密度':>10} | {'存活率':>8} | {'收敛率':>8} | {'仍在演化':>10} | 平均末态活细胞")
        print("-" * 78)

        def on_point(done: int, total: int, res: DensityResult) -> None:
            bar = "█" * int(round(res.survival_rate * 20))
            print(f"{res.density:>10.2f} | {res.survival_rate:>8.2f} | "
                  f"{res.settled_rate:>8.2f} | {res.ongoing / res.trials:>10.2f} | "
                  f"{res.mean_population:>8.1f} {bar}")
            sys.stdout.flush()

        scan_survival(densities, rows=rows, cols=cols, generations=generations,
                      trials=trials, rule=rule, boundary=boundary, rng=seed,
                      progress=on_point)
        print("-" * 78)
        print("提示：这不是渗流那种「量变引起质变」的阶跃曲线 —— 生命游戏没有确定的临界密度。")
        print("      密度太低时随机结构很难自维持（很快消亡），太高时迅速僵化成静止块 /")
        print("      短周期；只有中间一段才容易长出长时间活跃的结构，曲线是**平缓**的。")
        return 0

    board, run = run_board({"rows": rows, "cols": cols, "boundary": boundary,
                            "pattern": pattern, "rule": rule, "density": density,
                            "generations": generations, "seed": seed})
    print("=" * 78)
    print(f"生命游戏 | {rows}×{cols} | {board.rule_name} | {board.boundary_name} | "
          f"开局：{board.pattern_name}"
          + (f"（密度 {density:.2f}）" if pattern == "random" else ""))
    print("=" * 78)
    print(f"{'代数':>6} | {'活细胞数':>10} | {'密度':>8} | {'新生':>6} | {'死亡':>6}")
    print("-" * 78)
    step_size = max(1, run.stop_generation // 12)
    for generation, population, births, deaths in run.census:
        if generation % step_size and generation != run.stop_generation:
            continue
        total_cells = rows * cols
        print(f"{generation:>6} | {population:>10} | "
              f"{population / total_cells:>8.3f} | {births:>6} | {deaths:>6}")
    print("-" * 78)
    print(f"结局：{run.outcome_label} —— "
          + outcome_text(run.outcome, run.period, run.period_start,
                         run.stop_generation, run.population))
    print(f"本次实际演化 {run.stop_generation} 代，耗时 {run.elapsed * 1000:.1f} ms"
          f"（帧采样步长 {run.stride}）")
    if run.frames:
        print()
        print("末态（▀ 上半格活、▄ 下半格活、█ 都活；每两个像素行合成一行）")
        for line in _ascii_board(run.frames[-1], rows, cols):
            print("  " + line)
    print("=" * 78)
    return 0


def build_spec() -> ModelSpec:
    """构造并返回生命游戏模型的元数据。"""
    return ModelSpec(
        key="life_game",
        name="生命游戏模型",
        topic="简单规则与涌现",
        summary="每个格子只看周围 8 格，按三条局部规则同时更新："
                "局部规则不变，却能长出滑翔机、振荡子与滑翔机枪 —— "
                "复杂度可以来自规则本身，而不来自规则的复杂。",
        description=(
            "在 n × m 的棋盘上，每个格子要么活要么死。每一代**同时**更新所有格子，"
            "只看 Moore 邻域（周围 8 格）里的活细胞数：\n\n"
            "    B3/S23：死格恰好 3 个邻居就新生；活格有 2 或 3 个邻居就存活。\n\n"
            "**三条局部规则、没有中央控制、没有随机性**，却同时产生了：\n\n"
            "1. **静止物**（周期 1）：如方块，一直不变；\n"
            "2. **振荡子**（周期 k）：如闪烁器（周期 2）、脉冲星（周期 3），来回振荡；\n"
            "3. **会走路的结构**：滑翔机每 4 代整体平移一格，在环面上会绕棋盘一圈回来；\n"
            "4. **无限增长**：高斯帕滑翔机枪每 30 代射出一架滑翔机，永不收敛；\n"
            "5. 以及更惊人的结论：生命游戏是**图灵完备**的，能构造出通用计算机。\n\n"
            "**为什么「必然周期化」又不必然看得见**：棋盘状态有限（2^(n·m) 种），演化完全确定，"
            "所以状态序列迟早会重复 —— 无序最终走向有序（离散版的「热力学箭头」）。"
            "但瞬态的长度没有上界：12×12 的小棋盘上几十代就收敛，20×20 的环面上跑 600 代"
            "可能仍在变化，50×50 的状态数是 2^2500。所以模型会**主动检测状态重复**，"
            "一旦确认周期就提前停止并给出周期长度。\n\n"
            "**初始密度不是临界值**：密度太低时随机结构难以自维持（很快消亡），密度太高时"
            "棋盘迅速僵化成大片静止块与短周期（0.9 的密度一代之内就全灭）。只有中间一段"
            "（约 0.2–0.4）最容易长出长时间活跃的结构。这**不是**渗流那种有确定临界点的"
            "相变，而是一条平缓的曲线 —— 终端里的 ``--scan`` 扫的就是它。\n\n"
            "界面怎么玩：\n\n"
            "1. **先画开局**：棋盘一开始是**空白**的，按住鼠标在画布上拖动画细胞 ——"
            "按下的那一格决定这一笔是「画」还是「擦」，所以按住不动不会反复翻转；"
            "也可以用「生成开局」按图案 / 密度铺一片，用「清空」回到空白；\n"
            "2. **播放**：左侧顶部的「▶ 播放」逐代演化（可暂停 / 单步 / 调速），"
            "右侧的指标与**人口曲线**随每一代实时刷新；\n"
            "3. **随时改**：改规则或边界不用重画（它们作用在现有棋盘上），"
            "画布上点击 / 拖拽可以随时涂改，改完接着演化。"
        ),
        params=PARAMS,
        actions=ACTIONS,
        view="life_game",
        accent="#4ade80",
        icon="▩",
        handler=handle,
        cli=_cli,
        cli_options=LIFE_CLI_OPTIONS,
        # 对象级契约：桌面视图用它造棋盘（点击涂画后的单帧重绘也复用它）
        factory=build_board,
        highlights=("B3/S23 三条局部规则 -> 滑翔机 / 振荡子 / 滑翔机枪",
                    "确定性 + 有限状态：必然进入周期，瞬态长度没有上界",
                    "初始密度不是临界值：曲线平缓，两端都会「死」"),
        order=10,
    )
