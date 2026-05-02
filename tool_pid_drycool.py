# tool_pid_drycool.py — AHU Cooling Coil PID Station
# Air Handling Unit: supply-air temperature control (22 °C setpoint)
# FOPDT reverse-action: modulating chilled-water valve → supply air temp
# Physics: T_supply = T_room − K·valve%  |  K=0.500 °C/%  τ=30 s  L=1 s
# Part of the Clawde Industrial Engineering Suite

from collections import deque

try:
    import pyqtgraph as pg
    pg.setConfigOption("background", "transparent")
    pg.setConfigOption("foreground", "#888")
    pg.setConfigOptions(antialias=True)
    HAS_PG = True
except ImportError:
    HAS_PG = False

from PyQt6.QtCore    import Qt, QTimer, QRect
from PyQt6.QtGui     import (QPainter, QColor, QPen, QPainterPath,
                              QFont, QLinearGradient, QBrush)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QComboBox, QScrollArea, QSlider,
)
from styles import BaseToolWindow


# ═══════════════════════════════════════════════════════
#  AHU DUCT DIAGRAM  (painter widget)
# ═══════════════════════════════════════════════════════
class _AhuDiagram(QWidget):
    """Cross-section painter: louver inlet → cooling coil → supply outlet."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(210, 360)
        self._valve_pct = 53.6
        self._t_pv      = 28.0
        self._t_sv      = 22.0
        self._t_room    = 28.0
        self._t_cw      = 14.0   # linked to PV_MIN

    def refresh(self, valve_pct: float, t_pv: float, t_sv: float,
                t_room: float = None, t_cw: float = None):
        self._valve_pct = valve_pct
        self._t_pv      = t_pv
        self._t_sv      = t_sv
        if t_room is not None: self._t_room = t_room
        if t_cw   is not None: self._t_cw   = t_cw
        self.update()

    # ── helpers ──────────────────────────────────────────
    @staticmethod
    def _lbl(p: QPainter, text: str, x: int, y: int, w: int, h: int,
             color: str, fsize: float, bold: bool = False):
        p.setPen(QPen(QColor(color)))
        p.setFont(QFont("Microsoft JhengHei", int(fsize),
                        QFont.Weight.Bold if bold else QFont.Weight.Normal))
        p.drawText(QRect(x, y, w, h), Qt.AlignmentFlag.AlignCenter, text)

    @staticmethod
    def _coil(p: QPainter, x: int, y: int, w: int, h: int):
        pen = QPen(QColor("#00AACC"), 2.5, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        n, sh = 3, h // 3
        for i in range(n):
            yo = y + i * sh + sh // 2
            x0, x1 = (x, x + w) if i % 2 == 0 else (x + w, x)
            p.drawLine(x0, yo, x1, yo)
            if i < n - 1:
                bx = x + w if i % 2 == 0 else x
                r  = sh // 2
                p.drawArc(QRect(bx - r, yo, 2 * r, sh), 90 * 16, 180 * 16)

    @staticmethod
    def _valve(p: QPainter, cx: int, cy: int, r: int, pct: float):
        p.setPen(QPen(QColor("#2A4A4A"), 2)); p.setBrush(QColor("#0A1A1A"))
        p.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
        span = int(pct / 100.0 * 360 * 16)
        rect = QRect(cx - r + 3, cy - r + 3, 2 * r - 6, 2 * r - 6)
        g = int(80 + 60 * pct / 100)
        p.setBrush(QColor(255, g, 0, 210)); p.setPen(Qt.PenStyle.NoPen)
        p.drawPie(rect, 90 * 16, -span)
        p.setPen(QPen(QColor("#FFFFFF")))
        p.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        p.drawText(QRect(cx - r, cy - 8, 2 * r, 16),
                   Qt.AlignmentFlag.AlignCenter, f"{pct:.0f}%")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.fillRect(0, 0, W, H, QColor("#0A1818"))

        # Title
        self._lbl(p, "AHU 空氣冷卻系統", 0, 2, W, 20, "#FF8800", 10, True)

        # Duct — wide, centred, with side margins for labels
        dx, dw = int(W * 0.14), int(W * 0.72)
        dy, dh = 26, H - 34
        path = QPainterPath()
        path.addRoundedRect(dx, dy, dw, dh, 10, 10)
        p.fillPath(path, QColor("#0D2020"))
        p.setPen(QPen(QColor("#1A5050"), 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        zt_h = int(dh * 0.28)
        zc_h = int(dh * 0.44)
        zb_h = dh - zt_h - zc_h
        zt_y, zc_y, zb_y = dy, dy + zt_h, dy + zt_h + zc_h
        cx = dx + dw // 2

        # ── Top: supply outlet ───────────────────────────
        gr = QLinearGradient(0, zt_y, 0, zt_y + zt_h)
        gr.setColorAt(0.0, QColor("#001525")); gr.setColorAt(1.0, QColor("#00263A"))
        p.fillRect(dx + 2, zt_y + 2, dw - 4, zt_h - 2, QBrush(gr))

        # Up arrow
        p.setPen(QPen(QColor("#00CCFF"), 2.5))
        ay1, ay2 = zt_y + 8, zt_y + zt_h - 46
        p.drawLine(cx, ay2, cx, ay1)
        arr = QPainterPath()
        arr.moveTo(cx, ay1); arr.lineTo(cx - 9, ay1 + 16); arr.lineTo(cx + 9, ay1 + 16)
        arr.closeSubpath()
        p.fillPath(arr, QColor("#00CCFF"))

        self._lbl(p, "供氣  Supply Air", dx, zt_y + zt_h - 42, dw, 18, "#00AAEE", 9, True)
        t_clr = "#00FF88" if self._t_pv <= self._t_sv + 0.3 else "#FF5555"
        self._lbl(p, f"{self._t_pv:.1f} °C", dx, zt_y + zt_h - 24, dw, 22, t_clr, 14, True)

        # ── Middle: cooling coil ─────────────────────────
        p.fillRect(dx + 2, zc_y, dw - 4, zc_h, QColor("#001A22"))
        p.setPen(QPen(QColor("#1A4A4A"), 1))
        p.drawLine(dx + 2, zc_y, dx + dw - 2, zc_y)
        p.drawLine(dx + 2, zb_y, dx + dw - 2, zb_y)

        self._lbl(p, "冷卻盤管  Cooling Coil", dx, zc_y + 4, dw, 18, "#3A9AAA", 9, True)
        self._lbl(p, f"冷水入口  CW in  {self._t_cw:.1f} °C", dx, zc_y + 22, dw, 16, "#1A7788", 8)

        self._coil(p, dx + 14, zc_y + 40, dw - 28, 52)

        # Valve indicator (larger radius)
        vy = zc_y + 106
        self._valve(p, cx, vy, 38, self._valve_pct)
        self._lbl(p, f"閥開度  {self._valve_pct:.1f} %", dx, vy + 42, dw, 18, "#FF8800", 9, True)
        self._lbl(p, f"SV = {self._t_sv:.1f} °C",        dx, vy + 58, dw, 16, "#FF5555", 9)

        # ── Bottom: room air inlet ───────────────────────
        gr2 = QLinearGradient(0, zb_y, 0, zb_y + zb_h)
        gr2.setColorAt(0.0, QColor("#1A0E00")); gr2.setColorAt(1.0, QColor("#0C0600"))
        p.fillRect(dx + 2, zb_y, dw - 4, zb_h - 2, QBrush(gr2))

        # Inlet arrow (from bottom-left into duct)
        p.setPen(QPen(QColor("#FF7733"), 2.5))
        iy = zb_y + zb_h // 2
        p.drawLine(dx + 2, iy, dx + dw // 3, iy)
        for dy_ in (-6, 6):
            p.drawLine(dx + dw // 3, iy, dx + dw // 3 - 10, iy + dy_)

        self._lbl(p, "室內回風  Room Air", dx, zb_y + 6,  dw, 18, "#FF8844", 9, True)
        self._lbl(p, f"T_room = {self._t_room:.1f} °C",  dx, zb_y + 24, dw, 17, "#DD7733", 9)

        # Louver bars at bottom
        lx, lw_ = dx + 6, dw - 12
        p.setPen(QPen(QColor("#2A3A2A"), 1.5))
        for i in range(5):
            yb = zb_y + zb_h - 6 - i * 5
            p.drawLine(lx, yb, lx + lw_, yb)

        p.end()


# ═══════════════════════════════════════════════════════
#  AHU COOLING COIL PID STATION
# ═══════════════════════════════════════════════════════
class AhuDryCoolTuner(BaseToolWindow):
    """
    AHU supply-air temperature controller.
    • FOPDT reverse-action: opening valve cools supply air.
    • PV = supply air temperature (°C), stored directly (not normalised).
    • SV = 22 °C (adjustable).  MV = valve opening (%).
    • T_supply_ss = T_room − K·valve%   K = 0.300 °C/%  τ=20 s  L=1 s
    """
    _DT      = 0.05
    _SPAN    = 600.0
    _MAX_PTS = 12_000

    # AHU physical constants
    _T_ROOM = 28.0   # °C  room return-air temperature
    _T_CW   = 14.0   # °C  chilled water supply
    _EFF    = 0.80   # heat-exchanger effectiveness at full flow
    # Derived: K = (T_ROOM - T_CW) * EFF / 100 = 0.112 °C/%

    # Palette (shared with sibling tools)
    _BG     = "#121212"; _CELL = "#1A1A1A"; _BORDER = "#3D3D3D"
    _LBL    = "#FFFFFF"; _LBL2 = "#A0A0A0"
    _INPUT  = "#FFD700"; _RESULT = "#00FFFF"
    _PV_CLR = "#00FF88"; _SV_CLR = "#FF5555"; _MV_CLR = "#00BFFF"
    _ACC    = "#FF8800"; _INP_BG = "#1E1E1E"; _OK = "#00FF88"; _WARN = "#FF4444"

    # PID / FOPDT specs
    _PID_SPECS = [
        ("Kp", "Kp  比例增益  Proportional",  0.0, 200.0, 3),
        ("Ki", "Ki  積分增益  Integral",        0.0,  50.0, 4),
        ("Kd", "Kd  微分增益  Derivative",      0.0,  50.0, 4),
    ]
    _FOPDT_SPECS = [
        ("pK", "K   製程增益  °C/%",        0.001, 2.0,  3, "°C/%"),
        ("pT", "τ   時間常數  Time Const",   1.0, 300.0,  1, "s"),
        ("pL", "L   延遲時間  Dead Time",    0.0,  60.0,  1, "s"),
    ]

    def __init__(self):
        super().__init__("❄️ AHU Cooling Coil PID Station", 980, 960)
        self.setMinimumSize(760, 700)

        # ── PID gains ────────────────────────────────────
        self._Kp = 3.5;  self._Ki = 1.2;   self._Kd = 0.0
        # ── FOPDT ────────────────────────────────────────
        self._pK = 0.500; self._pT = 30.0;  self._pL = 1.0
        # ── Control state ─────────────────────────────────
        self._sv_pct     = 22.0    # °C setpoint (displayed as "SV")
        self._sv_init    = 35.0    # °C  init / reset baseline = T_room
        self._cv_manual  = 50.0    # % valve (manual mode)
        self._manual_mode    = False
        self._reverse_action = True   # cooling: reverse action default
        # ── Limits — pv_min linked to T_CW, sv_init linked to T_ROOM ──
        self._pv_max = 35.0; self._pv_min = 14.0   # pv_min = CW temp
        self._mv_max = 100.0; self._mv_min = 0.0
        # ── Sim internals ─────────────────────────────────
        self._T_pv      = self._T_ROOM
        self._integral  = 0.0
        self._prev_err  = 0.0
        self._dead_buf: deque = deque()
        self._t_data:   deque = deque(maxlen=self._MAX_PTS)
        self._pv_data:  deque = deque(maxlen=self._MAX_PTS)
        self._sv_data:  deque = deque(maxlen=self._MAX_PTS)
        self._cv_data:  deque = deque(maxlen=self._MAX_PTS)
        self._t_now = 0.0; self._step = 0
        self._peak_pv = self._T_ROOM; self._last_cv = 0.0
        self._zn_results: dict = {}; self._pid_inputs: dict = {}
        self._slider_following = True; self._slider_dragging = False

        self.content.setStyleSheet(f"background:{self._BG};")

        # ── Top-level layout: left content | right diagram ─
        top = QHBoxLayout(self.content)
        top.setContentsMargins(4, 4, 4, 4); top.setSpacing(6)

        # Left: scrollable PID content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QScrollBar:vertical{background:#1A1A1A;width:6px;border-radius:3px;}"
            "QScrollBar::handle:vertical{background:#3D3D3D;border-radius:3px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
        inner = QWidget(); inner.setStyleSheet(f"background:{self._BG};")
        scroll.setWidget(inner)
        root = QVBoxLayout(inner); root.setContentsMargins(6, 4, 6, 4); root.setSpacing(5)
        top.addWidget(scroll, 1)

        # Right: AHU diagram  (t_room syncs with sv_init; t_cw syncs with pv_min)
        self._diagram = _AhuDiagram()
        self._diagram.setFixedWidth(260)
        self._diagram._t_room = self._sv_init   # linked to Init SV
        self._diagram._t_cw   = self._pv_min    # linked to PV MIN
        top.addWidget(self._diagram)

        self._build_plot(root)
        self._build_timeline_slider(root)
        self._build_live_strip(root)
        self._build_ctrl_row(root)
        self._build_mv_limit_row(root)
        self._build_param_cols(root)
        self._build_zn_section(root)
        self._build_status_bar(root)

        self._sim_timer = QTimer(self)
        self._sim_timer.timeout.connect(self._sim_tick)
        self._reset_sim()

    # ════════════════════════════════════════════════════
    #  PAINT / RESIZE
    # ════════════════════════════════════════════════════
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 13, 13)
        p.fillPath(path, QColor(0x12, 0x12, 0x12))
        p.setPen(QPen(QColor(0x3D, 0x3D, 0x3D), 1)); p.drawPath(path)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "_grip"):
            self._grip.move(self.width() - self._grip.width(),
                            self.height() - self._grip.height())

    # ════════════════════════════════════════════════════
    #  SECTION BUILDERS
    # ════════════════════════════════════════════════════
    def _build_plot(self, lay: QVBoxLayout):
        if not HAS_PG:
            lay.addWidget(self._tag("缺少 pyqtgraph — pip install pyqtgraph", self._WARN, 11))
            return
        pw = pg.PlotWidget()
        pw.setBackground(self._BG); pw.setMinimumHeight(185)
        pw.showGrid(x=True, y=True, alpha=0.18)
        for ax in ("bottom", "left"):
            pw.getAxis(ax).setTextPen(pg.mkPen(self._LBL2))
            pw.getAxis(ax).setPen(pg.mkPen(self._BORDER))
        pw.setLabel("bottom", "Time (s)", color=self._LBL2)
        pw.setLabel("left",   "Temperature (°C)", color=self._LBL2)
        pw.setXRange(0, self._SPAN, padding=0)
        pw.setYRange(14, 32, padding=0)
        pw.getPlotItem().setMenuEnabled(False)
        pw.getPlotItem().setClipToView(True)
        pw.getPlotItem().setDownsampling(auto=True, mode="peak")
        self._sv_curve = pw.plot([], [], pen=pg.mkPen(self._SV_CLR, width=1.8,
                                  style=Qt.PenStyle.DashLine), name="SV °C")
        self._pv_curve = pw.plot([], [], pen=pg.mkPen(self._PV_CLR, width=2.5), name="PV °C")
        self._cv_curve = pw.plot([], [], pen=pg.mkPen(self._MV_CLR, width=1.8), name="Valve %")
        legend = pw.addLegend(offset=(4, 4)); legend.setLabelTextColor(self._LBL)
        lay.addWidget(pw, 3); self._pw = pw

        self._xhair = pg.InfiniteLine(angle=90, movable=False,
                                      pen=pg.mkPen((200, 200, 200, 55), width=1))
        pw.addItem(self._xhair, ignoreBounds=True)
        self._hover_lbl = pg.TextItem(anchor=(0, 0), fill=pg.mkBrush(8, 12, 20, 210))
        self._hover_lbl.setVisible(False)
        pw.addItem(self._hover_lbl)
        self._mouse_proxy = pg.SignalProxy(
            pw.scene().sigMouseMoved, rateLimit=60, slot=self._on_hover)

    def _on_hover(self, evt):
        if not HAS_PG or not hasattr(self, "_pw"): return
        pos = evt[0]
        if not self._pw.sceneBoundingRect().contains(pos):
            self._hover_lbl.setVisible(False); return
        mp = self._pw.plotItem.vb.mapSceneToView(pos)
        t  = mp.x(); self._xhair.setPos(t)
        ta = list(self._t_data)
        if len(ta) < 2: self._hover_lbl.setVisible(False); return
        idx = min(range(len(ta)), key=lambda i: abs(ta[i] - t))
        pv  = list(self._pv_data)[idx]
        sv  = list(self._sv_data)[idx]
        mv  = list(self._cv_data)[idx]
        self._hover_lbl.setHtml(
            f'<span style="color:#888888">t = {ta[idx]:.1f} s</span><br/>'
            f'<span style="color:{self._PV_CLR}">PV = {pv:.2f} °C</span><br/>'
            f'<span style="color:{self._SV_CLR}">SV = {sv:.2f} °C</span><br/>'
            f'<span style="color:{self._MV_CLR}">Valve = {mv:.1f} %</span>')
        xr, yr = (self._pw.plotItem.vb.viewRange()[0],
                  self._pw.plotItem.vb.viewRange()[1])
        ax = 1.0 if t > xr[0] + (xr[1] - xr[0]) * 0.6 else 0.0
        try: self._hover_lbl.setAnchor((ax, 0))
        except Exception: pass
        self._hover_lbl.setPos(t, yr[0] + (yr[1] - yr[0]) * 0.98)
        self._hover_lbl.setVisible(True)

    def _build_timeline_slider(self, lay: QVBoxLayout):
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:#151515;border:1px solid {self._BORDER};border-radius:3px;}}")
        f.setFixedHeight(28)
        h = QHBoxLayout(f); h.setContentsMargins(8, 4, 8, 4); h.setSpacing(6)
        h.addWidget(self._tag("進度桿", self._LBL2, 7))
        self._timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self._timeline_slider.setRange(0, int(self._SPAN)); self._timeline_slider.setValue(0)
        self._timeline_slider.setStyleSheet(
            "QSlider::groove:horizontal{background:#252525;height:4px;border-radius:2px;}"
            f"QSlider::handle:horizontal{{background:{self._ACC};width:10px;height:10px;"
            "border-radius:5px;margin:-3px 0;}"
            f"QSlider::sub-page:horizontal{{background:#7A3A00;border-radius:2px;}}")
        self._timeline_slider.sliderPressed.connect(lambda: setattr(self, "_slider_dragging", True) or setattr(self, "_slider_following", False))
        self._timeline_slider.sliderReleased.connect(lambda: setattr(self, "_slider_dragging", False))
        self._timeline_slider.valueChanged.connect(self._slider_moved)
        h.addWidget(self._timeline_slider, 1)
        fb = QPushButton("⏩ 追蹤"); fb.setFixedHeight(20); fb.setFixedWidth(62)
        fb.setStyleSheet(
            f"QPushButton{{background:{self._CELL};color:{self._LBL2};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:7.5pt;font-weight:700;padding:0 4px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';}}"
            f"QPushButton:hover{{background:#2A2A2A;color:{self._LBL};}}")
        fb.clicked.connect(self._slider_resume_follow)
        h.addWidget(fb); lay.addWidget(f)

    def _build_live_strip(self, lay: QVBoxLayout):
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:{self._CELL};border:1px solid {self._BORDER};border-radius:4px;}}")
        f.setFixedHeight(58)
        h = QHBoxLayout(f); h.setContentsMargins(14, 4, 14, 4); h.setSpacing(0)

        def _big(tag, clr, unit="°C"):
            col = QVBoxLayout(); col.setSpacing(0)
            lbl = QLabel(tag)
            lbl.setStyleSheet(f"color:{self._LBL2};font-size:7.5pt;font-weight:600;"
                              f"background:transparent;border:none;"
                              f"font-family:'Microsoft JhengHei','Segoe UI';")
            rw = QHBoxLayout(); rw.setSpacing(2); rw.setContentsMargins(0, 0, 0, 0)
            val = QLabel("0.00")
            val.setStyleSheet(f"color:{clr};font-size:19pt;font-weight:700;"
                              f"background:transparent;border:none;"
                              f"font-family:Consolas,'Courier New';font-variant-numeric:tabular-nums;")
            unt = QLabel(unit)
            unt.setStyleSheet(f"color:#606060;font-size:10pt;font-weight:600;"
                              f"background:transparent;border:none;"
                              f"font-family:'Segoe UI';padding-bottom:2px;")
            unt.setAlignment(Qt.AlignmentFlag.AlignBottom)
            rw.addWidget(val); rw.addWidget(unt); rw.addStretch()
            col.addWidget(lbl); col.addLayout(rw); return col, val

        pv_lay, self._pv_disp = _big("PV  供氣溫度  Supply Air", self._PV_CLR)
        sv_lay, self._sv_disp = _big("SV  設定溫度  Setpoint",   self._SV_CLR)
        mv_lay, self._mv_disp = _big("MV  閥開度  Valve",        self._MV_CLR, "%")
        h.addLayout(pv_lay, 1); h.addWidget(self._vline())
        h.addSpacing(8); h.addLayout(sv_lay, 1); h.addWidget(self._vline())
        h.addSpacing(8); h.addLayout(mv_lay, 1)
        lay.addWidget(f)

    def _build_ctrl_row(self, lay: QVBoxLayout):
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:{self._CELL};border:1px solid {self._BORDER};border-radius:4px;}}")
        v = QVBoxLayout(f); v.setContentsMargins(10, 6, 10, 6); v.setSpacing(5)

        r1 = QHBoxLayout(); r1.setSpacing(8)
        r1.addWidget(self._tag("模式  MODE", self._LBL2, 8))
        self._man_btn  = self._btn("手動  Manual", 80)
        self._auto_btn = self._btn("自動  Auto",   80)
        self._man_btn.clicked.connect(lambda: self._set_mode(True))
        self._auto_btn.clicked.connect(lambda: self._set_mode(False))
        r1.addWidget(self._man_btn); r1.addWidget(self._auto_btn)
        r1.addWidget(self._vline())
        r1.addWidget(self._tag("SV °C", self._LBL2, 8))
        self._sv_in = self._inp(f"{self._sv_pct:.1f}", self._SV_CLR, 72, 11)
        self._sv_in.editingFinished.connect(self._sv_changed)
        r1.addWidget(self._sv_in)
        r1.addWidget(self._tag("°C", self._LBL2, 8))
        r1.addWidget(self._vline())
        r1.addWidget(self._tag("手動輸出  Valve", self._LBL2, 8))
        self._man_cv_in = self._inp(f"{self._cv_manual:.1f}", self._INPUT, 64, 10)
        self._man_cv_in.editingFinished.connect(self._man_cv_changed)
        r1.addWidget(self._man_cv_in)
        r1.addWidget(self._tag("%", self._LBL2, 8)); r1.addStretch()
        rst = self._btn("⟳ 重置  Reset", 100)
        rst.clicked.connect(self._reset_sim); r1.addWidget(rst)
        v.addLayout(r1)

        r2 = QHBoxLayout(); r2.setSpacing(8)
        r2.addWidget(self._tag("作用方向  Action", self._LBL2, 8))
        self._act_btn = QPushButton("反向  Reverse")
        self._act_btn.setFixedHeight(24); self._act_btn.setFixedWidth(110)
        self._act_btn.clicked.connect(self._toggle_action)
        r2.addWidget(self._act_btn); r2.addWidget(self._vline())
        r2.addWidget(self._tag("初始設定值  Init SV", self._LBL2, 8))
        self._sv_init_in = self._inp(f"{self._sv_init:.1f}", self._INPUT, 72, 10)
        self._sv_init_in.editingFinished.connect(self._sv_init_changed)
        r2.addWidget(self._sv_init_in)
        r2.addWidget(self._tag("°C  (reset → SV)", self._LBL2, 8)); r2.addStretch()
        v.addLayout(r2)
        lay.addWidget(f)
        self._refresh_mode_btns(); self._refresh_action_btn()

    def _build_mv_limit_row(self, lay: QVBoxLayout):
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:{self._CELL};border:1px solid {self._BORDER};border-radius:4px;}}")
        h = QHBoxLayout(f); h.setContentsMargins(14, 5, 14, 5); h.setSpacing(14)

        mv_col = QVBoxLayout(); mv_col.setSpacing(0)
        self._mv_mode_lbl = QLabel("Valve  閥位 (自動)")
        self._mv_mode_lbl.setStyleSheet(
            f"color:{self._LBL2};font-size:7.5pt;font-weight:600;"
            f"background:transparent;border:none;font-family:'Microsoft JhengHei','Segoe UI';")
        mv_rw = QHBoxLayout(); mv_rw.setSpacing(2); mv_rw.setContentsMargins(0, 0, 0, 0)
        self._mv_big = QLabel("0.0")
        self._mv_big.setStyleSheet(
            f"color:{self._RESULT};font-size:19pt;font-weight:700;"
            f"background:transparent;border:none;"
            f"font-family:Consolas,'Courier New';font-variant-numeric:tabular-nums;")
        mv_u = QLabel("%"); mv_u.setStyleSheet(f"color:#606060;font-size:10pt;font-weight:600;"
                                               f"background:transparent;border:none;"
                                               f"font-family:'Segoe UI';padding-bottom:2px;")
        mv_u.setAlignment(Qt.AlignmentFlag.AlignBottom)
        mv_rw.addWidget(self._mv_big); mv_rw.addWidget(mv_u); mv_rw.addStretch()
        mv_col.addWidget(self._mv_mode_lbl); mv_col.addLayout(mv_rw)
        h.addLayout(mv_col, 1)

        info_col = QVBoxLayout(); info_col.setSpacing(2)
        self._t_disp    = QLabel("t = 00:00")
        self._peak_disp = QLabel("peak  —")
        for lbl, clr in [(self._t_disp, self._LBL2), (self._peak_disp, self._ACC)]:
            lbl.setStyleSheet(f"color:{clr};font-size:8pt;font-weight:600;"
                              f"background:transparent;border:none;"
                              f"font-family:Consolas,'Courier New';")
            info_col.addWidget(lbl)
        h.addLayout(info_col); h.addWidget(self._vline())

        grid = QGridLayout(); grid.setSpacing(4); grid.setContentsMargins(0, 0, 0, 0)

        def _badge(text, clr):
            l = QLabel(text); l.setFixedSize(24, 16); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet(f"color:#000;background:{clr};font-size:6.5pt;"
                            f"font-weight:700;border-radius:2px;font-family:'Segoe UI';"); return l

        def _ll(txt):
            l = QLabel(txt)
            l.setStyleSheet(f"color:{self._LBL2};font-size:7.5pt;font-weight:600;"
                            f"background:transparent;border:none;"
                            f"font-family:'Microsoft JhengHei','Segoe UI';"); return l

        def _lim(val, attr, lo, hi, fmt=".0f"):
            e = self._inp(f"{val:{fmt}}", self._INPUT, 50, 9); e.setFixedHeight(20)
            def _c(a=attr, ie=e, l=lo, hh=hi, f=fmt):
                try: v = max(l, min(hh, float(ie.text())))
                except ValueError: v = getattr(self, f"_{a}")
                setattr(self, f"_{a}", v); ie.setText(f"{v:{f}}")
                # Sync: pv_min = CW temperature (physics lower bound)
                if a == "pv_min" and hasattr(self, "_diagram"):
                    self._diagram._t_cw = v; self._diagram.update()
            e.editingFinished.connect(_c); return e

        grid.addWidget(_badge("PV", self._PV_CLR), 0, 0); grid.addWidget(_ll("最大 MAX °C"), 0, 1)
        self._pv_max_in = _lim(self._pv_max, "pv_max", 10, 60, ".1f"); grid.addWidget(self._pv_max_in, 0, 2)
        grid.addWidget(_badge("MV", self._MV_CLR), 0, 3); grid.addWidget(_ll("最大 MAX %"), 0, 4)
        self._mv_max_in = _lim(self._mv_max, "mv_max", 0, 100); grid.addWidget(self._mv_max_in, 0, 5)

        grid.addWidget(_badge("PV", self._PV_CLR), 1, 0); grid.addWidget(_ll("最小 MIN °C"), 1, 1)
        self._pv_min_in = _lim(self._pv_min, "pv_min", 0, 35, ".1f"); grid.addWidget(self._pv_min_in, 1, 2)
        grid.addWidget(_badge("MV", self._MV_CLR), 1, 3); grid.addWidget(_ll("最小 MIN %"), 1, 4)
        self._mv_min_in = _lim(self._mv_min, "mv_min", 0, 100); grid.addWidget(self._mv_min_in, 1, 5)

        h.addLayout(grid); lay.addWidget(f)

    def _build_param_cols(self, lay: QVBoxLayout):
        lay.addWidget(self._sec_hdr("≡  主要參數  Controller & Process Parameters"))
        cols = QHBoxLayout(); cols.setSpacing(10)

        _eq  = (f"color:#00E5A0;font-size:9pt;font-weight:700;"
                f"background:transparent;border:none;font-family:Consolas,'Courier New';")
        _sep = (f"color:#2A4A3A;font-size:7pt;"
                f"background:transparent;border:none;font-family:Consolas,'Courier New';")
        _ann = (f"color:#80C8A8;font-size:8.5pt;font-weight:600;"
                f"background:transparent;border:none;"
                f"font-family:'Microsoft JhengHei','Segoe UI';")

        def _div():
            d = QFrame(); d.setFrameShape(QFrame.Shape.VLine)
            d.setStyleSheet("QFrame{border:none;border-left:1px solid #242424;background:transparent;}"); return d

        def _framed_col(hdr_text, formula_block):
            fr = QFrame()
            fr.setStyleSheet(f"QFrame{{background:{self._CELL};border:1px solid {self._ACC};border-radius:4px;}}")
            outer = QHBoxLayout(fr); outer.setContentsMargins(8, 6, 8, 6); outer.setSpacing(8)
            lv = QVBoxLayout(); lv.setSpacing(3); lv.setContentsMargins(0, 0, 0, 0)
            hl = QLabel(hdr_text)
            hl.setStyleSheet(f"color:{self._ACC};font-size:8.5pt;font-weight:700;"
                             f"background:transparent;border:none;padding-bottom:3px;"
                             f"font-family:'Microsoft JhengHei','Segoe UI';")
            lv.addWidget(hl); outer.addLayout(lv, 0); outer.addWidget(_div())
            rv = QVBoxLayout(); rv.setSpacing(1); rv.setContentsMargins(4, 0, 4, 0)
            for text, style in formula_block:
                fl = QLabel(text); fl.setStyleSheet(style); fl.setWordWrap(True); rv.addWidget(fl)
            rv.addStretch(); outer.addLayout(rv, 1)
            return fr, lv

        pid_formula = [
            ("PID 控制核心  AHU Control Core",                              _eq),
            ("────────────────────────────────────────",                   _sep),
            ("供氣溫度 PV vs 設定溫度 SV → 調節閥開度 MV",                  _ann),
            ("P (比例)  ─  溫差即時反應，超溫即開閥",                       _ann),
            ("I (積分)  ─  累積偏差，消除穩態溫差殘留",                     _ann),
            ("D (微分)  ─  預測溫度趨勢，防止供氣過冷",                     _ann),
            ("─  MV = Kp·e + Ki·∫e dt + Kd·de/dt",                       _sep),
            ("─  e = T_PV − T_SV  (反向: 熱 → 開閥)",                     _sep),
        ]
        fopdt_formula = [
            ("FOPDT 冷卻盤管製程模型",                                       _eq),
            ("────────────────────────────────────────",                   _sep),
            ("T_ss = T_room − K · valve%",                                 _ann),
            ("K  (°C/%)  ─  每 1% 開度帶走多少 °C",                        _ann),
            ("τ  (時間常數) ─  盤管熱容與氣流熱交換時間",                   _ann),
            ("L  (延遲)    ─  氣流輸送 + 感測器延遲",                       _ann),
            ("─  T(t) = T_ss·(1 − e^(−(t−L)/τ))",                         _sep),
        ]

        pid_fr, pid_col = _framed_col("PID 控制器", pid_formula)
        for attr, label, lo, hi, dec in self._PID_SPECS:
            le = self._param_row(pid_col, attr, label, lo, hi, dec, "")
            self._pid_inputs[attr] = le

        fopdt_fr, fopdt_col = _framed_col("FOPDT 製程", fopdt_formula)
        for attr, label, lo, hi, dec, unit in self._FOPDT_SPECS:
            self._param_row(fopdt_col, attr, label, lo, hi, dec, unit)

        cols.addWidget(pid_fr, 1); cols.addWidget(fopdt_fr, 1)
        lay.addLayout(cols)

    def _build_zn_section(self, lay: QVBoxLayout):
        lay.addWidget(self._sec_hdr("Z-N  一鍵算  Ziegler-Nichols  (終極增益法)"))
        box = QVBoxLayout(); box.setSpacing(5); box.setContentsMargins(2, 2, 2, 2)

        top = QHBoxLayout(); top.setSpacing(8)
        self._method_box = QComboBox()
        self._method_box.addItems(["Ziegler-Nichols (Z-N)  經典模式",
                                   "Tyreus-Luyben  (T-L)   穩健模式"])
        self._method_box.setFixedHeight(24)
        self._method_box.setStyleSheet(
            f"QComboBox{{background:{self._INP_BG};color:{self._LBL};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:8.5pt;font-weight:700;padding:1px 6px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';}}"
            f"QComboBox:focus{{border:1px solid {self._ACC};}}"
            f"QComboBox::drop-down{{border:none;width:14px;}}"
            f"QComboBox QAbstractItemView{{background:{self._CELL};color:{self._LBL};"
            f"border:1px solid {self._BORDER};"
            f"selection-background-color:{self._ACC};selection-color:#fff;font-size:8.5pt;}}")
        self._method_box.currentIndexChanged.connect(self._on_method_changed)
        top.addWidget(self._method_box); top.addWidget(self._vline())
        top.addWidget(self._tag("Ku", self._LBL2, 8))
        self._ku_in = self._inp("6.000", self._INPUT, 72, 9); self._ku_in.setFixedHeight(24)
        top.addWidget(self._ku_in)
        top.addWidget(self._tag("Pu", self._LBL2, 8))
        self._pu_in = self._inp("90.0",  self._INPUT, 72, 9); self._pu_in.setFixedHeight(24)
        top.addWidget(self._pu_in); top.addWidget(self._tag("s", self._LBL2, 8))
        calc = self._btn("一鍵換算  Calculate", 130)
        calc.setStyleSheet(
            f"QPushButton{{background:#1A2A0A;color:{self._OK};"
            f"border:1px solid #3A5A1A;border-radius:3px;"
            f"font-size:9pt;font-weight:700;padding:0 8px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';}}"
            f"QPushButton:hover{{background:#243A10;color:#fff;}}")
        calc.clicked.connect(self._zn_calculate)
        top.addWidget(calc); top.addStretch(); box.addLayout(top)

        ac_row = QHBoxLayout(); ac_row.setSpacing(8)
        auto_btn = QPushButton("🔍 自動擷取波型  Auto Capture Ku/Pu")
        auto_btn.setFixedHeight(36); auto_btn.setFixedWidth(240)
        auto_btn.setStyleSheet(
            f"QPushButton{{background:#1A1A3A;color:#8888FF;"
            f"border:1px solid #2A2A6A;border-radius:4px;"
            f"font-size:9.5pt;font-weight:700;padding:0 8px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';}}"
            f"QPushButton:hover{{background:#22226A;color:#fff;}}")
        auto_btn.clicked.connect(self._auto_capture)
        self._warn_lbl = QLabel("")
        self._warn_lbl.setStyleSheet(
            f"color:{self._WARN};font-size:8.5pt;font-weight:600;"
            f"background:transparent;border:none;font-family:'Microsoft JhengHei','Segoe UI';")
        self._warn_lbl.setWordWrap(True)
        ac_row.addWidget(auto_btn); ac_row.addWidget(self._warn_lbl, 1); box.addLayout(ac_row)

        prin = QLabel(
            "① 超調量與穩定性    Z-N: 增益大，響應快，易超調 ─── "
            "T-L: 係數修正，響應保守，平穩趨近 SV，適合空調溫控        "
            "② 抗干擾能力    Z-N: 初期反應劇烈 ─── "
            "T-L: 阻尼效果佳，防止盤管閥體劇烈抖動，延長機械壽命")
        prin.setWordWrap(True)
        prin.setStyleSheet(
            f"color:#00D890;font-size:8.5pt;font-weight:700;"
            f"background:#0D1A12;border:1px solid #1A4A2A;border-radius:3px;"
            f"padding:5px 12px;font-family:'Microsoft JhengHei','Segoe UI';")
        box.addWidget(prin)

        tbl = QFrame()
        tbl.setStyleSheet(f"QFrame{{background:#0D0D0D;border:1px solid {self._BORDER};border-radius:4px;}}")
        tg = QGridLayout(tbl); tg.setSpacing(0); tg.setContentsMargins(0, 0, 0, 0)
        _hss = (f"color:{self._LBL2};font-size:8pt;font-weight:700;"
                f"background:#181818;border-bottom:1px solid {self._BORDER};"
                f"padding:2px 6px;font-family:'Microsoft JhengHei','Segoe UI';")
        _css = (f"color:{self._RESULT};font-size:9pt;font-weight:bold;"
                f"font-family:Consolas,'Courier New';"
                f"border-bottom:1px solid #252525;border-left:1px solid #252525;"
                f"padding:3px 6px;background:transparent;")
        _mss = (f"color:{self._ACC};font-size:9pt;font-weight:700;"
                f"font-family:Consolas,'Courier New';"
                f"border-bottom:1px solid #252525;padding:3px 8px;background:transparent;")
        for ci, hdr in enumerate(["模式  Mode", "Kp", "Ki", "Kd", "套用  Apply"]):
            hl = QLabel(hdr); hl.setFixedHeight(22); hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hl.setStyleSheet(_hss); tg.addWidget(hl, 0, ci)
        tg.setColumnStretch(0, 1); tg.setColumnStretch(1, 1)
        tg.setColumnStretch(2, 1); tg.setColumnStretch(3, 1)
        self._zn_cells: dict = {}
        for ri, mode in enumerate(["P", "PI", "PID"], 1):
            ml = QLabel(mode); ml.setFixedHeight(26)
            ml.setAlignment(Qt.AlignmentFlag.AlignCenter); ml.setStyleSheet(_mss)
            tg.addWidget(ml, ri, 0); cells = []
            for ci in range(1, 4):
                cl = QLabel("—"); cl.setFixedHeight(26)
                cl.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.setStyleSheet(_css)
                tg.addWidget(cl, ri, ci); cells.append(cl)
            self._zn_cells[mode] = cells
            ab = self._btn("套用", 58); ab.setFixedHeight(22)
            ab.clicked.connect(lambda _=False, m=mode: self._zn_apply(m))
            tg.addWidget(ab, ri, 4, Qt.AlignmentFlag.AlignCenter)
        self._formula_lbl = QLabel("")
        self._formula_lbl.setStyleSheet(
            f"color:#505050;font-size:7.5pt;padding:2px 6px;"
            f"font-family:Consolas,'Courier New';background:transparent;border:none;")
        self._formula_lbl.setWordWrap(True)
        box.addWidget(tbl); box.addWidget(self._formula_lbl)
        lay.addLayout(box); self._refresh_formula_lbl()

    def _build_status_bar(self, lay: QVBoxLayout):
        f = QFrame()
        f.setStyleSheet("QFrame{background:#0A1020;border:1px solid #1C2B4A;border-radius:4px;}")
        f.setFixedHeight(38)
        h = QHBoxLayout(f); h.setContentsMargins(10, 4, 10, 4); h.setSpacing(8)
        name = QLabel("亞聖國際科技有限公司")
        name.setStyleSheet("color:#8FA8C8;font-size:8pt;font-weight:700;"
                           "background:transparent;border:none;"
                           "font-family:'Microsoft JhengHei','Segoe UI';")
        div = QLabel("│"); div.setStyleSheet("color:#2A3A5A;background:transparent;border:none;")
        msg = QLabel("AHU Cooling Coil PID Station  │  FOPDT Reverse-Action  "
                     "───  Supply Air Temp Control  T_room=28°C  CW=14°C  SV=22°C")
        msg.setStyleSheet(f"color:{self._ACC};font-size:8.5pt;font-weight:600;"
                          f"background:transparent;border:none;"
                          f"font-family:'Microsoft JhengHei','Segoe UI';")
        h.addWidget(name); h.addWidget(div); h.addWidget(msg); h.addStretch()
        lay.addWidget(f)

    # ════════════════════════════════════════════════════
    #  WIDGET FACTORIES
    # ════════════════════════════════════════════════════
    def _sec_hdr(self, text: str) -> QLabel:
        l = QLabel(f"  {text}"); l.setFixedHeight(21)
        l.setStyleSheet(f"color:{self._ACC};font-size:8.5pt;font-weight:700;"
                        f"background:#1A1A1A;border-top:1px solid {self._ACC};"
                        f"border-left:3px solid {self._ACC};"
                        f"border-bottom:none;border-right:none;padding-left:6px;"
                        f"font-family:'Microsoft JhengHei','Segoe UI';"); return l

    def _tag(self, text: str, color: str = None, size: int = 9, bold: bool = False) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color:{color or self._LBL};font-size:{size}pt;"
                        f"font-weight:{'700' if bold else '600'};"
                        f"background:transparent;border:none;"
                        f"font-family:'Microsoft JhengHei','Segoe UI';"); return l

    def _inp(self, text: str, color: str, width: int = 80, fsize: int = 10) -> QLineEdit:
        e = QLineEdit(text); e.setFixedWidth(width); e.setFixedHeight(24)
        e.setAlignment(Qt.AlignmentFlag.AlignRight)
        e.setStyleSheet(
            f"QLineEdit{{background:{self._INP_BG};color:{color};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:{fsize}pt;font-weight:700;"
            f"font-family:Consolas,'Courier New';padding:1px 5px;}}"
            f"QLineEdit:focus{{border:1px solid {self._ACC};}}")
        return e

    def _btn(self, text: str, width: int = 80) -> QPushButton:
        b = QPushButton(text); b.setFixedHeight(24)
        if width: b.setFixedWidth(width)
        b.setStyleSheet(
            f"QPushButton{{background:{self._CELL};color:{self._LBL2};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:8.5pt;font-weight:700;padding:0 6px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';}}"
            f"QPushButton:hover{{background:#2A2A2A;color:{self._LBL};}}")
        return b

    def _vline(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.Shape.VLine)
        f.setStyleSheet(f"QFrame{{border:none;border-left:1px solid {self._BORDER};"
                        f"background:transparent;}}"); return f

    def _param_row(self, lay: QVBoxLayout, attr: str, label: str,
                   lo: float, hi: float, dec: int, unit: str) -> QLineEdit:
        row = QHBoxLayout(); row.setSpacing(4)
        lb = QLabel(label); lb.setFixedWidth(150)
        lb.setStyleSheet(f"color:{self._LBL};font-size:8.5pt;font-weight:600;"
                         f"font-family:'Microsoft JhengHei','Segoe UI';"
                         f"background:transparent;border:none;")
        le = QLineEdit(f"{getattr(self, '_' + attr):.{dec}f}")
        le.setFixedWidth(80); le.setFixedHeight(22); le.setAlignment(Qt.AlignmentFlag.AlignRight)
        le.setStyleSheet(
            f"QLineEdit{{background:{self._INP_BG};color:{self._INPUT};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:9.5pt;font-weight:700;"
            f"font-family:Consolas,'Courier New';padding:1px 5px;}}"
            f"QLineEdit:focus{{border:1px solid {self._ACC};}}")
        ul = QLabel(unit or ""); ul.setFixedWidth(28)
        ul.setStyleSheet(f"color:{self._LBL2};font-size:8pt;background:transparent;border:none;")
        rl = QLabel(f"[{lo:.3g}–{hi:.4g}]")
        rl.setStyleSheet("color:#505050;font-size:7.5pt;background:transparent;border:none;")

        def _commit(a=attr, l=lo, h=hi, d=dec, e=le):
            try: v = float(e.text())
            except ValueError: v = getattr(self, f"_{a}")
            v = max(l, min(h, v)); e.setText(f"{v:.{d}f}")
            old = getattr(self, f"_{a}"); setattr(self, f"_{a}", v)
            if a == "pL" and abs(v - old) > 1e-9:
                self._rebuild_dead_buf()

        le.editingFinished.connect(_commit)
        row.addWidget(lb); row.addWidget(le); row.addWidget(ul); row.addWidget(rl)
        row.addStretch(); lay.addLayout(row); return le

    # ════════════════════════════════════════════════════
    #  CONTROL HANDLERS
    # ════════════════════════════════════════════════════
    def _toggle_action(self):
        self._reverse_action = not self._reverse_action
        self._integral = 0.0; self._prev_err = 0.0
        self._refresh_action_btn()

    def _refresh_action_btn(self):
        if self._reverse_action:
            self._act_btn.setText("反向  Reverse")
            self._act_btn.setStyleSheet(
                f"QPushButton{{background:#002A2A;color:#00CCCC;"
                f"border:1px solid #005A5A;border-radius:3px;"
                f"font-size:8.5pt;font-weight:700;"
                f"font-family:'Microsoft JhengHei','Segoe UI';}}"
                f"QPushButton:hover{{background:#003A3A;color:#fff;}}")
        else:
            self._act_btn.setText("正向  Direct")
            self._act_btn.setStyleSheet(
                f"QPushButton{{background:#0A2A1A;color:{self._OK};"
                f"border:1px solid #2A6A3A;border-radius:3px;"
                f"font-size:8.5pt;font-weight:700;"
                f"font-family:'Microsoft JhengHei','Segoe UI';}}"
                f"QPushButton:hover{{background:#1A3A2A;color:#fff;}}")

    def _set_mode(self, manual: bool):
        self._manual_mode = manual
        self._mv_mode_lbl.setText("Valve  閥位 (手動)" if manual else "Valve  閥位 (自動)")
        self._refresh_mode_btns()

    def _refresh_mode_btns(self):
        _on  = (f"QPushButton{{background:{self._ACC};color:#000;border:none;"
                f"border-radius:3px;font-size:8.5pt;font-weight:700;"
                f"font-family:'Microsoft JhengHei','Segoe UI';}}")
        _off = (f"QPushButton{{background:{self._CELL};color:{self._LBL2};"
                f"border:1px solid {self._BORDER};border-radius:3px;"
                f"font-size:8.5pt;font-weight:600;"
                f"font-family:'Microsoft JhengHei','Segoe UI';}}"
                f"QPushButton:hover{{background:#2A2A2A;color:{self._LBL};}}")
        self._man_btn.setStyleSheet(_on  if self._manual_mode else _off)
        self._auto_btn.setStyleSheet(_off if self._manual_mode else _on)

    def _sv_changed(self):
        try: v = max(10.0, min(35.0, float(self._sv_in.text())))
        except ValueError: v = self._sv_pct
        self._sv_pct = v; self._sv_in.setText(f"{v:.1f}")

    def _sv_init_changed(self):
        try: v = max(10.0, min(35.0, float(self._sv_init_in.text())))
        except ValueError: v = self._sv_init
        self._sv_init = v; self._sv_init_in.setText(f"{v:.1f}")
        # Sync: Init SV = room air temperature (physics origin)
        self._T_ROOM = v
        if hasattr(self, "_diagram"): self._diagram._t_room = v; self._diagram.update()

    def _man_cv_changed(self):
        try: v = max(0.0, min(100.0, float(self._man_cv_in.text())))
        except ValueError: v = self._cv_manual
        self._cv_manual = v; self._man_cv_in.setText(f"{v:.1f}")

    # ════════════════════════════════════════════════════
    #  Z-N WIZARD
    # ════════════════════════════════════════════════════
    def _zn_calculate(self):
        try: Ku = float(self._ku_in.text()); Pu = float(self._pu_in.text())
        except ValueError: return
        if Ku <= 0 or Pu <= 0:
            self._warn_lbl.setText("⚠ Ku 和 Pu 必須大於 0"); return
        self._warn_lbl.setText("")
        tl = self._method_box.currentIndex() == 1
        if tl:
            kp_b = Ku / 2.2
            results = {"P":  (kp_b, 0.0, 0.0),
                       "PI": (kp_b, kp_b / (2.2 * Pu), 0.0),
                       "PID":(kp_b, kp_b / (2.2 * Pu), kp_b * (Pu / 6.3))}
        else:
            results = {"P":  (0.50*Ku, 0.0, 0.0),
                       "PI": (0.45*Ku, 0.45*Ku / (Pu/1.2), 0.0),
                       "PID":(0.60*Ku, 0.60*Ku / (Pu/2.0), 0.60*Ku * (Pu/8.0))}
        self._zn_results = results
        _hi = (f"color:#FFFF00;font-size:9pt;font-weight:bold;"
               f"font-family:Consolas,'Courier New';"
               f"border-bottom:1px solid #252525;border-left:1px solid #252525;"
               f"padding:3px 6px;background:transparent;")
        for mode, (kp, ki, kd) in results.items():
            kp_l, ki_l, kd_l = self._zn_cells[mode]
            kp_l.setText(f"{kp:.4f}");                kp_l.setStyleSheet(_hi)
            ki_l.setText(f"{ki:.5f}" if ki else "—"); ki_l.setStyleSheet(_hi)
            kd_l.setText(f"{kd:.5f}" if kd else "—"); kd_l.setStyleSheet(_hi)

    def _zn_apply(self, mode: str):
        if mode not in self._zn_results: return
        kp, ki, kd = self._zn_results[mode]
        self._Kp = max(0.0, min(200.0, kp))
        self._Ki = max(0.0, min(50.0,  ki))
        self._Kd = max(0.0, min(50.0,  kd))
        for attr, val, dec in [("Kp", self._Kp, 3), ("Ki", self._Ki, 4), ("Kd", self._Kd, 4)]:
            if attr in self._pid_inputs:
                self._pid_inputs[attr].setText(f"{val:.{dec}f}")
        self._reset_sim()

    def _refresh_formula_lbl(self):
        tl = self._method_box.currentIndex() == 1
        if tl:
            txt = "T-L：P → Kp=Ku/2.2  │  PI → Ti=2.2·Pu, Ki=Kp/Ti  │  PID → Td=Pu/6.3, Kd=Kp·Td"
        else:
            txt = "Z-N：P → Kp=0.50·Ku  │  PI → Kp=0.45·Ku, Ti=Pu/1.2  │  PID → Kp=0.60·Ku, Ti=Pu/2, Td=Pu/8"
        self._formula_lbl.setText(txt)

    def _on_method_changed(self):
        self._refresh_formula_lbl()
        if self._zn_results: self._zn_calculate()

    # ════════════════════════════════════════════════════
    #  TIMELINE SLIDER
    # ════════════════════════════════════════════════════
    def _slider_resume_follow(self):
        self._slider_following = True
        if HAS_PG:
            x_hi = max(self._SPAN, self._t_now)
            self._pw.setXRange(x_hi - self._SPAN, x_hi, padding=0)

    def _slider_moved(self, val: int):
        if self._slider_dragging and HAS_PG:
            self._pw.setXRange(float(val), float(val) + self._SPAN, padding=0)

    # ════════════════════════════════════════════════════
    #  AUTO CAPTURE (same algorithm, works on °C values)
    # ════════════════════════════════════════════════════
    def _auto_capture(self):
        N = min(1200, len(self._pv_data))
        if N < 200:
            self._warn_lbl.setText("資料不足 — 等待 PV 溫度震盪後再擷取。"); return
        seg   = list(self._pv_data)[-N:]
        t_seg = list(self._t_data)[-N:]
        sm = list(seg)
        for i in range(1, N - 1):
            sm[i] = (seg[i-1] + 2*seg[i] + seg[i+1]) / 4.0
        min_sep, min_prom = 60, 0.2   # promincence in °C
        peaks: list = []; last = -min_sep; i = 1
        while i < N - 1:
            if sm[i] > sm[i-1] and sm[i] > sm[i+1] and i - last >= min_sep:
                lo = max(0, i - min_sep); hi = min(N, i + min_sep + 1)
                if sm[i] - min(sm[lo:hi]) >= min_prom:
                    peaks.append(i); last = i
            i += 1
        if len(peaks) < 3:
            self._warn_lbl.setText("峰值不足 — 請增加 Kp 直到溫度等幅震盪。"); return
        rec   = peaks[-4:]; amps = [sm[j] for j in rec]
        mean  = sum(amps) / len(amps)
        std   = (sum((a - mean)**2 for a in amps) / len(amps))**0.5
        if std / (abs(mean) + 1e-6) > 0.25:
            self._warn_lbl.setText("波型不穩定 — 重新調整 Kp 後再試。"); return
        periods = [t_seg[rec[j+1]] - t_seg[rec[j]] for j in range(len(rec)-1)]
        Pu = sum(periods) / len(periods)
        if Pu < 1.0: self._warn_lbl.setText("週期過短 — 確認 FOPDT 參數。"); return
        Ku = self._Kp
        self._ku_in.setText(f"{Ku:.3f}"); self._pu_in.setText(f"{Pu:.2f}")
        self._warn_lbl.setStyleSheet(
            f"color:{self._OK};font-size:8.5pt;font-weight:600;"
            f"background:transparent;border:none;font-family:'Microsoft JhengHei','Segoe UI';")
        self._warn_lbl.setText(f"✓  Ku={Ku:.3f}  Pu={Pu:.2f}s  → 點擊「一鍵換算」")
        self._zn_calculate()
        if HAS_PG:
            cap_dur = N * self._DT
            x_lo = max(0.0, self._t_now - cap_dur)
            self._pw.setXRange(x_lo, x_lo + cap_dur * 3.0, padding=0)
            self._slider_following = False

    # ════════════════════════════════════════════════════
    #  SIMULATION
    # ════════════════════════════════════════════════════
    def _rebuild_dead_buf(self):
        n = max(1, round(self._pL / self._DT))
        self._dead_buf = deque([self._last_cv] * n, maxlen=n)

    def _reset_sim(self):
        if not hasattr(self, "_sim_timer"): return
        self._sim_timer.stop()
        n = max(1, round(self._pL / self._DT))

        # Steady-state valve to hold supply temp at sv_init
        # T_supply_ss = T_room - pK * 100 * valve_n → valve_n = (T_room - sv_init) / (pK * 100)
        valve_ss = (self._T_ROOM - self._sv_init) / (self._pK * 100.0)
        valve_ss = max(self._mv_min / 100.0, min(self._mv_max / 100.0, valve_ss))

        if self._manual_mode:
            valve_ss = max(self._mv_min / 100.0,
                           min(self._mv_max / 100.0, self._cv_manual / 100.0))

        self._T_pv     = self._sv_init
        self._integral = 0.0; self._prev_err = 0.0
        self._last_cv  = valve_ss
        self._dead_buf = deque([valve_ss] * n, maxlen=n)
        self._t_data.clear(); self._pv_data.clear()
        self._sv_data.clear(); self._cv_data.clear()
        self._t_now = 0.0; self._step = 0
        self._peak_pv = self._sv_init

        if HAS_PG:
            self._sv_curve.setData([], []); self._pv_curve.setData([], [])
            self._cv_curve.setData([], [])
            self._pw.setXRange(0, self._SPAN, padding=0)
        self._slider_following = True
        if hasattr(self, "_timeline_slider"):
            self._timeline_slider.blockSignals(True)
            self._timeline_slider.setRange(0, int(self._SPAN))
            self._timeline_slider.setValue(0)
            self._timeline_slider.blockSignals(False)
        self._sim_timer.start(50)

    def _sim_tick(self):
        dt = self._DT
        mv_lo = self._mv_min / 100.0
        mv_hi = self._mv_max / 100.0

        # ── Controller ────────────────────────────────────
        if self._manual_mode:
            valve_n = max(mv_lo, min(mv_hi, self._cv_manual / 100.0))
        else:
            # Reverse action: err positive when PV > SV (too warm → open valve)
            err = (self._T_pv - self._sv_pct) if self._reverse_action \
                  else (self._sv_pct - self._T_pv)
            self._integral = max(-50.0, min(50.0, self._integral + err * dt))
            deriv  = (err - self._prev_err) / dt
            cv_raw = self._Kp * err + self._Ki * self._integral + self._Kd * deriv
            valve_n = max(mv_lo, min(mv_hi, cv_raw / 100.0))
            self._prev_err = err

        # ── FOPDT: T_supply ─────────────────────────────
        # T_ss = T_room - K_ahu * valve_n  where K_ahu = pK * 100 (°C per full unit)
        delayed_v = self._dead_buf[0]; self._dead_buf.append(valve_n)
        alpha = dt / (self._pT + dt)
        T_ss  = self._T_ROOM - self._pK * 100.0 * delayed_v
        T_raw = alpha * T_ss + (1.0 - alpha) * self._T_pv

        # PV limits
        self._T_pv = max(self._pv_min, min(self._pv_max, T_raw))
        if self._T_pv > self._peak_pv: self._peak_pv = self._T_pv
        self._last_cv = valve_n

        self._t_data.append(self._t_now)
        self._pv_data.append(self._T_pv)
        self._sv_data.append(self._sv_pct)
        self._cv_data.append(valve_n * 100.0)
        self._t_now += dt; self._step += 1

        # ── Plot refresh (5 Hz) ──────────────────────────
        if self._step % 4 == 0 and HAS_PG:
            ta   = list(self._t_data)
            x_hi = max(self._SPAN, self._t_now)
            x_lo = x_hi - self._SPAN
            if self._slider_following:
                self._pw.setXRange(x_lo, x_hi, padding=0)
                self._timeline_slider.blockSignals(True)
                self._timeline_slider.setRange(0, int(x_hi))
                self._timeline_slider.setValue(int(max(0.0, x_lo)))
                self._timeline_slider.blockSignals(False)
            self._sv_curve.setData(ta, list(self._sv_data))
            self._pv_curve.setData(ta, list(self._pv_data))
            self._cv_curve.setData(ta, list(self._cv_data))

        # ── Live strip (2 Hz) ────────────────────────────
        if self._step % 10 == 0:
            valve_pct = valve_n * 100.0
            self._pv_disp.setText(f"{self._T_pv:5.2f}")
            self._sv_disp.setText(f"{self._sv_pct:5.1f}")
            self._mv_disp.setText(f"{valve_pct:5.1f}")
            self._mv_big.setText(f"{valve_pct:5.1f}")
            m, s = divmod(int(self._t_now), 60)
            self._t_disp.setText(f"t = {m:02d}:{s:02d}")
            err_c = abs(self._T_pv - self._sv_pct)
            self._peak_disp.setText(f"ΔT = {err_c:.2f} °C")
            # Update AHU diagram
            if hasattr(self, "_diagram"):
                self._diagram.refresh(valve_pct, self._T_pv, self._sv_pct,
                                      t_room=self._T_ROOM, t_cw=self._pv_min)

    def closeEvent(self, e):
        self._sim_timer.stop(); super().closeEvent(e)

    def hideEvent(self, e):
        self._sim_timer.stop(); super().hideEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        if not self._sim_timer.isActive(): self._sim_timer.start(50)
