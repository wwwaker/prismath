"""Logistic Map 的数学性质、数据契约与参数边界测试。"""

from __future__ import annotations

import json
import math
import unittest

import numpy as np

from prismath.models.logistic_map import (
    DEFAULT_R,
    DEFAULT_X0,
    LogisticMap,
    bifurcation,
    iterate,
    logistic_step,
    lyapunov_exponent,
)
from prismath.models.logistic_map.spec import (
    build_logistic,
    handle,
    options_from_ui,
)


class LogisticNumericsTest(unittest.TestCase):
    def test_logistic_step_supports_scalar_and_array(self):
        self.assertAlmostEqual(float(logistic_step(0.2, 2.5)), 0.4)
        np.testing.assert_allclose(logistic_step(np.array([0.0, 0.5, 1.0]), 4.0),
                                   [0.0, 1.0, 0.0])

    def test_fixed_point_at_r_2_5(self):
        values = iterate(2.5, 0.2, iterations=40, discard=100)
        np.testing.assert_allclose(values, 0.6, rtol=0.0, atol=1e-12)
        self.assertLess(lyapunov_exponent(2.5, 0.2, 300, 100), 0.0)

    def test_period_two_at_r_3_2(self):
        values = iterate(3.2, 0.2, iterations=20, discard=300)
        self.assertAlmostEqual(values[-1], values[-3], places=12)
        self.assertNotAlmostEqual(values[-1], values[-2], places=5)
        self.assertLess(lyapunov_exponent(3.2, 0.2, 300, 300), 0.0)

    def test_r_4_is_bounded_and_has_positive_lyapunov_exponent(self):
        values = iterate(4.0, 0.2, iterations=500, discard=100)
        self.assertGreaterEqual(float(values.min()), 0.0)
        self.assertLessEqual(float(values.max()), 1.0)
        self.assertGreater(lyapunov_exponent(4.0, 0.2, 2000, 200), 0.6)
        self.assertAlmostEqual(lyapunov_exponent(4.0, 0.2, 5000, 500), math.log(2.0), delta=0.02)

    def test_bifurcation_shape_and_parameter_order(self):
        result = bifurcation(3.0, 3.5, r_samples=40, points_per_r=20,
                             x0=0.2, discard=100)
        self.assertEqual(result.rs.shape, (800,))
        self.assertEqual(result.xs.shape, (800,))
        self.assertTrue(np.all(np.diff(result.rs) >= 0.0))
        self.assertGreaterEqual(float(result.xs.min()), 0.0)
        self.assertLessEqual(float(result.xs.max()), 1.0)
        np.testing.assert_array_equal(result.rs[:20], result.rs[0])
        np.testing.assert_array_equal(result.rs[-20:], result.rs[-1])

    def test_model_swaps_reversed_bifurcation_range(self):
        model = LogisticMap(r_min=3.9, r_max=2.9, r_samples=40, points_per_r=20)
        self.assertLess(model.r_min, model.r_max)
        result = model.bifurcation()
        self.assertAlmostEqual(result.rs[0], 2.9)
        self.assertAlmostEqual(result.rs[-1], 3.9)

    def test_parameters_are_clamped(self):
        options = options_from_ui({
            "r": 99, "x0": -1, "iterations": 10 ** 9, "discard": -4,
            "r_min": 4.5, "r_max": -1, "r_samples": 1, "points_per_r": 9999,
        })
        self.assertEqual(options["r"], 4.0)
        self.assertEqual(options["x0"], 0.0)
        self.assertEqual(options["iterations"], 5000)
        self.assertEqual(options["discard"], 0)
        self.assertEqual(options["r_min"], 4.0)
        self.assertEqual(options["r_max"], 0.0)
        self.assertEqual(options["r_samples"], 40)
        self.assertEqual(options["points_per_r"], 120)


class LogisticContractTest(unittest.TestCase):
    def _params(self, **overrides):
        from prismath.models.logistic_map import SPEC
        params = {param.key: param.default for param in SPEC.params}
        params.update(overrides)
        return params

    def test_factory_uses_normalized_values(self):
        model = build_logistic({"r": 5, "x0": -2, "iterations": 10})
        self.assertEqual(model.r, 4.0)
        self.assertEqual(model.x0, 0.0)
        self.assertEqual(model.iterations, 20)

    def test_actions_return_json_serializable_payloads(self):
        params = self._params(iterations=40, discard=30, r_samples=40, points_per_r=20)
        orbit = handle("orbit", params, {})
        diagram = handle("bifurcation", params, {})
        self.assertEqual(orbit["view"], "logistic-orbit")
        self.assertEqual(diagram["view"], "logistic-bifurcation")
        self.assertEqual(orbit["mode"], "单参数轨道")
        self.assertEqual(diagram["mode"], "分岔扫描")
        self.assertEqual(diagram["sampleCount"], len(diagram["xs"]))
        self.assertEqual(diagram["lyapunov"], "每个 r 不同")
        self.assertEqual(len(orbit["records"]), 40)
        self.assertEqual(len(diagram["rs"]), 800)
        self.assertEqual(len(diagram["xs"]), len(diagram["thetas"]))
        json.dumps(orbit, ensure_ascii=False)
        json.dumps(diagram, ensure_ascii=False)

    def test_unknown_action_raises(self):
        with self.assertRaises(ValueError):
            handle("not-an-action", self._params(), {})

    def test_default_parameters_are_stable(self):
        model = build_logistic(self._params())
        self.assertAlmostEqual(model.r, DEFAULT_R)
        self.assertAlmostEqual(model.x0, DEFAULT_X0)
        first = model.orbit().values
        second = model.orbit().values
        np.testing.assert_array_equal(first, second)


if __name__ == "__main__":
    unittest.main()
