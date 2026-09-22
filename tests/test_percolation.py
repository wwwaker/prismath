"""边渗流内核：向量化重写的**等价性**护栏 + 判据语义（与 ``test_site_percolation`` 同构）。

这次改动的形状：边的生成从"逐边 Python 随机"改成"一次抽满 numpy 数组"，蔓延从
``deque`` 逐点出队改成**预编译邻居表 + 逐层推进**。于是需要钉住的不是某个数字，而是：

1. **邻居表**必须与 ``_candidate_neighbors`` + ``direction_allows`` 逐条一致；
2. **逐层推进**必须与"用公开接口 ``neighbors()`` 写的朴素 BFS"得到相同的浸润集合、
   相同的分层与相同的判定；
3. **"有没有纵贯簇"的快路径**（顶行整行一次推进）必须与"逐簇扫描"答案一致；
4. **两种表示必须互相对得上**：``bytes`` 掩码 / 四张分类型边表 / ``is_open`` /
   ``iter_open_edges`` / ``open_edge_count`` 说的必须是同一件事 —— 这是"缓存不落后于
   真相"的护栏；
5. 无向模式下**并查集与 BFS 必须同答案**（两条独立算法互为对照）。

有了这些，自检里那些 p_c 表数字的浮动就只是随机源换代造成的噪声。
"""

from __future__ import annotations

import unittest
from collections import deque
from typing import Dict, List, Sequence, Set, Tuple

from awe_math.models.percolation.model import (
    PercolationGrid,
    batch_percolation_probability,
    encode_edges,
)

#: 覆盖全部格子类型 × 全部方向模式
COMBOS: Tuple[Tuple[str, str], ...] = tuple(
    (lattice, direction)
    for lattice in ("square", "triangular")
    for direction in ("undirected", "no_up", "down_right", "down_left")
)


def _naive_bfs(grid: PercolationGrid, origins: Sequence[int],
               ) -> Tuple[Set[int], bool, bool, Dict[int, int]]:
    """参照实现：用公开接口 ``neighbors()`` 做双端队列 BFS（旧代码的形状）。

    返回 ``(浸润集合, 是否碰到顶行, 是否碰到底行, 每个节点的层号)``。
    """
    cols = grid.cols
    last_row_start = (grid.rows - 1) * cols
    seen: Set[int] = set()
    depth_of: Dict[int, int] = {}
    queue: deque = deque()
    for index in origins:
        if index not in seen:
            seen.add(index)
            depth_of[index] = 0
            queue.append(index)
    while queue:
        index = queue.popleft()
        for neighbour in grid.neighbors(index):
            if neighbour not in seen:
                seen.add(neighbour)
                depth_of[neighbour] = depth_of[index] + 1
                queue.append(neighbour)
    return (seen,
            any(index < cols for index in seen),
            any(index >= last_row_start for index in seen),
            depth_of)


class NeighbourTableTest(unittest.TestCase):
    """邻居表 = 「几何 + 方向 + 流通」的编译结果，必须与逐点判定逐条一致。"""

    def test_matches_candidate_neighbors_when_all_edges_open(self) -> None:
        """``p = 1``（所有边都通）时应等于纯几何结果 —— 最能暴露"少一条边"。"""
        for lattice, direction in COMBOS:
            with self.subTest(lattice=lattice, direction=direction):
                grid = PercolationGrid(rows=6, cols=5, p=1.0, lattice=lattice,
                                       direction=direction, rng=1)
                expected = {
                    (index, neighbour)
                    for index in range(grid.node_count)
                    for neighbour, dr, dc in grid._candidate_neighbors(index)
                    if grid.direction_allows(dr, dc)
                }
                self.assertEqual(self._walk(grid), expected)

    def test_matches_candidate_neighbors_on_random_grids(self) -> None:
        for lattice, direction in COMBOS:
            for p in (0.3, 0.6, 0.9):
                with self.subTest(lattice=lattice, direction=direction, p=p):
                    grid = PercolationGrid(rows=6, cols=5, p=p, lattice=lattice,
                                           direction=direction, rng=7)
                    self.assertEqual(self._walk(grid), self._walk_naive(grid))

    @staticmethod
    def _walk(grid: PercolationGrid) -> Set[Tuple[int, int]]:
        """邻居表里"这一步真的能走"的有向对（查流通掩码）。"""
        return {
            (index, neighbour)
            for index, entries in enumerate(grid._nbr)
            for neighbour, eid in entries
            if grid._open_bytes[eid]
        }

    @staticmethod
    def _walk_naive(grid: PercolationGrid) -> Set[Tuple[int, int]]:
        """逐点判定版：几何相邻 + 方向允许 + 这条边流通。"""
        return {
            (index, neighbour)
            for index in range(grid.node_count)
            for neighbour, dr, dc in grid._candidate_neighbors(index)
            if grid.direction_allows(dr, dc)
        }


class RepresentationTest(unittest.TestCase):
    """``bytes`` 掩码 / 分类型边表 / ``is_open`` / 迭代器必须是同一件事。"""

    def test_sizes_line_up(self) -> None:
        for lattice, _direction in (("square", "undirected"), ("triangular", "undirected")):
            with self.subTest(lattice=lattice):
                grid = PercolationGrid(rows=7, cols=6, p=0.5, lattice=lattice, rng=3)
                self.assertEqual(len(grid._open_bytes), len(grid._edge_pairs))
                self.assertEqual(len(grid._edge_pairs), grid.total_edge_count())

    def test_mask_and_tables_agree(self) -> None:
        for lattice, direction in COMBOS:
            with self.subTest(lattice=lattice, direction=direction):
                grid = PercolationGrid(rows=6, cols=5, p=0.55, lattice=lattice,
                                       direction=direction, rng=5)
                self.assertEqual(sum(grid._open_bytes), grid.open_edge_count())
                self.assertEqual(set(grid.iter_open_edges()),
                                 set(grid.iter_all_edges()) & {
                                     pair for pair in grid.iter_all_edges()
                                     if grid.is_open(*pair)
                                 })

    def test_is_open_is_symmetric(self) -> None:
        grid = PercolationGrid(rows=6, cols=6, p=0.4, rng=11)
        for a, b in grid.iter_all_edges():
            with self.subTest(edge=(a, b)):
                self.assertEqual(grid.is_open(a, b), grid.is_open(b, a))

    def test_encode_edges_layout(self) -> None:
        square = PercolationGrid(rows=5, cols=4, p=0.5, lattice="square", rng=9)
        payload = encode_edges(square)
        self.assertEqual(set(payload), {"h", "v"})
        self.assertEqual(len(payload["h"]), 5 * 3)
        self.assertEqual(len(payload["v"]), 4 * 4)
        self.assertEqual(payload["h"].count("1") + payload["v"].count("1"),
                         square.open_edge_count())

        triangle = PercolationGrid(rows=5, cols=4, p=0.5, lattice="triangular", rng=9)
        payload = encode_edges(triangle)
        self.assertEqual(set(payload), {"h", "dl", "dr"})
        for key in ("dl", "dr"):
            with self.subTest(key=key):
                self.assertEqual(len(payload[key]), 4 * 4)


class TraversalEquivalenceTest(unittest.TestCase):
    """逐层推进必须与朴素 BFS 等价（集合、分层、判定）。"""

    def test_spread_stats_matches_naive_bfs(self) -> None:
        for lattice, direction in COMBOS:
            for p in (0.4, 0.6, 0.8):
                with self.subTest(lattice=lattice, direction=direction, p=p):
                    grid = PercolationGrid(rows=8, cols=9, p=p, lattice=lattice,
                                           direction=direction, inject="top", rng=7)
                    origins = grid.source_nodes()
                    seen, top, bottom, _depths = _naive_bfs(grid, origins)
                    self.assertEqual(grid.spread_stats(origins), (len(seen), top, bottom))

    def test_simulate_layers_match_naive_depths(self) -> None:
        for lattice, direction in COMBOS:
            with self.subTest(lattice=lattice, direction=direction):
                grid = PercolationGrid(rows=8, cols=8, p=0.6, lattice=lattice,
                                       direction=direction, inject="top", rng=3)
                result = grid.simulate()
                seen, top, bottom, depth_of = _naive_bfs(grid, result.origins)
                self.assertEqual(set(result.wet), seen)
                self.assertEqual(result.percolates, bottom)
                self.assertEqual(result.origin_spans, top and bottom)
                for depth, members in enumerate(result.layers):
                    self.assertTrue(members, "空层不该出现")
                    for index in members:
                        self.assertEqual(depth_of[index], depth)

    def test_percolates_bfs_matches_simulation(self) -> None:
        for _lattice, direction in COMBOS:
            for p in (0.4, 0.5, 0.7):
                with self.subTest(direction=direction, p=p):
                    grid = PercolationGrid(rows=10, cols=10, p=p, direction=direction,
                                           inject="top", rng=13)
                    self.assertEqual(grid.percolates_bfs(), grid.simulate().percolates)

    def test_union_find_matches_bfs_in_undirected_mode(self) -> None:
        """两条独立算法互为对照：并查集只在无向模式有效，必须与 BFS 同答案。"""
        for p in (0.4, 0.5, 0.6, 0.7):
            for seed in range(4):
                with self.subTest(p=p, seed=seed):
                    grid = PercolationGrid(rows=12, cols=12, p=p, direction="undirected",
                                           inject="top", rng=seed)
                    self.assertEqual(grid.percolates_uf(), grid.percolates_bfs())


class SpanningFastPathTest(unittest.TestCase):
    """「有没有纵贯簇」的快路径必须与「逐簇扫描」答案一致。"""

    def test_fast_path_matches_cluster_scan(self) -> None:
        for lattice, direction in COMBOS:
            for seed in range(10):
                with self.subTest(lattice=lattice, direction=direction, seed=seed):
                    grid = PercolationGrid(rows=10, cols=10, p=0.5, lattice=lattice,
                                           direction=direction, rng=seed)
                    self.assertEqual(grid.has_spanning_cluster(),
                                     bool(grid.spanning_nodes()))

    def test_spanning_cluster_touches_both_rows(self) -> None:
        checked = 0
        for p in (0.5, 0.6, 0.7):
            for seed in range(8):
                grid = PercolationGrid(rows=12, cols=12, p=p, rng=seed)
                members = grid.spanning_nodes()
                if not members:
                    continue
                checked += 1
                with self.subTest(p=p, seed=seed):
                    self.assertTrue(grid.has_spanning_cluster())
                    last_row_start = (grid.rows - 1) * grid.cols
                    self.assertTrue(any(index < grid.cols for index in members))
                    self.assertTrue(any(index >= last_row_start for index in members))
        self.assertGreater(checked, 0, "一个纵贯簇都没抽到，这条测试等于没跑")


class CriticalSweepTest(unittest.TestCase):
    """单遍扫描（临界 p）必须与逐 p 重跑的曲线一致，且结构上更"整"。"""

    def test_matches_per_point_path(self) -> None:
        """默认组合走单遍扫描；与"每点独立重跑"的曲线应在统计容差内一致。

        两条路径的随机流不同，所以差值按"两个独立估计之差"的尺度给容差（≈ 2√2 σ），
        粗错（曲线整体偏移、方向搞反）一定会被抓到。
        """
        from awe_math.models.percolation.model import scan_curve

        points = [0.35, 0.45, 0.50, 0.55, 0.65]
        trials = 300
        sweep = scan_curve(points, rows=20, cols=20, trials=trials, rng=7)
        self.assertEqual([res.p for res in sweep], points)
        for res in sweep:
            direct = batch_percolation_probability(
                rows=20, cols=20, p=res.p, trials=trials, rng=7, inject="top")
            sigma = (max(res.probability, 1e-6) * (1 - res.probability) / trials) ** 0.5
            with self.subTest(p=res.p):
                self.assertLess(abs(res.probability - direct.probability),
                                4 * sigma + 0.02)
                # "平均浸润比例"两条路径说的是同一个量（顶端整行的簇大小），要对得上。
                # 容差比 P 的容差宽松：p 略高于 p_c 时簇大小分布是重尾的，两个独立样本
                # 的均值差会明显大于二项那套直觉（但系统性错误仍远在这条线之外）。
                self.assertLess(abs(res.mean_ratio - direct.mean_ratio), 0.10)

    def test_curve_is_monotone_and_hits_the_extremes(self) -> None:
        from awe_math.models.percolation.model import scan_curve

        points = [0.05, 0.20, 0.35, 0.50, 0.65, 0.80, 0.95]
        results = scan_curve(points, rows=16, cols=16, trials=200, rng=11)
        probabilities = [res.probability for res in results]
        self.assertEqual(probabilities, sorted(probabilities))       # 随 p 单调不减
        self.assertEqual(results[0].success, 0)                      # 很小 p：不贯通
        self.assertEqual(results[-1].success, results[-1].trials)    # 很大 p：必贯通
        # 整条曲线共用一遍扫描：每个结果里的 elapsed 是同一遍的耗时
        self.assertEqual(len({res.elapsed for res in results}), 1)

    def test_mean_ratio_comes_from_the_top_cluster(self) -> None:
        """平均浸润比例要与"顶端整行注水"的量级一致（不是随机一格的量级）。"""
        from awe_math.models.percolation.model import scan_curve

        results = scan_curve([0.5], rows=20, cols=20, trials=150, rng=5)
        self.assertGreater(results[0].mean_ratio, 0.2)

    def test_other_combinations_keep_the_per_point_path(self) -> None:
        """非默认组合仍逐 p 重跑（每个点各自计时，elapsed 不会全部相同）。"""
        from awe_math.models.percolation.model import scan_curve

        results = scan_curve([0.3, 0.5, 0.7], rows=12, cols=12, trials=40, rng=3,
                             inject="random")
        self.assertEqual(len(results), 3)
        self.assertGreater(len({res.elapsed for res in results}), 1)


class OptionsContractTest(unittest.TestCase):
    """``_grid_options`` 必须同时认中文标签与内部取值。

    分块批量的 payload 会把上一次结果的字段回传，那些字段存的是**内部取值**
    （``"triangular"`` / ``"down_right"``），界面表单给的则是中文标签 —— 两条路都要通，
    否则回传的内部取值会被当成"无法识别"而落到 fallback，用户选的格子与方向被静默换掉。
    """

    def test_accepts_labels_and_internal_values(self) -> None:
        from awe_math.models.percolation.spec import _grid_options

        labelled = _grid_options({"lattice": "三角网（6 邻域）",
                                  "direction": "只允许向下/向右（经典有向渗流）"})
        self.assertEqual(labelled["lattice"], "triangular")
        self.assertEqual(labelled["direction"], "down_right")

        internal = _grid_options({"lattice": "triangular", "direction": "down_right",
                                  "inject": "random"})
        self.assertEqual(internal["lattice"], "triangular")
        self.assertEqual(internal["direction"], "down_right")
        self.assertEqual(internal["inject"], "random")

        self.assertEqual(_grid_options({})["lattice"], "square")     # 缺省仍然回退


class StructureChangeTest(unittest.TestCase):
    """就地改尺寸 / 形状后，内核必须自己重建内部表 —— 界面走的就是这条路。

    ``ui/tk/kit/base.py`` 的 ``_on_shape_change`` / ``_sync_model_params`` 是**就地**改
    ``model.rows`` / ``cols`` / ``lattice`` / ``direction``、再调 ``regenerate()`` 的，
    注释也写着"尺寸变化会重建内部结构"。重构前的内核没有缓存表，怎么改都没事；换成按尺寸
    预编译的表之后，忘了重建就会拿旧尺寸的表去索引新网格 —— 表现正是"长宽比不为 1 就
    ``IndexError: bytearray index out of range``"。这组测试钉住这件事。
    """

    def test_resize_in_place_rebuilds_tables(self) -> None:
        from awe_math.models.percolation.model import PercolationGrid

        grid = PercolationGrid(rows=20, cols=20, p=0.5, rng=1)
        for rows, cols in ((20, 30), (30, 20), (15, 25), (25, 15)):
            with self.subTest(shape=(rows, cols)):
                grid.rows, grid.cols = rows, cols
                grid.regenerate()                    # 界面改尺寸就是这么重排的
                self.assertEqual(grid.node_count, rows * cols)
                self.assertEqual(grid._last_row_start, (rows - 1) * cols)
                result = grid.simulate()
                self.assertEqual((result.rows, result.cols), (rows, cols))
                self.assertLess(max(result.wet), rows * cols)
                self.assertTrue(grid.spanning_nodes() is not None)
                size, _top, _bottom = grid.spread_stats()
                self.assertLessEqual(size, rows * cols)

    def test_resize_without_regenerate_is_still_safe(self) -> None:
        """没调 ``regenerate`` 就直接读，也要安全：入口会自己对齐（与旧内核一样宽容）。"""
        from awe_math.models.percolation.model import PercolationGrid

        grid = PercolationGrid(rows=20, cols=20, p=0.5, rng=1)
        grid.rows, grid.cols = 12, 34
        result = grid.simulate()
        self.assertEqual((result.rows, result.cols), (12, 34))
        self.assertLess(max(result.wet), 12 * 34)

    def test_switch_lattice_and_direction_in_place(self) -> None:
        """换格子类型 / 方向模式同样是结构变化 —— 表要重编、旧结果要作废。"""
        from awe_math.models.percolation.model import PercolationGrid

        grid = PercolationGrid(rows=16, cols=24, p=0.5, rng=1)
        for lattice in ("square", "triangular"):
            for direction in ("undirected", "down_right"):
                if lattice == "triangular" and direction != "undirected":
                    continue
                with self.subTest(lattice=lattice, direction=direction):
                    grid.lattice, grid.direction = lattice, direction
                    grid.regenerate()
                    result = grid.simulate()
                    self.assertEqual((result.rows, result.cols), (16, 24))
                    self.assertLess(max(result.wet), 16 * 24)
                    self.assertEqual(len(list(grid.iter_open_edges())) > 0,
                                     grid.open_edge_count() > 0)


class UiContractTest(unittest.TestCase):
    """桌面骨架实际传的那套参数必须能跑通（含 ``progress`` / ``cancel`` 回调）。

    渗流视图"进去一片空白"那次事故的根因就是"骨架与内核之间的参数契约是隐式的"：
    骨架传了一个内核已经不接受的随机源类型（``random.Random``），构造期抛异常，窗口只剩空壳。
    这条测试按骨架的真实调用形状走一遍（``spec.batch`` / ``spec.scan`` 就是这两个函数），
    把这条契约钉在测试里 —— 内核再改签名时，这里会先红，而不是让窗口变空白。
    """

    def test_ui_style_kwargs_reach_the_model(self) -> None:
        import threading

        from awe_math.models.percolation.model import (
            batch_percolation_probability,
            scan_curve,
        )

        cancel = threading.Event()
        seen = []

        batched = batch_percolation_probability(
            rows=20, cols=20, p=0.5, trials=20, rng=7,
            lattice="square", direction="undirected", inject="top", criterion="span",
            threshold=0.5,
            progress=lambda done, total, success: seen.append((done, total)),
            cancel=cancel,
        )
        self.assertEqual(batched.trials, 20)
        self.assertTrue(seen, "progress 回调一次都没被调用")
        self.assertEqual(seen[-1], (20, 20))

        points = scan_curve(
            [0.3, 0.5, 0.7], rows=20, cols=20, trials=10, rng=7,
            lattice="square", direction="undirected", inject="top", criterion="span",
            threshold=0.5,
            progress=lambda done, total, res: None, cancel=cancel,
        )
        self.assertEqual(len(points), 3)
        for point in points:
            self.assertGreaterEqual(point.probability, 0.0)
            self.assertLessEqual(point.probability, 1.0)


class BatchAndScanTest(unittest.TestCase):
    """批量统计与扫描的对外契约。"""

    def test_batch_is_reproducible_with_a_seed(self) -> None:
        first = batch_percolation_probability(rows=20, cols=20, p=0.5, trials=40, rng=99)
        second = batch_percolation_probability(rows=20, cols=20, p=0.5, trials=40, rng=99)
        self.assertEqual(first.success, second.success)
        self.assertAlmostEqual(first.mean_ratio, second.mean_ratio, places=12)

    def test_span_criterion_ignores_injection(self) -> None:
        """文档里那句"贯通判据与注水点无关"必须在同一批网格上逐次成立。"""
        for p in (0.4, 0.5, 0.62):
            with self.subTest(p=p):
                top = batch_percolation_probability(rows=16, cols=16, p=p, trials=60,
                                                    rng=2026, inject="top")
                centre = batch_percolation_probability(rows=16, cols=16, p=p, trials=60,
                                                       rng=2026, inject="center")
                self.assertEqual(top.success, centre.success)

    def test_extremes_are_certain(self) -> None:
        """p = 0 必定不贯通、p = 1 必定贯通 —— 不需要随机源就能断言。"""
        lowest = batch_percolation_probability(rows=10, cols=10, p=0.0, trials=5, rng=1)
        highest = batch_percolation_probability(rows=10, cols=10, p=1.0, trials=5, rng=1)
        self.assertEqual(lowest.success, 0)
        self.assertEqual(highest.success, highest.trials)

    def test_scan_reports_every_point(self) -> None:
        from awe_math.models.percolation.model import scan_curve

        points = [0.2, 0.5, 0.8]
        seen: List[Tuple[int, float]] = []
        results = scan_curve(points, rows=12, cols=12, trials=20, rng=4,
                             progress=lambda done, total, res: seen.append((done, res.p)))
        self.assertEqual([res.p for res in results], points)
        self.assertEqual([done for done, _p in seen], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
