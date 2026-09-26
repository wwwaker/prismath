# -*- coding: utf-8 -*-
"""Qt 窗口壳与进程内启动函数。"""
from typing import Dict, Optional
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget
from ...registry import load_models
from ...spec import ModelSpec
from .pages import ModelPage
from .portal import ModelPortal
from .theme import install_style
class PrismathWindow(QMainWindow):
    def __init__(self, initial: Optional[ModelSpec] = None):
        super().__init__()
        self.setWindowTitle("prismath · 数学模型可视化")
        self.resize(1220, 860)
        self.setMinimumSize(900, 680)
        self.models = load_models()
        self.stack = QStackedWidget()
        self.portal = ModelPortal(self.models)
        self.portal.opened.connect(self.show_model)
        self.stack.addWidget(self.portal)
        self.setCentralWidget(self.stack)
        self._pages: Dict[str, ModelPage] = {}
        if initial is not None:
            self.show_model(initial)

    def show_model(self, spec: ModelSpec) -> None:
        page = self._pages.get(spec.key)
        if page is None:
            page = ModelPage(spec)
            page.backRequested.connect(self.show_portal)
            self._pages[spec.key] = page
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def show_portal(self) -> None:
        self.stack.setCurrentWidget(self.portal)




def launch_app(initial: Optional[ModelSpec] = None) -> int:
    app = QApplication.instance() or QApplication([])
    install_style(app)
    window = PrismathWindow(initial)
    window.show()
    return app.exec()
