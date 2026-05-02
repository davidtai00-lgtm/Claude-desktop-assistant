# tool_pid_vfd_anim.py — VFD Pump Animation Window
# Centrifugal pump cross-section with:
#   • Rotating impeller (speed ∝ Hz)
#   • Flow particles in inlet / outlet pipes
#   • Speed ring (0-60 Hz colour arc)
#   • Play / Pause button

import math

from PyQt6.QtCore    import Qt, QTimer, QPoint, QRect
from PyQt6.QtGui     import QPainter, QColor, QPen, QFont, QPainterPath
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QPushButton, QFrame)


# ══════════════════════════════════════════════════════════
#  PUMP DRAWING CANVAS
# ══════════════════════════════════════════════════════════
class _PumpCanvas(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(340, 310)
        self._angle  = 0.0    # impeller rotation angle (°)
        self._flow   = 0.0    # particle phase  0–1
        self._hz     = 0.0
        self._pa     = 0.0
        self._sv_pa  = 2.5
        self._paused = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)           # ≈ 60 fps

    # ── External API ────────────────────────────────────────────
    def update_values(self, pa: float, hz: float, sv_pa: float):
        self._pa = pa; self._hz = hz; self._sv_pa = sv_pa

    def set_paused(self, v: bool):
        self._paused = v

    # ── Animation tick ───────────────────────────────────────────
    def _tick(self):
        if not self._paused:
            spd = self._hz / 60.0
            self._angle = (self._angle - spd * 11.0) % 360.0
            self._flow  = (self._flow  + spd * 0.040) % 1.0
        self.update()

    # ════════════════════════════════════════════════════
    #  PAINT
    # ════════════════════════════════════════════════════
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#080E14"))

        cx = w // 2
        cy = h // 2 + 10   # shift slightly downward to make room for Hz text above
        r  = int(min(w * 0.42, (h - 30) * 0.44))

        self._draw_pipes(p, cx, cy, r)
        self._draw_casing(p, cx, cy, r)
        self._draw_speed_ring(p, cx, cy, r)
        self._draw_impeller(p, cx, cy, int(r * 0.85))
        self._draw_particles(p, cx, cy, r)
        self._draw_hz_text(p, w, cx, cy, r)
        if self._paused:
            self._draw_pause_overlay(p, w, h)
        p.end()

    # ── Pump casing ──────────────────────────────────────────────
    def _draw_casing(self, p, cx, cy, r):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0C1A28"))
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        p.setPen(QPen(QColor("#1E4060"), 7))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

    # ── Inlet (bottom) / Outlet (right) pipes ────────────────────
    def _draw_pipes(self, p, cx, cy, r):
        pw = int(r * 0.40)      # pipe width
        ph = int(r * 0.58)      # pipe height/length

        # Pipe bodies
        p.setPen(QPen(QColor("#1E4060"), 4))
        p.setBrush(QColor("#0C1A28"))
        p.drawRect(cx - pw // 2, cy + r - 5, pw, ph)       # inlet (bottom)
        p.drawRect(cx + r - 5,   cy - pw // 2, ph, pw)     # outlet (right)

        # Flowing fill (teal) when running
        if self._hz > 0.5 and not self._paused:
            a = int(min(200, self._hz / 60.0 * 160))
            p.setBrush(QColor(0, 110, 200, a))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(cx - pw // 2 + 4, cy + r + 3, pw - 8, ph - 8)
            p.drawRect(cx + r + 3, cy - pw // 2 + 4, ph - 8, pw - 8)

        # Chevron arrows
        arw = QColor("#1E6080") if self._hz > 0 else QColor("#222830")
        p.setPen(QPen(arw, 2, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        mid_in  = cy + r + ph // 2
        mid_out = cx + r + ph // 2
        for d in (-8, 8):
            # Inlet ↑
            p.drawLine(cx - 10, mid_in + d + 8, cx, mid_in + d)
            p.drawLine(cx + 10, mid_in + d + 8, cx, mid_in + d)
            # Outlet →
            p.drawLine(mid_out + d, cy - 10, mid_out + d + 8, cy)
            p.drawLine(mid_out + d, cy + 10, mid_out + d + 8, cy)

        # Labels
        f7 = QFont("Microsoft JhengHei", 7); f7.setBold(True)
        p.setFont(f7); p.setPen(QColor("#2A4A5A"))
        p.drawText(QRect(cx - 24, cy + r + ph - 18, 48, 16),
                   Qt.AlignmentFlag.AlignCenter, "入口  IN")
        p.drawText(QRect(cx + r + ph - 10, cy - 8, 36, 16),
                   Qt.AlignmentFlag.AlignLeft, "→ OUT")

    # ── Outer Hz speed ring ──────────────────────────────────────
    def _draw_speed_ring(self, p, cx, cy, r):
        rr   = r + 16
        rect = QRect(cx - rr, cy - rr, rr * 2, rr * 2)

        # Background (dark)
        p.setPen(QPen(QColor("#101820"), 7,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 0, 360 * 16)

        # Hz fill arc (CW from top)
        ratio = max(0.0, min(1.0, self._hz / 60.0))
        if ratio > 0.01:
            rc = int(ratio * 240)
            bc = int((1.0 - ratio) * 190 + 60)
            p.setPen(QPen(QColor(rc, 80, bc), 7,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, 90 * 16, -int(ratio * 360 * 16))

    # ── Rotating impeller ────────────────────────────────────────
    def _draw_impeller(self, p, cx, cy, r):
        p.save()
        p.translate(cx, cy)
        p.rotate(self._angle)

        N     = 6
        r_in  = r * 0.22
        r_out = r * 0.90
        spd   = self._hz / 60.0

        # Fluid wedges between blades
        for i in range(N):
            a0 = math.radians(i * 360 / N)
            a1 = math.radians((i + 1) * 360 / N)
            back = math.radians(52)
            path = QPainterPath()
            path.moveTo(r_in  * math.cos(a0),        r_in  * math.sin(a0))
            path.lineTo(r_out * math.cos(a0 - back), r_out * math.sin(a0 - back))
            path.lineTo(r_out * math.cos(a1 - back), r_out * math.sin(a1 - back))
            path.lineTo(r_in  * math.cos(a1),        r_in  * math.sin(a1))
            path.closeSubpath()
            p.setBrush(QColor(0, 80, 160, int(spd * 55)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(path)

        # Backward-curved blades
        for i in range(N):
            sd  = i * 360.0 / N
            sr  = math.radians(sd)
            sx  = r_in * math.cos(sr);      sy  = r_in * math.sin(sr)
            cr  = math.radians(sd - 28);    cr_r = (r_in + r_out) * 0.52
            cx2 = cr_r * math.cos(cr);      cy2  = cr_r * math.sin(cr)
            er  = math.radians(sd - 56)
            ex  = r_out * math.cos(er);     ey   = r_out * math.sin(er)

            path = QPainterPath()
            path.moveTo(sx, sy); path.quadTo(cx2, cy2, ex, ey)

            gc = int(140 + spd * 80);  bc_c = int(190 + spd * 65)
            p.setPen(QPen(QColor(0, gc, bc_c), 5,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        # Hub
        rh = int(r_in * 0.85)
        p.setBrush(QColor("#2A4A6A")); p.setPen(QPen(QColor("#3A6A8A"), 2))
        p.drawEllipse(-rh, -rh, rh * 2, rh * 2)
        p.setBrush(QColor("#7AAABB")); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(-4, -4, 8, 8)

        p.restore()

    # ── Flow particles ───────────────────────────────────────────
    def _draw_particles(self, p, cx, cy, r):
        if self._hz < 1 or self._paused:
            return
        pw = int(r * 0.40); ph = int(r * 0.58)
        a  = int(min(220, self._hz / 60.0 * 190))
        clr = QColor(0, 190, 255, a)
        sz  = 7

        p.setPen(Qt.PenStyle.NoPen); p.setBrush(clr)
        for i in range(5):
            t = (self._flow + i * 0.20) % 1.0
            py = int(cy + r + ph * (1.0 - t))
            p.drawEllipse(cx - sz // 2, py - sz // 2, sz, sz)
            px = int(cx + r + ph * t)
            p.drawEllipse(px - sz // 2, cy - sz // 2, sz, sz)

    # ── Hz text above pump ───────────────────────────────────────
    def _draw_hz_text(self, p, w, cx, cy, r):
        fhz = QFont("Consolas", 13); fhz.setBold(True)
        p.setFont(fhz)
        clr = QColor("#FF8800") if self._hz > 0 else QColor("#303030")
        p.setPen(clr)
        p.drawText(QRect(cx - 60, cy - r - 36, 120, 26),
                   Qt.AlignmentFlag.AlignCenter, f"{self._hz:.1f} Hz")

    # ── Pause overlay ────────────────────────────────────────────
    def _draw_pause_overlay(self, p, w, h):
        fp = QFont("Segoe UI", 32); fp.setBold(True)
        p.setFont(fp); p.setPen(QColor(255, 255, 255, 80))
        p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "⏸")


# ══════════════════════════════════════════════════════════
#  FLOATING ANIMATION WINDOW
# ══════════════════════════════════════════════════════════
class VfdAnimWindow(QWidget):
    """Frameless floating window: pump animation + Pa/Hz readout + play/pause."""

    def __init__(self, parent=None):
        super().__init__(parent,
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(370, 500)
        self._drag_pos = QPoint()
        self._paused   = False
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # Outer container (rounded, dark)
        ctn = QWidget(); ctn.setObjectName("ctn")
        ctn.setStyleSheet(
            "#ctn{background:#0D1218;"
            "border:1px solid #1E3A5A;border-radius:12px;}")
        root.addWidget(ctn)

        lay = QVBoxLayout(ctn)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        # Title bar
        tbar = QFrame()
        tbar.setFixedHeight(36)
        tbar.setStyleSheet(
            "QFrame{background:#0A1018;"
            "border-bottom:1px solid #1A3050;"
            "border-radius:12px 12px 0 0;}")
        th = QHBoxLayout(tbar)
        th.setContentsMargins(12, 0, 8, 0); th.setSpacing(6)
        title_lbl = QLabel("⚡  VFD 泵浦動畫  Pump Simulation")
        title_lbl.setStyleSheet(
            "color:#4A8AAA;font-size:9pt;font-weight:700;"
            "background:transparent;border:none;"
            "font-family:'Microsoft JhengHei','Segoe UI';")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "QPushButton{background:#2A1A1A;color:#AA4444;"
            "border:1px solid #3A2222;border-radius:4px;"
            "font-size:11pt;font-weight:700;}"
            "QPushButton:hover{background:#AA2222;color:#FFF;}")
        close_btn.clicked.connect(self.hide)
        th.addWidget(title_lbl); th.addStretch(); th.addWidget(close_btn)
        lay.addWidget(tbar)

        # Pump canvas
        self._canvas = _PumpCanvas()
        self._canvas.setFixedSize(370, 330)
        lay.addWidget(self._canvas)

        # Info strip (Pa / SV / Hz)
        info = QFrame(); info.setFixedHeight(58)
        info.setStyleSheet(
            "QFrame{background:#0A1018;"
            "border-top:1px solid #152030;}")
        ih = QHBoxLayout(info)
        ih.setContentsMargins(14, 6, 14, 6); ih.setSpacing(0)

        self._pa_val, pa_lay   = self._make_val_col("壓力  PV", "0.00 Pa",  "#00FF88")
        self._sv_val, sv_lay   = self._make_val_col("設定  SV", "2.50 Pa",  "#FF5555")
        self._hz_val, hz_lay   = self._make_val_col("頻率  Hz", "30.0 Hz",  "#FF8800")

        ih.addLayout(pa_lay, 1)
        ih.addWidget(self._sep())
        ih.addLayout(sv_lay, 1)
        ih.addWidget(self._sep())
        ih.addLayout(hz_lay, 1)
        lay.addWidget(info)

        # Control row (play / pause)
        ctrl = QFrame(); ctrl.setFixedHeight(56)
        ctrl.setStyleSheet(
            "QFrame{background:#080E14;"
            "border-top:1px solid #152030;"
            "border-radius:0 0 12px 12px;}")
        ch = QHBoxLayout(ctrl)
        ch.setContentsMargins(16, 10, 16, 10)

        self._pp_btn = QPushButton("⏸   暫停動畫  Pause")
        self._pp_btn.setFixedHeight(36)
        self._pp_btn.setStyleSheet(self._pp_qss(False))
        self._pp_btn.clicked.connect(self._toggle_pause)
        ch.addWidget(self._pp_btn)
        lay.addWidget(ctrl)

    def _make_val_col(self, tag: str, init: str, clr: str):
        col = QVBoxLayout(); col.setSpacing(1); col.setContentsMargins(4, 0, 4, 0)
        t = QLabel(tag)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet("color:#404050;font-size:7pt;font-weight:600;"
                        "background:transparent;border:none;"
                        "font-family:'Microsoft JhengHei','Segoe UI';")
        v = QLabel(init)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setStyleSheet(f"color:{clr};font-size:12pt;font-weight:700;"
                        "background:transparent;border:none;"
                        "font-family:Consolas,'Courier New';")
        col.addWidget(t); col.addWidget(v)
        return v, col

    def _sep(self):
        f = QFrame(); f.setFrameShape(QFrame.Shape.VLine)
        f.setStyleSheet("QFrame{border:none;border-left:1px solid #1A3050;"
                        "background:transparent;}"); return f

    def _pp_qss(self, paused: bool) -> str:
        if paused:
            return ("QPushButton{background:#0A2A0A;color:#00FF88;"
                    "border:1px solid #1A4A1A;border-radius:6px;"
                    "font-size:10.5pt;font-weight:700;"
                    "font-family:'Microsoft JhengHei','Segoe UI';}"
                    "QPushButton:hover{background:#143A14;color:#FFF;}")
        return ("QPushButton{background:#1A1A2A;color:#8888FF;"
                "border:1px solid #2A2A4A;border-radius:6px;"
                "font-size:10.5pt;font-weight:700;"
                "font-family:'Microsoft JhengHei','Segoe UI';}"
                "QPushButton:hover{background:#22224A;color:#FFF;}")

    # ── Toggle pause ─────────────────────────────────────────────
    def _toggle_pause(self):
        self._paused = not self._paused
        self._canvas.set_paused(self._paused)
        if self._paused:
            self._pp_btn.setText("▶   啟動動畫  Resume")
        else:
            self._pp_btn.setText("⏸   暫停動畫  Pause")
        self._pp_btn.setStyleSheet(self._pp_qss(self._paused))

    # ── Called from VfdPressureTuner._sim_tick ───────────────────
    def update_values(self, pa: float, hz: float, sv_pa: float):
        self._canvas.update_values(pa, hz, sv_pa)
        self._pa_val.setText(f"{pa:.2f} Pa")
        self._sv_val.setText(f"{sv_pa:.2f} Pa")
        self._hz_val.setText(f"{hz:.1f} Hz")

    # ── Transparent background paint ─────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

    # ── Window drag (frameless) ───────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (e.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    # ── Timer lifecycle ───────────────────────────────────────────
    def showEvent(self, e):
        super().showEvent(e)
        if not self._canvas._timer.isActive():
            self._canvas._timer.start(16)

    def hideEvent(self, e):
        self._canvas._timer.stop(); super().hideEvent(e)

    def closeEvent(self, e):
        self._canvas._timer.stop(); super().closeEvent(e)
