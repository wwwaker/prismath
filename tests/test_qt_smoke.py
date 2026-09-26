"""Qt 桌面后端的无头冒烟测试。

它走真实的 ``ModelPage`` 路径，确保每个模型都能从统一的 ``ModelSpec`` 生成参数面板，
执行首个动作并得到结果。渗流页额外验证彩色分层画布可以播放到末层。
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from prismath.registry import load_models
    from prismath.ui.qt.app import ModelPage
except Exception:  # pragma: no cover - 环境没有 Qt 时跳过
    QApplication = None  # type: ignore[assignment]
    load_models = None  # type: ignore[assignment]
    ModelPage = None  # type: ignore[assignment]


@unittest.skipUnless(QApplication is not None, "没有安装 PySide6")
class QtSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_every_model_runs_primary_action(self) -> None:
        for spec in load_models():
            with self.subTest(model=spec.key):
                page = ModelPage(spec)
                action = next((item.key for item in spec.actions if item.kind == "primary"), None)
                self.assertIsNotNone(action)
                page._run_action(action)  # type: ignore[arg-type]
                self.assertTrue(page.payload, spec.key)
                self.assertIn("view", page.payload, spec.key)
                page.close()

    def test_importing_qt_does_not_short_circuit_model_discovery(self) -> None:
        """Qt 的兼容导出必须懒加载，不能提前只注册某几个模型。"""
        keys = [spec.key for spec in load_models()]
        self.assertEqual(
            keys,
            ["mandelbrot", "buffon_needle", "n_body", "life_game",
             "percolation", "site_percolation"],
        )

    def test_percolation_stage_reaches_final_layer(self) -> None:
        spec = next(item for item in load_models() if item.view == "percolation")
        page = ModelPage(spec)
        page._run_action("generate")
        stage = page.stage
        self.assertEqual(type(stage).__name__, "PercolationStage")
        stage.finish()  # type: ignore[union-attr]
        self.assertEqual(stage.shown, len(page.payload.get("layers", [])))  # type: ignore[union-attr]
        page.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
