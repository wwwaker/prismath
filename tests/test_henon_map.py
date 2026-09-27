"""Hénon Map 的递推、混沌指数与数据契约测试。"""

from __future__ import annotations

import json
import math
import unittest

import numpy as np

from prismath.models.henon_map import (
    DEFAULT_A,
    DEFAULT_B,
    HenonMap,
    henon_step,
    iterate,
    lyapunov_exponent,
)
from prismath.models.henon_map.spec import handle, options_from_ui


class HenonNumericsTest(unittest.TestCase):
    def test_one_step_matches_definition(self):
        x, y = henon_step(0.2, 0.1, 1.4, 0.3)
        self.assertAlmostEqual(float(x), 1.044, places=12)
        self.assertAlmostEqual(float(y), 0.06, places=12)

    def test_default_orbit_is_bounded_and_two_dimensional(self):
        values = iterate(DEFAULT_A, DEFAULT_B, 0.0, 0.0, 2000, 500)
        self.assertEqual(values.shape, (2000, 2))
        self.assertTrue(np.isfinite(values).all())
        self.assertLess(float(np.max(np.abs(values[:, 0]))), 1.5)
        self.assertLess(float(np.max(np.abs(values[:, 1]))), 0.5)

    def test_classic_parameters_have_positive_lyapunov_exponent(self):
        exponent = lyapunov_exponent(DEFAULT_A, DEFAULT_B, 0.0, 0.0, 4000, 500)
        self.assertGreater(exponent, 0.2)
        self.assertLess(exponent, 0.7)

    def test_parameters_are_clamped(self):
        options = options_from_ui({
            "a": 99, "b": -99, "x0": 99, "y0": -99,
            "iterations": 10 ** 9, "discard": -4,
        })
        self.assertEqual(options["a"], 2.0)
        self.assertEqual(options["b"], -1.0)
        self.assertEqual(options["x0"], 2.0)
        self.assertEqual(options["y0"], -2.0)
        self.assertEqual(options["iterations"], 20000)
        self.assertEqual(options["discard"], 0)

    def test_recurrence_and_discard_match_independent_short_orbit(self):
        x, y = 0.15, -0.12
        expected = []
        for n in range(25):
            x, y = 1 - 0.9 * x * x + y, 0.2 * x
            if n >= 5:
                expected.append((x, y))
        np.testing.assert_allclose(iterate(0.9, 0.2, 0.15, -0.12, 20, 5), expected)

    def test_stable_preset_converges_to_analytic_fixed_point(self):
        result = HenonMap(a=0.2).orbit()
        fixed_x = (-0.7 + math.sqrt(0.7 ** 2 + 4 * 0.2)) / (2 * 0.2)
        np.testing.assert_allclose(result.values[:, 0], fixed_x, atol=1e-12)
        np.testing.assert_allclose(result.values[:, 1], 0.3 * fixed_x, atol=1e-12)
        self.assertLess(result.lyapunov, 0)

    def test_linear_map_exponent_matches_spectral_radius(self):
        # a=0 时 J=[[0,1],[b,0]]，每两步切向量缩放 b。
        self.assertAlmostEqual(lyapunov_exponent(a=0, b=0.3), math.log(0.3) / 2, places=10)

    def test_escape_during_burn_and_sampling_stops_before_overflow(self):
        for discard in (0, 300):
            with self.subTest(discard=discard), np.errstate(all="raise"):
                result = HenonMap(x0=2, y0=2, discard=discard).orbit()
                self.assertIsNotNone(result.stopped_step)
                self.assertLess(result.stopped_step, 20)
                self.assertTrue(np.isfinite(result.values).all())
                self.assertIsNone(result.lyapunov)
                with self.assertRaisesRegex(ValueError, "超出计算范围"):
                    iterate(x0=2, y0=2, discard=discard)

    def test_nonfinite_integer_inputs_use_defaults(self):
        model = HenonMap(iterations=float("inf"), discard=float("nan"))
        self.assertEqual(model.iterations, HenonMap().iterations)
        self.assertEqual(model.discard, HenonMap().discard)


class HenonContractTest(unittest.TestCase):
    def _params(self, **overrides):
        from prismath.models.henon_map import SPEC
        params = {param.key: param.default for param in SPEC.params}
        params.update(overrides)
        return params

    def test_actions_return_json_serializable_payloads(self):
        params = self._params(iterations=80, discard=40)
        attractor = handle("attractor", params, {})
        orbit = handle("orbit", params, {})
        self.assertEqual(attractor["view"], "henon-attractor")
        self.assertEqual(orbit["view"], "henon-orbit")
        self.assertEqual(len(attractor["xs"]), 80)
        self.assertEqual(len(attractor["ys"]), 80)
        self.assertEqual(len(orbit["records"]), 80)
        json.dumps(attractor, ensure_ascii=False, allow_nan=False)
        json.dumps(orbit, ensure_ascii=False, allow_nan=False)

    def test_escape_and_singular_map_have_strict_json_payloads(self):
        for params in ({"x0": 2, "y0": 2}, {"a": 0, "b": 0}):
            for action in ("attractor", "orbit"):
                with self.subTest(params=params, action=action):
                    payload = handle(action, self._params(**params), {})
                    json.dumps(payload, allow_nan=False)
                    self.assertIsNone(payload["lyapunov"])
                    if "a" in params:
                        self.assertEqual(payload["lyapunovText"], "−∞")
                    else:
                        self.assertIsNotNone(payload["stoppedStep"])

    def test_cli_defaults_do_not_leak_between_models(self):
        from prismath.launcher import build_parser
        from prismath.models.logistic_map.model import DEFAULT_X0 as LOGISTIC_X0
        from prismath.models.henon_map.model import DEFAULT_DISCARD, DEFAULT_ITERATIONS
        args = build_parser().parse_args(["--model", "henon_map", "--ui", "cli"])
        self.assertEqual(args.henon_iterations, DEFAULT_ITERATIONS)
        self.assertEqual(args.henon_discard, DEFAULT_DISCARD)
        self.assertEqual(args.henon_x0, 0)
        self.assertEqual(args.x0, LOGISTIC_X0)
        custom = build_parser().parse_args(["--henon-x0", "0.1", "--henon-iterations", "80"])
        self.assertEqual(custom.henon_x0, 0.1)
        self.assertEqual(custom.henon_iterations, 80)

    def test_factory_uses_normalized_values(self):
        model = HenonMap(a=99, b=-99, x0=99, y0=-99, iterations=1)
        self.assertEqual(model.a, 2.0)
        self.assertEqual(model.b, -1.0)
        self.assertEqual(model.x0, 2.0)
        self.assertEqual(model.y0, -2.0)
        self.assertEqual(model.iterations, 20)


try:
    import tkinter as tk
    probe = tk.Tk()
    probe.withdraw()
    probe.destroy()
    TK_OK = True
except Exception:
    TK_OK = False


@unittest.skipUnless(TK_OK, "没有可用的图形环境")
class HenonViewTest(unittest.TestCase):
    def setUp(self):
        from prismath.models.henon_map import SPEC
        from prismath.models.henon_map.views.tk import HenonMapView
        from prismath.ui.tk.theme import install_theme
        self.root = tk.Tk()
        self.root.geometry("1400x900")
        install_theme(self.root)
        host = tk.Frame(self.root)
        host.pack(fill="both", expand=True)
        self.view = HenonMapView(self.root, host, SPEC)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.root.after(200, self.root.quit)
        self.root.mainloop()

    def tearDown(self):
        self.view.shutdown()
        self.root.destroy()

    def test_startup_renders_real_data_then_readable_time_series(self):
        self.assertFalse(self.errors)
        self.assertEqual(self.view._last["view"], "henon-attractor")
        self.assertEqual(len(self.view.canvas.find_withtag("henon-points")), 1)
        self.view.run_action("orbit")
        for column in (0, 1):
            line = self.view.canvas.find_withtag(f"henon-series-{column}")
            self.assertEqual(len(line), 1)
            self.assertEqual(len(self.view.canvas.coords(line[0])), 80 * 2)

    def test_escape_and_recovery_replace_old_chart_and_summary(self):
        self.view.param_vars["x0"].set(2)
        self.view.param_vars["y0"].set(2)
        self.view.run_action("attractor")
        self.view._redraw()
        self.assertIn("超出计算范围", self.view.var_badge.get())
        self.assertFalse(self.view.canvas.find_withtag("henon-points"))
        self.view._preset(True)
        self.assertIn("稳定收缩", self.view.var_badge.get())
        self.assertTrue(self.view.canvas.find_withtag("henon-fixed-point"))
        self.view.on_key("r")
        self.assertIn("混沌迹象", self.view.var_badge.get())
        self.assertTrue(self.view.canvas.find_withtag("henon-points"))


if __name__ == "__main__":
    unittest.main()
