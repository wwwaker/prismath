# -*- coding: utf-8 -*-
"""单模型工作台页面。

页面只负责把 ModelSpec 接到通用控件和视觉舞台；模型算法不放在这里。
"""
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget
from ...spec import ModelSpec
from .params import ParamEditor
from .stages import create_stage
from .widgets import CollapsibleBox, PaperSurface


class ModelPage(PaperSurface):
    """单模型页面，只负责把模型契约接到控件和舞台。"""

    backRequested = Signal()

    def __init__(self, spec: ModelSpec, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.spec = spec
        self.payload: Dict[str, Any] = {}
        self.editor = ParamEditor(spec)
        self._build()
        self.editor.changed.connect(self._mark_dirty)
        self._run_initial()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 18, 30, 30)
        outer.setSpacing(12)
        header = QHBoxLayout()
        back = QPushButton("← 模型目录")
        back.setObjectName("quietButton")
        back.clicked.connect(self.backRequested.emit)
        heading = QVBoxLayout()
        eyebrow = QLabel(f"{self.spec.topic}  ·  {self.spec.icon}")
        eyebrow.setObjectName("eyebrow")
        title = QLabel(self.spec.name)
        title.setObjectName("pageTitle")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        header.addWidget(back, 0, Qt.AlignTop)
        header.addLayout(heading, 1)
        self.console_button = QPushButton("☷  控制台")
        self.console_button.setObjectName("quietButton")
        self.console_button.clicked.connect(self._toggle_console)
        header.addWidget(self.console_button, 0, Qt.AlignTop)
        outer.addLayout(header)

        intro = QLabel(self.spec.summary)
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        self.stage: QWidget
        self.stage = create_stage(self.spec)
        if hasattr(self.stage, "originClicked"):
            self.stage.originClicked.connect(self._origin_clicked)  # type: ignore[attr-defined]
        if hasattr(self.stage, "edited"):
            self.stage.edited.connect(self._stage_edited)  # type: ignore[attr-defined]
        if getattr(self.stage, "playback", False):
            self.play_button = QPushButton(getattr(self.stage, "play_label", "▶ 播放"))
            self.finish_button = QPushButton(getattr(self.stage, "finish_label", "⏭ 完成"))
            self.play_button.clicked.connect(self._toggle_play)
            self.finish_button.clicked.connect(self._finish_play)
        self.stage.setObjectName("stage")
        outer.addWidget(self.stage, 1)

        action_row = QHBoxLayout()
        self.status = QLabel("正在准备实验…")
        self.status.setObjectName("status")
        action_row.addWidget(self.status, 1)
        if getattr(self.stage, "playback", False):
            action_row.addWidget(self.play_button)
            action_row.addWidget(self.finish_button)
        primary = next((action for action in self.spec.actions if action.kind == "primary"), None)
        if primary is not None:
            run = QPushButton(primary.label)
            run.setObjectName("accentButton")
            run.clicked.connect(lambda _checked=False, key=primary.key: self._run_action(key))
            action_row.addWidget(run)
        outer.addLayout(action_row)

        self.metrics = QLabel("关键数值将在这里出现")
        self.metrics.setObjectName("metrics")
        self.metrics.setWordWrap(True)
        outer.addWidget(self.metrics)

        # 控制台是页面的浮层子控件，不进入 outer 布局；这样展开时舞台不会缩小。
        self.console = QFrame(self)
        self.console.setObjectName("console")
        console_layout = QVBoxLayout(self.console)
        console_layout.setContentsMargins(16, 12, 16, 14)
        console_title = QHBoxLayout()
        console_title.addWidget(QLabel("实验控制台"), 1)
        close = QPushButton("收起")
        close.setObjectName("quietButton")
        close.clicked.connect(self._toggle_console)
        console_title.addWidget(close)
        console_layout.addLayout(console_title)
        secondary = CollapsibleBox("高级动作", checked=False)
        secondary.body_layout.addWidget(QLabel("批量统计、扫描和其他低频动作放在这里，避免打断主舞台。"))
        primary_key = next((item.key for item in self.spec.actions if item.kind == "primary"), None)
        for action in self.spec.actions:
            if action.key == primary_key:
                continue
            button = QPushButton(action.label)
            button.setToolTip(action.hint or action.label)
            button.clicked.connect(lambda _checked=False, key=action.key: self._run_action(key))
            secondary.body_layout.addWidget(button)
        if len(self.spec.actions) > 1:
            console_layout.addWidget(secondary)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(315)
        scroll.setWidget(self.editor)
        console_layout.addWidget(scroll)
        self.console.setVisible(False)
        self._position_console()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_console()

    def _position_console(self) -> None:
        """把控制台锚定在右上角，尺寸随页面变化但不参与主布局。"""
        if not hasattr(self, "console"):
            return
        margin_right = 20
        top = 70
        width = min(420, max(340, self.width() // 3))
        width = min(width, max(1, self.width() - 40))
        height = min(560, max(260, self.height() - top - 24))
        height = min(height, max(1, self.height() - top - 12))
        self.console.setGeometry(max(20, self.width() - width - margin_right), top,
                                 width, height)
        if self.console.isVisible():
            self.console.raise_()

    def _run_initial(self) -> None:
        action = next((item.key for item in self.spec.actions if item.kind == "primary"), None)
        if action:
            QTimer.singleShot(50, lambda: self._run_action(action))

    def _toggle_console(self) -> None:
        opened = not self.console.isVisible()
        self.console.setVisible(opened)
        if opened:
            self._position_console()
            self.console.raise_()
        self.console_button.setText("☷  收起控制台" if opened else "☷  控制台")

    def _mark_dirty(self) -> None:
        self.status.setText("参数已改变 · 点击主动作应用")

    def _stage_edited(self, _cells: str) -> None:
        self.status.setText("棋盘已编辑 · 点击“开始演化”从当前状态继续")

    def _origin_clicked(self, index: int) -> None:
        action = getattr(self.stage, "origin_action", "")
        if not action:
            return
        self._run_action(action, {"origin": index})

    def _toggle_play(self) -> None:
        stage = self.stage
        if hasattr(stage, "play"):
            stage.play()
            self.play_button.setText(getattr(stage, "pause_label", "⏸ 暂停")
                                     if stage.playing else getattr(stage, "play_label", "▶ 播放"))

    def _finish_play(self) -> None:
        if hasattr(self.stage, "finish"):
            self.stage.finish()
            self.play_button.setText(getattr(self.stage, "play_label", "▶ 播放"))

    def _run_action(self, action: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self.spec.handler is None:
            self.status.setText("这个模型没有可执行动作")
            return
        self.status.setText("计算中…")
        QApplication.processEvents()
        try:
            action_input = payload
            if action_input is None:
                provider = getattr(self.stage, "action_payload", None)
                action_input = provider() if callable(provider) else {}
            result = self.spec.run(action, self.editor.values(), action_input or {})
        except Exception as exc:  # 让错误留在界面中，不抛窗口级 traceback
            self.status.setText(f"运行失败：{type(exc).__name__}: {exc}")
            return
        self.payload = result
        self.stage.set_payload(result)
        if hasattr(self, "play_button"):
            self.play_button.setText(getattr(self.stage, "play_label", "▶ 播放"))
        self._update_metrics(result)
        self.status.setText("已就绪 · 可以播放、点击网格或打开控制台继续实验")

    def _update_metrics(self, payload: Dict[str, Any]) -> None:
        keys = ["p", "probability", "success", "wetRatio", "spreadRatio", "depth",
                "insideRatio", "area", "piEstimate", "population", "energyDrift"]
        shown = []
        for key in keys:
            if key in payload:
                shown.append(f"{key} = {payload[key]}")
        self.metrics.setText("   ·   ".join(shown) if shown else "结果已绘制；打开控制台查看完整参数。")


