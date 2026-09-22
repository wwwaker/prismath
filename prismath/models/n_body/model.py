# -*- coding: utf-8 -*-
"""
万有引力多星（N 体）模型核心
=============================
``N`` 颗星体两两之间只有万有引力：

    F_ij = G m_i m_j (r_j − r_i) / (|r_j − r_i|² + ε²)^{3/2}

每颗星按牛顿第二定律加速，**没有别的力、没有中央控制、没有人为脚本**。于是：

* ``N = 2`` 时它是开普勒问题，轨迹是精确的圆锥曲线（椭圆 / 圆 / 抛物线 / 双曲线）；
* ``N = 3`` 时它已经可以混沌 —— 著名的"三体问题"没有一般解析解；
* 再多几颗，同一个初值只要抖动最后一位小数，几百年后的轨道就完全不同（对初值的敏感依赖）。

本模型要展示的正是这条链子：**同一条确定性规则（``F = Gm m/r²``）既能给出钟表般精确的
周期轨道，也能给出不可长期预测的混沌**。

单位制
------
用**自然单位**：``G = 1``，质量 / 长度 / 时间都不带物理单位。几何形状、轨道周期与
守恒量都是无量纲的，换成真实的千克 / 米 / 秒只需等比缩放，结论不变。

场景（初值库）
--------------
* ``figure_eight``：8 字三体 —— Chenciner & Montgomery 的**精确周期解**，三个等质量星体
  沿同一条"8"字曲线首尾相接，周期 ``T = 6.32591398``。它是本模型最好的精度标尺：
  积分一个周期后应当回到出发点；
* ``binary``：双星 + 一颗远处的行星（层级三体）——双星自身快速绕转，行星在外圈慢慢画波浪；
* ``solar``："太阳 + 四颗行星"的圆形轨道近似 —— 半径不同则周期不同（开普勒第三定律），
  轨迹上叠出一圈圈同心轨道；
* ``cluster``：随机星团 —— 位置与速度都随机，**混沌**：星体互相甩动、有的被抛出去
  （逃逸），整体从"抱团"演化到"少数据团 + 逃逸者"；
* ``disk``：星系盘 —— 中心一颗重星，外围一圈轻粒子做近圆轨道，轨迹画出盘面结构。

积分器
------
用**速度 Verlet（leapfrog）**：

    v(t+dt/2) = v(t) + a(t)·dt/2
    r(t+dt)   = r(t) + v(t+dt/2)·dt
    v(t+dt)   = v(t+dt/2) + a(t+dt)·dt/2

选它的理由不是"精度阶数最高"，而是**辛（symplectic）**：它保持相空间体积，
能量误差**有界、只在真值附近振荡**，不会像低阶显式方法那样单调漂移。
对天体轨道这种"要跑很久"的问题，这一点比单步精度重要得多。

实现要点（为什么这样写）
------------------------
1. **力是 ``(N, N, 2)`` 的一整块数组算的**：``diff[i, j] = r_i − r_j``，随后
   ``einsum('ij,ijk->ik', w, diff)`` 一次求和 —— **没有两层 Python 循环**，
   所以 8 颗星与 400 颗星走的是同一段代码，只是数组更大（代价是 O(N²) 内存）；
2. **软化长度 ε**：把 ``1/r²`` 换成 ``1/(r²+ε²)``，让"两星贴到一起"时力保持有限。
   ``ε = 0`` 是严格的牛顿引力（8 字三体这类精确解**必须**用 0），
   随机星团则建议给一点 ε，否则近距遭遇会把速度打到数值爆炸；
3. **数值爆炸要检测而不是硬崩**：任何一步出现 ``NaN / inf`` 就置 :attr:`NBody.blown_up`
   并停下 —— 界面据此提示"减小 dt 或增大 ε"，而不是把异常抛给用户；
4. **轨迹用环形缓冲**：每帧记一个位置快照，超过 ``trail`` 长度就丢最旧的；
   画布读 :meth:`NBody.trail_array` 一次拿到 ``(帧, N, 2)`` 的整块数组；
5. **编辑星体后要重锚基准**（:meth:`NBody.rebase`）：能量漂移是"相对初值"的量，
   而拖动位置 / 改质量都改变了被积分的系统 —— 旧的 ``E₀`` 已经不属于这条轨迹了。
   界面据此暂停播放、把曲线从当前时刻重画（同生命游戏"涂改会让人口曲线从这一代重来"）。

实测（Windows / Python 3.13.9 · numpy 2.3.5，中位数）
-----------------------------------------------------
复现命令：``python -X utf8 -m tests.bench n_body``
（``-X utf8`` 是为了让 µs / ± 这类字符在 GBK 控制台上也能打印。）

* **星系盘 60 颗 × 600 帧 × 6 子步**（= 桌面实时播放的口径）**1.4 s**，约 **2.4 ms/帧**；
* **8 字三体积分一个周期**（dt = 0.002，3163 步）**0.36 s** —— 即约 0.36 s 走完一整条闭合轨道；
* 单步代价随 N² 增长：24 颗约 **0.3 ms**、60 颗约 **0.6–1.0 ms**、200 颗约 **6–12 ms**。
  小 N 的单步计时被 numpy 的调用开销主导，实测波动在 ±50% 以上（``bench`` 会把波动一并打出来）——
  所以这里只把它们当**量级**看，不当作可以逐位复现的定值。

本模块只依赖标准库 + ``numpy``（numpy 是必需依赖，内核统一向量化 —— 见 README 的
「依赖规则」）。不含任何绘图 / GUI 代码，可单独导入：

    python -m prismath.models.n_body.model     # 跑一段积分器自检
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

__all__ = [
    "GRAVITY",
    "MIN_MASS",
    "DEFAULT_STARS",
    "MIN_STARS",
    "MAX_STARS",
    "DEFAULT_DT",
    "MIN_DT",
    "MAX_DT",
    "DEFAULT_SUBSTEPS",
    "MIN_SUBSTEPS",
    "MAX_SUBSTEPS",
    "DEFAULT_SOFTENING",
    "MAX_SOFTENING",
    "DEFAULT_TRAIL",
    "MIN_TRAIL",
    "MAX_TRAIL",
    "DEFAULT_FRAMES",
    "MAX_FRAMES",
    "DEFAULT_SEED",
    "SCENARIO_FIGURE_EIGHT",
    "SCENARIO_BINARY",
    "SCENARIO_SOLAR",
    "SCENARIO_CLUSTER",
    "SCENARIO_DISK",
    "SCENARIO_ORDER",
    "SCENARIOS",
    "SCENARIO_LABELS",
    "FIGURE_EIGHT_PERIOD",
    "Scenario",
    "Preset",
    "NBodyRun",
    "DriftPoint",
    "NBody",
    "build_scenario",
    "scan_drift",
    "encode_positions",
    "circular_velocity",
]

#: 引力常数。自然单位制里取 1：模型的看点是轨道形状与守恒量，不是某个真实的千克 / 米 / 秒。
GRAVITY: float = 1.0

# ---- 星体数 ----
DEFAULT_STARS: int = 24
MIN_STARS: int = 2
#: 上限由 O(N²) 的力计算决定：400 颗时单步已到毫秒量级，再大画布与实时播放都吃不消
MAX_STARS: int = 400

# ---- 时间步长 ----
DEFAULT_DT: float = 0.004
MIN_DT: float = 0.0002
MAX_DT: float = 0.05

# ---- 每帧推进的子步数（动画节奏，不影响物理本身）----
DEFAULT_SUBSTEPS: int = 6
MIN_SUBSTEPS: int = 1
MAX_SUBSTEPS: int = 60

# ---- 软化长度 ε ----
DEFAULT_SOFTENING: float = 0.0
MAX_SOFTENING: float = 0.5

# ---- 轨迹长度（每个星体保留多少个历史点）----
DEFAULT_TRAIL: int = 160
MIN_TRAIL: int = 0
MAX_TRAIL: int = 1200

# ---- 无头后端（终端 / 网页 / 通用视图）一次跑多少帧 ----
DEFAULT_FRAMES: int = 400
MAX_FRAMES: int = 600

#: 随机种子约定：``-1`` 表示随机，``>=0`` 表示可复现
DEFAULT_SEED: int = -1

#: 质量的允许下限（界面上的质量滑块与 :meth:`NBody.set_mass` 共用）：
#: 质量可以很小（行星对恒星的扰动本来就微乎其微），但不允许为 0 或负 ——
#: 质量为 0 的粒子不受力也不产生引力，留在数组里只会白费计算。
MIN_MASS: float = 1e-4

# ----------------------------------------------------------------------
# 场景
# ----------------------------------------------------------------------
SCENARIO_FIGURE_EIGHT = "figure_eight"
SCENARIO_BINARY = "binary"
SCENARIO_SOLAR = "solar"
SCENARIO_CLUSTER = "cluster"
SCENARIO_DISK = "disk"

#: 8 字三体精确解的周期（每个质量 = 1、G = 1）
FIGURE_EIGHT_PERIOD: float = 6.32591398

#: 场景展示顺序（界面下拉框、终端菜单、文档三处共用）
SCENARIO_ORDER: Tuple[str, ...] = (
    SCENARIO_FIGURE_EIGHT,
    SCENARIO_BINARY,
    SCENARIO_SOLAR,
    SCENARIO_CLUSTER,
    SCENARIO_DISK,
)


@dataclass(frozen=True)
class Scenario:
    """一个场景的元数据：默认星体数、推荐软化长度、周期（有的话）与一句说明。"""

    key: str
    label: str
    stars: int
    softening: float
    period: float = 0.0
    hint: str = ""


SCENARIOS: Dict[str, Scenario] = {
    SCENARIO_FIGURE_EIGHT: Scenario(
        key=SCENARIO_FIGURE_EIGHT,
        label="8 字三体（精确周期解）",
        stars=3,
        softening=0.0,
        period=FIGURE_EIGHT_PERIOD,
        hint="三个等质量星体沿同一条「8」字首尾相接 —— 已知的精确周期解，"
             "积分一个周期后应当回到出发点。它是本模型的精度标尺，所以 ε 必须为 0。",
    ),
    SCENARIO_BINARY: Scenario(
        key=SCENARIO_BINARY,
        label="双星 + 行星（层级三体）",
        stars=3,
        softening=0.0,
        period=0.0,
        hint="两颗重星近距绕转，第三颗轻行星在远处画波浪 —— "
             "外圈轨道被双星的引力“抖动”出周期性的起伏。",
    ),
    SCENARIO_SOLAR: Scenario(
        key=SCENARIO_SOLAR,
        label="太阳 + 四行星（近圆轨道）",
        stars=5,
        softening=0.0,
        period=0.0,
        hint="半径越大周期越长（开普勒第三定律）：轨迹上叠出一圈圈同心轨道，"
             "内圈跑好几圈时外圈才走完一圈。",
    ),
    SCENARIO_CLUSTER: Scenario(
        key=SCENARIO_CLUSTER,
        label="随机星团（混沌）",
        stars=DEFAULT_STARS,
        softening=0.16,
        period=0.0,
        hint="位置与速度都随机、总动量为 0：星体互相甩动，有的被抛出去再也回不来。"
             "同一初值只差最后一位小数，长期轨道就会完全不同 —— 这就是混沌。",
    ),
    SCENARIO_DISK: Scenario(
        key=SCENARIO_DISK,
        label="星系盘（多星轨道）",
        stars=60,
        softening=0.04,
        period=0.0,
        hint="中心一颗重星，外围一圈轻粒子做近圆轨道：外圈慢、内圈快，"
             "轨迹上直接画出盘面的结构。",
    ),
}

#: 场景取值 -> 界面标签（下拉框用）
SCENARIO_LABELS: Dict[str, str] = {
    key: SCENARIOS[key].label for key in SCENARIO_ORDER
}

#: 随机源可以传入 None / int（种子）/ numpy Generator 实例
RngLike = Union[None, int, np.random.Generator]


def _resolve_rng(rng: RngLike = None) -> np.random.Generator:
    """把 None / 种子 / Generator 实例统一转换成一个 numpy 随机源。"""
    if isinstance(rng, np.random.Generator):
        return rng
    return np.random.default_rng(rng)


def _clamp(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return max(low, min(high, number))


def circular_velocity(central_mass: float, radius: float, softening: float = 0.0) -> float:
    """半径 ``radius`` 处绕 ``central_mass`` 做**圆轨道**所需的速度。

    软化引力 ``a(r) = G M r / (r² + ε²)^{3/2}`` 下，圆周运动要求
    ``v² / r = a(r)``，于是 ``v = √(G M r² / (r² + ε²)^{3/2})``；``ε = 0`` 时
    退化为教科书上的 ``v = √(G M / r)``。
    """
    r2 = float(radius) * float(radius)
    denom = (r2 + float(softening) ** 2) ** 1.5
    return math.sqrt(GRAVITY * float(central_mass) * r2 / denom)


@dataclass
class Preset:
    """一个场景的初始条件（位置 / 速度 / 质量）与它的元数据。"""

    key: str
    label: str
    positions: np.ndarray
    velocities: np.ndarray
    masses: np.ndarray
    softening: float = 0.0
    period: float = 0.0

    @property
    def count(self) -> int:
        """星体数 N。"""
        return int(self.masses.size)


def _figure_eight() -> Preset:
    """8 字三体：Chenciner & Montgomery 的精确周期解（G = 1，每个质量 = 1）。"""
    x1 = np.array([0.97000436, -0.24308753])
    v3 = np.array([-0.93240737, -0.86473146])
    positions = np.array([x1, -x1, [0.0, 0.0]])
    velocities = np.array([-v3 / 2.0, -v3 / 2.0, v3])
    return Preset(
        key=SCENARIO_FIGURE_EIGHT,
        label=SCENARIOS[SCENARIO_FIGURE_EIGHT].label,
        positions=positions,
        velocities=velocities,
        masses=np.ones(3),
        softening=0.0,
        period=FIGURE_EIGHT_PERIOD,
    )


def _binary_planet() -> Preset:
    """双星 + 行星：双星（1.0 / 0.6）间距 1，第三颗（0.002）在 r = 3 的近圆轨道上。"""
    m1, m2, m3 = 1.0, 0.6, 0.002
    total = m1 + m2
    separation = 1.0
    # 质心在原点：重星离质心近、轻星离质心远（杠杆关系）
    r1 = -m2 / total * separation
    r2 = m1 / total * separation
    v_rel = math.sqrt(GRAVITY * total / separation)
    positions = np.array([[r1, 0.0], [r2, 0.0], [3.0, 0.0]])
    velocities = np.array([[0.0, m2 / total * v_rel],
                           [0.0, -m1 / total * v_rel],
                           [0.0, circular_velocity(total + m3, 3.0)]])
    return Preset(
        key=SCENARIO_BINARY,
        label=SCENARIOS[SCENARIO_BINARY].label,
        positions=positions,
        velocities=velocities,
        masses=np.array([m1, m2, m3]),
        softening=0.0,
    )


def _solar_system() -> Preset:
    """太阳 + 四颗行星的圆形轨道近似（质量很小，行星之间的引力可忽略）。"""
    sun_mass = 1.0
    planets = ((0.60, 0.0015), (1.00, 0.0045), (1.55, 0.0035), (2.20, 0.0012))
    phases = (0.0, 2.1, 4.4, 1.2)
    positions = [np.zeros(2)]
    velocities = [np.zeros(2)]
    masses = [sun_mass]
    for (radius, mass), phase in zip(planets, phases):
        positions.append(np.array([radius * math.cos(phase), radius * math.sin(phase)]))
        speed = circular_velocity(sun_mass, radius)
        velocities.append(np.array([-speed * math.sin(phase), speed * math.cos(phase)]))
        masses.append(mass)

    pos = np.array(positions)
    vel = np.array(velocities)
    mass = np.array(masses)
    # 把整体平移掉（质心速度归零），这样总动量严格为 0，画面也不会整体漂走
    vel = vel - np.sum(mass[:, None] * vel, axis=0) / mass.sum()
    pos = pos - np.sum(mass[:, None] * pos, axis=0) / mass.sum()
    return Preset(
        key=SCENARIO_SOLAR,
        label=SCENARIOS[SCENARIO_SOLAR].label,
        positions=pos,
        velocities=vel,
        masses=mass,
        softening=0.0,
    )


def _cluster(stars: int, rng: np.random.Generator) -> Preset:
    """随机星团：质量在 [0.6, 1.4]、位置均匀分布在半径 1.4 的圆盘内、速度随机。

    初速度取得比"维里平衡"低得多（动能只有势能的一个零头），所以它一开始就**冷塌缩**：
    星体先挤向中心，近距遭遇把几颗甩出去 —— 这正是 N 体系统最典型的一段历史。
    """
    count = max(MIN_STARS, int(stars))
    masses = 0.6 + 0.8 * rng.random(count)
    # 均匀分布在圆盘上：半径按 √u（否则会往圆心堆）
    radius = 1.4 * np.sqrt(rng.random(count))
    angle = 2.0 * math.pi * rng.random(count)
    positions = np.column_stack((radius * np.cos(angle), radius * np.sin(angle)))
    velocities = (rng.random((count, 2)) - 0.5) * 1.1
    # 总动量为 0：否则整个星团会整体平移，画面上看着像"漂走"
    velocities -= np.sum(masses[:, None] * velocities, axis=0) / masses.sum()
    positions -= np.sum(masses[:, None] * positions, axis=0) / masses.sum()
    return Preset(
        key=SCENARIO_CLUSTER,
        label=SCENARIOS[SCENARIO_CLUSTER].label,
        positions=positions,
        velocities=velocities,
        masses=masses,
        softening=SCENARIOS[SCENARIO_CLUSTER].softening,
    )


def _disk(stars: int, rng: np.random.Generator) -> Preset:
    """星系盘：中心重星 + 一圈近圆轨道的轻粒子（半径 0.45–1.5 均匀分布）。"""
    count = max(MIN_STARS, int(stars))
    particles = count - 1
    central = 1.0
    softening = SCENARIOS[SCENARIO_DISK].softening
    radius = 0.45 + 1.05 * np.sqrt(rng.random(particles))
    angle = 2.0 * math.pi * rng.random(particles)
    positions = np.column_stack((radius * np.cos(angle), radius * np.sin(angle)))
    speed = np.array([circular_velocity(central, r, softening) for r in radius])
    velocities = np.column_stack((-speed * np.sin(angle), speed * np.cos(angle)))
    # 一点点扰动：让盘面不至于退化成完美的同心圆（也顺带暴露不稳定性）
    velocities += (rng.random((particles, 2)) - 0.5) * 0.02

    positions = np.vstack((np.zeros((1, 2)), positions))
    velocities = np.vstack((np.zeros((1, 2)), velocities))
    masses = np.concatenate(([central], np.full(particles, 0.0008)))
    com_v = np.sum(masses[:, None] * velocities, axis=0) / masses.sum()
    velocities -= com_v
    return Preset(
        key=SCENARIO_DISK,
        label=SCENARIOS[SCENARIO_DISK].label,
        positions=positions,
        velocities=velocities,
        masses=masses,
        softening=softening,
    )


def build_scenario(scenario: str = SCENARIO_FIGURE_EIGHT,
                   stars: Optional[int] = None,
                   seed: RngLike = None) -> Preset:
    """按场景名构造初始条件。

    ``stars`` 只对随机场景（星团 / 星系盘）有效，其余场景的星体数由场景本身决定；
    ``seed`` 同样只对随机场景有效（给定种子即可复现同一个初值）。
    """
    key = scenario if scenario in SCENARIOS else SCENARIO_FIGURE_EIGHT
    if key == SCENARIO_FIGURE_EIGHT:
        return _figure_eight()
    if key == SCENARIO_BINARY:
        return _binary_planet()
    if key == SCENARIO_SOLAR:
        return _solar_system()
    count = SCENARIOS[key].stars if stars is None else int(stars)
    rng = _resolve_rng(seed)
    if key == SCENARIO_DISK:
        return _disk(count, rng)
    return _cluster(count, rng)


# ----------------------------------------------------------------------
# 结果容器
# ----------------------------------------------------------------------
@dataclass
class NBodyRun:
    """一段**有上限**的演化结果（终端 / 网页 / 通用视图用）。

    ``frames`` 是按 ``stride`` 抽样后的位置快照（每帧一个 ``(N, 2)`` 数组），
    诊断量取**末态**；``blown_up`` 为真表示数值发散，此时帧序列会提前截断。
    """

    scenario: str
    label: str
    count: int
    dt: float
    substeps: int
    softening: float
    frames: List[np.ndarray] = field(default_factory=list)
    #: 每个采样帧的 ``(时间 t, 总能量 E, 相对漂移, 最大半径)``
    samples: List[Tuple[float, float, float, float]] = field(default_factory=list)
    masses: np.ndarray = field(default_factory=lambda: np.empty(0))
    stride: int = 1
    steps: int = 0
    time: float = 0.0
    energy0: float = 0.0
    energy: float = 0.0
    energy_drift: float = 0.0
    max_drift: float = 0.0
    momentum: float = 0.0
    angular_momentum: float = 0.0
    escaped: int = 0
    blown_up: bool = False
    elapsed: float = 0.0

    @property
    def frame_count(self) -> int:
        """帧数。"""
        return len(self.frames)

    @property
    def extent(self) -> Tuple[float, float, float, float]:
        """所有帧的包围盒 ``(xmin, xmax, ymin, ymax)``（画布据此定标）。"""
        if not self.frames:
            return (-1.0, 1.0, -1.0, 1.0)
        points = np.vstack(self.frames)
        low = points.min(axis=0)
        high = points.max(axis=0)
        return (float(low[0]), float(high[0]), float(low[1]), float(high[1]))


@dataclass
class DriftPoint:
    """一个时间步长下的能量漂移测量结果。"""

    dt: float
    steps: int
    drift: float          # 整段积分里"相对能量漂移"的最大绝对值


# ----------------------------------------------------------------------
# 模型
# ----------------------------------------------------------------------
class NBody:
    """万有引力多星模型（纯计算）。

    参数
    ----
    positions / velocities / masses : 形如 ``(N, 2)`` / ``(N, 2)`` / ``(N,)`` 的数组
        初始位置、初始速度、质量。
    dt : float
        单个积分步长（速度 Verlet 的一步）。
    softening : float
        软化长度 ε，见模块说明；``0`` 即严格牛顿引力。
    trail : int
        轨迹长度：保留多少个**帧**位置快照（0 表示不记轨迹）。
    scenario / label / period : str / str / float
        场景标识、场景名与（已知时的）精确周期，仅供界面文案使用。

    约定：时间步长与软化长度都会夹到合法范围；质量非正的星体直接丢掉
    （质量为 0 的粒子不受力、也不产生引力，留在数组里只会白费计算）。
    """

    def __init__(
        self,
        positions: Any,
        velocities: Any,
        masses: Any,
        *,
        dt: float = DEFAULT_DT,
        softening: float = DEFAULT_SOFTENING,
        trail: int = DEFAULT_TRAIL,
        scenario: str = "custom",
        label: str = "",
        period: float = 0.0,
    ) -> None:
        pos = np.asarray(positions, dtype=float)
        vel = np.asarray(velocities, dtype=float)
        mass = np.asarray(masses, dtype=float).reshape(-1)
        if pos.ndim != 2 or pos.shape[1] != 2:
            raise ValueError("positions 必须是 (N, 2) 的数组")
        if vel.shape != pos.shape or mass.size != pos.shape[0]:
            raise ValueError("positions / velocities / masses 的形状必须匹配：得到 "
                             f"{pos.shape} / {vel.shape} / {mass.shape}")

        self.dt = _clamp(dt, MIN_DT, MAX_DT, DEFAULT_DT)
        self.softening = _clamp(softening, 0.0, MAX_SOFTENING, DEFAULT_SOFTENING)
        self.trail_len = int(max(MIN_TRAIL, min(MAX_TRAIL, int(trail))))
        self.scenario = str(scenario)
        self.label = str(label) or str(scenario)
        self.period = float(period)

        self.pos = np.array(pos, dtype=float, copy=True)
        self.vel = np.array(vel, dtype=float, copy=True)
        self.mass = np.array(mass, dtype=float, copy=True)
        self.count = int(self.mass.size)

        self.steps = 0
        self.time = 0.0
        self.blown_up = False
        self._history: List[np.ndarray] = [self.pos.copy()]
        self.initial_energy = self.total_energy()
        self.max_drift = 0.0
        #: "逃逸"判据的半径：初始最大半径的 4 倍（对每个场景都自适应）
        self._escape_radius = self._compute_escape_radius()

    # ---------------- 基础属性 ----------------
    @property
    def shape(self) -> Tuple[int, int]:
        """``(N, 2)``。"""
        return self.count, 2

    def trail_array(self) -> np.ndarray:
        """轨迹快照 ``(帧数, N, 2)``（最旧的在前）；没有轨迹时返回空数组。"""
        if len(self._history) <= 1:
            return np.empty((0, self.count, 2))
        return np.stack(self._history)

    # ---------------- 力与能量 ----------------
    def _geometry(self) -> Tuple[np.ndarray, np.ndarray]:
        """返回 ``(diff, inv_cube)``：``diff[i, j] = r_i − r_j``，``inv_cube[i, j] = 1/(d²+ε²)^{3/2}``。"""
        diff = self.pos[:, None, :] - self.pos[None, :, :]
        dist2 = np.sum(diff * diff, axis=-1) + self.softening ** 2
        np.fill_diagonal(dist2, np.inf)          # 自己不受自己的力
        with np.errstate(divide="ignore", invalid="ignore"):
            inv_cube = 1.0 / (dist2 * np.sqrt(dist2))
        return diff, inv_cube

    def accelerations(self) -> np.ndarray:
        """所有星体的加速度 ``(N, 2)``（向量化的一次两两求和）。"""
        diff, inv_cube = self._geometry()
        weighted = inv_cube * self.mass[None, :]
        return -GRAVITY * np.einsum("ij,ijk->ik", weighted, diff)

    def kinetic(self) -> float:
        """总动能 ``½ Σ m|v|²``。"""
        return float(0.5 * np.sum(self.mass * np.sum(self.vel * self.vel, axis=1)))

    def potential(self) -> float:
        """总势能 ``−G Σ_{i<j} m_i m_j / √(r² + ε²)``。"""
        diff = self.pos[:, None, :] - self.pos[None, :, :]
        dist2 = np.sum(diff * diff, axis=-1) + self.softening ** 2
        np.fill_diagonal(dist2, np.inf)          # 对角线（自己与自己）不计入
        with np.errstate(divide="ignore", invalid="ignore"):
            inv_r = 1.0 / np.sqrt(dist2)
        weights = self.mass[:, None] * self.mass[None, :]
        # 对角线上 inv_r = 0，所以直接求和再除 2 就是 Σ_{i<j}
        return float(-0.5 * GRAVITY * np.sum(weights * inv_r))

    def total_energy(self) -> float:
        """总机械能 ``E = K + U``（本模型里没有别的能量项，所以它应当守恒）。"""
        return self.kinetic() + self.potential()

    def momentum(self) -> np.ndarray:
        """总动量 ``Σ m v``（应当严格守恒：内力成对抵消）。"""
        return np.sum(self.mass[:, None] * self.vel, axis=0)

    def angular_momentum(self) -> float:
        """总角动量（绕原点的 z 分量）``Σ m (x·vy − y·vx)``。"""
        return float(np.sum(self.mass * (self.pos[:, 0] * self.vel[:, 1]
                                         - self.pos[:, 1] * self.vel[:, 0])))

    def center_of_mass(self) -> np.ndarray:
        """质心位置。"""
        total = float(np.sum(self.mass)) or 1.0
        return np.sum(self.mass[:, None] * self.pos, axis=0) / total

    def relative_energy_drift(self) -> float:
        """相对能量漂移 ``(E − E₀) / |E₀|``（辛积分器下应当有界地小幅振荡）。"""
        base = abs(self.initial_energy)
        if base < 1e-15:
            return 0.0
        return (self.total_energy() - self.initial_energy) / base

    def escaped_count(self) -> int:
        """已经"逃逸"的星体数（离质心超过初始最大半径的 4 倍）。"""
        centered = self.pos - self.center_of_mass()
        radius = np.hypot(centered[:, 0], centered[:, 1])
        return int(np.count_nonzero(radius > self._escape_radius))

    def _compute_escape_radius(self) -> float:
        """按当前构型定出"逃逸"判据的半径（初始最大半径的 4 倍）。

        初值被编辑过（拖动位置、改质量）之后要重新算 —— 它和能量基准一样，
        是一个"相对初值"的参考量。
        """
        centered = self.pos - self.center_of_mass()
        radius = np.hypot(centered[:, 0], centered[:, 1])
        return max(4.0 * float(np.max(radius)), 1e-6)

    def max_radius(self) -> float:
        """离质心最远的那颗星的距离（用来观察星团"散开"的程度）。"""
        centered = self.pos - self.center_of_mass()
        return float(np.max(np.hypot(centered[:, 0], centered[:, 1])))

    def bounds(self, include_trail: bool = True) -> Tuple[float, float, float, float]:
        """当前画面的包围盒 ``(xmin, xmax, ymin, ymax)``（画布定标用）。"""
        points = [self.pos]
        trail = self.trail_array() if include_trail else np.empty((0, self.count, 2))
        if trail.size:
            points.append(trail.reshape(-1, 2))
        stacked = np.vstack(points)
        low = stacked.min(axis=0)
        high = stacked.max(axis=0)
        # 最小跨度：起步时所有星体挤在一点，别让画布"放大到极限"
        span = max(float(high[0] - low[0]), float(high[1] - low[1]), 1e-3)
        if span < 1.0:
            pad = (1.0 - span) / 2.0
            low = low - pad
            high = high + pad
        return (float(low[0]), float(high[0]), float(low[1]), float(high[1]))

    # ---------------- 编辑单颗星（桌面画布上拖 / 改质量用） ----------------
    def set_mass(self, index: int, mass: float) -> None:
        """设置第 ``index`` 颗星的质量（夹到 ≥ :data:`MIN_MASS`）。

        改的是"被积分的物理"，所以调用方改完之后要调用 :meth:`rebase` 重新锚定基准。
        """
        if not 0 <= int(index) < self.count:
            raise IndexError(f"星体下标越界：{index}（共 {self.count} 颗）")
        self.mass[int(index)] = max(MIN_MASS, float(mass))

    def move_star(self, index: int, x: float, y: float) -> None:
        """把第 ``index`` 颗星挪到 ``(x, y)``（速度保持不变；同样需要 :meth:`rebase`）。"""
        if not 0 <= int(index) < self.count:
            raise IndexError(f"星体下标越界：{index}（共 {self.count} 颗）")
        self.pos[int(index)] = (float(x), float(y))

    def rebase(self) -> None:
        """把能量与逃逸判据的**基准**重新锚定到当前状态（编辑星体之后调用）。

        能量漂移是"相对初值"的量：初值一旦被改过（拖动位置、改质量），
        旧的 ``E₀`` 就已经不属于这条轨迹了 —— 不重新取基准，界面上会显示一个
        巨大的假漂移。
        """
        self.initial_energy = self.total_energy()
        self.max_drift = 0.0
        self._escape_radius = self._compute_escape_radius()

    # ---------------- 演化 ----------------
    def _record_trail(self) -> None:
        """记录一个轨迹点（在 :meth:`advance` 里每帧记一次，而不是每个子步都记）。"""
        if self.trail_len <= 0:
            return
        self._history.append(self.pos.copy())
        if len(self._history) > self.trail_len:
            del self._history[0:len(self._history) - self.trail_len]

    def step(self) -> None:
        """推进一个时间步（速度 Verlet，辛积分器）。"""
        if self.blown_up:
            return
        dt = self.dt
        a0 = self.accelerations()
        self.pos += self.vel * dt + 0.5 * a0 * dt * dt
        a1 = self.accelerations()
        self.vel += 0.5 * (a0 + a1) * dt
        self.steps += 1
        self.time += dt
        if not (np.isfinite(self.pos).all() and np.isfinite(self.vel).all()):
            # 近距遭遇把速度打到 inf/NaN：标记后停下，让界面给一句人话提示
            self.blown_up = True

    def advance(self, substeps: int = 1) -> "NBody":
        """推进 ``substeps`` 个子步并记录**一个**轨迹点（"一帧"= 一次画面更新）。"""
        for _ in range(max(1, int(substeps))):
            if self.blown_up:
                break
            self.step()
        self._record_trail()
        drift = abs(self.relative_energy_drift())
        if drift > self.max_drift:
            self.max_drift = drift
        return self

    def run(self, frames: int = DEFAULT_FRAMES, substeps: int = DEFAULT_SUBSTEPS,
            progress: Optional[Callable[[int, int], None]] = None,
            cancel: Optional[Any] = None,
            max_frames: int = MAX_FRAMES) -> NBodyRun:
        """连续演化 ``frames`` 帧（**有上限**），返回抽样后的帧序列与末态诊断。

        ``progress(已完成帧, 总帧数)`` 每 10 帧回调一次（后台线程用它刷新进度，
        主线程不要直接画图）；``cancel`` 传 ``threading.Event`` 可中途停止。
        帧数超过 ``max_frames`` 时按 ``stride`` 抽样，避免给通用视图 / 网页塞一份巨载荷。
        """
        total = max(1, int(frames))
        per_frame = max(1, int(substeps))
        # 帧数 = 初始帧 + total/stride 帧 + 末帧；按 (max_frames - 2) 折算，帧数不超上限
        budget = max(1, int(max_frames) - 2)
        stride = max(1, math.ceil(total / budget)) if budget >= 1 else 1
        started = time.perf_counter()
        cancelled = getattr(cancel, "is_set", None)

        snapshots: List[np.ndarray] = [self.pos.copy()]
        samples: List[Tuple[float, float, float, float]] = [
            (self.time, self.initial_energy, 0.0, self.max_radius())]

        def capture() -> None:
            snapshots.append(self.pos.copy())
            samples.append((self.time, self.total_energy(),
                            self.relative_energy_drift(), self.max_radius()))

        for offset in range(1, total + 1):
            if cancelled is not None and cancelled():
                break
            self.advance(per_frame)
            if offset % stride == 0 or self.blown_up:
                capture()
            if progress is not None and (offset % 10 == 0 or offset == total):
                progress(offset, total)
            if self.blown_up:
                break

        # 末态必须收帧：否则"最后一帧"与诊断量（末态）说的不是同一时刻，
        # 回放出来的结局会比表格里报的少一段。
        if self.steps and not np.array_equal(snapshots[-1], self.pos):
            capture()

        return NBodyRun(
            scenario=self.scenario,
            label=self.label,
            count=self.count,
            dt=self.dt,
            substeps=per_frame,
            softening=self.softening,
            frames=snapshots,
            samples=samples,
            masses=self.mass.copy(),
            stride=stride,
            steps=self.steps,
            time=self.time,
            energy0=self.initial_energy,
            energy=self.total_energy(),
            energy_drift=self.relative_energy_drift(),
            max_drift=self.max_drift,
            momentum=float(np.linalg.norm(self.momentum())),
            angular_momentum=self.angular_momentum(),
            escaped=self.escaped_count(),
            blown_up=self.blown_up,
            elapsed=time.perf_counter() - started,
        )


# ----------------------------------------------------------------------
# 编码：给前端最轻的载荷
# ----------------------------------------------------------------------
def encode_positions(positions: Any) -> List[float]:
    """把 ``(N, 2)`` 的位置压成扁平列表 ``[x0, y0, x1, y1, …]``（前端一次遍历即可还原）。"""
    array = np.asarray(positions, dtype=float).reshape(-1, 2)
    return [float(v) for v in np.round(array, 4).reshape(-1)]


# ----------------------------------------------------------------------
# 时间步长 -> 能量漂移（辛积分器的精度标尺）
# ----------------------------------------------------------------------
def scan_drift(dt_values: Sequence[float],
               scenario: str = SCENARIO_FIGURE_EIGHT,
               spans: float = 1.0,
               softening: Optional[float] = None) -> List[DriftPoint]:
    """扫描「时间步长 dt -> 最大相对能量漂移」。

    对每个 ``dt`` 都积分**同样长的一段物理时间**（有精确周期的场景取一个周期，
    否则取 ``spans`` 个时间单位），所以不同 ``dt`` 的结果可以直接横向比较：
    速度 Verlet 是二阶方法，漂移应当大致按 ``dt²`` 下降（每把 dt 减半、漂移降为 1/4）。
    """
    preset = build_scenario(scenario)
    epsilon = preset.softening if softening is None else float(softening)
    span = preset.period * float(spans) if preset.period else float(spans)
    results: List[DriftPoint] = []

    for raw_dt in dt_values:
        dt = _clamp(raw_dt, MIN_DT, MAX_DT, DEFAULT_DT)
        body = NBody(preset.positions, preset.velocities, preset.masses,
                     dt=dt, softening=epsilon, trail=0,
                     scenario=preset.key, label=preset.label, period=preset.period)
        steps = max(1, int(round(span / dt)))
        base = abs(body.initial_energy) or 1.0
        # 取整段积分里**最大**的那次漂移：辛积分器的能量误差是振荡的，只看末值会
        # 恰好落在"误差回零"的那一刻（8 字三体积分整周期就有这种巧合），
        # 那样量到的不是精度，而是运气。
        worst = 0.0
        for _ in range(steps):
            body.step()
            if body.blown_up:
                break
            drift = abs(body.total_energy() - body.initial_energy) / base
            if drift > worst:
                worst = drift
        results.append(DriftPoint(dt=dt, steps=steps, drift=worst))
    return results


# ----------------------------------------------------------------------
# 直接运行本文件时的自检：积分器精度与守恒量
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    try:  # Windows 控制台默认 GBK，需要切到 UTF-8 才能正常输出中文
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    print("=" * 70)
    print("万有引力多星自检：积分器精度与守恒量（自然单位 G = 1）")
    print("=" * 70)

    # 1. 两体圆轨道：周期、半径、回到出发点的偏差
    mass = 1.0
    radius = 0.5                        # 两星各自离质心的距离（间距 a = 1）
    separation = 2.0 * radius
    v_rel = math.sqrt(GRAVITY * 2.0 * mass / separation)
    two_body = NBody(
        positions=[[-radius, 0.0], [radius, 0.0]],
        velocities=[[0.0, -v_rel / 2.0], [0.0, v_rel / 2.0]],
        masses=[mass, mass], dt=0.002, softening=0.0, trail=0,
        scenario="two_body",
    )
    period = 2.0 * math.pi * math.sqrt(separation ** 3 / (GRAVITY * 2.0 * mass))
    start = two_body.pos.copy()
    r_max = 0.0
    for _ in range(int(round(period / two_body.dt))):
        two_body.step()
        r_max = max(r_max, float(np.hypot(*two_body.pos[0])))
    back = float(np.max(np.abs(two_body.pos - start)))
    print("\n1. 两体圆轨道（m₁ = m₂ = 1，间距 a = 1，dt = 0.002）")
    print(f"   理论周期 T = 2πa^(3/2)/√(G·M) = {period:.6f}"
          f"，积分 {two_body.steps} 步")
    print(f"   半径 r = {radius:.4f} 的最大偏差 = {abs(r_max - radius):.3e}")
    print(f"   一个周期后回到初始位置的最大偏差 = {back:.3e}")
    assert abs(r_max - radius) < 2e-3, "圆轨道半径不应越跑越偏"
    assert back < 5e-3, "一个周期后应当回到出发点"

    # 2. 守恒量（8 字三体跑一段）
    figure = build_scenario(SCENARIO_FIGURE_EIGHT)
    body = NBody(figure.positions, figure.velocities, figure.masses,
                 dt=0.002, trail=0, scenario=figure.key, period=figure.period)
    momentum0 = float(np.linalg.norm(body.momentum()))
    angular0 = body.angular_momentum()
    e0 = body.initial_energy
    for _ in range(2000):
        body.step()
    print("\n2. 守恒量（8 字三体，dt = 0.002，2000 步）")
    print(f"   总能量 E₀ = {e0:.8f} -> E = {body.total_energy():.8f}"
          f"，相对漂移 = {body.relative_energy_drift():.3e}")
    print(f"   总动量 |P| = {float(np.linalg.norm(body.momentum())):.3e}"
          f"（初始 {momentum0:.3e}）")
    print(f"   角动量 L = {angular0:.8f} -> {body.angular_momentum():.8f}")
    assert abs(body.relative_energy_drift()) < 1e-5, "辛积分器的能量漂移应当有界且很小"
    assert float(np.linalg.norm(body.momentum())) < 1e-10, "总动量应当守恒（内力成对抵消）"
    assert abs(body.angular_momentum() - angular0) < 1e-6, "角动量应当守恒"

    # 3. 8 字三体：一个周期后回到初始构型
    clock = NBody(figure.positions, figure.velocities, figure.masses,
                  dt=0.002, trail=0, scenario=figure.key, period=figure.period)
    steps = int(round(FIGURE_EIGHT_PERIOD / clock.dt))
    for _ in range(steps):
        clock.step()
    error = float(np.max(np.abs(clock.pos - figure.positions)))
    print("\n3. 8 字三体（精确周期解，T = %.6f）" % FIGURE_EIGHT_PERIOD)
    print(f"   dt = 0.002、{steps} 步后回到初始构型的最大偏差 = {error:.3e}")
    assert error < 5e-3, "8 字三体应当在一个周期后回到出发点"

    # 4. 随机场景：跑得动、不爆炸
    print("\n4. 随机场景（固定种子 20260922，600 帧 × 6 子步）")
    for key in (SCENARIO_CLUSTER, SCENARIO_DISK):
        preset = build_scenario(key, seed=20260922)
        runner = NBody(preset.positions, preset.velocities, preset.masses,
                       dt=DEFAULT_DT, softening=preset.softening, trail=0,
                       scenario=preset.key, label=preset.label)
        result = runner.run(frames=600, substeps=6)
        print(f"   {preset.label}: N = {result.count}，"
              f"末态最大半径 = {runner.max_radius():.3f}，逃逸 {result.escaped} 颗，"
              f"数值爆炸 = {result.blown_up}")
        assert not result.blown_up, f"{key} 在默认参数下不应数值爆炸"

    # 5. dt -> 能量漂移：二阶收敛
    print("\n5. 时间步长 -> 最大相对能量漂移（8 字三体，积分一个周期）")
    print(f"{'dt':>10}{'步数':>10}{'最大相对漂移':>16}")
    print("-" * 70)
    points = scan_drift((0.008, 0.004, 0.002, 0.001))
    for point in points:
        print(f"{point.dt:>10.4f}{point.steps:>10}{point.drift:>16.3e}")
    print("-" * 70)
    drifts = [point.drift for point in points]
    assert drifts == sorted(drifts, reverse=True), "时间步长越小，能量漂移应当越小"
    assert drifts[-1] < drifts[0] / 4.0, "二阶方法：dt 减半应当让漂移降为约 1/4"
    print("提示：速度 Verlet 是辛积分器 —— 能量误差有界、只在真值附近振荡，")
    print("      不随时间单调漂移；这也是它比同阶显式方法更适合长时间天体积分的原因。")
    print("\n全部自检通过 ✔")
