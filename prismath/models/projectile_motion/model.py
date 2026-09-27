# -*- coding: utf-8 -*-
"""抛体运动（理想模型与线性阻力）的数值内核。"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, List

import numpy as np

DEFAULT_SPEED = 18.0
DEFAULT_ANGLE = 48.0
DEFAULT_HEIGHT = 2.0
DEFAULT_GRAVITY = 9.81
DEFAULT_DRAG = 0.08
DEFAULT_STEPS = 180


def _number(value, low, high, fallback):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(value):
        return fallback
    return max(low, min(high, value))


@dataclass(frozen=True)
class ProjectileResult:
    records: List[Dict[str, float]]
    ideal_records: List[Dict[str, float]]
    speed: float
    angle: float
    height: float
    gravity: float
    drag: float
    flight_time: float
    range: float
    max_height: float
    impact_speed: float
    ideal_range: float
    ideal_flight_time: float
    elapsed: float


class ProjectileMotion:
    def __init__(self, speed: float = DEFAULT_SPEED, angle: float = DEFAULT_ANGLE,
                 height: float = DEFAULT_HEIGHT, gravity: float = DEFAULT_GRAVITY,
                 drag: float = DEFAULT_DRAG, steps: int = DEFAULT_STEPS) -> None:
        self.speed = _number(speed, 1.0, 100.0, DEFAULT_SPEED)
        self.angle = _number(angle, 1.0, 89.0, DEFAULT_ANGLE)
        self.height = _number(height, 0.0, 50.0, DEFAULT_HEIGHT)
        self.gravity = _number(gravity, 0.1, 30.0, DEFAULT_GRAVITY)
        self.drag = _number(drag, 0.0, 1.0, DEFAULT_DRAG)
        try:
            self.steps = max(30, min(2000, int(float(steps))))
        except (TypeError, ValueError):
            self.steps = DEFAULT_STEPS

    def simulate(self) -> ProjectileResult:
        started = time.perf_counter()
        theta = math.radians(self.angle)
        vx0, vy0 = self.speed * math.cos(theta), self.speed * math.sin(theta)
        disc = vy0 * vy0 + 2.0 * self.gravity * self.height
        ideal_flight = (vy0 + math.sqrt(max(disc, 0.0))) / self.gravity
        # 空阻轨迹通常落得更早，给数值积分留一点余量。
        horizon = ideal_flight * (1.25 if self.drag > 0 else 1.0)
        dt = horizon / self.steps
        ideal: List[Dict[str, float]] = []
        actual: List[Dict[str, float]] = []
        x = 0.0
        y = self.height
        vx, vy = vx0, vy0
        max_height = y
        impact_speed = self.speed
        landed = False
        impact_time = ideal_flight
        impact_x = 0.0
        for index in range(self.steps + 1):
            t = index * dt
            ideal_y = self.height + vy0 * t - 0.5 * self.gravity * t * t
            ideal.append({"step": index, "t": t, "x": vx0 * t, "y": max(0.0, ideal_y)})
            actual.append({"step": index, "t": t, "x": x, "y": max(0.0, y), "ideal_y": max(0.0, ideal_y)})
            if landed:
                continue
            if index > 0 and y <= 0.0:
                landed = True
                impact_speed = math.hypot(vx, vy)
                impact_time, impact_x = t, x
                continue
            ax, ay = -self.drag * vx, -self.gravity - self.drag * vy
            # 半隐式 Euler：先更新速度，再更新位置，落体时比显式 Euler 稳定。
            vx += ax * dt
            vy += ay * dt
            x += vx * dt
            y += vy * dt
            max_height = max(max_height, y)
            if y <= 0.0:
                y = 0.0
                if not landed:
                    landed = True
                    impact_speed = math.hypot(vx, vy)
                    impact_time, impact_x = t, x
        if not landed:
            impact_speed = math.hypot(vx, vy)
        flight_time = float(impact_time)
        distance = float(impact_x)
        if self.height == 0.0 and distance == 0.0:
            flight_time, distance = 0.0, 0.0
        return ProjectileResult(
            records=actual, ideal_records=ideal, speed=self.speed, angle=self.angle,
            height=self.height, gravity=self.gravity, drag=self.drag,
            flight_time=flight_time, range=distance, max_height=max_height,
            impact_speed=impact_speed, ideal_range=vx0 * ideal_flight,
            ideal_flight_time=ideal_flight, elapsed=time.perf_counter() - started,
        )
