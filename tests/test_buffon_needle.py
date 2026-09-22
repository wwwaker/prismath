"""蒲丰投针内核：公式、边界情形、编码。

与生命游戏不同，这里**必然涉及随机**，所以断言分两类：

* **精确断言**只用在"算术恒等式"上（π 的估计式、编码长度、累计计数）——与随机源无关；
* **统计断言**一律"固定种子 + 容差"，且容差按 ``3σ`` 量级给（σ = √(p(1-p)/N)），
  这样即便以后换掉随机数实现（numpy 的 ``default_rng`` 与 ``random.Random`` 序列不同），
  断言依然成立，同时仍能抓住"公式写错了"这类真问题（错的公式会偏离 0.1 以上）。

``L/d`` 的理论命中率 ``2L/(πd)`` 只在 ``L ≤ d`` 时是那个简单式子，因此这里**不**去断言
``L > d`` 的具体概率，只断言"概率随 L/d 单调上升"（对任意 L 都成立）。
"""

from __future__ import annotations

import math
import unittest

from prismath.models.buffon_needle.model import (
    MAX_RATIO,
    MIN_RATIO,
    PI,
    BuffonNeedle,
    encode_needles,
    estimate_pi,
)


class EstimateFormulaTest(unittest.TestCase):
    """π ≈ 2LN/(dH)：这条式子是整个模型的数学内核，必须精确成立。"""

    def test_closed_form(self) -> None:
        # 2 · 0.8 · 1000 / (1 · 500) = 3.2
        self.assertAlmostEqual(estimate_pi(0.8, 1.0, 1000, 500), 3.2, places=12)

    def test_zero_hits_has_no_estimate(self) -> None:
        """一次都没命中时无法反解 π（分母为 0），返回 None 而不是抛异常。"""
        self.assertIsNone(estimate_pi(0.8, 1.0, 1000, 0))


class ThrowTest(unittest.TestCase):
    """一次投掷：几何、命中数、估计值三者必须自洽。"""

    def test_counts_are_consistent(self) -> None:
        result = BuffonNeedle(ratio=0.8, throws=2000, rng=7).throw()
        self.assertEqual(result.throws, 2000)
        self.assertEqual(len(result.needles), 2000)
        self.assertEqual(result.hits, sum(1 for needle in result.needles if needle.hit))
        self.assertAlmostEqual(
            result.pi_estimate, 2 * result.length * result.throws / (result.gap * result.hits),
            places=12,
        )

    def test_hit_rate_is_near_the_theory(self) -> None:
        """N = 50000 时命中率的 3σ ≈ 0.0067 —— 容差给 0.02（约 9σ），不会误报。"""
        needle = BuffonNeedle(ratio=0.8, throws=50_000, rng=7)
        result = needle.throw()
        rate = result.hits / result.throws
        self.assertLess(abs(rate - needle.theory_rate), 0.02)

    def test_theory_rate_formula(self) -> None:
        needle = BuffonNeedle(ratio=0.8, gap=1.0)
        self.assertAlmostEqual(needle.theory_rate, 2 * 0.8 / (PI * 1.0), places=12)

    def test_hit_rate_grows_with_ratio(self) -> None:
        """针越长（相对线距）越容易压线 —— 对任意 L/d 都成立，且不依赖具体公式。"""
        rates = []
        for ratio in (0.3, 0.8, 1.5):
            needle = BuffonNeedle(ratio=ratio, throws=20_000, rng=11)
            rates.append(needle.throw().hits / needle.throws)
        self.assertLess(rates[0], rates[1])
        self.assertLess(rates[1], rates[2])

    def test_ratio_is_clamped(self) -> None:
        self.assertEqual(BuffonNeedle(ratio=-5.0).ratio, MIN_RATIO)
        self.assertEqual(BuffonNeedle(ratio=99.0).ratio, MAX_RATIO)

    def test_same_seed_reproduces_the_same_throws(self) -> None:
        first = BuffonNeedle(ratio=0.8, throws=500, rng=3).throw()
        second = BuffonNeedle(ratio=0.8, throws=500, rng=3).throw()
        self.assertEqual(first.hits, second.hits)
        self.assertEqual([n.hit for n in first.needles], [n.hit for n in second.needles])

    def test_arrays_agree_with_needle_objects(self) -> None:
        """几何的两种读法（数组 / 逐根对象）必须逐根一致：``needles`` 只是换个看法。"""
        result = BuffonNeedle(ratio=0.8, throws=400, rng=5).throw()
        self.assertEqual(result.xs.size, result.throws)
        self.assertEqual(result.hits, int(result.hits_mask.sum()))
        needles = result.needles
        self.assertEqual(len(needles), result.throws)
        self.assertEqual(sum(1 for n in needles if n.hit), result.hits)
        for needle, cx, cy, theta, hit in zip(needles, result.xs, result.ys,
                                              result.thetas, result.hits_mask):
            self.assertEqual((needle.cx, needle.cy, needle.theta, needle.hit),
                             (float(cx), float(cy), float(theta), bool(hit)))

    def test_needle_objects_are_built_lazily_and_cached(self) -> None:
        """逐根对象按需构建（批量路径不该为大 N 付对象化的代价），而且只构建一次。"""
        result = BuffonNeedle(ratio=0.8, throws=300, rng=5).throw()
        self.assertIs(result.needles, result.needles)


class ConvergeTest(unittest.TestCase):
    """多组重复：累计计数与逐组记录必须对得上。"""

    def test_cumulative_counts(self) -> None:
        result = BuffonNeedle(ratio=0.8, throws=500, rng=7).converge(8)
        self.assertEqual(len(result.samples), 8)
        self.assertEqual(len(result.per_group), 8)
        self.assertEqual(result.total_throws, 8 * 500)
        for position, (throws, _hits, _estimate) in enumerate(result.samples, start=1):
            with self.subTest(sample=position):
                self.assertEqual(throws, position * 500)
        self.assertEqual(result.samples[-1][1], result.total_hits)

    def test_samples_are_monotone_in_hits(self) -> None:
        """命中数是累计量，只能不减（单调性写错的话这里会立刻暴露）。"""
        result = BuffonNeedle(ratio=0.8, throws=500, rng=7).converge(6)
        hits = [hits for _throws, hits, _estimate in result.samples]
        self.assertEqual(hits, sorted(hits))

    def test_estimate_matches_cumulative_counts(self) -> None:
        result = BuffonNeedle(ratio=0.8, throws=500, rng=7).converge(3)
        throws, hits, estimate = result.samples[-1]
        self.assertAlmostEqual(
            estimate, 2 * result.length * throws / (result.gap * hits), places=12)


class EncodeTest(unittest.TestCase):
    """投针结果的压缩表示（画布按"坐标数组 + 0/1 掩码"还原几何）。"""

    def test_shapes_and_mask(self) -> None:
        result = BuffonNeedle(ratio=0.8, throws=300, rng=5).throw()
        payload = encode_needles(result)
        for key in ("xs", "ys", "thetas", "hitsMask"):
            with self.subTest(key=key):
                self.assertEqual(len(payload[key]), 300)
        self.assertLessEqual(set(payload["hitsMask"]), {"0", "1"})
        self.assertEqual(payload["hitsMask"].count("1"), result.hits)


if __name__ == "__main__":
    unittest.main()
