# -*- coding: utf-8 -*-
"""
网页界面后端（**暂时弃用**）
=============================

本后端目前不是默认入口，也不再出现在桌面入口页与终端菜单里，只能显式进入：

    python main.py --ui web            # 直接打开网页界面
    python main.py --model perc --ui web

弃用原因：入口与交互统一收敛到桌面窗口（模型列表入口页 + 逐层动画），
网页端暂不投入维护。**代码保留**（:mod:`~prismath.ui.web.server` 与 ``static/`` 下的
前端资源），需要时可以随时恢复为默认入口之一：把 :data:`prismath.ui.UI_BACKENDS` 里
``web`` 的 ``deprecated`` 改回 ``False`` 即可。

后续若要继续维护网页端，建议按与桌面端相同的规则整理：
共享前端骨架留在 ``ui/web/``，每个模型的渲染器跟着模型走
（``prismath/models/<模型包>/views/web.js``），由后端按约定懒加载——
这样新增模型同样不需要改动 ``app.js``。
"""
