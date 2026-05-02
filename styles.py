# styles.py — Shared styles, base classes, config, and paths
# Imported by all tool modules and main.py

import os, sys, json
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore    import Qt, QPoint
from PyQt6.QtGui     import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QFrame,
                              QVBoxLayout, QHBoxLayout, QPushButton, QSizeGrip)

# ═══════════════════════════════════════════════════════
#  PATHS
# ═══════════════════════════════════════════════════════
BASE_DIR = str(Path(__file__).resolve().parent)
if BASE_DIR.lower().endswith('.py'):
    BASE_DIR = os.path.dirname(BASE_DIR)

ASSETS_DIR  = os.path.join(BASE_DIR, "assets")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
IP_LOG_FILE = os.path.join(BASE_DIR, "clawde_ip_log.txt")

def asset(f: str) -> str:
    return os.path.join(ASSETS_DIR, f)

# ═══════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════
_DEFAULT_CONFIG = {
    "watchlist":          ["^TWII", "2330.TW", "^GSPC", "^IXIC", "^SOX"],
    "heat_wall_interval": 60,
    "ip_channels":        [{"label": f"CH{i+1:02d}", "ip": ""} for i in range(10)],
    "converter_presets":  [
        {"name": "4-20mA→0-100%",
         "in_min": 4.0, "in_max": 20.0, "out_min": 0.0, "out_max": 100.0}
    ]
}

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return {**_DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return dict(_DEFAULT_CONFIG)

def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] config: {e}", file=sys.stderr)

# ═══════════════════════════════════════════════════════
#  SHARED QSS  (glass-morphism dark theme)
# ═══════════════════════════════════════════════════════
GLASS_QSS = """
QWidget { color:#ddd; font-family:'Microsoft JhengHei','Segoe UI',sans-serif; }
QLabel   { background:transparent; }
QLineEdit, QTextEdit {
    background:rgba(30,30,30,218); border:1px solid rgba(255,255,255,0.08);
    border-radius:5px; color:#e0e0e0; padding:3px 7px; font-size:12px;
    selection-background-color:rgba(255,128,0,150); }
QPushButton {
    background:rgba(255,128,0,172); color:#fff; border:none;
    border-radius:5px; padding:4px 12px; font-size:12px; }
QPushButton:hover   { background:rgba(255,150,40,228); }
QPushButton:pressed { background:rgba(200,96,0,228);   }
QPushButton#Gray  { background:rgba(58,58,58,162); }
QPushButton#Gray:hover  { background:rgba(84,84,84,212); }
QPushButton#Green { background:rgba(26,136,56,172); }
QPushButton#Green:hover { background:rgba(36,165,70,228); }
QPushButton#Red   { background:rgba(148,36,36,152); }
QPushButton#Red:hover   { background:rgba(188,48,48,222); }
QTabWidget::pane {
    border:1px solid rgba(255,255,255,0.07); border-radius:8px;
    background:rgba(24,24,24,212); margin-top:-1px; }
QTabBar::tab {
    background:rgba(42,42,42,182); color:#999; padding:5px 12px;
    border-radius:4px; margin-right:2px; font-size:12px; }
QTabBar::tab:selected { background:rgba(255,128,0,202); color:#fff; }
QTabBar::tab:hover:!selected { background:rgba(60,60,60,182); color:#ddd; }
QScrollArea { border:none; background:transparent; }
QScrollBar:vertical { background:rgba(18,18,18,52); width:5px; border-radius:3px; }
QScrollBar::handle:vertical { background:rgba(255,128,0,88); border-radius:3px; min-height:16px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
"""

# ═══════════════════════════════════════════════════════
#  TITLE BAR
# ═══════════════════════════════════════════════════════
class TitleBar(QWidget):
    def __init__(self, title: str, win: QWidget):
        super().__init__(win)
        self._win = win; self._drag = QPoint()
        self.setFixedHeight(38)
        lay = QHBoxLayout(self); lay.setContentsMargins(14, 0, 8, 0)
        lbl = QLabel(title)
        lbl.setStyleSheet("color:#c6c6c6;font-size:13px;font-weight:600;"
                          "background:transparent;"
                          "font-family:'Microsoft JhengHei','Segoe UI',sans-serif;")
        btn = QPushButton("✕"); btn.setFixedSize(26, 26)
        btn.setStyleSheet(
            "QPushButton{background:transparent;color:#525252;border:none;"
            "border-radius:13px;font-size:14px;}"
            "QPushButton:hover{background:rgba(195,46,46,202);color:#fff;}")
        btn.clicked.connect(win.hide)
        lay.addWidget(lbl); lay.addStretch(); lay.addWidget(btn)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self._win.move(e.globalPosition().toPoint() - self._drag)

# ═══════════════════════════════════════════════════════
#  BASE TOOL WINDOW
# ═══════════════════════════════════════════════════════
class BaseToolWindow(QWidget):
    def __init__(self, title: str, w: int, h: int):
        super().__init__(None,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(GLASS_QSS)
        # Resizable: initial size + sensible minimum; no fixed size
        self.resize(w, h)
        self.setMinimumSize(300, 220)
        self.setMaximumSize(16777215, 16777215)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        outer.addWidget(TitleBar(title, self))
        self.content = QWidget()
        self.content.setStyleSheet("background:transparent;")
        outer.addWidget(self.content, 1)

        # Universal resize grip — orange dot, bottom-right corner
        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(14, 14)
        self._grip.setStyleSheet(
            "QSizeGrip{background:#FF8800;border-radius:2px;}")
        self._grip.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._grip.move(self.width()  - self._grip.width(),
                        self.height() - self._grip.height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 13, 13)
        p.fillPath(path, QColor(24, 24, 24, 215))
        p.setPen(QPen(QColor(255, 128, 0, 46), 1))
        p.drawPath(path)

    def center_near(self, ref: QPoint):
        scr = QApplication.primaryScreen().availableGeometry()
        x = ref.x() - self.width() // 2
        y = ref.y() - self.height() - 10
        self.move(max(0, min(x, scr.width()  - self.width())),
                  max(0, min(y, scr.height() - self.height())))
