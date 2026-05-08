# main.py — Clawde Desktop Assistant  (Modular Edition)
# Static YS launcher — no animation, no speech bubble.
# Tool windows live in tool_*.py; shared utilities in styles.py.

import os, sys, math
_YS_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_ys.png")
from PyQt6.QtCore    import Qt, QPoint, QRect
from PyQt6.QtGui     import QPixmap, QPainter, QColor, QPen, QPainterPath, QFont
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel,
                              QVBoxLayout, QPushButton, QFrame)

# ── Shared infrastructure ────────────────────────────────────────────────────
from styles import (BASE_DIR, ASSETS_DIR, CONFIG_FILE, asset,
                    GLASS_QSS, load_config, save_config, BaseToolWindow)

# ── Tool windows ─────────────────────────────────────────────────────────────
from tool_network        import IPMonitor
from tool_pid            import PidTunerBuddy
from tool_pid_vfd        import VfdPressureTuner
from tool_unit_converter import UnitConverterTool
from tool_advanced_calc  import AdvancedCalcTool
from tool_pid_drycool    import AhuDryCoolTuner
from tool_pid_mau        import MauSimulator

# ═══════════════════════════════════════════════════════
#  YS LOGO  (drawn programmatically — no image files)
# ═══════════════════════════════════════════════════════
def _make_ys_pixmap(size: int = 48) -> QPixmap:
    # ── Try real logo file first ───────────────────────
    for logo_path in (_YS_LOGO_PATH, asset("logo_ys.png")):
        if os.path.exists(logo_path):
            src = QPixmap(logo_path)
            if not src.isNull():
                return src.scaled(size, size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
    # ── Fallback: draw programmatically ───────────────
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx = cy = size / 2.0
    r_outer = cx - 1.0

    # Outer dark-navy circle
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#1C2B4A"))
    p.drawEllipse(1, 1, size - 2, size - 2)

    # Ring marks (8 pairs)
    r_mark  = r_outer - 2.5
    mark_sz = max(2, size // 14)
    for i in range(8):
        angle = math.radians(i * 45.0 - 90)
        mx = cx + r_mark * math.cos(angle)
        my = cy + r_mark * math.sin(angle)
        p.setBrush(QColor("#8FA8C8"))
        p.drawEllipse(int(mx - mark_sz / 2), int(my - mark_sz / 2), mark_sz, mark_sz)
        r2  = r_mark - mark_sz - 1
        mx2 = cx + r2 * math.cos(angle)
        my2 = cy + r2 * math.sin(angle)
        p.setBrush(QColor("#4A6A8A"))
        p.drawEllipse(int(mx2 - mark_sz / 2), int(my2 - mark_sz / 2),
                      mark_sz - 1, mark_sz - 1)

    # Inner white circle
    r_inner = r_outer * 0.60
    p.setBrush(QColor("#E8EEF5"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(int(cx - r_inner), int(cy - r_inner),
                  int(r_inner * 2), int(r_inner * 2))

    # "YS." text
    fsize = max(6, int(size * 0.28))
    font  = QFont("Segoe UI", fsize, QFont.Weight.Black)
    p.setFont(font)
    p.setPen(QColor("#1C2B4A"))
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "YS.")

    p.end()
    return pix


# ═══════════════════════════════════════════════════════
#  LAUNCHER BAR
# ═══════════════════════════════════════════════════════
class LauncherBar(QWidget):
    def __init__(self, buttons: dict, close_cb=None):
        super().__init__(None,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 8); lay.setSpacing(4)
        for lbl, cb in buttons.items():
            if cb is None:
                # Section header / separator label
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet("QFrame{border:none;border-top:1px solid "
                                  "rgba(255,255,255,0.10);background:transparent;}")
                sep.setFixedHeight(1)
                lay.addWidget(sep)
                hdr = QLabel(lbl)
                hdr.setFixedHeight(20)
                hdr.setStyleSheet(
                    "QLabel{color:rgba(255,128,0,180);font-size:10px;"
                    "font-family:'Microsoft JhengHei','Segoe UI',sans-serif;"
                    "font-weight:bold;padding:0 6px;background:transparent;}")
                lay.addWidget(hdr)
                continue
            btn = QPushButton(lbl); btn.setFixedHeight(36)
            btn.setStyleSheet(
                "QPushButton{background:rgba(38,38,38,220);color:#c6c6c6;"
                "border:1px solid rgba(255,255,255,0.06);border-radius:7px;"
                "font-size:13px;font-family:'Microsoft JhengHei','Segoe UI',sans-serif;"
                "padding:0 14px;text-align:left;}"
                "QPushButton:hover{background:rgba(255,128,0,190);color:#fff;"
                "border-color:rgba(255,128,0,88);}")
            btn.clicked.connect(cb); btn.clicked.connect(self.hide)
            lay.addWidget(btn)

        if close_cb is not None:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("QFrame{border:none;border-top:1px solid "
                              "rgba(255,255,255,0.08);background:transparent;}")
            sep.setFixedHeight(1)
            lay.addWidget(sep)

            cb_btn = QPushButton("✕   關閉  Exit"); cb_btn.setFixedHeight(36)
            cb_btn.setStyleSheet(
                "QPushButton{background:rgba(38,38,38,220);color:#CC4444;"
                "border:1px solid rgba(255,255,255,0.06);border-radius:7px;"
                "font-size:13px;font-family:'Microsoft JhengHei','Segoe UI',sans-serif;"
                "padding:0 14px;text-align:left;}"
                "QPushButton:hover{background:rgba(180,35,35,210);color:#fff;"
                "border-color:rgba(220,60,60,88);}")
            cb_btn.clicked.connect(close_cb)
            lay.addWidget(cb_btn)

        self.setFixedWidth(202); self.adjustSize()

    def popup_at(self, pos: QPoint):
        scr = QApplication.primaryScreen().availableGeometry()
        x   = pos.x() - self.width()  // 2
        y   = pos.y() - self.height() - 6
        self.move(max(0, min(x, scr.width()  - self.width())),
                  max(0, min(y, scr.height() - self.height())))
        self.show(); self.raise_()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 10, 10)
        p.fillPath(path, QColor(24, 24, 24, 224))
        p.setPen(QPen(QColor(255, 128, 0, 40), 1)); p.drawPath(path)


# ═══════════════════════════════════════════════════════
#  MAIN WINDOW  —  static YS icon + tool orchestration
# ═══════════════════════════════════════════════════════
ICON_SIZE = 144

class ClawdeWindow(QWidget):
    def __init__(self):
        super().__init__(None,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self.setFixedSize(ICON_SIZE, ICON_SIZE)

        # Static YS logo
        self.img = QLabel(self)
        self.img.setGeometry(0, 0, ICON_SIZE, ICON_SIZE)
        self.img.setPixmap(_make_ys_pixmap(ICON_SIZE))
        self.img.setScaledContents(True)
        self.img.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.img.setStyleSheet("background:transparent;")

        # Tool windows
        self.ip_mon    = IPMonitor()
        self.pid_tuner = PidTunerBuddy()
        self.vfd_tuner = VfdPressureTuner()
        self.unit_conv = UnitConverterTool()
        self.adv_calc  = AdvancedCalcTool()
        self.ahu_cool  = AhuDryCoolTuner()
        self.mau_sim   = MauSimulator()

        # Launcher
        self.launcher = LauncherBar({
            "━━  工具  ━━━━━━━━━━━━━": None,
            "🌐 IP 監控器":             self._open_ip,
            "📐 單位換算器":             self._open_unit,
            "🔬 進階計算器":             self._open_adv,
            "━━  PID 控制  ━━━━━━━━": None,
            "⚙️ PID Tuner":            self._open_pid,
            "⚡ VFD 壓力控制":          self._open_vfd,
            "❄️ AHU 冷卻盤管":         self._open_ahu,
            "🌬️ MAU 空調箱":           self._open_mau,
        }, close_cb=QApplication.instance().quit)

        self._drag_pos = QPoint()
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - ICON_SIZE - 8, scr.bottom() - ICON_SIZE - 8)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

    # ── Tool openers ───────────────────────────────────────────────────
    def _open_vfd(self):
        self.vfd_tuner.center_near(self.pos()); self.vfd_tuner.show(); self.vfd_tuner.raise_()

    def _open_ahu(self):
        self.ahu_cool.center_near(self.pos()); self.ahu_cool.show(); self.ahu_cool.raise_()

    def _open_mau(self):
        self.mau_sim.center_near(self.pos()); self.mau_sim.show(); self.mau_sim.raise_()

    def _open_unit(self):
        self.unit_conv.center_near(self.pos()); self.unit_conv.show(); self.unit_conv.raise_()

    def _open_adv(self):
        self.adv_calc.center_near(self.pos()); self.adv_calc.show(); self.adv_calc.raise_()

    def _open_ip(self):
        self.ip_mon.center_near(self.pos()); self.ip_mon.show(); self.ip_mon.raise_()

    def _open_pid(self):
        self.pid_tuner.center_near(self.pos()); self.pid_tuner.show(); self.pid_tuner.raise_()

    # ── Mouse events ───────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.MouseButton.RightButton:
            self.launcher.popup_at(self.pos() + QPoint(ICON_SIZE // 2, 0))

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)


# ═══════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════
def main():
    print(f"[INFO] BASE_DIR   = {BASE_DIR}")
    print(f"[INFO] ASSETS_DIR = {ASSETS_DIR}")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("亞聖國際科技有限公司")

    win = ClawdeWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
