"""桌面视图的**无头冒烟**：每个模型的视图真的建得起来，并且画出了东西。

为什么必须有这一层
------------------
视图骨架与内核之间的接口是**隐式**的（谁给谁传什么参数），而 Step 6 的 85 条测试全绿时，
渗流两个模型进模型却是**一片空白**：内核的随机源从 ``random.Random`` 换成
``numpy.random.Generator`` 之后，渗流骨架仍在传 ``random.Random()``，于是视图构造期就抛
异常，窗口只剩空壳。内核测试与数据级契约全都不建窗口，所以谁都没红。

这条测试直接复现"用户点开模型"这条路：建窗口 → 建外壳 → 建视图 → 跑一轮事件循环，
断言视图存在、画布存在、且**画布上真有图元**。它同时也顺带守住了四个视图的构造契约
（骨架改了、内核签名改了，这里会先红）。

没有图形环境时自动跳过（``tk.Tk()`` 抛异常）：不该因为 CI 没显示器而失败。
注意：跑这条测试时本机会**短暂弹出窗口**（每个模型一个，建完就关），这是它必须做的动作。
"""

from __future__ import annotations

import unittest

from awe_math.registry import all_models, load_models

try:                                                    # pragma: no cover
    import tkinter as tk
except Exception:                                       # pragma: no cover
    tk = None


def _tk_available() -> bool:
    """能不能真的起一个 Tk 窗口（无图形环境时返回 False，测试整体跳过）。"""
    if tk is None:
        return False
    try:
        root = tk.Tk()
    except Exception:
        return False
    root.destroy()
    return True


TK_OK = _tk_available()


@unittest.skipUnless(TK_OK, "没有可用的图形环境（tk.Tk() 起不来）")
class ViewSmokeTest(unittest.TestCase):
    """四个模型的桌面视图：建得起来、画得出东西、能干净关掉。"""

    def _open(self, spec):
        """按外壳的真实路径打开一个模型视图，返回 ``(root, shell)``。"""
        from awe_math.ui.tk.kit import discover_views
        from awe_math.ui.tk.shell import DesktopShell
        from awe_math.ui.tk.theme import install_theme

        discover_views()
        root = tk.Tk()
        install_theme(root)
        shell = DesktopShell(root, spec)
        root.update()                                   # 触发布局与首屏绘制
        return root, shell

    def test_every_model_opens_with_content(self) -> None:
        load_models()                                   # 先扫描 models/，否则注册表是空的
        models = all_models()
        self.assertTrue(models, "注册表里一个模型都没有")
        for spec in models:
            with self.subTest(model=spec.key):
                root, shell = self._open(spec)
                try:
                    view = shell.view
                    self.assertIsNotNone(view, f"{spec.key}：外壳没有建出视图")
                    canvas = getattr(view, "canvas", None)
                    self.assertIsNotNone(canvas, f"{spec.key}：视图没有画布")
                    items = canvas.find_all()
                    self.assertGreater(
                        len(items), 0,
                        f"{spec.key}：画布是空的（首屏一个图元都没画出来）")
                finally:
                    if shell.view is not None:
                        shell.view.shutdown()
                    root.destroy()

    def test_switching_between_models_is_clean(self) -> None:
        """连着切模型（先渗流再生命游戏）不该留下残影或抛异常 —— 走的是 ``_reset_host``。"""
        from awe_math.ui.tk.kit import discover_views
        from awe_math.ui.tk.shell import DesktopShell
        from awe_math.ui.tk.theme import install_theme

        discover_views()
        load_models()
        models = {spec.key: spec for spec in all_models()}
        if "percolation" not in models or "life_game" not in models:
            self.skipTest("缺少用于切换的模型")

        root = tk.Tk()
        install_theme(root)
        shell = None
        try:
            shell = DesktopShell(root, models["percolation"])
            root.update()
            self.assertIsNotNone(shell.view)
            shell.show(models["life_game"])               # 切到另一个骨架
            root.update()
            self.assertIsNotNone(shell.view)
            shell.show(models["percolation"])             # 再切回来
            root.update()
            self.assertIsNotNone(shell.view)
            self.assertIsNotNone(getattr(shell.view, "model", None))
        finally:
            if shell is not None and shell.view is not None:
                shell.view.shutdown()
            root.destroy()


    def test_non_square_shape_change_keeps_working(self) -> None:
        """在界面里把行数 / 列数改成**不相等**（用户报的"长宽比不为 1"），视图仍要正常。

        骨架改尺寸是就地改 ``model.rows`` / ``cols`` 再让内核重排（``_on_shape_change``）；
        内核的邻居表 / 边表都是按尺寸预编译的，所以这一步必须真的重建 —— 否则就是
        ``IndexError: bytearray index out of range``。这条测试把用户那一步原样走一遍。
        """
        from awe_math.ui.tk.kit import discover_views
        from awe_math.ui.tk.shell import DesktopShell
        from awe_math.ui.tk.theme import install_theme

        discover_views()
        load_models()
        models = {spec.key: spec for spec in all_models()}
        for key in ("percolation", "site_percolation"):
            with self.subTest(model=key):
                root = tk.Tk()
                install_theme(root)
                shell = None
                try:
                    shell = DesktopShell(root, models[key])
                    root.update()
                    view = shell.view
                    view.var_rows.set(20)
                    view.var_cols.set(30)
                    view._on_shape_change()          # 界面改尺寸走的就是这个回调
                    root.update()
                    view.regenerate()                # 立即重排 + 重绘（不等防抖）
                    root.update()
                    self.assertEqual((view.model.rows, view.model.cols), (20, 30))
                    self.assertGreater(len(view.canvas.find_all()), 0,
                                       f"{key}：改成 20×30 后画布是空的")
                finally:
                    if shell is not None and shell.view is not None:
                        shell.view.shutdown()
                    root.destroy()


if __name__ == "__main__":                              # pragma: no cover
    unittest.main()
