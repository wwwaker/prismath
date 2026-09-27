# -*- coding: utf-8 -*-
"""梯度下降实验室的参数与 payload。"""

from __future__ import annotations

from typing import Any, Dict

from ...spec import ActionSpec, ModelSpec, ParamSpec
from .model import (DEFAULT_FUNCTION, DEFAULT_ITERATIONS, DEFAULT_RATE, DEFAULT_START,
                    FUNCTIONS, FUNCTION_LABELS, GradientDescent)

FUNCTION_CHOICES = {FUNCTION_LABELS[key]: key for key in FUNCTIONS}

PARAMS = (
    ParamSpec("function", "函数预设", kind="choice", default=FUNCTION_LABELS[DEFAULT_FUNCTION],
              choices=tuple(FUNCTION_CHOICES), group="函数",
              hint="除了简单抛物线，还可以试试波纹、多势阱、高阶多项式和光滑绝对值函数。"),
    ParamSpec("start", "初始位置 x₀", kind="float", default=DEFAULT_START,
              min=-4.0, max=4.0, step=0.1, group="下降过程"),
    ParamSpec("rate", "学习率", kind="float", default=DEFAULT_RATE,
              min=0.001, max=1.0, step=0.005, group="下降过程",
              hint="太小会走得慢；太大可能跨过谷底并震荡。"),
    ParamSpec("iterations", "迭代次数", kind="int", default=DEFAULT_ITERATIONS,
              min=1, max=500, step=5, group="下降过程"),
)
ACTIONS = (ActionSpec("run", "开始下降", kind="primary", hint="播放每一步 x ← x − 学习率 × 梯度。"),)


def options_from_ui(params: Dict[str, Any]) -> Dict[str, Any]:
    options = {p.key: params.get(p.key, p.default) for p in PARAMS}
    function = options.get("function", FUNCTION_LABELS[DEFAULT_FUNCTION])
    options["function"] = FUNCTION_CHOICES.get(str(function), str(function))
    return options


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    if action != "run":
        raise ValueError(f"梯度下降实验室不支持的动作：{action}")
    result = GradientDescent(**options_from_ui(params)).run()
    return {
        "view": "gradient-descent", "function": result.function,
        "functionLabel": FUNCTION_LABELS[result.function], "start": result.start,
        "rate": result.rate, "iterations": result.iterations, "records": result.records,
        "curve": result.curve, "minimumX": result.minimum_x, "finalX": result.final_x,
        "finalValue": result.final_value, "converged": result.converged,
        "elapsedMs": result.elapsed * 1000.0,
    }


def build_spec() -> ModelSpec:
    return ModelSpec(
        key="gradient_descent", name="梯度下降实验室", topic="课堂与直觉", order=30,
        summary="把导数变成一步一步的下坡路线，直观看见学习率如何决定收敛。",
        description=("蓝色曲线是函数，橙色点是每一次迭代。每一步沿负梯度方向移动；"
                     "学习率太小会磨蹭，太大则可能越过谷底甚至发散。双势阱还能展示初始位置决定落入哪个谷底。"),
        params=PARAMS, actions=ACTIONS, view="gradient_descent", accent="#2563eb", icon="∇",
        handler=handle, factory=lambda params: GradientDescent(**options_from_ui(params)),
        highlights=("逐步显示函数最小值搜索", "学习率对收敛的影响", "波纹函数与多势阱展示局部最小值"),
    )
