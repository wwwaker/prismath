"""Fourier Epicycles 的采样、频谱、重建和 payload 契约测试。"""

from __future__ import annotations

import json
import unittest

import numpy as np

from prismath.models.fourier_epicycles import (
    DEFAULT_FRAMES,
    DEFAULT_SAMPLES,
    DEFAULT_TERMS,
    FourierEpicycle,
    analyze_points,
    dft_coefficients,
    evaluate_series,
    extract_image_contour,
    sample_shape,
)
from prismath.models.fourier_epicycles.spec import handle, options_from_ui, payload_for_points
from prismath.models.fourier_epicycles.model import MAX_FRAMES


class FourierNumericsTest(unittest.TestCase):
    def test_builtin_shapes_are_finite_closed_ordered_contours(self):
        for shape in ("heart", "star", "flower", "circle", "lissajous", "sample_image"):
            with self.subTest(shape=shape):
                points = sample_shape(shape, 128)
                self.assertEqual(points.shape, (128,))
                self.assertTrue(np.isfinite(points).all())
                self.assertAlmostEqual(float(abs(np.mean(points))), 0.0, places=12)
                self.assertAlmostEqual(float(np.max(np.abs(points))), 1.0, places=12)

    def test_circle_has_one_positive_frequency(self):
        frequencies, coefficients = dft_coefficients(sample_shape("circle", 256), 9)
        dominant = int(frequencies[np.argmax(np.abs(coefficients))])
        self.assertEqual(dominant, 1)
        self.assertAlmostEqual(float(np.max(np.abs(coefficients))), 1.0, places=12)

    def test_dft_reconstructs_low_harmonic_signal(self):
        times = np.arange(128, dtype=float) / 128.0
        source = np.exp(2j * np.pi * 3 * times)
        frequencies, coefficients = dft_coefficients(source, 7)
        reconstructed = evaluate_series(frequencies, coefficients, times)
        np.testing.assert_allclose(reconstructed, source, atol=1e-12)

    def test_terms_trade_accuracy_for_star(self):
        low = FourierEpicycle("star", 512, 5, 120).analyze()
        high = FourierEpicycle("star", 512, 31, 120).analyze()
        self.assertGreater(low.rmse, high.rmse)
        self.assertLess(high.rmse, low.rmse * 0.8)
        self.assertEqual(len(high.trajectory), 120)

    def test_parse_and_clamp_options(self):
        options = options_from_ui({
            "shape": "unknown", "samples": 1, "terms": 99999, "frames": -3,
        })
        self.assertEqual(options["shape"], "heart")
        self.assertEqual(options["samples"], 64)
        self.assertEqual(options["terms"], 64)
        self.assertEqual(options["frames"], 60)

    def test_frame_limit_allows_fine_trajectory_sampling(self):
        options = options_from_ui({"frames": 99999})
        self.assertEqual(options["frames"], MAX_FRAMES)
        result = FourierEpicycle(frames=99999).analyze()
        self.assertEqual(result.frames, MAX_FRAMES)

    def test_image_contour_accepts_rgb_array_without_optional_opencv(self):
        image = np.full((96, 128, 3), 245, dtype=np.uint8)
        image[18:78, 48:80] = 22
        image[60:88, 34:94] = 22
        contour = extract_image_contour(image, 128)
        self.assertEqual(contour.shape, (128,))
        self.assertTrue(np.isfinite(contour).all())
        self.assertAlmostEqual(float(np.max(np.abs(contour))), 1.0, places=12)

    def test_custom_points_reject_bad_input(self):
        with self.assertRaisesRegex(ValueError, "至少需要 3"):
            analyze_points([1 + 1j, 2 + 2j])
        with self.assertRaisesRegex(ValueError, "有限"):
            analyze_points([0j, 1 + 0j, complex(float("nan"), 0)])

    def test_manual_points_use_the_same_payload_contract(self):
        points = np.column_stack((np.cos(np.linspace(0, 2 * np.pi, 80, endpoint=False)),
                                  np.sin(np.linspace(0, 2 * np.pi, 80, endpoint=False))))
        payload = payload_for_points(points, {"terms": 9, "frames": 60})
        self.assertEqual(payload["shape"], "manual")
        self.assertEqual(payload["shapeLabel"], "手绘轮廓")
        self.assertEqual(len(payload["trajectory"]), 60)


class FourierContractTest(unittest.TestCase):
    def _params(self, **overrides):
        from prismath.models.fourier_epicycles import SPEC
        params = {param.key: param.default for param in SPEC.params}
        params.update(overrides)
        return params

    def test_actions_return_strict_json_payloads(self):
        params = self._params(shape="circle", samples=96, terms=9, frames=60)
        for action in ("draw", "replay"):
            with self.subTest(action=action):
                payload = handle(action, params, {})
                self.assertEqual(payload["view"], "fourier-epicycle")
                self.assertEqual(payload["shape"], "circle")
                self.assertEqual(len(payload["harmonics"]), 9)
                self.assertEqual(len(payload["trajectory"]), 60)
                json.dumps(payload, ensure_ascii=False, allow_nan=False)

    def test_default_result_shape(self):
        result = FourierEpicycle().analyze()
        self.assertEqual(result.samples, DEFAULT_SAMPLES)
        self.assertEqual(result.terms, DEFAULT_TERMS)
        self.assertEqual(result.frames, DEFAULT_FRAMES)
        self.assertEqual(len(result.harmonics()), DEFAULT_TERMS)
        self.assertEqual(len(result.records()), DEFAULT_FRAMES)

    def test_unknown_action_raises(self):
        with self.assertRaises(ValueError):
            handle("unknown", self._params(), {})


if __name__ == "__main__":
    unittest.main()
