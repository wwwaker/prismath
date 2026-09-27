# -*- coding: utf-8 -*-
"""抛体运动实验室的参数与 payload。"""

from __future__ import annotations

from typing import Any, Dict

from ...spec import ActionSpec, ModelSpec, ParamSpec
from .model import (DEFAULT_ANGLE, DEFAULT_DRAG, DEFAULT_GRAVITY, DEFAULT_HEIGHT,
                    DEFAULT_SPEED, DEFAULT_STEPS, ProjectileMotion)

PARAMS = (
    ParamSpec("speed", "初速度", kind="float", default=DEFAULT_SPEED, min=1.0, max=100.0, step=0.5, group="发射"),
    ParamSpec("angle", "发射角度", kind="float", default=DEFAULT_ANGLE, min=1.0, max=89.0, step=1.0, group="发射"),
    ParamSpec("height", "初始高度", kind="float", default=DEFAULT_HEIGHT, min=0.0, max=50.0, step=0.5, group="发射"),
    ParamSpec("gravity", "重力加速度", kind="float", default=DEFAULT_GRAVITY, min=0.1, max=30.0, step=0.1, group="环境"),
    ParamSpec("drag", "空气阻力系数", kind="float", default=DEFAULT_DRAG, min=0.0, max=1.0, step=0.01, group="环境",
              hint="0 是理想抛体；增大后会看到轨迹变矮、落点变近。"),
    ParamSpec("steps", "模拟步数", kind="int", default=DEFAULT_STEPS, min=30, max=2000, step=10, group="精度"),
)
ACTIONS = (ActionSpec("simulate", "发射！", kind="primary", hint="播放轨迹并比较理想模型与空气阻力模型。"),)


def options_from_ui(params: Dict[str, Any]) -> Dict[str, Any]:
    return {p.key: params.get(p.key, p.default) for p in PARAMS}


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    if action != "simulate":
        raise ValueError(f"抛体运动实验室不支持的动作：{action}")
    result = ProjectileMotion(**options_from_ui(params)).simulate()
    return {
        "view": "projectile-motion", "records": result.records,
        "idealRecords": result.ideal_records, "speed": result.speed,
        "angle": result.angle, "height": result.height, "gravity": result.gravity,
        "drag": result.drag, "flightTime": result.flight_time, "range": result.range,
        "maxHeight": result.max_height, "impactSpeed": result.impact_speed,
        "idealRange": result.ideal_range, "idealFlightTime": result.ideal_flight_time,
        "elapsedMs": result.elapsed * 1000.0,
    }


def build_spec() -> ModelSpec:
    return ModelSpec(
        key="projectile_motion", name="抛体运动实验室", topic="课堂与直觉", order=20,
        summary="改变角度、初速度和空气阻力，像做一次物理实验一样观察轨迹。",
        description=("粉色曲线是带空气阻力的数值轨迹，灰色虚线是同样初始条件下的理想抛体。"
                     "调角度可以寻找远射角，调阻力可以看到理想公式何时失效。"),
        params=PARAMS, actions=ACTIONS, view="projectile_motion", accent="#ea580c", icon="↗",
        handler=handle, factory=lambda params: ProjectileMotion(**options_from_ui(params)),
        highlights=("轨迹动画与最高点标记", "理想模型 / 空阻模型叠加", "直接观察角度与射程关系"),
    )
