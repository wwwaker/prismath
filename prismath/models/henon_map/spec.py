# -*- coding: utf-8 -*-
"""Hénon Map 的参数、动作、JSON payload 与命令行入口。"""

from __future__ import annotations

import math
from typing import Any, Dict

from ...spec import ActionSpec, CliArgs, CliOption, ModelSpec, ParamSpec
from .model import (
    DEFAULT_A,
    DEFAULT_B,
    DEFAULT_DISCARD,
    DEFAULT_ITERATIONS,
    DEFAULT_X0,
    DEFAULT_Y0,
    MAX_DISCARD,
    MAX_ITERATIONS,
    HenonMap,
    HenonOrbit,
)

__all__ = ["PARAMS", "ACTIONS", "CLI_OPTIONS", "options_from_ui", "build_henon",
           "handle", "build_spec"]


PARAMS = (
    ParamSpec(
        key="a", label="非线性参数 a", kind="float", default=DEFAULT_A,
        min=0.0, max=2.0, step=0.01, group="映射参数",
        hint="控制二次非线性强度；经典混沌吸引子使用 a=1.4。",
    ),
    ParamSpec(
        key="b", label="反馈参数 b", kind="float", default=DEFAULT_B,
        min=-1.0, max=1.0, step=0.01, group="映射参数",
        hint="把上一轮的 x 反馈到 y；经典参数为 b=0.3。",
    ),
    ParamSpec(
        key="x0", label="初值 x₀", kind="float", default=DEFAULT_X0,
        min=-2.0, max=2.0, step=0.01, group="初始状态",
        hint="初始 x 坐标；吸引域内的初值趋向同一结构，域外可能发散。",
    ),
    ParamSpec(
        key="y0", label="初值 y₀", kind="float", default=DEFAULT_Y0,
        min=-2.0, max=2.0, step=0.01, group="初始状态",
        hint="初始 y 坐标。",
    ),
    ParamSpec(
        key="iterations", label="采样步数", kind="int", default=DEFAULT_ITERATIONS,
        min=20, max=MAX_ITERATIONS, step=100, group="采样",
        hint="丢弃瞬态后保留多少个状态；越多，吸引子越完整。",
    ),
    ParamSpec(
        key="discard", label="丢弃瞬态步数", kind="int", default=DEFAULT_DISCARD,
        min=0, max=MAX_DISCARD, step=50, group="采样",
        hint="先迭代多少步再开始绘制，避免初值过渡过程遮住吸引子。",
    ),
)

ACTIONS = (
    ActionSpec("attractor", "查看相图", mode="once", kind="primary",
               hint="每个点是一个长期状态 (x, y)，经典参数下呈现折叠带状吸引子"),
    ActionSpec("orbit", "查看时间轨道", mode="once", kind="default",
               hint="按迭代步显示 xₙ 与 yₙ 的变化，并计算最大 Lyapunov 指数"),
)

CLI_OPTIONS = (
    CliOption(("--a",), kind="float", default=DEFAULT_A,
              help=f"非线性参数 a，默认 {DEFAULT_A}"),
    CliOption(("--b",), kind="float", default=DEFAULT_B,
              help=f"反馈参数 b，默认 {DEFAULT_B}"),
    CliOption(("--henon-x0",), kind="float", default=DEFAULT_X0,
              help=f"初值 x0，默认 {DEFAULT_X0}"),
    CliOption(("--henon-y0",), kind="float", default=DEFAULT_Y0,
              help=f"初值 y0，默认 {DEFAULT_Y0}"),
    # 统一入口里 Logistic / Mandelbrot 已占用 --iterations / --discard；使用
    # 模型前缀避免 argparse 的共享默认值污染 Hénon 的首屏采样设置。
    CliOption(("--henon-iterations",), kind="int", dest="henon_iterations",
              default=DEFAULT_ITERATIONS,
              help=f"Hénon 轨道采样步数，默认 {DEFAULT_ITERATIONS}"),
    CliOption(("--henon-discard",), kind="int", dest="henon_discard",
              default=DEFAULT_DISCARD,
              help=f"Hénon 丢弃瞬态步数，默认 {DEFAULT_DISCARD}"),
    CliOption(("--orbit",), kind="flag", help="查看时间轨道（默认查看吸引子）"),
)


def options_from_ui(params: Dict[str, Any]) -> Dict[str, Any]:
    """与直接 API 共用参数规范化规则。"""
    keys = ("a", "b", "x0", "y0", "iterations", "discard")
    model = HenonMap(**{key: params[key] for key in keys if key in params})
    return {key: getattr(model, key) for key in keys}


def build_henon(params: Dict[str, Any]) -> HenonMap:
    return HenonMap(**options_from_ui(params))


def _base_payload(result: HenonOrbit, view: str) -> Dict[str, Any]:
    values = result.values
    exponent = result.lyapunov
    exponent_text = "未计算" if exponent is None else (
        f"{exponent:.5f}" if math.isfinite(exponent) else "−∞")
    return {
        "view": view,
        "mode": "相平面" if view == "henon-attractor" else "时间轨道",
        "a": result.a,
        "b": result.b,
        "x0": result.x0,
        "y0": result.y0,
        "iterations": result.iterations,
        "discard": result.discard,
        "sampleCount": len(values),
        "lyapunov": exponent if exponent is not None and math.isfinite(exponent) else None,
        "lyapunovText": exponent_text,
        "stoppedStep": result.stopped_step,
        "elapsedMs": result.elapsed * 1000.0,
        "xs": values[:, 0].tolist(),
        "ys": values[:, 1].tolist(),
        "records": result.records(),
    }


def _attractor_payload(options: Dict[str, Any]) -> Dict[str, Any]:
    return _base_payload(build_henon(options).orbit(), "henon-attractor")


def _orbit_payload(options: Dict[str, Any]) -> Dict[str, Any]:
    return _base_payload(build_henon(options).orbit(), "henon-orbit")


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    options = options_from_ui(params)
    if action == "attractor":
        return _attractor_payload(options)
    if action == "orbit":
        return _orbit_payload(options)
    raise ValueError(f"Hénon Map 不支持的动作：{action}")


def _cli(raw_args) -> int:
    args = CliArgs(raw_args, CLI_OPTIONS)
    options = options_from_ui({
        "a": args.a, "b": args.b, "x0": args.henon_x0, "y0": args.henon_y0,
        "iterations": args.henon_iterations, "discard": args.henon_discard,
    })
    result = _orbit_payload(options)
    values = result["records"]
    print("=" * 78)
    title = "Hénon Map 时间轨道" if args.orbit else "Hénon Map 相图"
    print(f"{title} | a = {result['a']:.4f} | b = {result['b']:.4f} | "
          f"丢弃 {result['discard']} 步后采样 {result['iterations']} 步")
    print("=" * 78)
    if result["stoppedStep"] is not None:
        print(f"轨道在第 {result['stoppedStep']} 步超出计算范围，已停止。请调整参数或恢复 a=1.4、b=0.3、初值 (0, 0)。")
        return 0
    print(f"x 范围 [{min(row['x'] for row in values):.6f}, {max(row['x'] for row in values):.6f}]，"
          f"y 范围 [{min(row['y'] for row in values):.6f}, {max(row['y'] for row in values):.6f}]")
    print(f"最大 Lyapunov 指数估计 {result['lyapunovText']}，耗时 {result['elapsedMs']:.1f} ms")
    if args.orbit:
        print("末 12 步（n, x, y）：")
        for row in values[-12:]:
            print(f"{row['step']:>6}  {row['x']: .6f}  {row['y']: .6f}")
    print("提示：指数为有限步估计，正值提示对初值敏感；相图的每个点代表一次迭代状态。")
    return 0


def build_spec() -> ModelSpec:
    return ModelSpec(
        key="henon_map",
        name="Hénon Map 模型",
        topic="确定性与混沌",
        summary="二维递推 xₙ₊₁=1−a·xₙ²+yₙ、yₙ₊₁=b·xₙ，观察经典混沌吸引子。",
        description=(
            "Hénon Map 是研究二维离散动力系统的经典模型。每一步先用 x 的平方产生非线性，"
            "再把上一轮的 x 反馈到 y。经典参数 a=1.4、b=0.3 会把许多不同初值吸引到一个"
            "折叠带状的混沌吸引子上；吸引域外的初值可能发散。\n\n"
            "「查看相图」把丢弃瞬态后的 (xₙ, yₙ) 画在相平面；「查看时间轨道」显示最后"
            "至多 80 个连续状态，x 与 y 用两种颜色区分。最大 Lyapunov 指数按完整采样估计，"
            "正值提示相近初值会快速分离。"
        ),
        params=PARAMS,
        actions=ACTIONS,
        view="henon_map",
        accent="#0891b2",
        icon="◈",
        handler=handle,
        cli=_cli,
        cli_options=CLI_OPTIONS,
        factory=build_henon,
        highlights=("二维状态与相平面吸引子", "一键对比稳定点与混沌", "最大 Lyapunov 指数估计"),
        order=30,
    )
