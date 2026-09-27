# -*- coding: utf-8 -*-
"""Logistic Map 的参数、动作、JSON payload 与命令行入口。"""

from __future__ import annotations

import sys
from typing import Any, Dict, Tuple

from ...spec import ActionSpec, CliArgs, CliOption, ModelSpec, ParamSpec
from .model import (
    DEFAULT_DISCARD,
    DEFAULT_ITERATIONS,
    DEFAULT_POINTS_PER_R,
    DEFAULT_R,
    DEFAULT_R_MAX,
    DEFAULT_R_MIN,
    DEFAULT_R_SAMPLES,
    DEFAULT_X0,
    MAX_DISCARD,
    MAX_ITERATIONS,
    MAX_POINTS_PER_R,
    MAX_R_SAMPLES,
    LogisticMap,
)

__all__ = ["PARAMS", "ACTIONS", "CLI_OPTIONS", "options_from_ui", "build_logistic",
           "handle", "build_spec"]


PARAMS = (
    ParamSpec(
        key="r", label="控制参数 r", kind="float", default=DEFAULT_R,
        min=0.0, max=4.0, step=0.01, group="轨道",
        hint="xₙ₊₁ = r·xₙ·(1−xₙ)。r 较小时趋于稳定，接近 4 时通常进入混沌。",
    ),
    ParamSpec(
        key="x0", label="初值 x₀", kind="float", default=DEFAULT_X0,
        min=0.0, max=1.0, step=0.01, group="轨道",
        hint="初始种群比例 / 归一化状态，范围为 [0, 1]。",
    ),
    ParamSpec(
        key="iterations", label="轨道步数", kind="int", default=DEFAULT_ITERATIONS,
        min=20, max=MAX_ITERATIONS, step=20, group="轨道",
        hint="绘制多少个丢弃瞬态后的连续状态。",
    ),
    ParamSpec(
        key="discard", label="丢弃瞬态步数", kind="int", default=DEFAULT_DISCARD,
        min=0, max=MAX_DISCARD, step=10, group="轨道",
        hint="先迭代这些步数再开始采样，避免初值瞬态把周期 / 混沌结构遮住。",
    ),
    ParamSpec(
        key="r_min", label="分岔图 r 起点", kind="float", default=DEFAULT_R_MIN,
        min=0.0, max=4.0, step=0.01, group="分岔图",
        hint="分岔图横轴的起点。",
    ),
    ParamSpec(
        key="r_max", label="分岔图 r 终点", kind="float", default=DEFAULT_R_MAX,
        min=0.0, max=4.0, step=0.01, group="分岔图",
        hint="分岔图横轴的终点。",
    ),
    ParamSpec(
        key="r_samples", label="r 采样数", kind="int", default=DEFAULT_R_SAMPLES,
        min=40, max=MAX_R_SAMPLES, step=10, group="分岔图",
        hint="横轴采样越密，分岔图越细，但计算与绘图点数也越多。",
    ),
    ParamSpec(
        key="points_per_r", label="每个 r 保留点数", kind="int", default=DEFAULT_POINTS_PER_R,
        min=10, max=MAX_POINTS_PER_R, step=5, group="分岔图",
        hint="每个 r 丢弃瞬态后保留的连续点数；周期轨道会显示多个重复点。",
    ),
)

ACTIONS = (
    ActionSpec("orbit", "查看轨道", mode="once", kind="default",
               hint="固定 r，显示丢弃瞬态后的 xₙ 序列与 Lyapunov 指数"),
    ActionSpec("bifurcation", "生成分岔图", mode="once", kind="primary",
               hint="扫描一段 r，观察固定点 → 倍周期 → 混沌"),
)

CLI_OPTIONS = (
    CliOption(("--r",), kind="float", default=DEFAULT_R,
              help=f"控制参数 r，范围 0..4，默认 {DEFAULT_R}"),
    CliOption(("--x0",), kind="float", default=DEFAULT_X0,
              help=f"初值 x0，范围 0..1，默认 {DEFAULT_X0}"),
    CliOption(("--iterations",), kind="int", default=DEFAULT_ITERATIONS,
              help=f"轨道采样步数，默认 {DEFAULT_ITERATIONS}"),
    CliOption(("--discard",), kind="int", default=DEFAULT_DISCARD,
              help=f"丢弃瞬态步数，默认 {DEFAULT_DISCARD}"),
    CliOption(("--r-min",), kind="float", default=DEFAULT_R_MIN,
              help=f"分岔图 r 起点，默认 {DEFAULT_R_MIN}"),
    CliOption(("--r-max",), kind="float", default=DEFAULT_R_MAX,
              help=f"分岔图 r 终点，默认 {DEFAULT_R_MAX}"),
    CliOption(("--r-samples",), kind="int", default=DEFAULT_R_SAMPLES,
              help=f"分岔图 r 采样数，默认 {DEFAULT_R_SAMPLES}"),
    CliOption(("--points-per-r",), kind="int", default=DEFAULT_POINTS_PER_R,
              help=f"每个 r 保留点数，默认 {DEFAULT_POINTS_PER_R}"),
    CliOption(("--scan",), kind="flag",
              help="生成分岔图（不开窗口）"),
)


def _float(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number or number in (float("inf"), float("-inf")):
        return fallback
    return max(low, min(high, number))


def _int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def options_from_ui(params: Dict[str, Any]) -> Dict[str, Any]:
    """把表单 / CLI / 直接 API 输入规范化为模型内部参数。"""
    return {
        "r": _float(params.get("r"), 0.0, 4.0, DEFAULT_R),
        "x0": _float(params.get("x0"), 0.0, 1.0, DEFAULT_X0),
        "iterations": _int(params.get("iterations"), 20, MAX_ITERATIONS, DEFAULT_ITERATIONS),
        "discard": _int(params.get("discard"), 0, MAX_DISCARD, DEFAULT_DISCARD),
        "r_min": _float(params.get("r_min"), 0.0, 4.0, DEFAULT_R_MIN),
        "r_max": _float(params.get("r_max"), 0.0, 4.0, DEFAULT_R_MAX),
        "r_samples": _int(params.get("r_samples"), 40, MAX_R_SAMPLES, DEFAULT_R_SAMPLES),
        "points_per_r": _int(params.get("points_per_r"), 20, MAX_POINTS_PER_R,
                              DEFAULT_POINTS_PER_R),
    }


def build_logistic(params: Dict[str, Any]) -> LogisticMap:
    opts = options_from_ui(params)
    return LogisticMap(**opts)


def _orbit_payload(options: Dict[str, Any]) -> Dict[str, Any]:
    result = build_logistic(options).orbit()
    return {
        "view": "logistic-orbit",
        "mode": "单参数轨道",
        "rLabel": f"r = {result.r:.4f}",
        "r": result.r,
        "x0": result.x0,
        "iterations": result.iterations,
        "sampleCount": result.iterations,
        "discard": result.discard,
        "lyapunov": result.lyapunov,
        "records": result.records(),
        "elapsedMs": result.elapsed * 1000.0,
    }


def _bifurcation_payload(options: Dict[str, Any]) -> Dict[str, Any]:
    result = build_logistic(options).bifurcation()
    return {
        "view": "logistic-bifurcation",
        "mode": "分岔扫描",
        "rLabel": f"r ∈ [{result.r_min:.3f}, {result.r_max:.3f}]",
        "x0": options["x0"],
        "discard": options["discard"],
        "sampleCount": int(result.rs.size),
        # 分岔扫描同时包含许多个 r，单个 Lyapunov 指数没有定义；用文案
        # 明确告诉用户这里看的是整段参数的结构，而不是留下一个空白值。
        "lyapunov": "每个 r 不同",
        "rMin": result.r_min,
        "rMax": result.r_max,
        "rSamples": result.r_samples,
        "pointsPerR": result.points_per_r,
        "iterations": result.points_per_r,
        "rs": result.rs.tolist(),
        "xs": result.xs.tolist(),
        "thetas": [0.0] * int(result.rs.size),
        # 每个分岔采样点画成一小段水平短线；区间退化时也要留出可见宽度。
        "length": max((result.r_max - result.r_min) /
                       max(result.r_samples * 2.0, 1.0), 0.006),
        "elapsedMs": result.elapsed * 1000.0,
    }


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    options = options_from_ui(params)
    if action == "orbit":
        return _orbit_payload(options)
    if action == "bifurcation":
        return _bifurcation_payload(options)
    raise ValueError(f"Logistic Map 不支持的动作：{action}")


def _cli(raw_args) -> int:
    args = CliArgs(raw_args, CLI_OPTIONS)
    # ``--iterations`` 也是 Mandelbrot 的全局模型参数；它在统一入口里的
    # 默认值是 0（自动），而 Logistic Map 的默认值由本模块定义。没有显式
    # 传入时把这个共享默认还原回来，避免 CLI 首次运行被夹成最小 20 步。
    iterations = args.iterations or DEFAULT_ITERATIONS
    options = options_from_ui({
        "r": args.r, "x0": args.x0, "iterations": iterations,
        "discard": args.discard, "r_min": args.r_min, "r_max": args.r_max,
        "r_samples": args.r_samples, "points_per_r": args.points_per_r,
    })
    print("=" * 78)
    if args.scan:
        result = _bifurcation_payload(options)
        print(f"Logistic Map 分岔图 | r ∈ [{result['rMin']:.3f}, {result['rMax']:.3f}] | "
              f"{result['rSamples']} 个 r × 每个 {result['pointsPerR']} 点")
        print("=" * 78)
        print(f"采样点数 {len(result['xs'])}，x 范围 "
              f"[{min(result['xs']):.6f}, {max(result['xs']):.6f}]，"
              f"耗时 {result['elapsedMs']:.1f} ms")
        print("提示：r 较小时轨道会收敛到固定点或短周期；继续增大 r，周期不断倍增，"
              "最后出现正 Lyapunov 指数的混沌区。")
    else:
        result = _orbit_payload(options)
        print(f"Logistic Map 轨道 | r = {result['r']:.6f} | x₀ = {result['x0']:.6f} | "
              f"丢弃 {result['discard']} 步后采样 {result['iterations']} 步")
        print("=" * 78)
        values = [row["x"] for row in result["records"]]
        print(f"x 范围 [{min(values):.6f}, {max(values):.6f}]，末项 {values[-1]:.9f}，"
              f"Lyapunov 指数 {result['lyapunov']:.6f}，耗时 {result['elapsedMs']:.1f} ms")
        print("提示：Lyapunov 指数 < 0 通常表示稳定轨道，> 0 表示对初值敏感的混沌。")
    return 0


def build_spec() -> ModelSpec:
    return ModelSpec(
        key="logistic_map",
        name="Logistic Map 模型",
        topic="确定性与混沌",
        summary="只用 xₙ₊₁ = r·xₙ·(1−xₙ) 一条规则，观察稳定、倍周期分岔与混沌如何出现。",
        description=(
            "Logistic Map 是研究离散动力系统和混沌的经典模型。x 可以理解为归一化种群比例，"
            "r 是增长与拥挤共同决定的控制参数。r 较小时，轨道会收敛到固定点；继续增大 r，"
            "固定点先变成周期 2、周期 4，再不断倍周期，最后进入混沌。\n\n"
            "「查看轨道」固定 r，画出丢弃初始瞬态后的 xₙ 序列，并计算 Lyapunov 指数；"
            "「生成分岔图」扫描一段 r，把每个 r 最后的若干状态画成一列，能一次看见整个"
            "稳定区、倍周期级联和混沌带。Lyapunov 指数为负通常对应稳定轨道，正值表示"
            "附近初值会指数分离。"
        ),
        params=PARAMS,
        actions=ACTIONS,
        view="logistic_map",
        accent="#7c3aed",
        icon="∿",
        handler=handle,
        cli=_cli,
        cli_options=CLI_OPTIONS,
        factory=build_logistic,
        highlights=("固定点 → 周期倍增 → 混沌",
                    "分岔图一次展示整段控制参数",
                    "Lyapunov 指数刻画对初值的敏感性"),
        order=20,
    )
