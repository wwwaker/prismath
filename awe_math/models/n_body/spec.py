# -*- coding: utf-8 -*-
"""
万有引力多星模型 —— 界面元数据与动作处理器
==========================================
本文件是「模型」与「界面」之间的唯一桥梁：

* :data:`PARAMS` 描述可调参数（场景 / 星体数 / 时间步长 / 子步数 / 软化长度 / 轨迹 / 种子），
  桌面侧栏由 ``kit/form.py`` 按 ``spec.params`` 自动生成，网页 / 终端同样据此生成控件；
* :func:`handle` 处理界面发来的动作请求（跑一段模拟），返回 **JSON 可序列化** 的结果；
* :func:`build_nbody` 是「内部取值 -> 模型实例」的**唯一构造入口**，数据级契约与对象级契约
  共用它（与生命游戏的 ``build_board``、渗流模型的 ``build_grid`` 同一约定）；
* :func:`snapshot_payload` / :func:`run_payload` 是返回结构的**唯一真相源**：
  桌面视图的实时播放用前者（单帧 + 当前轨迹），终端 / 网页用后者（抽样帧序列）；
* :func:`_cli` 是终端模式的入口（含 ``--scan``：时间步长 -> 能量漂移）。

算法本身在 :mod:`~awe_math.models.n_body.model` 中，与本文件完全解耦。

返回结构（``payload["view"]``）
------------------------------
``nbody-orbit``：多星运动。
**实时路径**给单帧：``positions``（扁平 ``[x0, y0, x1, y1, …]``）+ 诊断量，
轨迹由桌面视图直接读模型对象（``NBody.trail_array``）—— 对象级契约的意义就在这里，
不必把上千个历史点每帧都序列化一遍。
**无头路径**给抽样后的 ``frames``（每个元素都是同样的扁平位置数组）+ ``samples``
（每个采样点的 ``(t, E, 相对漂移, 最大半径)``），供终端 / 网页 / 通用视图回放。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ...spec import ActionSpec, CliArgs, CliOption, ModelSpec, ParamSpec
from .model import (
    DEFAULT_DT,
    DEFAULT_FRAMES,
    DEFAULT_SEED,
    DEFAULT_SOFTENING,
    DEFAULT_STARS,
    DEFAULT_SUBSTEPS,
    DEFAULT_TRAIL,
    MAX_DT,
    MAX_SOFTENING,
    MAX_STARS,
    MAX_SUBSTEPS,
    MAX_TRAIL,
    MIN_DT,
    MIN_STARS,
    MIN_SUBSTEPS,
    MIN_TRAIL,
    SCENARIO_FIGURE_EIGHT,
    SCENARIO_LABELS,
    SCENARIO_ORDER,
    SCENARIOS,
    NBody,
    NBodyRun,
    build_scenario,
    encode_positions,
    scan_drift,
)

#: 场景下拉框：界面标签 -> 模型内部取值（与渗流 / 生命游戏同一做法）
SCENARIO_CHOICES: Dict[str, str] = {
    SCENARIO_LABELS[key]: key for key in SCENARIO_ORDER
}

# ----------------------------------------------------------------------
# 可调参数（桌面侧栏按 group 自动分组生成控件）
# ----------------------------------------------------------------------
PARAMS = (
    ParamSpec(
        key="scenario", label="场景", kind="choice",
        default=SCENARIO_LABELS[SCENARIO_FIGURE_EIGHT],
        choices=tuple(SCENARIO_CHOICES), group="场景",
        hint="初值库：8 字三体（精确周期解）/ 双星 + 行星 / 太阳 + 四行星 / "
             "随机星团（混沌）/ 星系盘。切换场景会按该场景的推荐软化长度重置模拟。",
    ),
    ParamSpec(
        key="stars", label="星体数 N（随机场景）", kind="int", default=DEFAULT_STARS,
        min=MIN_STARS, max=MAX_STARS, step=1, group="场景",
        hint="只对「随机星团」「星系盘」生效，其余场景的星体数由场景本身决定。\n"
             "代价是 O(N²)：200 颗时单步约 4 ms，实时播放会开始吃力。",
    ),
    ParamSpec(
        key="dt", label="时间步长 dt", kind="float", default=DEFAULT_DT,
        min=MIN_DT, max=MAX_DT, step=0.001, group="积分",
        hint="速度 Verlet 的一步。步长越小越准（能量漂移 ≈ dt²），但同样一段动画要算更多步；"
             "近距遭遇多的星团需要更小的 dt，否则会数值爆炸。",
    ),
    ParamSpec(
        key="substeps", label="每帧子步数", kind="int", default=DEFAULT_SUBSTEPS,
        min=MIN_SUBSTEPS, max=MAX_SUBSTEPS, step=1, group="积分",
        hint="一帧画面推进多少个 dt —— 它只影响**动画快慢**，不影响物理；"
             "想细看某一段就把「动画间隔」调大（或先暂停再单步）。",
    ),
    ParamSpec(
        key="softening", label="软化半径 ε", kind="float", default=DEFAULT_SOFTENING,
        min=0.0, max=MAX_SOFTENING, step=0.01, group="积分",
        hint="把 1/r² 换成 1/(r²+ε²)，让「两星贴到一起」时力保持有限。\n"
             "精确解（8 字三体 / 圆轨道）必须用 ε = 0；随机星团建议 0.1 以上，"
             "否则近距遭遇会把速度打到数值爆炸。",
    ),
    ParamSpec(
        key="trail", label="轨迹点数", kind="int", default=DEFAULT_TRAIL,
        min=MIN_TRAIL, max=MAX_TRAIL, step=10, group="轨迹",
        hint="每颗星保留多少个历史点（0 = 不画轨迹）。点越多尾迹越长，越能看清轨道的形状；"
             "代价是每帧都要画更长的折线。",
    ),
    ParamSpec(
        key="seed", label="随机种子（-1 表示随机）", kind="int", default=DEFAULT_SEED,
        min=-1, max=2147483647, step=1, group="随机性",
        hint="只对随机场景（星团 / 星系盘）有效；取 ≥0 时可以复现同一组初值。",
    ),
)

# ----------------------------------------------------------------------
# 动作
# ----------------------------------------------------------------------
ACTIONS = (
    ActionSpec("simulate", "开始模拟", mode="once", kind="primary",
               hint="按当前场景与参数重置初值并开始运动模拟（桌面端逐帧实时播放）"),
)

#: 本模型的终端命令行参数。
#:
#: ``--trail`` / ``--frames`` / ``--substeps`` 这些名字是本模型独有的，不会与别的模型冲突；
#: ``--scan`` 与其它模型共用（同一组选项串只登记一次，帮助里会标注）。
CLI_OPTIONS: Tuple[CliOption, ...] = (
    CliOption(
        ("--scenario",), kind="choice", choices=tuple(SCENARIO_ORDER),
        help="场景：" + " / ".join(SCENARIO_ORDER) + f"，默认 {SCENARIO_FIGURE_EIGHT}",
    ),
    CliOption(
        ("--stars",), kind="int",
        help=f"星体数（只对随机星团 / 星系盘生效），默认随场景（{DEFAULT_STARS}）",
    ),
    CliOption(
        ("--dt",), kind="float", default=DEFAULT_DT,
        help=f"时间步长，默认 {DEFAULT_DT}",
    ),
    CliOption(
        ("--substeps",), kind="int", default=DEFAULT_SUBSTEPS,
        help=f"每帧推进的子步数，默认 {DEFAULT_SUBSTEPS}",
    ),
    CliOption(
        ("--softening",), kind="float",
        help="软化半径 ε；省略则用场景的推荐值（精确解场景为 0）",
    ),
    CliOption(
        ("--trail",), kind="int", default=DEFAULT_TRAIL,
        help=f"轨迹点数，默认 {DEFAULT_TRAIL}",
    ),
    CliOption(
        ("--frames",), kind="int", default=DEFAULT_FRAMES,
        help=f"模拟帧数，默认 {DEFAULT_FRAMES}",
    ),
    CliOption(
        ("--scan",), kind="flag",
        help="扫描：渗流模型扫 p 曲线、投针模型逐级放大投针数、生命游戏扫密度、"
             "多星模型扫「时间步长 -> 能量漂移」（不开窗口）",
    ),
)


# ----------------------------------------------------------------------
# 参数校正（界面标签 -> 内部取值；数值 -> 合法范围）
# ----------------------------------------------------------------------
def _pick(mapping: Dict[str, str], value: Any, fallback: str) -> str:
    """把界面上的中文选项翻译成模型内部取值（已经是内部取值时原样返回）。"""
    text = str(value)
    if text in mapping:
        return mapping[text]
    if text in mapping.values():
        return text
    return fallback


def _resolve_stars(value: Any, fallback: int = DEFAULT_STARS) -> int:
    """把界面传来的星体数夹到 ``[MIN_STARS, MAX_STARS]``。"""
    try:
        count = int(float(value))
    except (TypeError, ValueError):
        return fallback
    return max(MIN_STARS, min(MAX_STARS, count))


def _resolve_dt(value: Any) -> float:
    """把界面传来的时间步长夹到 ``[MIN_DT, MAX_DT]``。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return DEFAULT_DT
    if not math.isfinite(number):
        return DEFAULT_DT
    return max(MIN_DT, min(MAX_DT, number))


def _resolve_substeps(value: Any) -> int:
    """把界面传来的子步数夹到 ``[MIN_SUBSTEPS, MAX_SUBSTEPS]``。"""
    try:
        count = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_SUBSTEPS
    return max(MIN_SUBSTEPS, min(MAX_SUBSTEPS, count))


def _resolve_softening(value: Any, fallback: float = DEFAULT_SOFTENING) -> float:
    """把界面传来的软化长度夹到 ``[0, MAX_SOFTENING]``；``None`` 时用场景推荐值。"""
    if value is None:
        return max(0.0, min(MAX_SOFTENING, float(fallback)))
    try:
        number = float(value)
    except (TypeError, ValueError):
        return max(0.0, min(MAX_SOFTENING, float(fallback)))
    if not math.isfinite(number):
        return max(0.0, min(MAX_SOFTENING, float(fallback)))
    return max(0.0, min(MAX_SOFTENING, number))


def _resolve_trail(value: Any) -> int:
    """把界面传来的轨迹长度夹到 ``[0, MAX_TRAIL]``。"""
    try:
        count = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_TRAIL
    return max(MIN_TRAIL, min(MAX_TRAIL, count))


def _resolve_frames(value: Any) -> int:
    """把界面传来的帧数夹到 ``[1, 5000]``（内部再按 ``MAX_FRAMES`` 抽样）。"""
    try:
        count = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_FRAMES
    return max(1, min(5000, count))


def _resolve_seed(value: Any) -> Optional[int]:
    """把界面传来的种子转成内核可用的形式（``None | int``）：-1 表示随机。"""
    try:
        seed = int(float(value))
    except (TypeError, ValueError):
        return None
    return None if seed < 0 else seed


def options_from_ui(params: Dict[str, Any]) -> Dict[str, Any]:
    """把**界面参数**（下拉框给的是中文标签）翻成模型内部取值并夹到合法范围。

    返回的字典可以直接交给 :func:`build_nbody`。界面（桌面侧栏 / 网页表单）走这一条路；
    终端直接用内部取值，不必经过本函数。
    """
    scenario = _pick(SCENARIO_CHOICES, params.get("scenario"), SCENARIO_FIGURE_EIGHT)
    return {
        "scenario": scenario,
        "stars": _resolve_stars(params.get("stars"), SCENARIOS[scenario].stars),
        "dt": _resolve_dt(params.get("dt")),
        "substeps": _resolve_substeps(params.get("substeps")),
        "softening": _resolve_softening(params.get("softening"),
                                        SCENARIOS[scenario].softening),
        "trail": _resolve_trail(params.get("trail")),
        "seed": params.get("seed"),
    }


# ----------------------------------------------------------------------
# 唯一构造入口（数据级 + 对象级共用）
# ----------------------------------------------------------------------
def build_nbody(params: Dict[str, Any]) -> NBody:
    """由**内部取值**构造模型实例 —— **两套契约共用的唯一构造入口**。

    与渗流模型的 ``build_grid``、生命游戏的 ``build_board`` 同一约定：``params`` 里的
    ``scenario`` 必须是模型内部取值（``"figure_eight"`` / ``"cluster"`` …）；
    界面上的中文标签请先过 :func:`options_from_ui`。

    ``softening`` 传 ``None``（或省略）表示"用场景的推荐值" —— 精确解场景是 0，
    随机星团是 0.16 —— 这样终端里不加 ``--softening`` 也能拿到合理的默认。
    """
    scenario = params.get("scenario")
    scenario = scenario if scenario in SCENARIOS else SCENARIO_FIGURE_EIGHT
    preset = build_scenario(
        scenario,
        stars=_resolve_stars(params.get("stars"), SCENARIOS[scenario].stars),
        seed=_resolve_seed(params.get("seed")),
    )
    return NBody(
        preset.positions,
        preset.velocities,
        preset.masses,
        dt=_resolve_dt(params.get("dt")),
        softening=_resolve_softening(params.get("softening"), preset.softening),
        trail=_resolve_trail(params.get("trail")),
        scenario=preset.key,
        label=preset.label,
        period=preset.period,
    )


# ----------------------------------------------------------------------
# payload：返回结构的唯一真相源
# ----------------------------------------------------------------------
def diagnostics(body: NBody, cost_ms: float = 0.0) -> Dict[str, Any]:
    """把模型的诊断量收成一份字典（实时 / 回放两条路共用，避免各写一遍）。"""
    return {
        "scenario": body.scenario,
        "scenarioName": SCENARIO_LABELS.get(body.scenario, body.label),
        "count": body.count,
        "steps": body.steps,
        "time": body.time,
        "dt": body.dt,
        "softening": body.softening,
        "energy0": body.initial_energy,
        "energy": body.total_energy(),
        "energyDrift": body.relative_energy_drift(),
        "maxDrift": body.max_drift,
        "momentum": float(np.linalg.norm(body.momentum())),
        "angularMomentum": body.angular_momentum(),
        "maxRadius": body.max_radius(),
        "escaped": body.escaped_count(),
        "blownUp": body.blown_up,
        "masses": [float(m) for m in np.round(body.mass, 6)],
        "costMs": float(cost_ms),
    }


def snapshot_payload(body: NBody, *, extent: Optional[Sequence[float]] = None,
                     cost_ms: float = 0.0, view: str = "nbody-orbit",
                     **scalars: Any) -> Dict[str, Any]:
    """把**当前这一帧**包成 payload（桌面视图的实时播放用它）。

    只带当前位置与诊断量；轨迹请让视图直接读 ``NBody.trail_array()`` ——
    那是对象级契约存在的意义：上千个历史点不必每帧序列化一次。
    """
    payload: Dict[str, Any] = {
        "view": view,
        "positions": encode_positions(body.pos),
        "frameCount": 1,
        **diagnostics(body, cost_ms),
    }
    payload["extent"] = (list(extent) if extent is not None
                         else list(body.bounds()))
    payload.update(scalars)
    return payload


def run_payload(body: NBody, run: NBodyRun, *, view: str = "nbody-orbit") -> Dict[str, Any]:
    """把一段**有上限**的模拟包成 payload（终端 / 网页 / 通用视图用它回放）。"""
    payload: Dict[str, Any] = {
        "view": view,
        "frames": [encode_positions(frame) for frame in run.frames],
        "frameCount": run.frame_count,
        "stride": run.stride,
        "substeps": run.substeps,
        "samples": [
            {"t": float(t), "energy": float(energy), "drift": float(drift),
             "maxRadius": float(radius)}
            for t, energy, drift, radius in run.samples
        ],
        "extent": list(run.extent),
        # 回放时模型已经跑到末态：诊断量用末态的值（与 frames[-1] 严格对应）
        "scenario": run.scenario,
        "scenarioName": SCENARIO_LABELS.get(run.scenario, run.label),
        "count": run.count,
        "steps": run.steps,
        "time": run.time,
        "dt": run.dt,
        "softening": run.softening,
        "energy0": run.energy0,
        "energy": run.energy,
        "energyDrift": run.energy_drift,
        "maxDrift": run.max_drift,
        "momentum": run.momentum,
        "angularMomentum": run.angular_momentum,
        "escaped": run.escaped,
        "blownUp": run.blown_up,
        "masses": [float(m) for m in np.round(run.masses, 6)],
        "costMs": run.elapsed * 1000.0,
    }
    return payload


# ----------------------------------------------------------------------
# 动作处理器
# ----------------------------------------------------------------------
def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """动作分发入口，由 :class:`~awe_math.spec.ModelSpec` 调用。

    桌面视图自己逐帧播放（不走这里）；本入口给**无头后端**用：
    按参数跑 ``DEFAULT_FRAMES`` 帧，返回抽样后的帧序列与诊断量。
    """
    if action != "simulate":
        raise ValueError(f"万有引力多星模型不支持的动作：{action}")
    internal = options_from_ui(params)
    body = build_nbody(internal)
    run = body.run(frames=DEFAULT_FRAMES, substeps=internal["substeps"])
    return run_payload(body, run)


# ----------------------------------------------------------------------
# 终端模式
# ----------------------------------------------------------------------
#: ``--scan`` 扫的时间步长（同一条曲线上的点：越小越准，代价是步数变多）
SCAN_DT_VALUES: Tuple[float, ...] = (0.016, 0.008, 0.004, 0.002, 0.001)


def _ascii_field(body: NBody, width: int = 66, height: int = 20) -> List[str]:
    """把末态星图画成字符点阵：重星用 ``@``、其余用 ``*``，画布范围取当前包围盒。"""
    x0, x1, y0, y1 = body.bounds(include_trail=False)
    span_x = max(x1 - x0, 1e-9)
    span_y = max(y1 - y0, 1e-9)
    grid = [[" "] * width for _ in range(height)]
    heaviest = float(np.max(body.mass)) if body.count else 1.0
    for index in range(body.count):
        x, y = body.pos[index]
        col = int((x - x0) / span_x * (width - 1))
        row = int((y1 - y) / span_y * (height - 1))     # 屏幕 y 向下，翻转一下
        col = max(0, min(width - 1, col))
        row = max(0, min(height - 1, row))
        grid[row][col] = "@" if body.mass[index] > 0.5 * heaviest else "*"
    return ["".join(line) for line in grid]


def _cli(raw_args) -> int:
    """终端模式：跑一段模拟打印诊断表与末态星图，或（``--scan``）扫时间步长 -> 能量漂移。"""
    args = CliArgs(raw_args, CLI_OPTIONS)
    scenario = args.scenario if args.scenario in SCENARIOS else SCENARIO_FIGURE_EIGHT
    stars = _resolve_stars(getattr(args, "stars", None), SCENARIOS[scenario].stars)
    dt = _resolve_dt(args.dt)
    substeps = _resolve_substeps(args.substeps)
    default_softening = SCENARIOS[scenario].softening
    softening = _resolve_softening(getattr(args, "softening", None), default_softening)
    trail = _resolve_trail(args.trail)
    frames = _resolve_frames(args.frames)
    seed = _resolve_seed(getattr(args, "seed", DEFAULT_SEED))

    if args.scan:
        print("=" * 78)
        print(f"万有引力多星 · 时间步长扫描 | {SCENARIO_LABELS[scenario]}")
        print("=" * 78)
        print("每行都积分同样长的一段物理时间，量的是「最大相对能量漂移」。")
        print(f"{'时间步长 dt':>14}{'步数':>10}{'最大相对漂移':>18}")
        print("-" * 78)
        for point in scan_drift(SCAN_DT_VALUES, scenario=scenario,
                                softening=default_softening):
            print(f"{point.dt:>14.4f}{point.steps:>10}{point.drift:>18.3e}")
        print("-" * 78)
        print("提示：速度 Verlet 是二阶辛积分器 —— dt 减半，漂移约降为 1/4，")
        print("      而且误差**有界振荡**、不随时间单调漂移；这正是它适合长时间天体轨道的原因。")
        return 0

    params = {"scenario": scenario, "stars": stars, "dt": dt, "substeps": substeps,
              "softening": softening, "trail": trail, "seed": seed}
    body = build_nbody(params)
    run = body.run(frames=frames, substeps=substeps)
    print("=" * 78)
    print(f"万有引力多星 | {body.label} | N = {body.count} | dt = {body.dt:g} | "
          f"ε = {body.softening:g} | {frames} 帧 × {substeps} 子步")
    print("=" * 78)
    print(f"{'帧':>6} | {'步数':>8} | {'时间 t':>9} | {'总能量 E':>12} | "
          f"{'相对漂移':>11} | {'最大半径':>9}")
    print("-" * 78)
    total = max(1, len(run.samples) - 1)
    sample_stride = max(1, total // 12)
    steps_per_frame = max(1, substeps)
    for index, (moment, energy, drift, radius) in enumerate(run.samples):
        if index % sample_stride and index != len(run.samples) - 1:
            continue
        print(f"{index:>6} | {index * steps_per_frame:>8} | {moment:>9.3f} | "
              f"{energy:>12.6f} | {drift:>11.3e} | {radius:>9.3f}")
    print("-" * 78)
    print(f"末态：t = {run.time:.3f}，共 {run.steps} 步；"
          f"总能量 {run.energy:.6f}（相对漂移 {run.energy_drift:.3e}，"
          f"全过程最大 {run.max_drift:.3e}）")
    print(f"      总动量 |P| = {run.momentum:.3e}，角动量 L = {run.angular_momentum:.6f}，"
          f"逃逸 {run.escaped} 颗，最大半径 {body.max_radius():.3f}")
    if run.blown_up:
        print(" ! 数值爆炸：近距遭遇把速度打到了 inf/NaN —— "
              "请减小 dt（或增大 ε、换一个随机种子）。")
    else:
        print(f"耗时 {run.elapsed * 1000:.1f} ms"
              + (f"（帧序列按步长 {run.stride} 抽样，共 {run.frame_count} 帧）"
                 if run.stride > 1 else ""))
    print()
    print("末态星图（@ 重星 / * 轻星；范围取当前包围盒）")
    for line in _ascii_field(body):
        print("  " + line)
    print("=" * 78)
    return 0


def build_spec() -> ModelSpec:
    """构造并返回万有引力多星模型的元数据。"""
    return ModelSpec(
        key="n_body",
        name="万有引力多星模型",
        topic="确定性与混沌",
        summary="N 颗星只受万有引力 F = G·m₁·m₂/r²：规则只有一条、完全确定，"
                "却既能给出钟表般精确的周期轨道（8 字三体），也能给出不可长期预测的混沌（三体 / 星团）。",
        description=(
            "N 颗星体两两之间只有万有引力：\n\n"
            "    F_ij = G·m_i·m_j·(r_j − r_i) / (|r_j − r_i|² + ε²)^{3/2}\n\n"
            "每颗星按牛顿第二定律加速，**没有别的力、没有中央控制、没有人为脚本**。"
            "于是同一条确定性规则在不同 N 下给出完全不同的世界：\n\n"
            "1. **N = 2**：开普勒问题，轨迹是精确的圆锥曲线（圆 / 椭圆 / 抛物线 / 双曲线），"
            "周期满足 T = 2π·a^{3/2}/√(G·M)；\n"
            "2. **N = 3**：8 字三体是 Chenciner–Montgomery 的**精确周期解** —— 三个等质量星体"
            "沿同一条「8」字首尾相接，周期 6.32591398 —— 而一般三体问题已经**没有解析解**；\n"
            "3. **N 更多**：随机星团里星体互相甩动，近距遭遇把个别星体加速到逃逸速度；"
            "初值只差最后一位小数，长期轨道就完全不同（对初值的敏感依赖）。\n\n"
            "**模型做什么**：用辛（symplectic）的速度 Verlet 积分器推进运动，"
            "并全程盯着四个守恒量 —— 总能量 E、总动量 P、角动量 L 与「回到出发点」的偏差。\n"
            "辛积分器的能量误差**有界、只在真值附近振荡**（不像低阶显式方法那样单调漂移），"
            "这正是它适合长时间天体积分的原因；终端里的 ``--scan`` 扫的就是"
            "「时间步长 dt -> 最大能量漂移」，能直接看到二阶收敛（dt 减半、漂移降为约 1/4）。\n\n"
            "界面怎么玩：\n\n"
            "1. **选场景**：8 字三体（精度标尺）/ 双星 + 行星 / 太阳 + 四行星 / "
            "随机星团（混沌）/ 星系盘。切换场景会自动套用该场景推荐的软化长度 ε；\n"
            "2. **播放**：左侧顶部的「▶ 播放」逐帧推进（可暂停 / 单步 / 调速），"
            "「↺ 重置模拟」回到初值重来；右侧的指标行与**能量曲线**随每一帧刷新；\n"
            "3. **调参数**：`dt` 与 `ε` 决定「能不能算准、会不会炸」，"
            "`子步数`只影响动画快慢（不影响物理），`轨迹点数`决定尾迹长短。\n\n"
            "两个容易踩的坑（模型会直接提示，不会甩异常）：\n\n"
            "* **ε = 0 是严格的牛顿引力**：8 字三体这类精确解必须用 0，"
            "而随机星团建议给 0.1 以上 —— 否则近距遭遇会让速度发散（界面会显示「数值爆炸」，"
            "请减小 dt 或增大 ε）；\n"
            "* **同一初值 ≠ 同一长期命运**：混沌场景里换个随机种子（甚至只改 dt）"
            "就会走出一条完全不同的历史，这不是 bug，而是本模型要展示的结论。"
        ),
        params=PARAMS,
        actions=ACTIONS,
        view="n_body",
        accent="#c084fc",
        icon="✷",
        handler=handle,
        cli=_cli,
        cli_options=CLI_OPTIONS,
        # 对象级契约：桌面视图用它造模型实例（实时播放直接读模型对象的轨迹）
        factory=build_nbody,
        highlights=("同一条 F = Gm₁m₂/r²：N=2 是精确轨道，N=3 就混沌",
                    "8 字三体精确周期解：转一圈回到出发点",
                    "速度 Verlet 辛积分：能量误差有界振荡、约按 dt² 收敛"),
        order=10,
    )
