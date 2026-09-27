# -*- coding: utf-8 -*-
"""概率实验室的参数、动作与模型适配。"""

from __future__ import annotations

from typing import Any, Dict

from ...spec import ActionSpec, ModelSpec, ParamSpec
from .model import (DEFAULT_BALLS, DEFAULT_BINS, DEFAULT_DISTRIBUTION,
                    DEFAULT_EXPERIMENT, DEFAULT_ROWS, DEFAULT_SAMPLE_SIZE,
                    DEFAULT_SEED, DEFAULT_TRIALS, DISTRIBUTIONS, EXPERIMENTS,
                    ProbabilityLab)

EXPERIMENT_CHOICES = {"大数定理": "lln", "中心极限定理": "clt", "高尔顿钉板": "galton"}
DISTRIBUTION_CHOICES = {"抛硬币（0/1）": "coin", "掷骰子（1~6）": "die",
                        "均匀分布（0~1）": "uniform", "标准正态分布": "normal"}

PARAMS = (
    ParamSpec("experiment", "实验主题", kind="choice", default="大数定理",
              choices=tuple(EXPERIMENT_CHOICES), group="实验", hint="大数定理看平均值收敛；中心极限定理看均值分布；钉板看二项分布如何出现。"),
    ParamSpec("distribution", "随机变量", kind="choice", default="掷骰子（1~6）",
              choices=tuple(DISTRIBUTION_CHOICES), group="实验", hint="大数定理和中心极限定理使用这里选择的分布。"),
    ParamSpec("trials", "实验次数 / 样本数", kind="int", default=DEFAULT_TRIALS,
              min=30, max=12000, step=100, group="采样"),
    ParamSpec("sample_size", "每个均值的样本数", kind="int", default=DEFAULT_SAMPLE_SIZE,
              min=2, max=300, step=1, group="采样", hint="只对中心极限定理生效；增大它会让均值分布更窄。"),
    ParamSpec("rows", "钉板层数", kind="int", default=DEFAULT_ROWS,
              min=4, max=16, step=1, group="钉板", hint="每个小球经过一层就随机向左或向右。"),
    ParamSpec("balls", "钉板小球数", kind="int", default=DEFAULT_BALLS,
              min=40, max=5000, step=100, group="钉板"),
    ParamSpec("bins", "直方图分箱数", kind="int", default=DEFAULT_BINS,
              min=11, max=61, step=2, group="显示"),
    ParamSpec("seed", "随机种子（-1 表示随机）", kind="int", default=DEFAULT_SEED,
              min=-1, max=2147483647, step=1, group="随机性"),
)
ACTIONS = (ActionSpec("run", "开始实验", kind="primary", hint="按当前主题和采样设置生成一次可重复的实验。"),)


def options_from_ui(params: Dict[str, Any]) -> Dict[str, Any]:
    options = {p.key: params.get(p.key, p.default) for p in PARAMS}
    options["experiment"] = EXPERIMENT_CHOICES.get(str(options["experiment"]), str(options["experiment"]))
    options["distribution"] = DISTRIBUTION_CHOICES.get(str(options["distribution"]), str(options["distribution"]))
    return options


def handle(action: str, params: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    if action != "run":
        raise ValueError(f"概率实验室不支持的动作：{action}")
    result = ProbabilityLab(**options_from_ui(params)).run()
    out = dict(result.payload)
    out["elapsedMs"] = result.elapsed * 1000.0
    return out


def build_spec() -> ModelSpec:
    return ModelSpec(
        key="probability_lab", name="概率实验室", topic="概率与统计", order=10,
        summary="把大数定理、中心极限定理和高尔顿钉板放进一组可调参数的随机实验。",
        description=("先用大数定理观察样本平均值靠近理论均值，再用中心极限定理观察“均值的均值”"
                     "逐渐呈钟形，最后把硬币的左右选择堆成高尔顿钉板，看到二项分布从碰撞中长出来。"),
        params=PARAMS, actions=ACTIONS, view="probability_lab", accent="#0f766e", icon="∑",
        handler=handle, factory=lambda params: ProbabilityLab(**options_from_ui(params)),
        highlights=("大数定理的收敛曲线", "中心极限定理的钟形直方图", "高尔顿钉板的二项分布"),
    )
