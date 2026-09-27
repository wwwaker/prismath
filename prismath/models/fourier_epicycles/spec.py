# -*- coding: utf-8 -*-
"""Fourier Epicycles 的参数、动作、JSON payload 与 CLI。"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np

from ...spec import ActionSpec, CliArgs, CliOption, ModelSpec, ParamSpec
from .model import (
    DEFAULT_FRAMES,
    DEFAULT_SAMPLES,
    DEFAULT_SHAPE,
    DEFAULT_TERMS,
    MAX_FRAMES,
    MAX_SAMPLES,
    MAX_TERMS,
    MIN_FRAMES,
    MIN_SAMPLES,
    MIN_TERMS,
    SHAPE_LABELS,
    FourierEpicycle,
    analyze_points,
)

__all__ = ["PARAMS", "ACTIONS", "CLI_OPTIONS", "options_from_ui", "build_fourier",
           "payload_for_points", "handle", "build_spec"]

PARAMS = (
    ParamSpec(
        key="shape", label="曲线形状", kind="choice", default=DEFAULT_SHAPE,
        choices=tuple(SHAPE_LABELS), group="轮廓",
        hint="选择内置曲线，或选择“图片轮廓”从图片提取外轮廓。",
    ),
    ParamSpec(
        key="image_path", label="图片路径", kind="str", default="", group="轮廓",
        hint="选择“图片轮廓”后生效；Tk 界面可点下方按钮选择 PNG/JPG。",
    ),
    ParamSpec(
        key="samples", label="轮廓采样点", kind="int", default=DEFAULT_SAMPLES,
        min=MIN_SAMPLES, max=MAX_SAMPLES, step=64, group="分析",
        hint="采样越密，原始轮廓越准确，但计算与载荷越大。",
    ),
    ParamSpec(
        key="terms", label="旋转向量数", kind="int", default=DEFAULT_TERMS,
        min=MIN_TERMS, max=MAX_TERMS, step=2, group="分析",
        hint="圆越多细节越丰富；少量低频向量更适合看清原理。",
    ),
    ParamSpec(
        key="frames", label="动画帧数", kind="int", default=DEFAULT_FRAMES,
        min=MIN_FRAMES, max=MAX_FRAMES, step=30, group="动画",
        hint="一圈轨迹的动画采样帧数，最多 36000；它影响播放细腻度，轮廓精度主要由旋转向量数和轮廓采样点决定。",
    ),
)

ACTIONS = (
    ActionSpec("draw", "绘制旋转矢量", mode="once", kind="primary",
               hint="显示嵌套圆、向量链、目标轮廓和画笔轨迹"),
    ActionSpec("replay", "重新播放轨迹", mode="once", kind="default",
               hint="从头播放末端画笔的运动轨迹"),
)

CLI_OPTIONS = (
    CliOption(("--epicycle-shape",), kind="choice", default=DEFAULT_SHAPE,
              choices=tuple(SHAPE_LABELS), help="内置曲线形状"),
    CliOption(("--epicycle-image",), kind="str", default="",
              help="图片轮廓的 PNG/JPG 路径（配合 --epicycle-shape image）"),
    CliOption(("--epicycle-samples",), kind="int", default=DEFAULT_SAMPLES,
              help=f"轮廓采样点，默认 {DEFAULT_SAMPLES}"),
    CliOption(("--epicycle-terms",), kind="int", default=DEFAULT_TERMS,
              help=f"旋转向量数，默认 {DEFAULT_TERMS}"),
    CliOption(("--epicycle-frames",), kind="int", default=DEFAULT_FRAMES,
              help=f"动画帧数，默认 {DEFAULT_FRAMES}"),
    CliOption(("--epicycle-replay",), kind="flag", help="终端输出旋转向量摘要"),
)


def options_from_ui(params: Dict[str, Any]) -> Dict[str, Any]:
    shape = str(params.get("shape", DEFAULT_SHAPE)).strip().lower()
    if shape not in SHAPE_LABELS:
        shape = DEFAULT_SHAPE
    try:
        samples = int(round(float(params.get("samples", DEFAULT_SAMPLES))))
    except (TypeError, ValueError, OverflowError):
        samples = DEFAULT_SAMPLES
    samples = max(MIN_SAMPLES, min(MAX_SAMPLES, samples))
    try:
        terms = int(round(float(params.get("terms", DEFAULT_TERMS))))
    except (TypeError, ValueError, OverflowError):
        terms = DEFAULT_TERMS
    terms = max(MIN_TERMS, min(min(MAX_TERMS, samples), terms))
    try:
        frames = int(round(float(params.get("frames", DEFAULT_FRAMES))))
    except (TypeError, ValueError, OverflowError):
        frames = DEFAULT_FRAMES
    frames = max(MIN_FRAMES, min(MAX_FRAMES, frames))
    image_path = str(params.get("image_path", "") or "").strip()
    return {"shape": shape, "image_path": image_path, "samples": samples,
            "terms": terms, "frames": frames}


def build_fourier(params: Dict[str, Any]) -> FourierEpicycle:
    return FourierEpicycle(**options_from_ui(params))


def _payload(options: Dict[str, Any], points: Any = None) -> Dict[str, Any]:
    normalized = options_from_ui(options)
    if points is None:
        result = build_fourier(normalized).analyze()
    else:
        result = analyze_points(points, normalized["terms"], normalized["frames"], "manual")
    shape_label = SHAPE_LABELS.get(result.shape, "手绘轮廓")
    return {
        "view": "fourier-epicycle",
        "shape": result.shape,
        "shapeLabel": shape_label,
        "imagePath": normalized.get("image_path", ""),
        "samples": result.samples,
        "terms": result.terms,
        "frames": result.frames,
        "rmse": result.rmse,
        "elapsedMs": result.elapsed * 1000.0,
        "harmonics": result.harmonics(),
        "target": [[float(value.real), float(value.imag)] for value in result.source],
        "trajectory": [[float(value.real), float(value.imag)] for value in result.trajectory],
        "records": result.records(),
        "radiusSum": float(np.sum(np.abs(result.coefficients))),
    }


def payload_for_points(points: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """把手绘或外部点列转换成与普通动作完全相同的 JSON payload。"""
    return _payload(options_from_ui(params), points)


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    if action not in {"draw", "replay"}:
        raise ValueError(f"Fourier Epicycles 不支持的动作：{action}")
    return _payload(options_from_ui(params), payload.get("customPoints") if payload else None)


def _cli(raw_args) -> int:
    args = CliArgs(raw_args, CLI_OPTIONS)
    result = _payload(options_from_ui({
        "shape": args.epicycle_shape, "samples": args.epicycle_samples,
        "terms": args.epicycle_terms, "frames": args.epicycle_frames,
        "image_path": args.epicycle_image,
    }))
    print("=" * 78)
    print(f"Fourier Epicycles | {result['shapeLabel']} | "
          f"{result['terms']} 个旋转向量 / {result['samples']} 个采样点")
    print("=" * 78)
    print(f"截断均方根误差 {result['rmse']:.6f}，动画 {result['frames']} 帧，耗时 {result['elapsedMs']:.1f} ms")
    print("频率顺序：" + ", ".join(str(item["frequency"]) for item in result["harmonics"][:12]))
    print("提示：每个系数对应一个旋转圆；圆心从上一个向量末端开始，最后一个端点就是画笔。")
    return 0


def build_spec() -> ModelSpec:
    return ModelSpec(
        key="fourier_epicycles",
        name="Fourier Epicycles 模型",
        topic="信号与几何",
        summary="把轮廓分解成一串不同频率的旋转向量，用末端轨迹重新绘制图形。",
        description=(
            "傅里叶旋转矢量把二维轮廓 x+iy 看成复数信号。离散傅里叶变换得到的每个系数"
            "对应一个旋转圆：模长决定半径，辐角决定初始相位，频率决定旋转速度和方向。"
            "多个向量首尾相接时，最后一个端点随时间移动，便能用一支“旋转画笔”画出原始轮廓。"
        ),
        params=PARAMS,
        actions=ACTIONS,
        view="fourier_epicycles",
        accent="#db2777",
        icon="◎",
        handler=handle,
        cli=_cli,
        cli_options=CLI_OPTIONS,
        factory=build_fourier,
        highlights=("离散傅里叶变换", "嵌套圆与旋转向量", "末端轨迹重绘轮廓"),
        order=10,
    )
