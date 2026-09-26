# Qt 视图扩展约定

Qt 后端采用“统一外框，模型拥有内部视图”的方式。

`prismath/ui/qt/` 只放不依赖某个数学模型的内容：`window.py` 负责应用窗口和目录，
`pages.py` 负责统一页面外框、状态区和控制台抽屉，`params.py` 按 `ModelSpec.params`
生成控件，`widgets.py` 提供稿纸背景与折叠面板，`stages/` 提供舞台协议、通用结果舞台
和动态发现机制，`theme.py` 集中管理淡色纸张和控件样式。

模型的 Qt 视图放在自己的目录中：

```text
prismath/models/<model_name>/views/qt/
├── __init__.py       # create_stage(spec)，可选；决定模型内部布局
├── stage.py          # 画布、动画、交互与模型专用指标
└── ...               # 需要时拆成 controls.py / metrics.py / animation.py
```

`ui/qt/stages.create_stage(spec)` 按 `spec.key` 自动导入这个包。没有专用 Qt 视图的模型
使用 `ResultStage`，所以新增模型不必修改中心注册表；有专用体验的模型只需增加自己的
`views/qt/` 目录。

组织思想与 Tk 相同：模型视图跟着模型走，后端只提供共享工具和懒加载机制。Qt 版本把
“外框”和“内部舞台”分得更明确：Tk 的旧视图可以继续继承共享骨架，而 Qt 视图可以完全
改变内部布局，只要实现最小舞台协议：

```python
class MyStage(StageBase):
    def set_payload(self, payload: dict) -> None: ...

    # 可选：舞台上的编辑内容作为下一次动作的输入
    def action_payload(self) -> dict: ...
```

模型需要播放、点击或自定义控制条时，可以在自己的 stage 类上增加 `play()`、`finish()`
和 Qt signals 等能力。渗流可以拥有彩色流动动画，Mandelbrot 可以拥有连续场交互，生命
游戏可以采用时间轴，蒲丰投针可以采用统计卡片，它们不必共享同一个三栏模板。

当前已有的三个专属舞台分别是：蒲丰投针的投针几何 / π 收敛曲线、生命游戏的可手绘
栅格 / 帧播放、万有引力的星体轨迹 / 尾迹回放。生命游戏手绘后，主动作会把当前棋盘
编码传回模型再演化，避免参数面板把手绘状态覆盖掉。

这种方式会让模型目录多一些 Qt 文件，但能保持模型边界清楚，避免通用页面累积大量
`if model == ...`，同时保留通用控件统一修复的好处。
