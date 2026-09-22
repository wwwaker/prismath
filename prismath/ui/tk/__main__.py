# -*- coding: utf-8 -*-
"""让 ``python -m prismath.ui.tk`` 直接打开桌面窗口（等价于 CLI 的 tk 界面）。"""

from .shell import launch

if __name__ == "__main__":
    raise SystemExit(launch())
