"""体验协议和引导会话测试。"""

from __future__ import annotations

import unittest

from prismath.experience import ExperienceSpec, GuideSession, GuideStep, RenderCapabilities
from prismath.models.mandelbrot.spec import CAPABILITIES, EXPERIENCE
from prismath.registry import load_models


class ExperienceSpecTest(unittest.TestCase):
    def test_capabilities_are_serializable(self) -> None:
        data = CAPABILITIES.to_dict()
        self.assertEqual(data["visualKind"], "field")
        self.assertIn("zoom", data["interactions"])
        self.assertTrue(data["supportsGpuPreview"])

    def test_mandelbrot_declares_guided_experience(self) -> None:
        self.assertEqual(EXPERIENCE.default_mode, "guided")
        self.assertEqual(len(EXPERIENCE.guide), 5)
        self.assertEqual(EXPERIENCE.guide[0].completion_event, "view_ready")

    def test_invalid_capability_and_duplicate_steps_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RenderCapabilities(visual_kind="unknown")
        step = GuideStep("same", "标题", "提示", completion_event="done")
        with self.assertRaises(ValueError):
            ExperienceSpec(guide=(step, step))


class GuideSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.experience = ExperienceSpec(
            default_mode="guided",
            guide=(
                GuideStep("one", "第一步", "完成第一步", completion_event="first"),
                GuideStep("two", "第二步", "完成第二步", completion_event="second"),
            ),
        )

    def test_events_advance_only_the_current_step(self) -> None:
        session = GuideSession(self.experience)
        self.assertEqual(session.current_step.key, "one")
        self.assertFalse(session.emit("second"))
        self.assertEqual(session.step_index, 0)
        self.assertTrue(session.emit("first", {"value": 1}))
        self.assertEqual(session.current_step.key, "two")
        self.assertTrue(session.emit("second"))
        self.assertTrue(session.guide_complete)
        self.assertEqual(session.mode, "explore")

    def test_skip_and_reset_are_reversible(self) -> None:
        session = GuideSession(self.experience)
        session.skip()
        self.assertEqual(session.mode, "explore")
        self.assertIsNone(session.current_step)
        session.reset()
        self.assertEqual(session.mode, "guided")
        self.assertEqual(session.current_step.key, "one")

    def test_model_spec_exposes_experience_metadata(self) -> None:
        specs = {spec.key: spec for spec in load_models(force=True)}
        spec = specs["mandelbrot"]
        data = spec.to_dict()
        self.assertEqual(data["capabilities"]["visualKind"], "field")
        self.assertEqual(data["experience"]["defaultMode"], "guided")
        self.assertEqual(len(data["experience"]["guide"]), 5)


if __name__ == "__main__":
    unittest.main()
