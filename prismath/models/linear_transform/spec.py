# -*- coding: utf-8 -*-
"""线性变换实验室的参数、动作与 JSON 适配。"""

from __future__ import annotations

from typing import Any, Dict

from ...spec import ActionSpec, ModelSpec, ParamSpec
from .model import (DEFAULT_ANGLE, DEFAULT_EXTENT, DEFAULT_MODE, DEFAULT_SCALE_X,
                    DEFAULT_SCALE_Y, DEFAULT_SHEAR, DEFAULT_VECTOR_X, DEFAULT_VECTOR_Y,
                    MODE_LABELS, MODES, LinearTransform)

PARAMS = (
    ParamSpec("mode", "变换预设", kind="choice", default=DEFAULT_MODE,
              choices=MODES, group="变换", hint="单位、旋转、缩放、剪切和镜像会直接改变网格与基向量。"),
    ParamSpec("angle", "旋转角度", kind="float", default=DEFAULT_ANGLE,
              min=-180.0, max=180.0, step=1.0, group="变换"),
    ParamSpec("scale_x", "横向缩放", kind="float", default=DEFAULT_SCALE_X,
              min=0.1, max=4.0, step=0.05, group="变换"),
    ParamSpec("scale_y", "纵向缩放", kind="float", default=DEFAULT_SCALE_Y,
              min=0.1, max=4.0, step=0.05, group="变换"),
    ParamSpec("shear", "剪切系数", kind="float", default=DEFAULT_SHEAR,
              min=-3.0, max=3.0, step=0.05, group="变换"),
    ParamSpec("vector_x", "向量 x", kind="float", default=DEFAULT_VECTOR_X,
              min=-4.0, max=4.0, step=0.05, group="拖动向量"),
    ParamSpec("vector_y", "向量 y", kind="float", default=DEFAULT_VECTOR_Y,
              min=-4.0, max=4.0, step=0.05, group="拖动向量"),
    ParamSpec("extent", "网格范围", kind="float", default=DEFAULT_EXTENT,
              min=1.0, max=6.0, step=0.5, group="显示"),
)
ACTIONS = (
    ActionSpec("apply", "应用变换", kind="primary", hint="显示网格、基向量、行列式和面积缩放。"),
    ActionSpec("reset_vector", "重置向量", hint="把可拖动向量恢复为 (1.25, 0.65)。"),
)


def options_from_ui(params: Dict[str, Any]) -> Dict[str, Any]:
    return {p.key: params.get(p.key, p.default) for p in PARAMS}


def _payload(options: Dict[str, Any]) -> Dict[str, Any]:
    result = LinearTransform(**options).transform()
    matrix = result.matrix
    return {
        "view": "linear-transform",
        "mode": result.mode,
        "modeLabel": MODE_LABELS[result.mode],
        "matrix": matrix.tolist(),
        "vector": result.vector.tolist(),
        "transformedVector": result.transformed_vector.tolist(),
        "determinant": result.determinant,
        "areaScale": result.area_scale,
        "orientation": result.orientation,
        "extent": float(options.get("extent", 3.0)),
        "grid": result.grid,
        "elapsedMs": result.elapsed * 1000.0,
    }


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    options = options_from_ui(params)
    if action == "reset_vector":
        options["vector_x"], options["vector_y"] = DEFAULT_VECTOR_X, DEFAULT_VECTOR_Y
    if action in ("apply", "reset_vector"):
        return _payload(options)
    raise ValueError(f"线性变换实验室不支持的动作：{action}")


def build_spec() -> ModelSpec:
    return ModelSpec(
        key="linear_transform", name="线性变换实验室", topic="课堂与直觉", order=10,
        summary="拖动一个向量，观察矩阵如何同时改变方向、长度和面积。",
        description=("这是一块 3Blue1Brown 风格的线性代数实验板。灰色网格是原坐标系，"
                     "彩色网格是变换后的坐标系；箭头 i、j 是基向量，粉色箭头是你正在拖动的向量。"
                     "行列式的绝对值是面积缩放倍数，负号表示方向翻转。"),
        params=PARAMS, actions=ACTIONS, view="linear_transform", accent="#7c3aed", icon="↗",
        handler=handle, factory=lambda params: LinearTransform(**options_from_ui(params)),
        highlights=("网格与基向量同步变形", "可拖动向量即时更新坐标", "行列式连接面积与方向"),
    )
