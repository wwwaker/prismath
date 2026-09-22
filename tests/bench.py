"""重构护栏 2：微基准（把"优化了多少"量出来成交付物）。

    python -m tests.bench                    # 全部模型
    python -m tests.bench life_game          # 只跑一个
    python -m tests.bench --list             # 看有哪些

**为什么放在 ``tests/`` 而不是内核里挂一个 ``--bench``**（原先的计划是后者）：
四个 ``model.py`` 现在是**完全自包含**的纯内核（只 import 标准库，连相对导入都没有），
它们的 ``__main__`` 注释也明确支持"直接运行本文件"（``python path/to/model.py``）。
往内核里加一个 ``from .._bench import Bench`` 会让这条用法失效（相对导入要求包上下文），
而"内核可以单独拷走、单独跑"是这个仓库值得保住的性质。把基准放在测试侧，内核一行都不用改。

**测法**（数字要写进 README / 文档，所以口径必须写死）：

* 取**中位数**而非均值，并附波动范围 —— 波动大就说明这个数字不可信，别往文档里写；
* 先预热一次再计时：排除首次分配内存、首次建邻居表之类的开销，测"稳态"而不是"第一次"；
* 每个用例单独一行，规模写进标签（"120×120 单代"这种），否则数字没有意义；
* 慢用例（秒级）把 ``repeat`` 调小甚至 ``warmup=0``，但**不能**改参数来"让数字好看"：
  参数要与自检 / CLI 默认玩法一致，否则优化成果跟用户感受没关系。
"""

from __future__ import annotations

import platform
import statistics
import sys
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = ["Bench", "BENCHES", "main", "timeit"]


def environment() -> str:
    """一行环境描述：性能数字离开这套环境就不保证复现，所以跟数字一起打印。"""
    try:
        import numpy as np

        numpy_info = f"numpy {np.__version__}"
    except ImportError:  # pragma: no cover - numpy 现在是必需依赖，仅为打印时不炸
        numpy_info = "numpy 未安装"
    return (f"Python {platform.python_version()} · {numpy_info} · "
            f"{platform.system()} {platform.machine()}")


def timeit(fn: Callable[[], object], *, repeat: int = 5,
           warmup: int = 1) -> Tuple[float, float]:
    """测 ``fn`` 的单次耗时，返回 ``(中位数秒, 极差秒)``。"""
    for _ in range(max(warmup, 0)):
        fn()
    samples: List[float] = []
    for _ in range(max(repeat, 1)):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    if len(samples) == 1:
        return samples[0], 0.0
    return statistics.median(samples), max(samples) - min(samples)


def _fmt(seconds: float) -> str:
    """自动选单位：够小就用 µs，免得文档里全是 0.00048。"""
    if seconds <= 0.0:
        return "0"
    if seconds < 1e-3:
        return f"{seconds * 1e6:.1f} µs"
    if seconds < 1.0:
        return f"{seconds * 1e3:.2f} ms"
    return f"{seconds:.2f} s"


class Bench:
    """一组微基准：``case(...)`` 若干次后 ``report()`` 出表。"""

    def __init__(self, title: str) -> None:
        self.title = title
        self._rows: List[Tuple[str, str, str, str]] = []

    def case(self, label: str, fn: Callable[[], object], *, unit: str = "次",
             repeat: int = 5, warmup: int = 1, note: str = "") -> "Bench":
        """登记一个用例。``label`` 里应当写清规模，``note`` 里写清口径上的坑。"""
        median, spread = timeit(fn, repeat=repeat, warmup=warmup)
        self._rows.append((label, f"{_fmt(median)} / {unit}",
                           f"±{_fmt(spread)}" if spread else "—", note))
        return self

    def report(self) -> None:
        print()
        print("=" * 80)
        print(f"微基准：{self.title}")
        print("=" * 80)
        print(environment())
        print("口径：每项取 repeat 次的中位数（已预热）；波动大 = 这个数字不可信，别写进文档。")
        print("-" * 80)
        width = max([len(row[0]) for row in self._rows] + [8])
        for label, value, spread, note in self._rows:
            line = f"  {label.ljust(width)}  {value.rjust(13)}  {spread.rjust(12)}"
            print(f"{line}  {note}".rstrip())
        print("-" * 80)


# ----------------------------------------------------------------------
# 每个模型的用例：参数要与自检 / CLI 的默认玩法一致，否则数字与用户感受无关
# ----------------------------------------------------------------------
def bench_life_game() -> None:
    from awe_math.models.life_game.model import LifeBoard, scan_survival

    bench = Bench("生命游戏内核（环面 B3/S23）")
    board_50 = LifeBoard(rows=50, cols=50, density=0.30, rng=7)
    board_120 = LifeBoard(rows=120, cols=120, density=0.30, rng=7)
    bench.case("50×50 随机播种 0.30 · 单代", board_50.step, unit="代")
    bench.case("120×120 随机播种 0.30 · 单代", board_120.step, unit="代")
    bench.case("50×50 · 连推 300 代", 
               lambda: LifeBoard(rows=50, cols=50, density=0.30, rng=7).run(300),
               unit="次", repeat=3, note="含 census 与周期检测")
    bench.case("30×30 密度扫描 5 点 × 12 次 × 200 代",
               lambda: scan_survival([0.05, 0.10, 0.30, 0.60, 0.90], rows=30, cols=30,
                                     generations=200, trials=12, rng=7),
               unit="次", repeat=1, warmup=0, note="自检里那条扫描表")
    bench.report()


def bench_buffon_needle() -> None:
    from awe_math.models.buffon_needle.model import BuffonNeedle

    bench = Bench("蒲丰投针内核（L/d = 0.8）")
    bench.case("1 万针 · 一次投掷",
               lambda: BuffonNeedle(ratio=0.8, throws=10_000, rng=7).throw(), unit="次")
    bench.case("10 万针 · 一次投掷",
               lambda: BuffonNeedle(ratio=0.8, throws=100_000, rng=7).throw(), unit="次")
    bench.case("100 万针 · 一次投掷",
               lambda: BuffonNeedle(ratio=0.8, throws=1_000_000, rng=7).throw(),
               unit="次", repeat=1, warmup=0, note="当前实现的算力上限")
    bench.case("8 组 × 500 根 · 收敛过程",
               lambda: BuffonNeedle(ratio=0.8, throws=500, rng=7).converge(8), unit="次")
    bench.case("100 组 × 1000 根 · 收敛过程",
               lambda: BuffonNeedle(ratio=0.8, throws=1000, rng=7).converge(100),
               unit="次", repeat=1, warmup=0, note="自检里的多组重复")
    bench.report()


def bench_site_percolation() -> None:
    from awe_math.models.site_percolation.model import (
        SitePercolation,
        batch_spread_probability,
        scan_curve,
    )

    bench = Bench("点渗流内核（方格网，40×40；p 取在 p_c 附近最费时）")
    bench.case("贯通判据 · 批量 300 次",
               lambda: batch_spread_probability(rows=40, cols=40, p=0.5927, trials=300,
                                                rng=11),
               unit="次", repeat=3)
    bench.case("贯通判据 · 扫描 5 个 p 各 100 次",
               lambda: scan_curve([0.52, 0.56, 0.60, 0.64, 0.68], rows=40, cols=40,
                                  trials=100, rng=11),
               unit="次", repeat=1, warmup=0, note="扫描是「点数 × 试验数」的重复劳动")
    bench.case("起点判据 · 随机单点 300 次",
               lambda: batch_spread_probability(rows=32, cols=32, p=0.6, trials=300,
                                                criterion="origin", inject="random",
                                                rng=11),
               unit="次", repeat=3, note="要跑完整蔓延才拿到顶/底")
    bench.case("面积判据 · 中心附近 300 次",
               lambda: batch_spread_probability(rows=32, cols=32, p=0.6, trials=300,
                                                criterion="area", inject="center",
                                                rng=11),
               unit="次", repeat=3)
    bench.case("三角网 · 贯通批量 300 次",
               lambda: batch_spread_probability(rows=40, cols=40, p=0.5, trials=300,
                                                lattice="triangular", rng=11),
               unit="次", repeat=3)
    bench.case("单次蔓延（含分层，界面用）",
               lambda: SitePercolation(rows=40, cols=40, p=0.62, inject="top",
                                       rng=11).simulate(),
               unit="次", repeat=5, note="含建边表 + 逐簇扫描")
    bench.report()


def bench_percolation() -> None:
    from awe_math.models.percolation.model import (
        PercolationGrid,
        batch_percolation_probability,
        scan_curve,
    )

    bench = Bench("边渗流内核（方格网 40×40，p 取在 p_c 附近最费时）")
    bench.case("贯通判据 · 无向批量 300 次",
               lambda: batch_percolation_probability(rows=40, cols=40, p=0.5, trials=300,
                                                     rng=11),
               unit="次", repeat=3, note="无向模式走并查集（最热的一段）")
    bench.case("贯通判据 · 扫描 5 个 p 各 100 次",
               lambda: scan_curve([0.42, 0.46, 0.50, 0.54, 0.58], rows=40, cols=40,
                                  trials=100, rng=11),
               unit="次", repeat=1, warmup=0, note="扫描是「点数 × 试验数」的重复劳动")
    bench.case("贯通判据 · 有向下右批量 300 次",
               lambda: batch_percolation_probability(rows=40, cols=40, p=0.6447, trials=300,
                                                     direction="down_right", rng=11),
               unit="次", repeat=3, note="有向模式没有并查集快路径，走 BFS")
    bench.case("起点判据 · 随机单点 300 次",
               lambda: batch_percolation_probability(rows=32, cols=32, p=0.5, trials=300,
                                                     criterion="origin", inject="random",
                                                     rng=11),
               unit="次", repeat=3)
    bench.case("面积判据 · 中心单点 300 次",
               lambda: batch_percolation_probability(rows=32, cols=32, p=0.5, trials=300,
                                                     criterion="area", inject="center",
                                                     rng=11),
               unit="次", repeat=3)
    bench.case("三角网 · 贯通批量 300 次",
               lambda: batch_percolation_probability(rows=40, cols=40, p=0.5, trials=300,
                                                     lattice="triangular", rng=11),
               unit="次", repeat=3, note="斜边数组里有越界占位，最容易被改坏")
    bench.case("单次模拟（含分层，界面用）",
               lambda: PercolationGrid(rows=40, cols=40, p=0.5, inject="top",
                                       rng=11).simulate(),
               unit="次", repeat=5)
    bench.report()


def bench_n_body() -> None:
    from awe_math.models.n_body.model import (
        DEFAULT_DT,
        NBody,
        SCENARIO_CLUSTER,
        SCENARIO_DISK,
        SCENARIO_FIGURE_EIGHT,
        build_scenario,
    )

    bench = Bench("万有引力多星内核（速度 Verlet，O(N^2) 的力计算就是全部成本）")

    def body(scenario: str, stars=None, softening=None, dt=DEFAULT_DT) -> NBody:
        preset = build_scenario(scenario, stars=stars, seed=7)
        return NBody(preset.positions, preset.velocities, preset.masses,
                     dt=dt, softening=preset.softening if softening is None else softening,
                     trail=0, scenario=preset.key)

    bench.case("8 字三体（3 颗）· 单步",
               lambda: body(SCENARIO_FIGURE_EIGHT).step(), unit="步")
    bench.case("8 字三体 · 积分一个周期（dt = 0.002）",
               lambda: body(SCENARIO_FIGURE_EIGHT, dt=0.002).run(frames=3163, substeps=1),
               unit="次", repeat=3, note="自检里那条回位偏差的口径")
    bench.case("随机星团 24 颗 · 单步",
               lambda: body(SCENARIO_CLUSTER).step(), unit="步")
    bench.case("星系盘 60 颗 · 单步",
               lambda: body(SCENARIO_DISK).step(), unit="步")
    bench.case("星系盘 60 颗 · 600 帧 × 6 子步",
               lambda: body(SCENARIO_DISK).run(frames=600, substeps=6),
               unit="次", repeat=3, note="桌面实时播放一帧 = 6 子步")
    bench.case("随机星团 200 颗 · 单步",
               lambda: body(SCENARIO_CLUSTER, stars=200).step(),
               unit="步", repeat=3, note="代价随 N² 增长，界面上的实时播放上限就在这附近")
    bench.report()


#: 模型名 -> 基准函数（新增模型时在这里加一行即可）
BENCHES: Dict[str, Callable[[], None]] = {
    "life_game": bench_life_game,
    "buffon_needle": bench_buffon_needle,
    "site_percolation": bench_site_percolation,
    "percolation": bench_percolation,
    "n_body": bench_n_body,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    names = [a for a in args if not a.startswith("-")]
    if "--list" in args or not names:
        for name in BENCHES:
            print(f"{name}")
        return 0
    if "all" in names:
        names = list(BENCHES)
    for name in names:
        if name not in BENCHES:
            print(f"没有这个模型的基准：{name}（可选：{', '.join(BENCHES)}）", file=sys.stderr)
            return 2
        BENCHES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
