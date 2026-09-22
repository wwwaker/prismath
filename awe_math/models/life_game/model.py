# -*- coding: utf-8 -*-
"""
生命游戏（Conway's Game of Life）核心模型
=========================================

在一个 ``rows × cols`` 的棋盘上，每个格子要么是活的（1）要么是死的（0）。每一代**同时**
更新所有格子，规则只看 Moore 邻域（周围 8 格）里的活细胞数：

* **活细胞**：邻居数落在 ``survive`` 集合里就继续存活，否则死亡；
* **死细胞**：邻居数落在 ``born`` 集合里就新生，否则保持死亡。

标准规则写成 ``B3/S23``（死格恰好 3 个邻居则新生，活格有 2 或 3 个邻居则存活）。
**三条局部规则**却产生了滑翔机、振荡子、乃至通用计算能力 —— 这是本模型要展示的东西。

边界条件
--------
* ``torus``（默认）：上下相连、左右相连（环面）。没有"边缘"，滑翔机会绕行一圈回来；
* ``dead``：棋盘之外一律当作死细胞。图案会在边缘撞死。

实现要点（为什么这样写）
------------------------
1. **numpy 向量化**：棋盘是一块 ``(rows, cols)`` 的 ``bool`` 数组，一代就是"补一圈边框 +
   8 次整块切片求和 + 查两张表"—— **没有逐格 Python 循环**。规则编译成 9 元查找表
   （下标 = 邻居数）而不是用 ``np.isin``，于是任意 ``born`` / ``survive`` 组合都走同一条路径。
2. **一次性补边框，两种边界共用一条求和路径**：先把棋盘放进 ``(rows+2, cols+2)`` 的零数组 ——
   "死边界"到此为止（外圈恒 0，天然正确）；"环面"再把外圈用**对边赋值**填上（四条边 + 四个角）。
   随后两种边界走**同一段** 8 次切片求和，热路径里没有分支、没有取模。
3. **一代一次分配**：每代新建一块数组整体替换，天然满足"同时更新"的语义，
   不需要"先算全部再写回"的两遍扫描。
4. **周期检测用状态哈希**：``hash(packbits(alive))`` 作为键（先压到 1/8 体积再哈希），
   只存"状态 -> 首次出现的代数"，内存 O(存活代数) 而不是 O(代数 × 棋盘)。

实测（Windows / Python 3.13，标准规则，密度 0.30，中位数）
--------------------------------------------------------
复现命令：``python -m tests.bench life_game``

* 50×50 每代 **46 µs**、120×120 每代 **133 µs**；
* 50×50 连推 300 代（含 census 与周期检测）**15.2 ms**；
* 30×30 的"密度 5 点 × 12 次 × 200 代"扫描 **207 ms**；
* 对照同一台机器上的旧字节数组实现（0.50 ms / 3.04 ms / 199 ms / 1.47 s）：
  单代约快 **15–23×**，扫描快 **7×** —— 扫描提升较小是因为它还要付 Python 侧的
  逐代记账（编码、census、周期检测），这部分不随向量化变快。

本模块只依赖标准库 + ``numpy``。numpy 现在是**必需依赖**：内核统一向量化，不再维护
"标准库回退实现"（见 README 的「依赖规则」）。不含任何绘图 / GUI 代码，可单独导入：

    python -m awe_math.models.life_game.model     # 跑一段教科书结论自检
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple, Union

import numpy as np

__all__ = [
    "DEFAULT_ROWS",
    "DEFAULT_COLS",
    "MIN_SIZE",
    "MAX_SIZE",
    "DEFAULT_DENSITY",
    "DEFAULT_GENERATIONS",
    "MAX_FRAMES",
    "DEFAULT_RULE",
    "BOUNDARY_TORUS",
    "BOUNDARY_DEAD",
    "BOUNDARIES",
    "OUTCOME_RUNNING",
    "OUTCOME_EXTINCT",
    "OUTCOME_STATIC",
    "OUTCOME_CYCLE",
    "OUTCOME_LABELS",
    "RULES",
    "PATTERNS",
    "PATTERN_LABELS",
    "PATTERN_BLANK",
    "LifeRule",
    "LifeStep",
    "LifeWatch",
    "LifeRun",
    "DensityResult",
    "LifeBoard",
    "encode_cells",
    "scan_survival",
]

#: 默认棋盘边长（正方形）与允许范围
DEFAULT_ROWS = 50
DEFAULT_COLS = 50
MIN_SIZE = 8
MAX_SIZE = 120

#: 默认初始存活密度。0.30 附近是"长期行为最丰富"的区间：
#: 太低会很快消亡，太高会迅速僵化成大片静止块或短周期振荡。
DEFAULT_DENSITY = 0.30

#: 默认演化代数（"演化 N 代"的 N）
DEFAULT_GENERATIONS = 200

#: 一次动作最多回传多少帧。超出时按 ``stride`` 抽样（结局判定仍逐代精确）。
#: 50×50 一帧是 2500 个字符，400 帧 ≈ 1 MB —— 这是给"通用视图 / 网页"也能吃得下的量级。
MAX_FRAMES = 400

#: 标准规则（Conway 的 B3/S23）
DEFAULT_RULE = "B3/S23"

BOUNDARY_TORUS = "torus"
BOUNDARY_DEAD = "dead"
#: 边界条件取值 -> 中文名（界面与终端共用同一套说法）
BOUNDARIES: Dict[str, str] = {
    BOUNDARY_TORUS: "环面（上下左右相连）",
    BOUNDARY_DEAD: "死边界（越界视为死细胞）",
}

#: 长期行为的四种结局 + 各自的说法
OUTCOME_RUNNING = "running"
OUTCOME_EXTINCT = "extinct"
OUTCOME_STATIC = "static"
OUTCOME_CYCLE = "cycle"
OUTCOME_LABELS: Dict[str, str] = {
    OUTCOME_RUNNING: "仍在演化",
    OUTCOME_EXTINCT: "已消亡",
    OUTCOME_STATIC: "静止不变",
    OUTCOME_CYCLE: "周期振荡",
}

#: 预置规则：规则串 -> 中文名（界面下拉框与终端 ``--rule`` 用的是同一份清单）
RULES: Dict[str, str] = {
    "B3/S23": "B3/S23 · 标准生命游戏",
    "B36/S23": "B36/S23 · HighLife（有复制器）",
    "B3/S12345": "B3/S12345 · 慢生长迷宫",
}

#: 空白开局：棋盘全空，由用户自己在界面上画（生命游戏最自然的玩法）
PATTERN_BLANK = "blank"

#: 预置图案：名字 -> 每行的字符画（``O`` 活、``.`` 空）。放置时居中。
PATTERNS: Dict[str, Tuple[str, ...]] = {
    # 每 4 代整体平移 (1,1)：最著名的"会走路"的结构
    "glider": (".O.",
               "..O",
               "OOO"),
    # 静止不变（周期 1）
    "block": ("OO",
              "OO"),
    # 周期 2 振荡子
    "blinker": ("OOO",),
    # 周期 3 的大振荡子
    "pulsar": ("..OOO...OOO..",
               ".............",
               "O....O.O....O",
               "O....O.O....O",
               "O....O.O....O",
               "..OOO...OOO..",
               ".............",
               "..OOO...OOO..",
               "O....O.O....O",
               "O....O.O....O",
               "O....O.O....O",
               ".............",
               "..OOO...OOO.."),
    # 每 30 代射出一架滑翔机：**无限增长**（棋盘上唯一不会周期化的结局）
    "gosper_gun": ("........................O...........",
                   "......................O.O...........",
                   "............OO......OO............OO",
                   "...........O...O....OO............OO",
                   "OO........O.....O...OO..............",
                   "OO........O...O.OO....O.O...........",
                   "..........O.....O.......O...........",
                   "...........O...O....................",
                   "............OO......................"),
    # 著名的"长寿者"（methuselah）：从 5 个细胞炸出一大片，很久以后才安定下来
    "r_pentomino": (".OO",
                    "OO.",
                    ".O."),
}

#: 图案名 -> 中文名
PATTERN_LABELS: Dict[str, str] = {
    PATTERN_BLANK: "空白（自己绘制）",
    "random": "随机播种",
    "glider": "滑翔机（每 4 代平移一格）",
    "pulsar": "脉冲星（周期 3）",
    "gosper_gun": "高斯帕滑翔机枪（无限增长）",
    "r_pentomino": "R 五连块（著名长寿者）",
}

#: 随机源可以传入 None / int（种子）/ numpy Generator 实例
RngLike = Union[None, int, np.random.Generator]


def _resolve_rng(rng: RngLike = None) -> np.random.Generator:
    """把 None / 种子 / Generator 实例统一转换成一个 numpy 随机源。

    用 ``default_rng``（PCG64）而不是旧式 ``RandomState``：同样的种子在同一个 numpy
    大版本内给出同一条序列，而 ``RandomState`` 只承诺"历史兼容"。

    注意：从 ``random.Random`` 换成 numpy 之后，**同一个种子不再产生同一个开局** ——
    可复现性只在同一实现内成立（这是本次重构被明确接受的代价之一）。
    """
    if isinstance(rng, np.random.Generator):
        return rng
    return np.random.default_rng(rng)


def _clamp_int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


# ----------------------------------------------------------------------
# 规则
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class LifeRule:
    """一条元胞自动机规则：``born``（死格新生所需邻居数）+ ``survive``（活格存活所需邻居数）。

    支持两种写法：``"B3/S23"``（现行写法）与 ``"23/3"``（老写法，是 **存活/新生** 的顺序，
    与现行写法相反 —— 解析时按有无 ``B``/``S`` 前缀区分，两种写法都能识别）。
    """

    born: FrozenSet[int] = frozenset({3})
    survive: FrozenSet[int] = frozenset({2, 3})

    @classmethod
    def parse(cls, text: Any) -> "LifeRule":
        """从规则串解析；无法识别时退回标准规则 ``B3/S23``。"""
        raw = str(text or "").strip().upper().replace(" ", "")
        if "/" not in raw:
            return cls()
        left, right = raw.split("/", 1)
        if left[:1] in ("B", "S"):                 # 现行写法：B<born>/S<survive>
            born_text = left[1:] if left[:1] == "B" else ""
            survive_text = right[1:] if right[:1] == "S" else right
        else:                                       # 老写法：<survive>/<born>
            born_text, survive_text = right, left

        def digits(chunk: str) -> FrozenSet[int]:
            return frozenset(int(ch) for ch in chunk if ch.isdigit() and ch != "9")

        return cls(digits(born_text), digits(survive_text))

    def to_string(self) -> str:
        """转回规范写法 ``B3/S23``（数字升序）。"""
        born = "".join(str(d) for d in sorted(self.born)) or ""
        survive = "".join(str(d) for d in sorted(self.survive)) or ""
        return f"B{born}/S{survive}"

    @property
    def label(self) -> str:
        """中文名（预置规则表里有就用它，否则只给出规则串）。"""
        text = self.to_string()
        return RULES.get(text, text)


@dataclass(frozen=True)
class LifeStep:
    """演化一代的结果。"""

    generation: int
    births: int          # 本代新生数
    deaths: int          # 本代死亡数
    population: int      # 本代结束时的活细胞总数
    elapsed: float = 0.0


class LifeWatch:
    """逐代演化的**判官**：检测状态重复，判定"消亡 / 静止 / 周期振荡"。

    它是"什么叫收敛"的唯一定义处，两条路径共用：

    * :meth:`LifeBoard.run` 用它跑完一段**有上限**的演化（终端 / 网页 / 通用视图那种
      "给参数就出结果"的场景，必须有个上限）；
    * 桌面视图的**实时播放**用它一代一代地看 —— 界面上不预先算好未来，也不设代数上限，
      一直演到消亡 / 进入周期（或者你按暂停），于是同一条轨迹在两边得到的结论完全一致。

    状态空间有限（2^(n·m) 种）而演化确定，所以状态序列迟早重复；但**瞬态长度没有上界**，
    所以"没等到重复"（:data:`OUTCOME_RUNNING`）只是一种当下的观察，不是结论。
    """

    __slots__ = ("outcome", "period", "period_start", "_seen")

    def __init__(self, board: "LifeBoard") -> None:
        self.outcome: str = OUTCOME_RUNNING
        self.period: int = 0
        self.period_start: int = 0
        #: 状态指纹 -> 首次出现的代数（内存只与"经历过的不同状态数"有关）
        self._seen: Dict[int, int] = {board.state_key(): board.generation}

    @property
    def settled(self) -> bool:
        """是否已经收敛（消亡 / 静止 / 周期振荡）。"""
        return self.outcome != OUTCOME_RUNNING

    @property
    def label(self) -> str:
        """结局的中文说法（周期振荡会带上周期长度）。"""
        if self.outcome == OUTCOME_CYCLE and self.period:
            return f"{OUTCOME_LABELS[OUTCOME_CYCLE]}（周期 {self.period}）"
        return OUTCOME_LABELS.get(self.outcome, self.outcome)

    def observe(self, board: "LifeBoard", step: LifeStep) -> str:
        """观察刚演化出的一代，返回当前结局（已经收敛后调用不会改变结论）。"""
        if self.settled:
            return self.outcome
        if step.population == 0:
            self.outcome = OUTCOME_EXTINCT
            return self.outcome
        key = board.state_key()
        first = self._seen.get(key)
        if first is None:
            self._seen[key] = step.generation
            return self.outcome
        period = step.generation - first
        self.period, self.period_start = period, first
        self.outcome = OUTCOME_STATIC if period == 1 else OUTCOME_CYCLE
        return self.outcome


@dataclass
class LifeRun:
    """一次「演化 N 代」的完整结果。

    ``frames`` 与 ``census`` **严格同长**（第 k 条对应同一代）：动画按帧播放，
    指标按帧取值，于是"跳帧"时两边永远一致。``outcome`` / ``period`` 是**逐代精确**判定的，
    与是否跳帧无关。
    """

    rows: int
    cols: int
    rule: str
    boundary: str
    density: float
    pattern: str
    generations: int                 # 请求的代数
    stride: int = 1                  # 帧采样步长（>1 表示每帧跨 stride 代）
    frames: List[str] = field(default_factory=list)
    census: List[Tuple[int, int, int, int]] = field(default_factory=list)   # (代, 活细胞, 生, 死)
    outcome: str = OUTCOME_RUNNING
    period: int = 0                  # outcome == cycle 时的周期长度
    period_start: int = 0            # 该周期最早出现的代数
    population: int = 0              # 末态活细胞数
    stop_generation: int = 0         # 实际演化到第几代（提前收敛时会小于 generations）
    elapsed: float = 0.0

    @property
    def outcome_label(self) -> str:
        """结局的中文说法（周期振荡会带上周期长度）。"""
        if self.outcome == OUTCOME_CYCLE and self.period:
            return f"{OUTCOME_LABELS[OUTCOME_CYCLE]}（周期 {self.period}）"
        return OUTCOME_LABELS.get(self.outcome, self.outcome)

    @property
    def density_now(self) -> float:
        """末态存活密度。"""
        total = self.rows * self.cols
        return self.population / total if total else 0.0

    @property
    def frame_count(self) -> int:
        """帧数（= ``census`` 长度）。"""
        return len(self.frames)

    def census_series(self) -> List[Dict[str, int]]:
        """人口曲线数据：``[{"gen": 代数, "population": 活细胞, …}, …]``。"""
        return [
            {"gen": gen, "population": population, "births": births, "deaths": deaths}
            for gen, population, births, deaths in self.census
        ]


# ----------------------------------------------------------------------
# 棋盘
# ----------------------------------------------------------------------
class LifeBoard:
    """生命游戏的棋盘（纯计算）。

    参数
    ----
    rows / cols : int
        棋盘尺寸，会被夹到 ``[MIN_SIZE, MAX_SIZE]``（``cols`` 省略时与 ``rows`` 相同）。
    rule : str | LifeRule
        规则串（如 ``"B3/S23"``）或已解析好的 :class:`LifeRule`。
    boundary : str
        ``"torus"``（环面，默认）或 ``"dead"``（死边界）。
    density : float
        随机播种时每个格子的初始存活概率（只影响 :meth:`randomize`）。
    rng : None | int | random.Random
        随机源，可以是种子（便于复现）。
    pattern : str
        开局图案名：``"blank"``（默认）表示全空、由界面上手绘；``"random"`` 表示按
        ``density`` 随机播种；其余取 :data:`PATTERNS` 里的预置图案。
    """

    def __init__(
        self,
        rows: int = DEFAULT_ROWS,
        cols: Optional[int] = None,
        rule: Union[str, LifeRule] = DEFAULT_RULE,
        boundary: str = BOUNDARY_TORUS,
        density: float = DEFAULT_DENSITY,
        rng: RngLike = None,
        pattern: str = "random",
    ) -> None:
        self.rows = _clamp_int(rows, MIN_SIZE, MAX_SIZE, DEFAULT_ROWS)
        self.cols = _clamp_int(cols if cols is not None else self.rows,
                               MIN_SIZE, MAX_SIZE, self.rows)
        self.rule = rule if isinstance(rule, LifeRule) else LifeRule.parse(rule)
        self.boundary = boundary if boundary in BOUNDARIES else BOUNDARY_TORUS
        self.density = min(1.0, max(0.0, float(density)))
        self.rng: random.Random = _resolve_rng(rng)
        self.pattern = str(pattern or "random")

        self.generation = 0
        self.population = 0
        #: 棋盘数据：``(rows, cols)`` 的布尔数组（``True`` = 活）
        self._alive = np.zeros((self.rows, self.cols), dtype=bool)
        self._build_rule_tables()

        self.seed_board(self.pattern, self.density)

    # ---------------- 基本属性 ----------------
    @property
    def node_count(self) -> int:
        """格子总数（画布、比例、指标都用它）。"""
        return self.rows * self.cols

    @property
    def shape(self) -> Tuple[int, int]:
        """``(行数, 列数)``。"""
        return self.rows, self.cols

    @property
    def rule_string(self) -> str:
        """规则串，如 ``"B3/S23"``。"""
        return self.rule.to_string()

    @property
    def rule_name(self) -> str:
        """规则的中文名。"""
        return self.rule.label

    @property
    def boundary_name(self) -> str:
        """边界条件的中文名。"""
        return BOUNDARIES.get(self.boundary, self.boundary)

    @property
    def pattern_name(self) -> str:
        """开局的中文名。"""
        return PATTERN_LABELS.get(self.pattern, self.pattern)

    @property
    def density_now(self) -> float:
        """当前存活密度。"""
        return self.population / self.node_count if self.node_count else 0.0

    # ---------------- 规则查找表 ----------------
    def _build_rule_tables(self) -> None:
        """把 ``born`` / ``survive`` 编译成两张 9 元查找表（下标 = 邻居数）。

        用查找表而不是 ``np.isin``：任意规则都走同一条向量化路径，而每次判定只是
        一次内存读取 —— 这是"规则可配置"与"快"之间最省事的折中。
        """
        self._born_lut = np.zeros(9, dtype=bool)
        self._survive_lut = np.zeros(9, dtype=bool)
        for count in self.rule.born:
            if 0 <= count <= 8:
                self._born_lut[count] = True
        for count in self.rule.survive:
            if 0 <= count <= 8:
                self._survive_lut[count] = True

    def resize(self, rows: Optional[int] = None, cols: Optional[int] = None) -> None:
        """改变棋盘尺寸（内容丢弃，按当前开局重排）。"""
        new_rows = self.rows if rows is None else _clamp_int(rows, MIN_SIZE, MAX_SIZE, self.rows)
        new_cols = self.cols if cols is None else _clamp_int(cols, MIN_SIZE, MAX_SIZE, self.cols)
        if (new_rows, new_cols) == (self.rows, self.cols):
            return
        self.rows, self.cols = new_rows, new_cols
        self._alive = np.zeros((new_rows, new_cols), dtype=bool)
        self.seed_board(self.pattern, self.density)

    def configure(self, rule: Optional[Union[str, LifeRule]] = None,
                  boundary: Optional[str] = None,
                  density: Optional[float] = None) -> bool:
        """更新规则 / 边界 / 密度，但**保留棋盘上现有的细胞**。

        界面上的玩法是"先画好开局，再改规则或边界，然后继续演化"，所以这些参数不能像
        重建那样把画面清掉。改动规则要重建查找表；改动边界什么都不用重建
        （边框是每一代现补的，没有预计算表）。
        返回是否真的发生了改动。
        """
        changed = False
        if rule is not None:
            new_rule = rule if isinstance(rule, LifeRule) else LifeRule.parse(rule)
            if new_rule != self.rule:
                self.rule = new_rule
                self._build_rule_tables()
                changed = True
        if density is not None:
            value = min(1.0, max(0.0, float(density)))
            if value != self.density:
                self.density = value
                changed = True
        if boundary in BOUNDARIES and boundary != self.boundary:
            self.boundary = boundary      # 边框是每一代现补的，没有预计算表要重建
            changed = True
        return changed

    # ---------------- 开局 ----------------
    def clear(self) -> None:
        """清空棋盘（全死），代数归零。"""
        self._alive[:] = False
        self.generation = 0
        self.population = 0

    def randomize(self, density: Optional[float] = None, rng: RngLike = None) -> None:
        """按密度随机播种（``rng`` 省略时用构造时的随机源）。"""
        if density is not None:
            self.density = min(1.0, max(0.0, float(density)))
        random_source = self.rng if rng is None else _resolve_rng(rng)
        # 一次抽满整块棋盘（行优先），比逐格 random() 快两个数量级
        self._alive = random_source.random((self.rows, self.cols)) < self.density
        self.generation = 0
        self._recount()

    def place(self, pattern: str, clear: bool = True) -> None:
        """把预置图案居中放在棋盘上（``clear=True`` 时先清空；放不下就按边界裁掉）。"""
        rows = PATTERNS.get(pattern)
        if clear:
            self.clear()
        if not rows:
            return
        height, width = len(rows), max(len(row) for row in rows)
        top = max(0, (self.rows - height) // 2)
        left = max(0, (self.cols - width) // 2)
        mask = np.array([[char in ("O", "o", "1", "#") for char in line.ljust(width)]
                         for line in rows], dtype=bool)
        target = self._alive[top:top + height, left:left + width]
        if target.size:
            target[:] = mask[: target.shape[0], : target.shape[1]]
        self.generation = 0
        self._recount()

    def seed_board(self, pattern: Optional[str] = None, density: Optional[float] = None) -> None:
        """按开局图案播种。

        * ``"blank"``（:data:`PATTERN_BLANK`）：全空 —— 界面上由用户自己画，这是默认玩法；
        * ``"random"``：按 ``density`` 随机播种；
        * 其余：把 :data:`PATTERNS` 里的预置图案居中放上去。
        """
        name = self.pattern if pattern is None else str(pattern)
        self.pattern = name
        if name == PATTERN_BLANK:
            self.clear()
        elif name in PATTERNS:
            self.place(name)
        else:
            self.pattern = "random"
            self.randomize(density)

    def _recount(self) -> None:
        self.population = int(np.count_nonzero(self._alive))

    # ---------------- 读写单个格子（供点击编辑） ----------------
    def is_alive(self, index: int) -> bool:
        row, col = divmod(int(index), self.cols)
        return bool(self._alive[row, col])

    def set_cell(self, index: int, alive: bool) -> None:
        """设置某个格子的状态（不改变代数：编辑的是"当前这一代"的棋盘）。"""
        row, col = divmod(int(index), self.cols)
        now = bool(alive)
        if bool(self._alive[row, col]) != now:
            self._alive[row, col] = now
            self.population += 1 if now else -1

    def toggle(self, index: int) -> bool:
        """翻转某个格子，返回翻转后的状态。"""
        alive = not self.is_alive(index)
        self.set_cell(index, alive)
        return alive

    def load(self, text: str) -> None:
        """按 0/1 字符串装载棋盘（与 :meth:`encode` 互为逆运算，不改变代数）。

        只覆盖字符串给出的那些格子（比棋盘短时其余保持原样），最后按**整块棋盘**重数
        活细胞 —— 于是"传进来半张棋盘"也不会让 :attr:`population` 与实际状态对不上。
        """
        values = np.frombuffer(str(text)[: self.node_count].encode("ascii", "replace"),
                               dtype=np.uint8)
        self._alive.reshape(-1)[: values.size] = values == ord("1")
        self._recount()

    def encode(self) -> str:
        """把棋盘压成 0/1 字符串（前端一次遍历即可还原）。

        走"字节数组 -> 字符串"（``np.where`` + ``tobytes``）而不是逐格拼字符：
        50×50 就是一次 2500 字节的转换。
        """
        chars = np.where(self._alive.reshape(-1), ord("1"), ord("0")).astype(np.uint8)
        return chars.tobytes().decode("ascii")

    def alive_indices(self) -> List[int]:
        """所有活细胞的下标（单位坐标，``r*cols+c``）。"""
        return [int(index) for index in np.flatnonzero(self._alive.reshape(-1))]

    def state_key(self) -> int:
        """状态指纹（用于周期检测）：压成位图再取 64 位哈希，不做整块状态比对。

        ``packbits`` 把 ``rows×cols`` 个布尔压到 1/8 体积（50×50 只剩 313 字节），
        哈希开销与内存随之下降；位序由 ``packbits`` 固定（大端、行优先），
        所以同一个状态永远得到同一个指纹。
        """
        return hash(np.packbits(self._alive).tobytes())

    # ---------------- 演化 ----------------
    def step(self) -> LifeStep:
        """演化一代（原地），返回本代的新生 / 死亡 / 活细胞数。

        整代只有几步数组运算：补边框 -> 8 次整块切片相加 -> 两张查找表判定。
        **没有逐格 Python 循环**，所以耗时与棋盘面积成正比，而与"当前有多少活细胞"
        无关（对极稀疏的开局反而不如逐格循环"省"，换来的是可预测的上限）。
        """
        started = time.perf_counter()
        alive = self._alive
        rows, cols = self.rows, self.cols

        # 一次性补一圈边框：死边界到此为止（外圈恒 0，天然正确）；环面则把四条边与
        # 四个角用"对边"赋值填上。随后两种边界走**同一段** 8 次切片求和，热路径无分支。
        padded = np.zeros((rows + 2, cols + 2), dtype=np.uint8)
        padded[1:-1, 1:-1] = alive
        if self.boundary == BOUNDARY_TORUS:
            padded[0, 1:-1] = alive[-1]
            padded[-1, 1:-1] = alive[0]
            padded[1:-1, 0] = alive[:, -1]
            padded[1:-1, -1] = alive[:, 0]
            padded[0, 0] = alive[-1, -1]
            padded[0, -1] = alive[-1, 0]
            padded[-1, 0] = alive[0, -1]
            padded[-1, -1] = alive[0, 0]

        neighbours = (padded[0:rows, 0:cols] + padded[0:rows, 1:cols + 1]
                      + padded[0:rows, 2:cols + 2] + padded[1:rows + 1, 0:cols]
                      + padded[1:rows + 1, 2:cols + 2] + padded[2:rows + 2, 0:cols]
                      + padded[2:rows + 2, 1:cols + 1] + padded[2:rows + 2, 2:cols + 2])

        new = ((self._born_lut[neighbours] & ~alive)
               | (self._survive_lut[neighbours] & alive))
        births = int(np.count_nonzero(new & ~alive))
        deaths = int(np.count_nonzero(alive & ~new))
        population = int(np.count_nonzero(new))

        self._alive = new
        self.generation += 1
        self.population = population
        return LifeStep(self.generation, births, deaths, population,
                        time.perf_counter() - started)

    def run(self, generations: Optional[int] = None,
            progress: Optional[Callable[[int, int], None]] = None,
            cancel: Optional[Any] = None,
            max_frames: int = MAX_FRAMES,
            watch: Optional[LifeWatch] = None) -> LifeRun:
        """连续演化若干代（**有上限**），返回末态 + 人口曲线 + 结局判定。

        一旦**状态重复**（消亡 / 静止 / 周期振荡，由 :class:`LifeWatch` 判定）就提前停止 ——
        再算下去只是重复同一段循环，没有新信息。界面上那个"不设代数上限"的实时播放走
        :meth:`step` + :class:`LifeWatch`（见桌面视图），两者共用同一套判定。

        * ``progress(代数, 总代数)`` 每代回调一次（后台线程用它刷新进度，主线程不要直接画图）；
        * ``cancel`` 传 ``threading.Event`` 可中途停止（调用方自己检查返回值即可）；
        * 帧数超过 ``max_frames`` 时按 ``stride`` 抽样（``census`` 同步抽样，结局判定仍逐代精确）。
        """
        total = DEFAULT_GENERATIONS if generations is None else max(0, int(generations))
        # 帧数 = 初始帧 + total/stride 帧，所以按 (max_frames - 1) 折算 stride，
        # 否则 total 恰好等于上限时会多出一帧、被 CHART_SPECS 的 limit 截掉末帧。
        stride = max(1, math.ceil(total / max(1, int(max_frames) - 1)))
        started = time.perf_counter()
        cancelled = getattr(cancel, "is_set", None)      # 通常是 threading.Event
        judge = watch or LifeWatch(self)

        run = LifeRun(
            rows=self.rows, cols=self.cols, rule=self.rule_string, boundary=self.boundary,
            density=self.density, pattern=self.pattern, generations=total, stride=stride,
            population=self.population, stop_generation=0,
        )
        run.frames.append(self.encode())
        run.census.append((self.generation, self.population, 0, 0))

        for offset in range(1, total + 1):
            if cancelled is not None and cancelled():
                break
            step = self.step()
            outcome = judge.observe(self, step)

            if offset % stride == 0 or outcome != OUTCOME_RUNNING:
                # 结局一旦确定就必定收帧：末帧必须能在画布上看到（不能因为 stride 被抽掉）
                run.frames.append(self.encode())
                run.census.append((step.generation, step.population, step.births, step.deaths))

            if progress is not None and (offset % 10 == 0 or offset == total):
                progress(step.generation, total)
            if outcome != OUTCOME_RUNNING:
                break

        run.outcome = judge.outcome
        run.period = judge.period
        run.period_start = judge.period_start
        run.population = self.population
        run.stop_generation = self.generation
        run.elapsed = time.perf_counter() - started
        return run


def encode_cells(board: LifeBoard) -> Dict[str, Any]:
    """把棋盘压成"尺寸 + 0/1 掩码"，供前端极轻量地还原（与渗流的 ``encode_edges`` 同构）。"""
    return {
        "rows": board.rows,
        "cols": board.cols,
        "cells": board.encode(),
        "alive": board.population,
    }


# ----------------------------------------------------------------------
# 批量统计：初始密度 -> 长期结局
# ----------------------------------------------------------------------
@dataclass
class DensityResult:
    """固定初始密度下重复若干次实验的统计结果。"""

    density: float
    trials: int
    generations: int
    #: 演化到 N 代上限时仍"没结束"（既没消亡、也没收敛到周期）的次数
    ongoing: int = 0
    extinct: int = 0
    settled: int = 0                 # 静止 + 周期（都属于"收敛了"）
    mean_population: float = 0.0     # 末态活细胞数均值
    mean_life: float = 0.0           # 平均"收敛代数"（消亡 / 周期化发生在第几代）
    elapsed: float = 0.0

    @property
    def survival_rate(self) -> float:
        """演化 N 代后仍有活细胞的比例（"活下来"的直观指标）。"""
        return (self.trials - self.extinct) / self.trials if self.trials else 0.0

    @property
    def settled_rate(self) -> float:
        """收敛到静止 / 周期的比例（越高说明越早"热寂"）。"""
        return self.settled / self.trials if self.trials else 0.0


def _sample_density(rows: int, cols: int, density: float, generations: int,
                    boundary: str, rule: str, rng: np.random.Generator) -> Tuple[bool, bool, int, int]:
    """一次实验：返回 ``(是否有活细胞, 是否收敛到周期, 末态活细胞数, 收敛代数)``。"""
    board = LifeBoard(rows=rows, cols=cols, rule=rule, boundary=boundary,
                      density=density, rng=rng, pattern="random")
    run = board.run(generations)
    settled = run.outcome in (OUTCOME_STATIC, OUTCOME_CYCLE)
    return board.population > 0, settled, board.population, run.stop_generation


def scan_survival(densities: Sequence[float], rows: int = DEFAULT_ROWS,
                  cols: Optional[int] = None, generations: int = DEFAULT_GENERATIONS,
                  trials: int = 100, rule: str = DEFAULT_RULE,
                  boundary: str = BOUNDARY_TORUS, rng: RngLike = None,
                  progress: Optional[Callable[[int, int, DensityResult], None]] = None,
                  cancel: Optional[Any] = None) -> List[DensityResult]:
    """扫描「初始密度 -> 长期结局」：每个密度重复 ``trials`` 次独立实验。

    这是在回答一个比渗流更模糊的问题：**没有一个确定的临界密度**。密度太低时，
    随机播种很难产生能持续自我维持的结构，很快消亡；密度太高时，棋盘迅速僵化成大片
    静止块与短周期振荡；只有中间一段（大约 0.2–0.4）才容易长出长时间活跃的结构。
    因此这里叫"相图"而不是"相变"，``survival_rate`` 是一条**平缓的曲线**，不是阶跃。
    """
    columns = cols if cols is not None else rows
    random_source = _resolve_rng(rng)
    cancelled = getattr(cancel, "is_set", None)
    results: List[DensityResult] = []
    total_points = len(densities)

    for position, density in enumerate(densities, start=1):
        started = time.perf_counter()
        alive_count = settled_count = population_sum = life_sum = 0
        completed = 0
        for _ in range(max(1, int(trials))):
            if cancelled is not None and cancelled():
                break
            alive, settled, population, life = _sample_density(
                rows, columns, float(density), generations, boundary, rule, random_source)
            alive_count += 1 if alive else 0
            settled_count += 1 if settled else 0
            population_sum += population
            life_sum += life
            completed += 1
        trials_done = max(1, completed)
        extinct = trials_done - alive_count
        results.append(DensityResult(
            density=float(density),
            trials=trials_done,
            generations=int(generations),
            extinct=extinct,
            settled=settled_count,
            # "仍在演化" = 既没消亡、也没收敛到周期（跑满 N 代还在变）
            ongoing=trials_done - extinct - settled_count,
            mean_population=population_sum / trials_done,
            mean_life=life_sum / trials_done,
            elapsed=time.perf_counter() - started,
        ))
        if progress is not None:
            progress(position, total_points, results[-1])
    return results


# ----------------------------------------------------------------------
# 直接运行本文件时的自检：教科书结论（这里是最值得断言的地方）
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    try:  # Windows 控制台默认 GBK，需要切到 UTF-8 才能正常输出中文
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    print("=" * 70)
    print("生命游戏自检：教科书结论")
    print("=" * 70)

    # 1. 方块：静止不变（周期 1）
    block = LifeBoard(rows=12, cols=12, boundary=BOUNDARY_DEAD, pattern="block")
    run_block = block.run(20)
    print(f"方块（静止物）      : 结局 = {run_block.outcome_label}，"
          f"第 {run_block.stop_generation} 代收敛，活细胞 {run_block.population}")
    assert run_block.outcome == OUTCOME_STATIC, "方块应当静止不变"
    assert run_block.population == 4, "方块应当始终是 4 个活细胞"

    # 2. 闪烁器：周期 2 振荡子
    blinker = LifeBoard(rows=12, cols=12, boundary=BOUNDARY_DEAD, pattern="blinker")
    run_blinker = blinker.run(20)
    print(f"闪烁器（振荡子）    : 结局 = {run_blinker.outcome_label}，"
          f"第 {run_blinker.stop_generation} 代收敛")
    assert run_blinker.outcome == OUTCOME_CYCLE and run_blinker.period == 2, "闪烁器周期应为 2"

    # 3. 脉冲星：周期 3 振荡子
    pulsar = LifeBoard(rows=20, cols=20, boundary=BOUNDARY_DEAD, pattern="pulsar")
    run_pulsar = pulsar.run(30)
    print(f"脉冲星（大振荡子）  : 结局 = {run_pulsar.outcome_label}")
    assert run_pulsar.period == 3, "脉冲星周期应为 3"

    # 4. 滑翔机：每 4 代整体平移 (1, 1)（死边界下才能看到"位移"本身）
    glider = LifeBoard(rows=20, cols=20, boundary=BOUNDARY_DEAD, pattern="glider")
    start = {(r, c) for r, c in (divmod(i, glider.cols) for i in glider.alive_indices())}
    for _ in range(4):
        glider.step()
    after = {(r, c) for r, c in (divmod(i, glider.cols) for i in glider.alive_indices())}
    shifted = {(r + 1, c + 1) for r, c in start}
    print(f"滑翔机（4 代平移）  : {sorted(start)} -> {sorted(after)}")
    assert after == shifted, "滑翔机每 4 代应当整体平移 (1, 1)"

    # 5. 高斯帕滑翔机枪：每 30 代射出一架滑翔机 —— 棋盘上唯一"不会收敛"的结局
    gun = LifeBoard(rows=60, cols=60, boundary=BOUNDARY_DEAD, pattern="gosper_gun")
    gun_start = gun.population
    run_gun = gun.run(40)
    print(f"滑翔机枪（无限增长）: 第 0 代 {gun_start} 个活细胞 -> "
          f"第 {run_gun.stop_generation} 代 {run_gun.population} 个，结局 = {run_gun.outcome_label}")
    assert run_gun.outcome == OUTCOME_RUNNING, "滑翔机枪不应在 40 代内收敛"
    assert run_gun.population > gun_start, "滑翔机枪应当持续增长（枪本身 36 个细胞 + 射出的滑翔机）"

    # 6. R 五连块：著名的"长寿者"（5 个细胞撑了几百代）
    #    注意：文献上"第 1103 代安定下来、最终 116 个细胞"说的是**无界平面**；
    #    有限棋盘上它喷出的滑翔机会撞墙死掉，安定代数并不相同，所以这里只断言"没收敛"。
    pentomino = LifeBoard(rows=40, cols=40, boundary=BOUNDARY_DEAD, pattern="r_pentomino")
    run_pentomino = pentomino.run(200)
    print(f"R 五连块（长寿者）  : 200 代后仍有 {run_pentomino.population} 个活细胞，"
          f"结局 = {run_pentomino.outcome_label}")
    assert run_pentomino.outcome == OUTCOME_RUNNING, "R 五连块在 200 代内不应收敛"

    # 7. 图案表本身的健全性：每行等宽（写错一个字符就会在这里暴露）
    for name, rows_text in PATTERNS.items():
        width = len(rows_text[0])
        assert all(len(line) == width for line in rows_text), f"图案 {name} 的行宽不一致"
    print(f"图案表              : {len(PATTERNS)} 个图案，行宽自洽")

    # 8. 环面上"必然周期化"：确定性 + 有限状态 => 一定进入周期。
    #    但**瞬态长度没有上界**：状态空间是 2^(格子数)，小棋盘上眨眼就收敛，
    #    大棋盘上"等到它重复"可能比宇宙寿命还久 —— 所以下面要分成两组来看。
    settled = []
    for seed in range(1, 9):
        small = LifeBoard(rows=12, cols=12, density=0.5, rng=seed)
        small_run = small.run(3000)
        assert small_run.outcome in (OUTCOME_EXTINCT, OUTCOME_STATIC, OUTCOME_CYCLE), \
            f"12×12 环面第 {seed} 号实验应当收敛"
        settled.append(small_run.stop_generation)
    print(f"环面 12×12 × 8 次   : 全部收敛，收敛代数 {settled}")

    big = LifeBoard(rows=20, cols=20, density=0.3, rng=7)
    run_big = big.run(600)
    print(f"环面 20×20（600 代）: 结局 = {run_big.outcome_label} "
          f"（瞬态可以远超我们愿意等的时间，这正是 2^400 个状态的威力）")

    # 9. 密度扫描：极低密度会消亡、极高密度会僵化
    table = scan_survival((0.05, 0.10, 0.30, 0.60, 0.90), rows=30, generations=200,
                          trials=12, rng=20260915)
    print("\n初始密度 -> 长期结局（30×30，200 代，每点 12 次）")
    print(f"{'密度':>6}{'存活率':>10}{'收敛率':>10}{'平均末态活细胞':>16}{'平均收敛代数':>14}")
    print("-" * 70)
    for res in table:
        print(f"{res.density:>6.2f}{res.survival_rate:>10.2f}{res.settled_rate:>10.2f}"
              f"{res.mean_population:>16.1f}{res.mean_life:>14.1f}")
    print("-" * 70)
    assert table[0].survival_rate <= table[2].survival_rate, "极低密度更容易消亡"
    print("提示：密度太低时随机结构难以自维持（很快消亡），太高时迅速僵化成静止块 / 短周期；")
    print("      中间一段（约 0.2–0.4）最容易长出长时间活跃的结构 —— 曲线是平缓的，不是阶跃。")
    print("\n全部自检通过 ✔")
