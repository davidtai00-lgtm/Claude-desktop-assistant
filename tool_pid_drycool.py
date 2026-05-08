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
    QApplication, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QScrollArea, QSlider,
)
from styles import BaseToolWindow


# ═══════════════════════════════════════════════════════
#  AHU DUCT DIAGRAM  (painter widget)
# ═══════════════════════════════════════════════════════
class _AhuDiagram(QWidget):
    """Cross-section painter: louver inlet → cooling coil → supply outlet."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(210, 320)
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
        pen = QPen(QColor("#00B4D8"), 2.5, Qt.PenStyle.SolidLine,
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
        p.setPen(QPen(QColor("#162440"), 2)); p.setBrush(QColor("#050B18"))
        p.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
        span = int(pct / 100.0 * 360 * 16)
        rect = QRect(cx - r + 3, cy - r + 3, 2 * r - 6, 2 * r - 6)
        g = int(80 + 60 * pct / 100)
        p.setBrush(QColor(255, g, 0, 210)); p.setPen(Qt.PenStyle.NoPen)
        p.drawPie(rect, 90 * 16, -span)
        p.setPen(QPen(QColor("#E0ECF8")))
        p.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        p.drawText(QRect(cx - r, cy - 8, 2 * r, 16),
                   Qt.AlignmentFlag.AlignCenter, f"{pct:.0f}%")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.fillRect(0, 0, W, H, QColor("#050B18"))

        # Title
        self._lbl(p, "AHU 空氣冷卻系統", 0, 2, W, 20, "#00B4D8", 10, True)

        # Duct — wide, centred, with side margins for labels
        dx, dw = int(W * 0.14), int(W * 0.72)
        dy, dh = 26, H - 34
        path = QPainterPath()
        path.addRoundedRect(dx, dy, dw, dh, 10, 10)
        p.fillPath(path, QColor("#0A1428"))
        p.setPen(QPen(QColor("#162440"), 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        zt_h = int(dh * 0.28)
        zc_h = int(dh * 0.44)
        zb_h = dh - zt_h - zc_h
        zt_y, zc_y, zb_y = dy, dy + zt_h, dy + zt_h + zc_h
        cx = dx + dw // 2

        # ── Top: supply outlet ───────────────────────────
        gr = QLinearGradient(0, zt_y, 0, zt_y + zt_h)
        gr.setColorAt(0.0, QColor("#050B18")); gr.setColorAt(1.0, QColor("#040F1E"))
        p.fillRect(dx + 2, zt_y + 2, dw - 4, zt_h - 2, QBrush(gr))

        # Up arrow
        p.setPen(QPen(QColor("#00D4FF"), 2.5))
        ay1, ay2 = zt_y + 8, zt_y + zt_h - 46
        p.drawLine(cx, ay2, cx, ay1)
        arr = QPainterPath()
        arr.moveTo(cx, ay1); arr.lineTo(cx - 9, ay1 + 16); arr.lineTo(cx + 9, ay1 + 16)
        arr.closeSubpath()
        p.fillPath(arr, QColor("#00D4FF"))

        self._lbl(p, "供氣  Supply Air", dx, zt_y + zt_h - 42, dw, 18, "#00B4D8", 9, True)
        t_clr = "#00FF9F" if self._t_pv <= self._t_sv + 0.3 else "#FF4444"
        self._lbl(p, f"{self._t_pv:.1f} °C", dx, zt_y + zt_h - 24, dw, 22, t_clr, 14, True)

        # ── Middle: cooling coil ─────────────────────────
        p.fillRect(dx + 2, zc_y, dw - 4, zc_h, QColor("#050B18"))
        p.setPen(QPen(QColor("#162440"), 1))
        p.drawLine(dx + 2, zc_y, dx + dw - 2, zc_y)
        p.drawLine(dx + 2, zb_y, dx + dw - 2, zb_y)

        self._lbl(p, "冷卻盤管  Cooling Coil", dx, zc_y + 4, dw, 18, "#00B4D8", 9, True)
        self._lbl(p, f"冷水入口  CW in  {self._t_cw:.1f} °C", dx, zc_y + 22, dw, 16, "#4A6A8A", 8)

        self._coil(p, dx + 14, zc_y + 40, dw - 28, 52)

        # Valve indicator (larger radius)
        vy = zc_y + 106
        self._valve(p, cx, vy, 38, self._valve_pct)
        self._lbl(p, f"閥開度  {self._valve_pct:.1f} %", dx, vy + 42, dw, 18, "#FF7700", 9, True)
        self._lbl(p, f"SV = {self._t_sv:.1f} °C",        dx, vy + 58, dw, 16, "#00FF9F", 9)

        # ── Bottom: room air inlet ───────────────────────
        gr2 = QLinearGradient(0, zb_y, 0, zb_y + zb_h)
        gr2.setColorAt(0.0, QColor("#0A0600")); gr2.setColorAt(1.0, QColor("#050300"))
        p.fillRect(dx + 2, zb_y, dw - 4, zb_h - 2, QBrush(gr2))

        # Inlet arrow (from bottom-left into duct)
        p.setPen(QPen(QColor("#FF7700"), 2.5))
        iy = zb_y + zb_h // 2
        p.drawLine(dx + 2, iy, dx + dw // 3, iy)
        for dy_ in (-6, 6):
            p.drawLine(dx + dw // 3, iy, dx + dw // 3 - 10, iy + dy_)

        self._lbl(p, "室內回風  Room Air", dx, zb_y + 6,  dw, 18, "#FF7700", 9, True)
        self._lbl(p, f"T_room = {self._t_room:.1f} °C",  dx, zb_y + 24, dw, 17, "#E0ECF8", 9)

        # Louver bars at bottom
        lx, lw_ = dx + 6, dw - 12
        p.setPen(QPen(QColor("#162440"), 1.5))
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

    # ── MAU Palette ──────────────────────────────────────
    _BG     = "#050B18"
    _CELL   = "#0A1428"
    _BORDER = "#162440"
    _LBL    = "#E0ECF8"
    _LBL2   = "#4A6A8A"
    _INPUT  = "#FFD700"
    _RESULT = "#00D4FF"
    _PV_CLR = "#00D4FF"
    _SV_CLR = "#00FF9F"
    _MV_CLR = "#FF7700"
    _ACC    = "#00B4D8"
    _INP_BG = "#040C1C"
    _WARN   = "#FF4444"
    _OK     = "#00FF88"

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
        super().__init__("❄️ AHU Cooling Coil PID Station", 1120, 960)
        self.setMinimumSize(860, 700)

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
        self._pid_inputs: dict = {}
        self._slider_following = True; self._slider_dragging = False

        self.content.setStyleSheet(f"background:{self._BG};")

        # ── Top-level layout: HMI | center scroll | right panel ───
        top = QHBoxLayout(self.content)
        top.setContentsMargins(4, 4, 4, 4); top.setSpacing(4)

        # Left: HMI industrial panel
        self._hmi_panel = self._build_hmi_panel()
        top.addWidget(self._hmi_panel, 1)

        # Centre: scrollable PID content (chart + controls + status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea{{border:none;background:{self._BG};}}"
            f"QScrollBar:vertical{{background:{self._BG};width:6px;border-radius:3px;}}"
            f"QScrollBar::handle:vertical{{background:{self._BORDER};border-radius:3px;}}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
        inner = QWidget(); inner.setStyleSheet(f"background:{self._BG};")
        scroll.setWidget(inner)
        root = QVBoxLayout(inner); root.setContentsMargins(6, 4, 6, 4); root.setSpacing(5)
        top.addWidget(scroll, 3)

        # Right: params + AHU diagram stacked
        right_frame = QFrame()
        right_frame.setMinimumWidth(270)
        right_frame.setStyleSheet(
            f"QFrame{{background:{self._CELL};"
            f"border-left:2px solid {self._BORDER};}}")
        right_lay = QVBoxLayout(right_frame)
        right_lay.setContentsMargins(6, 8, 6, 8); right_lay.setSpacing(6)
        top.addWidget(right_frame, 1)

        # Build center sections
        self._build_plot(root)
        self._build_timeline_slider(root)
        self._build_live_strip(root)
        self._build_ctrl_row(root)
        self._build_mv_limit_row(root)
        self._build_status_bar(root)

        # Build right panel: params at top, diagram below
        self._build_param_cols(right_lay)

        # AHU diagram — in right panel below params
        self._diagram = _AhuDiagram()
        self._diagram.setMinimumHeight(300)
        self._diagram._t_room = self._sv_init   # linked to Init SV
        self._diagram._t_cw   = self._pv_min    # linked to PV MIN
        right_lay.addWidget(self._diagram, 1)

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
        p.fillPath(path, QColor(0x05, 0x0B, 0x18))
        p.setPen(QPen(QColor(0x16, 0x24, 0x40), 1)); p.drawPath(path)

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

        # Watermark
        _wm = pg.TextItem(
            html='<div style="color:rgba(180,180,180,30);font-size:26pt;font-weight:700;'
                 'font-family:\'Microsoft JhengHei\',\'Segoe UI\',sans-serif;'
                 'white-space:nowrap;">亞聖國際科技有限公司</div>',
            anchor=(0.5, 0.5))
        pw.addItem(_wm, ignoreBounds=True)
        def _wm_pos(*_, pw=pw, wm=_wm):
            vr = pw.viewRange()
            wm.setPos((vr[0][0] + vr[0][1]) / 2, (vr[1][0] + vr[1][1]) / 2)
        pw.getPlotItem().vb.sigRangeChanged.connect(_wm_pos)
        _wm_pos()

        self._xhair = pg.InfiniteLine(angle=90, movable=False,
                                      pen=pg.mkPen((200, 200, 200, 55), width=1))
        pw.addItem(self._xhair, ignoreBounds=True)
        self._hover_lbl = pg.TextItem(anchor=(0, 0), fill=pg.mkBrush(5, 11, 24, 210))
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
        f.setStyleSheet(f"QFrame{{background:{self._CELL};border:1px solid {self._BORDER};border-radius:3px;}}")
        f.setFixedHeight(28)
        h = QHBoxLayout(f); h.setContentsMargins(8, 4, 8, 4); h.setSpacing(6)
        h.addWidget(self._tag("進度桿", self._LBL2, 7))
        self._timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self._timeline_slider.setRange(0, int(self._SPAN)); self._timeline_slider.setValue(0)
        self._timeline_slider.setStyleSheet(
            f"QSlider::groove:horizontal{{background:{self._BG};height:4px;border-radius:2px;}}"
            f"QSlider::handle:horizontal{{background:{self._ACC};width:10px;height:10px;"
            "border-radius:5px;margin:-3px 0;}"
            f"QSlider::sub-page:horizontal{{background:{self._ACC};border-radius:2px;}}")
        self._timeline_slider.sliderPressed.connect(
            lambda: (setattr(self, "_slider_dragging", True),
                     setattr(self, "_slider_following", False)))
        self._timeline_slider.sliderReleased.connect(
            lambda: setattr(self, "_slider_dragging", False))
        self._timeline_slider.valueChanged.connect(self._slider_moved)
        h.addWidget(self._timeline_slider, 1)
        fb = QPushButton("⏩ 追蹤"); fb.setFixedHeight(20); fb.setFixedWidth(62)
        fb.setStyleSheet(
            f"QPushButton{{background:{self._CELL};color:{self._LBL2};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:7.5pt;font-weight:700;padding:0 4px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';}}"
            f"QPushButton:hover{{background:{self._BG};color:{self._LBL};}}")
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
            unt.setStyleSheet(f"color:{self._LBL2};font-size:10pt;font-weight:600;"
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
        mv_u = QLabel("%"); mv_u.setStyleSheet(
            f"color:{self._LBL2};font-size:10pt;font-weight:600;"
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
        lay.addWidget(self._sec_hdr("≡  主要參數  Parameters"))

        _sep = (f"color:{self._BORDER};font-size:7pt;"
                f"background:transparent;border:none;font-family:Consolas,'Courier New';")
        _ann = (f"color:{self._LBL};font-size:9pt;font-weight:600;"
                f"background:transparent;border:none;"
                f"font-family:'Microsoft JhengHei','Segoe UI';")

        def _framed_section(hdr_text, formula_block):
            fr = QFrame()
            fr.setStyleSheet(f"QFrame{{background:{self._BG};"
                             f"border:1px solid {self._ACC};border-radius:4px;}}")
            flay = QVBoxLayout(fr)
            flay.setContentsMargins(8, 6, 8, 6); flay.setSpacing(6)
            hl = QLabel(hdr_text)
            hl.setStyleSheet(f"color:{self._ACC};font-size:9.5pt;font-weight:700;"
                             f"background:transparent;border:none;padding-bottom:3px;"
                             f"font-family:'Microsoft JhengHei','Segoe UI';")
            flay.addWidget(hl)
            param_lay = QVBoxLayout(); param_lay.setSpacing(3)
            flay.addLayout(param_lay)
            for text, style in formula_block:
                fl = QLabel(text); fl.setStyleSheet(style); fl.setWordWrap(True)
                flay.addWidget(fl)
            return fr, param_lay

        pid_formula = [
            ("────────────────────────",               _sep),
            ("供氣溫度 PV vs 設定溫度 SV → 調節閥 MV", _ann),
            ("P  ─  溫差即時反應，超溫即開閥",          _ann),
            ("I  ─  累積偏差，消除穩態溫差殘留",        _ann),
            ("D  ─  預測溫度趨勢，防止供氣過冷",        _ann),
            ("MV = Kp·e + Ki·∫e + Kd·de/dt",          _sep),
        ]
        fopdt_formula = [
            ("────────────────────────",               _sep),
            ("T_ss = T_room − K · valve%",             _ann),
            ("K  ─  每 1% 開度帶走多少 °C",             _ann),
            ("τ  ─  盤管熱容與氣流熱交換時間",           _ann),
            ("L  ─  氣流輸送 + 感測器延遲",             _ann),
            ("T(t) = T_ss·(1 − e^(−(t−L)/τ))",        _sep),
        ]

        pid_fr,   pid_col   = _framed_section("PID 控制器  AHU Control", pid_formula)
        fopdt_fr, fopdt_col = _framed_section("FOPDT 冷卻盤管製程模型",   fopdt_formula)

        for attr, label, lo, hi, dec in self._PID_SPECS:
            le = self._param_row(pid_col, attr, label, lo, hi, dec, "")
            self._pid_inputs[attr] = le

        for attr, label, lo, hi, dec, unit in self._FOPDT_SPECS:
            self._param_row(fopdt_col, attr, label, lo, hi, dec, unit)

        lay.addWidget(pid_fr)
        lay.addWidget(fopdt_fr)

    def _build_status_bar(self, lay: QVBoxLayout):
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:#04091A;border:1px solid {self._BORDER};border-radius:4px;}}")
        f.setFixedHeight(38)
        h = QHBoxLayout(f); h.setContentsMargins(10, 4, 10, 4); h.setSpacing(8)
        name = QLabel("亞聖國際科技有限公司")
        name.setStyleSheet(f"color:{self._LBL};font-size:8pt;font-weight:700;"
                           "background:transparent;border:none;"
                           "font-family:'Microsoft JhengHei','Segoe UI';")
        div = QLabel("│"); div.setStyleSheet(f"color:{self._BORDER};background:transparent;border:none;")
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
        l = QLabel(f"  {text}"); l.setFixedHeight(22)
        l.setStyleSheet(f"color:{self._ACC};font-size:9pt;font-weight:700;"
                        f"background:#08101E;border-top:1px solid {self._ACC};"
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
            f"QPushButton:hover{{background:{self._BG};color:{self._LBL};}}")
        return b

    def _vline(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.Shape.VLine)
        f.setStyleSheet(f"QFrame{{border:none;border-left:1px solid {self._BORDER};"
                        f"background:transparent;}}"); return f

    def _param_row(self, lay: QVBoxLayout, attr: str, label: str,
                   lo: float, hi: float, dec: int, unit: str) -> QLineEdit:
        row = QHBoxLayout(); row.setSpacing(4)
        lb = QLabel(label); lb.setFixedWidth(150)
        lb.setStyleSheet(f"color:{self._LBL};font-size:9.5pt;font-weight:600;"
                         f"font-family:'Microsoft JhengHei','Segoe UI';"
                         f"background:transparent;border:none;")
        le = QLineEdit(f"{getattr(self, '_' + attr):.{dec}f}")
        le.setFixedWidth(80); le.setFixedHeight(24); le.setAlignment(Qt.AlignmentFlag.AlignRight)
        le.setStyleSheet(
            f"QLineEdit{{background:{self._INP_BG};color:{self._INPUT};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:11pt;font-weight:700;"
            f"font-family:Consolas,'Courier New';padding:1px 5px;}}"
            f"QLineEdit:focus{{border:1px solid {self._ACC};}}")
        ul = QLabel(unit or ""); ul.setFixedWidth(32)
        ul.setStyleSheet(f"color:{self._LBL2};font-size:8pt;background:transparent;border:none;")
        rl = QLabel(f"[{lo:.3g}–{hi:.4g}]")
        rl.setStyleSheet(f"color:{self._LBL2};font-size:7.5pt;background:transparent;border:none;")

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
                f"QPushButton{{background:#04090A;color:{self._ACC};"
                f"border:1px solid #0A2A30;border-radius:3px;"
                f"font-size:8.5pt;font-weight:700;"
                f"font-family:'Microsoft JhengHei','Segoe UI';}}"
                f"QPushButton:hover{{background:#071218;color:#fff;}}")
        else:
            self._act_btn.setText("正向  Direct")
            self._act_btn.setStyleSheet(
                f"QPushButton{{background:#04130A;color:{self._OK};"
                f"border:1px solid #0A3A1A;border-radius:3px;"
                f"font-size:8.5pt;font-weight:700;"
                f"font-family:'Microsoft JhengHei','Segoe UI';}}"
                f"QPushButton:hover{{background:#081E14;color:#fff;}}")

    def _set_mode(self, manual: bool):
        self._manual_mode = manual
        self._mv_mode_lbl.setText("Valve  閥位 (手動)" if manual else "Valve  閥位 (自動)")
        self._refresh_mode_btns()
        self._refresh_hmi_mode_btns()

    def _refresh_mode_btns(self):
        _on  = (f"QPushButton{{background:{self._ACC};color:#000;border:none;"
                f"border-radius:3px;font-size:8.5pt;font-weight:700;"
                f"font-family:'Microsoft JhengHei','Segoe UI';}}")
        _off = (f"QPushButton{{background:{self._CELL};color:{self._LBL2};"
                f"border:1px solid {self._BORDER};border-radius:3px;"
                f"font-size:8.5pt;font-weight:600;"
                f"font-family:'Microsoft JhengHei','Segoe UI';}}"
                f"QPushButton:hover{{background:{self._BG};color:{self._LBL};}}")
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
        self._T_ROOM = v
        if hasattr(self, "_diagram"): self._diagram._t_room = v; self._diagram.update()

    def _man_cv_changed(self):
        try: v = max(0.0, min(100.0, float(self._man_cv_in.text())))
        except ValueError: v = self._cv_manual
        self._cv_manual = v; self._man_cv_in.setText(f"{v:.1f}")

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
    #  SIMULATION
    # ════════════════════════════════════════════════════
    def _rebuild_dead_buf(self):
        n = max(1, round(self._pL / self._DT))
        self._dead_buf = deque([self._last_cv] * n, maxlen=n)

    def _reset_sim(self):
        if not hasattr(self, "_sim_timer"): return
        self._sim_timer.stop()
        n = max(1, round(self._pL / self._DT))

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
            err = (self._T_pv - self._sv_pct) if self._reverse_action \
                  else (self._sv_pct - self._T_pv)
            self._integral = max(-50.0, min(50.0, self._integral + err * dt))
            deriv  = (err - self._prev_err) / dt
            cv_raw = self._Kp * err + self._Ki * self._integral + self._Kd * deriv
            valve_n = max(mv_lo, min(mv_hi, cv_raw / 100.0))
            self._prev_err = err

        # ── FOPDT: T_supply ─────────────────────────────
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
            if hasattr(self, "_diagram"):
                self._diagram.refresh(valve_pct, self._T_pv, self._sv_pct,
                                      t_room=self._T_ROOM, t_cw=self._pv_min)
            self._update_hmi()

    # ════════════════════════════════════════════════════
    #  INDUSTRIAL HMI PANEL
    # ════════════════════════════════════════════════════
    def _build_hmi_panel(self) -> QFrame:
        ROW_H = 56;  LBL_W = 88

        panel = QFrame()
        panel.setMinimumWidth(190)
        panel.setMaximumWidth(340)
        panel.setStyleSheet(
            f"QFrame{{background:#04091A;"
            f"border:3px solid {self._ACC};"
            f"border-radius:5px;}}")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(1)

        def _lbl_frame(label: str) -> QFrame:
            lf = QFrame(); lf.setMinimumWidth(LBL_W); lf.setMaximumWidth(LBL_W + 40)
            lf.setStyleSheet(f"QFrame{{background:{self._CELL};border:none;border-radius:2px;}}")
            ll = QVBoxLayout(lf); ll.setContentsMargins(3, 2, 3, 2)
            lt = QLabel(label); lt.setWordWrap(True)
            lt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lt.setStyleSheet(f"color:{self._LBL};font-size:8.5pt;font-weight:700;"
                             "background:transparent;border:none;"
                             "font-family:'Microsoft JhengHei','Segoe UI';")
            ll.addWidget(lt); return lf

        def _wrap(lf, vf):
            rf = QFrame(); rf.setFixedHeight(ROW_H)
            rf.setStyleSheet("QFrame{background:transparent;border:none;}")
            h = QHBoxLayout(rf); h.setContentsMargins(0,0,0,0); h.setSpacing(1)
            h.addWidget(lf); h.addWidget(vf, 1); lay.addWidget(rf)

        def _row_ro(label, val_bg, val_clr) -> QLabel:
            lf = _lbl_frame(label)
            vf = QFrame()
            vf.setStyleSheet(f"QFrame{{background:{val_bg};border:none;border-radius:2px;}}")
            vl = QVBoxLayout(vf); vl.setContentsMargins(4, 2, 4, 2)
            vt = QLabel("—"); vt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vt.setStyleSheet(f"color:{val_clr};font-size:14pt;font-weight:700;"
                             "background:transparent;border:none;"
                             "font-family:Consolas,'Courier New';")
            vl.addWidget(vt); _wrap(lf, vf); return vt

        def _row_edit(label, val_bg, val_clr, init) -> QLineEdit:
            lf = _lbl_frame(label)
            vf = QFrame()
            vf.setStyleSheet(f"QFrame{{background:{val_bg};border:none;border-radius:2px;}}")
            vl = QVBoxLayout(vf); vl.setContentsMargins(4, 2, 4, 2)
            le = QLineEdit(init); le.setAlignment(Qt.AlignmentFlag.AlignCenter)
            le.setStyleSheet(
                f"QLineEdit{{background:transparent;color:{val_clr};"
                f"border:none;font-size:14pt;font-weight:700;"
                f"font-family:Consolas,'Courier New';}}"
                f"QLineEdit:focus{{border-bottom:2px solid {self._ACC};}}")
            vl.addWidget(le); _wrap(lf, vf); return le

        def _mode_row():
            lf = _lbl_frame("手自動")
            vf = QFrame()
            vf.setStyleSheet(f"QFrame{{background:{self._BG};border:none;border-radius:2px;}}")
            vh = QHBoxLayout(vf); vh.setContentsMargins(4, 8, 4, 8); vh.setSpacing(4)
            ba = QPushButton("Auto");   ba.setFixedHeight(34)
            bm = QPushButton("Manual"); bm.setFixedHeight(34)
            ba.clicked.connect(lambda: self._set_mode(False))
            bm.clicked.connect(lambda: self._set_mode(True))
            vh.addWidget(ba, 1); vh.addWidget(bm, 1)
            _wrap(lf, vf); return ba, bm

        self._hmi_pv       = _row_ro  ("PV",       self._BG,    self._PV_CLR)
        self._hmi_sv_e     = _row_edit("SV 設定值", "#030C1A",   self._SV_CLR,  f"{self._sv_pct:.1f}")
        self._hmi_auto_btn, self._hmi_man_btn = _mode_row()
        self._hmi_man_e    = _row_edit("手動輸出",  "#0A0800",   self._MV_CLR,  f"{self._cv_manual:.1f}")
        self._hmi_auto_out = _row_ro  ("自動輸出",  self._BG,    self._RESULT)
        self._hmi_mv_max_e = _row_edit("MV Max",   "#080600",   self._INPUT,   f"{self._mv_max:.0f}")
        self._hmi_mv_min_e = _row_edit("MV Min",   "#080600",   self._INPUT,   f"{self._mv_min:.0f}")
        self._hmi_kp_e     = _row_edit("P  Kp",    "#080600",   self._INPUT,   f"{self._Kp:.3f}")
        self._hmi_ki_e     = _row_edit("I  Ki",    "#080600",   self._INPUT,   f"{self._Ki:.4f}")
        self._hmi_kd_e     = _row_edit("D  Kd",    "#080600",   self._INPUT,   f"{self._Kd:.4f}")

        self._hmi_sv_e.editingFinished.connect(self._hmi_commit_sv)
        self._hmi_man_e.editingFinished.connect(self._hmi_commit_man_out)
        self._hmi_mv_max_e.editingFinished.connect(self._hmi_commit_mv_max)
        self._hmi_mv_min_e.editingFinished.connect(self._hmi_commit_mv_min)
        self._hmi_kp_e.editingFinished.connect(self._hmi_commit_kp)
        self._hmi_ki_e.editingFinished.connect(self._hmi_commit_ki)
        self._hmi_kd_e.editingFinished.connect(self._hmi_commit_kd)

        self._refresh_hmi_mode_btns()
        lay.addStretch()
        return panel

    def _hmi_commit_sv(self):
        try:    v = max(10.0, min(35.0, float(self._hmi_sv_e.text())))
        except: v = self._sv_pct
        self._sv_pct = v;  self._hmi_sv_e.setText(f"{v:.1f}")
        if hasattr(self, "_sv_in"): self._sv_in.setText(f"{v:.1f}")

    def _hmi_commit_man_out(self):
        try:    v = max(0.0, min(100.0, float(self._hmi_man_e.text())))
        except: v = self._cv_manual
        self._cv_manual = v;  self._hmi_man_e.setText(f"{v:.1f}")
        if hasattr(self, "_man_cv_in"): self._man_cv_in.setText(f"{v:.1f}")

    def _hmi_commit_mv_max(self):
        try:    v = max(0.0, min(100.0, float(self._hmi_mv_max_e.text())))
        except: v = self._mv_max
        self._mv_max = v;  self._hmi_mv_max_e.setText(f"{v:.0f}")
        if hasattr(self, "_mv_max_in"): self._mv_max_in.setText(f"{v:.0f}")

    def _hmi_commit_mv_min(self):
        try:    v = max(0.0, min(100.0, float(self._hmi_mv_min_e.text())))
        except: v = self._mv_min
        self._mv_min = v;  self._hmi_mv_min_e.setText(f"{v:.0f}")
        if hasattr(self, "_mv_min_in"): self._mv_min_in.setText(f"{v:.0f}")

    def _hmi_commit_kp(self):
        try:    v = max(0.0, min(200.0, float(self._hmi_kp_e.text())))
        except: v = self._Kp
        self._Kp = v;  self._hmi_kp_e.setText(f"{v:.3f}")
        if "Kp" in self._pid_inputs: self._pid_inputs["Kp"].setText(f"{v:.3f}")

    def _hmi_commit_ki(self):
        try:    v = max(0.0, min(50.0, float(self._hmi_ki_e.text())))
        except: v = self._Ki
        self._Ki = v;  self._hmi_ki_e.setText(f"{v:.4f}")
        if "Ki" in self._pid_inputs: self._pid_inputs["Ki"].setText(f"{v:.4f}")

    def _hmi_commit_kd(self):
        try:    v = max(0.0, min(50.0, float(self._hmi_kd_e.text())))
        except: v = self._Kd
        self._Kd = v;  self._hmi_kd_e.setText(f"{v:.4f}")
        if "Kd" in self._pid_inputs: self._pid_inputs["Kd"].setText(f"{v:.4f}")

    def _refresh_hmi_mode_btns(self):
        if not hasattr(self, "_hmi_auto_btn"): return
        _on  = (f"QPushButton{{background:{self._ACC};color:#000;border:none;border-radius:3px;"
                "font-size:9.5pt;font-weight:700;"
                "font-family:'Microsoft JhengHei','Segoe UI';}")
        _off = (f"QPushButton{{background:{self._CELL};color:{self._LBL2};border:1px solid {self._BORDER};"
                "border-radius:3px;font-size:9.5pt;font-weight:700;"
                "font-family:'Microsoft JhengHei','Segoe UI';}"
                f"QPushButton:hover{{background:{self._BG};color:{self._LBL};}}")
        self._hmi_auto_btn.setStyleSheet(_on if not self._manual_mode else _off)
        self._hmi_man_btn.setStyleSheet (_on if     self._manual_mode else _off)

    def _update_hmi(self):
        if not hasattr(self, "_hmi_pv"): return
        valve_pct = self._last_cv * 100.0
        self._hmi_pv.setText(f"{self._T_pv:.1f} °C")
        self._hmi_auto_out.setText(f"{valve_pct:.1f} %")
        if not self._hmi_sv_e.hasFocus():     self._hmi_sv_e.setText(f"{self._sv_pct:.1f}")
        if not self._hmi_man_e.hasFocus():    self._hmi_man_e.setText(f"{self._cv_manual:.1f}")
        if not self._hmi_mv_max_e.hasFocus(): self._hmi_mv_max_e.setText(f"{self._mv_max:.0f}")
        if not self._hmi_mv_min_e.hasFocus(): self._hmi_mv_min_e.setText(f"{self._mv_min:.0f}")
        if not self._hmi_kp_e.hasFocus():     self._hmi_kp_e.setText(f"{self._Kp:.3f}")
        if not self._hmi_ki_e.hasFocus():     self._hmi_ki_e.setText(f"{self._Ki:.4f}")
        if not self._hmi_kd_e.hasFocus():     self._hmi_kd_e.setText(f"{self._Kd:.4f}")
        self._refresh_hmi_mode_btns()

    def closeEvent(self, e):
        self._sim_timer.stop(); super().closeEvent(e)

    def hideEvent(self, e):
        self._sim_timer.stop(); super().hideEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        if not self._sim_timer.isActive(): self._sim_timer.start(50)
        scr = QApplication.primaryScreen()
        if scr:
            ag = scr.availableGeometry()
            self.resize(ag.width(), ag.height())
            self.move(ag.left(), ag.top())
