"""prismath 的回归测试（stdlib ``unittest``，无额外测试依赖）。

    python -m unittest discover -s tests -t . -v      # 全跑
    python -m unittest tests.test_golden -v           # 只跑金样本回归

约定：

* 测试只 import 模型的**内核**（``prismath.models.<模型>.model``）与 ``spec`` 的纯函数，
  不启动 tkinter / 不读界面代码；
* 统计类断言一律**固定种子 + 容差**（不要写"某次实测到的"精确数值）；
* 已发布的教学结论（p_c、周期长度、滑翔机 4 代平移 (1,1)…）属于**契约**，只许不成立时报错。
"""
