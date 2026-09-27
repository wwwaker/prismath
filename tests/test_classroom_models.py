# -*- coding: utf-8 -*-
"""课堂与直觉模型的内核契约。"""

from __future__ import annotations

import unittest

import numpy as np


class ClassroomModelTest(unittest.TestCase):
    def test_linear_transform_rotation_preserves_length_and_area(self):
        from prismath.models.linear_transform.model import LinearTransform, matrix_for

        matrix = matrix_for("rotation", angle=90)
        np.testing.assert_allclose(matrix @ np.array((1.0, 0.0)), (0.0, 1.0), atol=1e-12)
        result = LinearTransform(mode="rotation", angle=90, vector_x=1, vector_y=0).transform()
        self.assertAlmostEqual(result.determinant, 1.0, places=12)
        self.assertAlmostEqual(float(np.linalg.norm(result.transformed_vector)), 1.0, places=12)

    def test_linear_transform_mirror_marks_orientation(self):
        from prismath.models.linear_transform.model import LinearTransform

        result = LinearTransform(mode="mirror").transform()
        self.assertAlmostEqual(result.determinant, -1.0, places=12)
        self.assertEqual(result.orientation, "方向翻转")

    def test_projectile_no_drag_matches_analytic_range(self):
        from prismath.models.projectile_motion.model import ProjectileMotion

        result = ProjectileMotion(speed=20, angle=45, height=0, drag=0, steps=800).simulate()
        expected = 20 * 20 / 9.81
        self.assertAlmostEqual(result.ideal_range, expected, places=10)
        self.assertAlmostEqual(result.range, expected, delta=0.15)
        self.assertLess(result.max_height, 11.0)

    def test_projectile_drag_reduces_range(self):
        from prismath.models.projectile_motion.model import ProjectileMotion

        ideal = ProjectileMotion(speed=20, angle=45, height=0, drag=0, steps=800).simulate()
        drag = ProjectileMotion(speed=20, angle=45, height=0, drag=0.1, steps=800).simulate()
        self.assertLess(drag.range, ideal.range)

    def test_gradient_descent_quadratic_converges(self):
        from prismath.models.gradient_descent.model import GradientDescent

        result = GradientDescent(function="quadratic", start=3, rate=0.1, iterations=100).run()
        self.assertTrue(result.converged)
        self.assertAlmostEqual(result.final_x, 0.0, places=6)
        self.assertAlmostEqual(result.final_value, 0.0, places=10)

    def test_gradient_descent_large_rate_can_oscillate(self):
        from prismath.models.gradient_descent.model import GradientDescent

        result = GradientDescent(function="quadratic", start=3, rate=0.99, iterations=10).run()
        self.assertLess(result.records[1]["x"], 0.0)
        self.assertGreater(result.records[2]["x"], 0.0)

    def test_gradient_descent_has_richer_function_presets(self):
        from prismath.models.gradient_descent.model import FUNCTIONS, GradientDescent

        self.assertGreaterEqual(len(FUNCTIONS), 7)
        for function in FUNCTIONS:
            result = GradientDescent(function=function, start=0.7, rate=0.02, iterations=20).run()
            self.assertGreaterEqual(len(result.records), 2)
            self.assertTrue(all(np.isfinite(row["x"]) and np.isfinite(row["y"])
                                for row in result.records))

    def test_probability_lln_converges_and_clt_has_normal_scale(self):
        from prismath.models.probability_lab.model import ProbabilityLab

        lln = ProbabilityLab(experiment="lln", distribution="coin", trials=12000, seed=4).run().payload
        self.assertLess(lln["absError"], 0.03)
        clt = ProbabilityLab(experiment="clt", distribution="die", trials=3000,
                             sample_size=40, bins=21, seed=4).run().payload
        self.assertEqual(sum(clt["counts"]), 3000)
        self.assertAlmostEqual(clt["standardError"], (35.0 / 12.0) ** 0.5 / 40 ** 0.5, places=12)

    def test_probability_galton_counts_and_animation_payload(self):
        from prismath.models.probability_lab.model import ProbabilityLab

        result = ProbabilityLab(experiment="galton", rows=8, balls=600, seed=2).run().payload
        self.assertEqual(len(result["finalBins"]), 600)
        self.assertEqual(sum(result["counts"]), 600)
        self.assertEqual(len(result["paths"]), 600)
        self.assertEqual(result["view"], "probability-galton")

    def test_all_seed_controls_default_to_random(self):
        from prismath.registry import all_models, load_models

        load_models(force=True)
        seed_controls = []
        for spec in all_models():
            for param in spec.params:
                if param.key == "seed":
                    seed_controls.append((spec.key, param.default))
        self.assertTrue(seed_controls)
        self.assertTrue(all(default == -1 for _key, default in seed_controls), seed_controls)

    def test_specs_are_registered_and_payloads_are_json_friendly(self):
        from prismath.registry import get, load_models

        load_models(force=True)
        for key in ("linear_transform", "projectile_motion", "gradient_descent", "probability_lab"):
            spec = get(key)
            payload = spec.run(spec.actions[0].key, {})
            self.assertTrue(payload["view"])
            self.assertIsInstance(payload, dict)


if __name__ == "__main__":
    unittest.main()
