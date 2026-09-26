# -*- coding: utf-8 -*-
"""Qt 主题：淡色数学稿纸，不包含任何模型逻辑。"""
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

PAPER = QColor("#f8f5ed")
PAPER_LIGHT = QColor("#fffdf8")
GRID = QColor("#e7dfd1")
GRID_MAJOR = QColor("#d8cdbc")
INK = QColor("#263238")
MUTED = QColor("#68737a")
LINE = QColor("#cfc5b5")
ACCENT = QColor("#ad5c34")
TEAL = QColor("#367b83")

def _qcolor(value: str, fallback: QColor = ACCENT) -> QColor:
    color = QColor(str(value or ""))
    return color if color.isValid() else QColor(fallback)

def install_style(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget { color: #263238; font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 12px; }
        QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget { background: #f8f5ed; border: 0; }
        QLabel#pageTitle { font-size: 30px; font-weight: 700; color: #263238; }
        QLabel#eyebrow { color: #ad5c34; font-size: 11px; font-weight: 700; }
        QLabel#muted, QLabel#hint { color: #68737a; }
        QLabel#hint { font-size: 10px; padding-bottom: 3px; }
        QFrame#modelCard, QFrame#console, QFrame#collapsibleBox { background: #fffdf8; border: 1px solid #cfc5b5; border-radius: 9px; }
        QFrame#modelCard:hover { border-color: #ad5c34; background: #fffaf0; }
        QLabel#cardNumber { color: #ad5c34; font-family: Consolas; font-size: 12px; }
        QLabel#cardIcon { color: #367b83; font-size: 24px; min-width: 34px; }
        QLabel#cardName { color: #263238; font-size: 16px; font-weight: 650; }
        QLabel#status { color: #367b83; padding: 5px 0; }
        QLabel#metrics { color: #526069; background: #fffdf8; border: 1px solid #ded5c8; border-radius: 7px; padding: 10px; }
        QWidget#stage { background: #fffdf8; border: 1px solid #a99d8e; border-radius: 10px; }
        QPushButton { color: #465057; background: #f1ece2; border: 1px solid #cfc5b5; border-radius: 6px; padding: 8px 13px; }
        QPushButton:hover { background: #e9e1d5; border-color: #a99d8e; }
        QPushButton#accentButton { color: #fffaf1; background: #ad5c34; border-color: #ad5c34; font-weight: 650; }
        QPushButton#accentButton:hover { background: #c77745; }
        QPushButton#quietButton { background: transparent; border-color: transparent; color: #68737a; }
        QPushButton#quietButton:hover { color: #263238; background: #eee7da; }
        QToolButton { color: #526069; background: transparent; border: 0; padding: 8px 4px; text-align: left; }
        QToolButton:checked { color: #ad5c34; font-weight: 650; }
        QComboBox, QSpinBox, QDoubleSpinBox { color: #263238; background: #fffdf8; border: 1px solid #cfc5b5; border-radius: 5px; padding: 5px; min-height: 22px; }
        QScrollArea { background: transparent; }
        QSlider::groove:horizontal { height: 4px; background: #ded5c8; border-radius: 2px; }
        QSlider::handle:horizontal { width: 13px; margin: -5px 0; background: #ad5c34; border-radius: 6px; }
    """)
