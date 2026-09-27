# -*- coding: utf-8 -*-
"""三个可以互相联系的概率实验：LLN、CLT 与 Galton board。"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

DEFAULT_EXPERIMENT = "lln"
DEFAULT_DISTRIBUTION = "die"
DEFAULT_TRIALS = 2400
DEFAULT_SAMPLE_SIZE = 30
DEFAULT_ROWS = 10
DEFAULT_BALLS = 900
DEFAULT_BINS = 31
# 桌面首次运行默认使用新的随机源；需要复现实验时再手动填入非负整数。
DEFAULT_SEED = -1
EXPERIMENTS = ("lln", "clt", "galton")
EXPERIMENT_LABELS = {"lln": "大数定理", "clt": "中心极限定理", "galton": "高尔顿钉板"}
DISTRIBUTIONS = ("coin", "die", "uniform", "normal")
DISTRIBUTION_LABELS = {"coin": "抛硬币（0/1）", "die": "掷骰子（1~6）",
                       "uniform": "均匀分布（0~1）", "normal": "标准正态分布"}


def _number(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return fallback
    return fallback if not math.isfinite(value) else max(low, min(high, value))


def _integer(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        return max(low, min(high, int(float(value))))
    except (TypeError, ValueError):
        return fallback


def distribution_info(name: str) -> Tuple[float, float, str]:
    key = str(name).strip().lower()
    if key == "coin":
        return 0.5, 0.5, DISTRIBUTION_LABELS["coin"]
    if key == "uniform":
        return 0.5, math.sqrt(1.0 / 12.0), DISTRIBUTION_LABELS["uniform"]
    if key == "normal":
        return 0.0, 1.0, DISTRIBUTION_LABELS["normal"]
    return 3.5, math.sqrt(35.0 / 12.0), DISTRIBUTION_LABELS["die"]


def _sample(rng: np.random.Generator, name: str, shape: Any) -> np.ndarray:
    key = str(name).strip().lower()
    if key == "coin":
        return rng.integers(0, 2, size=shape).astype(float)
    if key == "uniform":
        return rng.random(shape)
    if key == "normal":
        return rng.normal(0.0, 1.0, size=shape)
    return rng.integers(1, 7, size=shape).astype(float)


@dataclass(frozen=True)
class ProbabilityResult:
    experiment: str
    distribution: str
    target_mean: float
    target_std: float
    payload: Dict[str, Any]
    elapsed: float


class ProbabilityLab:
    """概率实验对象；计算全部使用 NumPy，绘图层只消费 payload。"""

    def __init__(self, experiment: str = DEFAULT_EXPERIMENT,
                 distribution: str = DEFAULT_DISTRIBUTION,
                 trials: int = DEFAULT_TRIALS,
                 sample_size: int = DEFAULT_SAMPLE_SIZE,
                 rows: int = DEFAULT_ROWS,
                 balls: int = DEFAULT_BALLS,
                 bins: int = DEFAULT_BINS,
                 seed: int = DEFAULT_SEED) -> None:
        self.experiment = str(experiment).strip().lower()
        if self.experiment not in EXPERIMENTS:
            self.experiment = DEFAULT_EXPERIMENT
        self.distribution = str(distribution).strip().lower()
        if self.distribution not in DISTRIBUTIONS:
            self.distribution = DEFAULT_DISTRIBUTION
        self.trials = _integer(trials, 30, 12000, DEFAULT_TRIALS)
        self.sample_size = _integer(sample_size, 2, 300, DEFAULT_SAMPLE_SIZE)
        self.rows = _integer(rows, 4, 16, DEFAULT_ROWS)
        self.balls = _integer(balls, 40, 5000, DEFAULT_BALLS)
        self.bins = _integer(bins, 11, 61, DEFAULT_BINS)
        try:
            seed_value = int(float(seed))
        except (TypeError, ValueError):
            seed_value = DEFAULT_SEED
        self.seed: Optional[int] = None if seed_value < 0 else seed_value
        self.target_mean, self.target_std, self.distribution_label = distribution_info(self.distribution)

    def run(self) -> ProbabilityResult:
        started = time.perf_counter()
        rng = np.random.default_rng(self.seed)
        if self.experiment == "clt":
            payload = self._clt(rng)
        elif self.experiment == "galton":
            payload = self._galton(rng)
        else:
            payload = self._lln(rng)
        payload.update({
            "experiment": self.experiment,
            "experimentLabel": EXPERIMENT_LABELS[self.experiment],
            "distribution": self.distribution,
            "distributionLabel": self.distribution_label,
            "targetMean": self.target_mean,
            "targetStd": self.target_std,
        })
        return ProbabilityResult(self.experiment, self.distribution, self.target_mean,
                                 self.target_std, payload, time.perf_counter() - started)

    def _lln(self, rng: np.random.Generator) -> Dict[str, Any]:
        values = _sample(rng, self.distribution, self.trials)
        running = np.cumsum(values) / np.arange(1, self.trials + 1, dtype=float)
        records = [{"step": i + 1, "value": float(running[i]),
                    "target": self.target_mean,
                    "deviation": float(running[i] - self.target_mean)}
                   for i in range(self.trials)]
        return {
            "view": "probability-lln", "records": records,
            "sampleCount": self.trials, "observed": float(running[-1]),
            "absError": float(abs(running[-1] - self.target_mean)),
            "standardError": float(self.target_std / math.sqrt(self.trials)),
        }

    def _clt(self, rng: np.random.Generator) -> Dict[str, Any]:
        sample_means = np.mean(_sample(rng, self.distribution,
                                       (self.trials, self.sample_size)), axis=1)
        standard_error = self.target_std / math.sqrt(self.sample_size)
        center = self.target_mean
        spread = max(4.0 * standard_error, float(np.std(sample_means)) * 1.25, 0.1)
        edges = np.linspace(center - spread, center + spread, self.bins + 1)
        counts, _ = np.histogram(sample_means, bins=edges)
        centers = (edges[:-1] + edges[1:]) / 2.0
        normal = np.exp(-0.5 * ((centers - center) / max(standard_error, 1e-9)) ** 2)
        normal = normal / max(float(normal.max()), 1e-9) * max(int(counts.max()), 1)
        return {
            "view": "probability-clt", "sampleCount": self.trials,
            "sampleSize": self.sample_size, "sampleMeans": sample_means.tolist(),
            "edges": edges.tolist(), "centers": centers.tolist(),
            "counts": counts.astype(int).tolist(), "normal": normal.tolist(),
            "observed": float(np.mean(sample_means)),
            "absError": float(abs(np.mean(sample_means) - center)),
            "standardError": float(standard_error),
        }

    def _galton(self, rng: np.random.Generator) -> Dict[str, Any]:
        choices = rng.integers(0, 2, size=(self.balls, self.rows), dtype=np.int8)
        final_bins = np.sum(choices, axis=1).astype(int)
        counts = np.bincount(final_bins, minlength=self.rows + 1)
        expected = np.asarray([
            self.balls * math.comb(self.rows, index) / (2.0 ** self.rows)
            for index in range(self.rows + 1)
        ], dtype=float)
        # 路径字符串很轻（每球最多 16 个字符），保留全部路径让动画在最后一颗球
        # 仍然能显示“当前小球”；视图只会绘制最近几条，不会把它们全部堆在画布上。
        paths = ["".join("R" if bit else "L" for bit in row) for row in choices]
        return {
            "view": "probability-galton", "sampleCount": self.balls,
            "rows": self.rows, "balls": self.balls,
            "finalBins": final_bins.tolist(), "counts": counts.tolist(),
            "expectedCounts": expected.tolist(),
            "labels": [str(i) for i in range(self.rows + 1)], "paths": paths,
            "observed": float(np.mean(final_bins)),
            "absError": float(abs(np.mean(final_bins) - self.rows / 2.0)),
            "standardError": float(math.sqrt(self.rows / 4.0 / self.balls)),
            "targetMean": self.rows / 2.0,
        }
