"""重构护栏 1：内核自检的金样本逐字回归（见 :mod:`tests._harness`）。

这一层故意"笨"：不解释任何数字，只回答一个问题 —— **重构前后，自检的输出还一模一样吗？**
数值被改坏了（p_c 漂了、周期算错、表格少了一列）会在这里第一时间爆掉，
而不是等到界面上看不出来、或者文档里的数字悄悄过期。
"""

from __future__ import annotations

import unittest

from tests import _harness


class GoldenSelfCheckTest(unittest.TestCase):
    """四个模型的内核自检必须与 ``tests/golden/<模型>.txt`` 逐字一致。"""

    def test_selfcheck_matches_golden(self) -> None:
        for model in _harness.MODELS:
            with self.subTest(model=model):
                expected = _harness.read_golden(model)
                actual = _harness.run_selfcheck(model)
                diff = _harness.first_diff(expected, actual)
                self.assertEqual(
                    diff, "",
                    f"\n{model} 的自检输出与金样本不一致（从上面那行开始）：\n{diff}\n"
                    f"若这次变化是有意为之（例如内核重写改变了 RNG 消耗顺序），"
                    f"请先确认新数字合理，再跑 `python -m tests._harness --update` 更新金样本。",
                )

    def test_golden_files_exist(self) -> None:
        """金样本本身要在位（否则上面的测试会因为"文件不存在"而报奇怪的错）。"""
        for model in _harness.MODELS:
            with self.subTest(model=model):
                self.assertTrue(
                    _harness.golden_path(model).is_file(),
                    f"缺少金样本 {_harness.golden_path(model)}，"
                    f"跑 `python -m tests._harness --update` 生成。",
                )


if __name__ == "__main__":
    unittest.main()
