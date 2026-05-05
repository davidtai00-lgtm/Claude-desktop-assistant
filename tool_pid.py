# tool_pid.py — PID Tuner Station 2.0  (Stability Release)
# Lightweight bilingual HMI — consolidated stable build.
#
# Init / Reset contract:
#   • PV starts at Init SV (normalised).
#   • Dead buffer pre-filled: Auto → MV_ss = InitSV/K; Manual → cv_manual.
#   • Reset clears only trend data + PV/MV; all params persist.
#   • SV is a pure step input — no ramp, no background tracking.
#   • Direct/Reverse action toggle; integral cleared on direction flip.
#   • Z-N (P/PI/PID) + T-L wizard with Auto Capture.
# Part of the Clawde Industrial Engineering Suite

from collections import deque
from typing import Callable

try:
    import pyqtgraph as pg
    pg.setConfigOption("background", "transparent")
    pg.setConfigOption("foreground", "#888")
    pg.setConfigOptions(antialias=True)
    HAS_PG = True
except ImportError:
    HAS_PG = False

from PyQt6.QtCore    import Qt, QTimer, QRect
from PyQt6.QtGui     import QPainter, QColor, QPen, QPainterPath, QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QComboBox, QScrollArea, QSlider,
)

from styles import BaseToolWindow


class PidTunerBuddy(BaseToolWindow):
    """
    PID Tuner Station 2.0 — Stability Release.
    • PV and SV both start at 0 on init / reset.
    • SV ramps smoothly from 0 → user target (_SV_RAMP %/s) to prevent
      large initial error and MV saturation.
    • FOPDT discrete-time simulation.  Z-N one-click tuning wizard.
    • PV / MV hard limits (clamped each tick).
    """
    _DT       = 0.05          # simulation time-step (s)
    _SPAN     = 600.0         # rolling plot window (s)
    _MAX_PTS  = 12_000        # deque capacity
    # SV is a pure step input — no ramping

    # ── Palette ──────────────────────────────────────────
    _BG     = "#121212"
    _CELL   = "#1A1A1A"
    _BORDER = "#3D3D3D"
    _LBL    = "#FFFFFF"
    _LBL2   = "#A0A0A0"
    _INPUT  = "#FFD700"       # Bold Yellow  — editable inputs
    _RESULT = "#00FFFF"       # Neon Cyan    — live results
    _PV_CLR = "#00FF00"       # Neon Green   — PV
    _SV_CLR = "#FF5555"       # Red          — SV
    _MV_CLR = "#00BFFF"       # Sky Blue     — MV
    _ACC    = "#FF8800"       # Orange       — headers / accent
    _INP_BG = "#1E1E1E"
    _WARN   = "#FF4444"
    _OK     = "#00FF88"

    # ── PID specs ────────────────────────────────────────
    _PID_SPECS = [
        ("Kp", "P 比例  Kp",  0.0, 100.0, 3),
        ("Ki", "I 積分  Ki",  0.0,  50.0, 4),
        ("Kd", "D 微分  Kd",  0.0,  20.0, 4),
    ]
    # ── FOPDT specs ──────────────────────────────────────
    _FOPDT_SPECS = [
        ("pK", "K  系統增益  Gain",      0.01, 10.0,  2, ""),
        ("pT", "τ  時間常數  Time Const", 0.10, 200.0, 1, "s"),
        ("pL", "L  延遲時間  Dead Time",  0.00,  30.0, 1, "s"),
    ]

    def __init__(self, on_thinking: Callable = None):
        super().__init__("⚙️ PID Tuner Station 2.0", 900, 960)
        self.setMinimumSize(640, 700)
        self._on_thinking = on_thinking

        # ── PID gains ────────────────────────────────────
        self._Kp = 1.5;  self._Ki = 0.0;  self._Kd = 0.0
        # ── FOPDT model ──────────────────────────────────
        self._pK = 0.80; self._pT = 2.0;  self._pL = 5.0
        # ── Setpoint / output state ───────────────────────
        self._sv_init        = 20.0   # baseline Init SV — persists across resets (%)
        self._sv_pct         = 50.0   # live SV — starts at Init SV, user-editable (%)
        self._cv_manual      = 50.0   # manual MV (%)
        self._manual_mode    = False
        self._reverse_action = False  # False=Direct 正向, True=Reverse 反向
        # ── Limits (%) ───────────────────────────────────
        self._pv_max = 100.0;  self._pv_min =  0.0
        self._mv_max = 100.0;  self._mv_min =  0.0
        # ── Sim internals ─────────────────────────────────
        self._pv_n      = 0.0
        self._integral  = 0.0
        self._prev_err  = 0.0
        self._dead_buf: deque = deque()
        self._t_data:   deque = deque(maxlen=self._MAX_PTS)
        self._pv_data:  deque = deque(maxlen=self._MAX_PTS)
        self._sv_data:  deque = deque(maxlen=self._MAX_PTS)
        self._cv_data:  deque = deque(maxlen=self._MAX_PTS)
        self._t_now   = 0.0
        self._step    = 0
        self._peak_pv = 0.0
        self._last_cv = 0.0
        self._zn_results: dict = {}
        self._pid_inputs: dict = {}

        self._slider_following = True
        self._slider_dragging  = False

        self.content.setStyleSheet(f"background:{self._BG};")

        # ── Scrollable root ───────────────────────────────
        scroll = QScrollArea(self.content)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QScrollBar:vertical{background:#1A1A1A;width:6px;border-radius:3px;}"
            "QScrollBar::handle:vertical{background:#3D3D3D;border-radius:3px;}"
            "QScrollBar::add-line:vertical,"
            "QScrollBar::sub-line:vertical{height:0;}")
        inner = QWidget(); inner.setStyleSheet(f"background:{self._BG};")
        scroll.setWidget(inner)
        root = QVBoxLayout(inner)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(5)

        h_ctn = QWidget(self.content)
        h_ctn.setStyleSheet(f"background:{self._BG};")
        self._h_lay = QHBoxLayout(h_ctn)
        self._h_lay.setContentsMargins(0, 0, 0, 0)
        self._h_lay.setSpacing(0)
        self._hmi_panel = self._build_hmi_panel()
        self._h_lay.addWidget(self._hmi_panel, 1)
        self._h_lay.addWidget(scroll, 4)
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(h_ctn)

        # ── Build sections ────────────────────────────────
        self._build_plot(root)              # 1. trend
        self._build_timeline_slider(root)  # 2. timeline scrubber
        self._build_live_strip(root)       # 3. PV / SV large
        self._build_ctrl_row(root)      # 3. mode + SV target + manual MV
        self._build_mv_limit_row(root)  # 4. MV readout + PV/MV MAX/MIN
        self._build_param_cols(root)    # 5. PID | FOPDT
        self._build_zn_section(root)    # 6. Z-N wizard
        self._build_status_bar(root)    # 7. status bar

        self._sim_timer = QTimer(self)
        self._sim_timer.timeout.connect(self._sim_tick)
        self._reset_sim()

    # ════════════════════════════════════════════════════
    #  WINDOW CHROME
    # ════════════════════════════════════════════════════
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 13, 13)
        p.fillPath(path, QColor(0x12, 0x12, 0x12))
        p.setPen(QPen(QColor(0x3D, 0x3D, 0x3D), 1))
        p.drawPath(path)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "_grip"):
            self._grip.move(self.width()  - self._grip.width(),
                            self.height() - self._grip.height())

    # ════════════════════════════════════════════════════
    #  SECTION BUILDERS
    # ════════════════════════════════════════════════════
    def _build_plot(self, lay: QVBoxLayout):
        if not HAS_PG:
            lbl = QLabel("缺少套件 → pip install pyqtgraph")
            lbl.setStyleSheet(f"color:{self._WARN};font-size:11pt;font-weight:bold;"
                              f"padding:12px;background:transparent;border:none;")
            lay.addWidget(lbl); return
        pw = pg.PlotWidget()
        pw.setBackground(self._BG)
        pw.setMinimumHeight(185)
        pw.showGrid(x=True, y=True, alpha=0.18)
        for ax in ("bottom", "left"):
            pw.getAxis(ax).setTextPen(pg.mkPen(self._LBL2))
            pw.getAxis(ax).setPen(pg.mkPen(self._BORDER))
        pw.setLabel("bottom", "Time (s)",   color=self._LBL2)
        pw.setLabel("left",   "Value (%)",  color=self._LBL2)
        pw.setXRange(0, self._SPAN, padding=0)
        pw.setYRange(-5, 135, padding=0)
        pw.getPlotItem().setMenuEnabled(False)
        pw.getPlotItem().setClipToView(True)
        pw.getPlotItem().setDownsampling(auto=True, mode="peak")
        self._sv_curve = pw.plot([], [],
            pen=pg.mkPen(self._SV_CLR, width=1.8,
                         style=Qt.PenStyle.DashLine), name="SV %")
        self._pv_curve = pw.plot([], [],
            pen=pg.mkPen(self._PV_CLR, width=2.5), name="PV %")
        self._cv_curve = pw.plot([], [],
            pen=pg.mkPen(self._MV_CLR, width=1.8), name="MV %")
        legend = pw.addLegend(offset=(4, 4))
        legend.setLabelTextColor(self._LBL)
        lay.addWidget(pw, 3)
        self._pw = pw

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

        # Vertical crosshair
        self._xhair = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen((200, 200, 200, 55), width=1))
        pw.addItem(self._xhair, ignoreBounds=True)

        # Hover value label
        self._hover_lbl = pg.TextItem(
            anchor=(0, 0), fill=pg.mkBrush(8, 12, 20, 210))
        self._hover_lbl.setVisible(False)
        pw.addItem(self._hover_lbl)

        self._mouse_proxy = pg.SignalProxy(
            pw.scene().sigMouseMoved, rateLimit=60, slot=self._on_hover)

    def _on_hover(self, evt):
        if not HAS_PG or not hasattr(self, '_pw'):
            return
        pos = evt[0]
        if not self._pw.sceneBoundingRect().contains(pos):
            self._hover_lbl.setVisible(False)
            return

        mp = self._pw.plotItem.vb.mapSceneToView(pos)
        t  = mp.x()
        self._xhair.setPos(t)

        ta = list(self._t_data)
        if len(ta) < 2:
            self._hover_lbl.setVisible(False)
            return

        idx = min(range(len(ta)), key=lambda i: abs(ta[i] - t))
        pv  = list(self._pv_data)[idx]
        sv  = list(self._sv_data)[idx]
        mv  = list(self._cv_data)[idx]

        self._hover_lbl.setHtml(
            f'<span style="color:#888888">t = {ta[idx]:.1f} s</span><br/>'
            f'<span style="color:{self._PV_CLR}">PV = {pv:.1f} %</span><br/>'
            f'<span style="color:{self._SV_CLR}">SV = {sv:.1f} %</span><br/>'
            f'<span style="color:{self._MV_CLR}">MV = {mv:.1f} %</span>')

        xr, yr = (self._pw.plotItem.vb.viewRange()[0],
                  self._pw.plotItem.vb.viewRange()[1])
        anchor_x = 1.0 if t > xr[0] + (xr[1] - xr[0]) * 0.6 else 0.0
        try:
            self._hover_lbl.setAnchor((anchor_x, 0))
        except Exception:
            pass
        self._hover_lbl.setPos(t, yr[0] + (yr[1] - yr[0]) * 0.98)
        self._hover_lbl.setVisible(True)

    def _build_live_strip(self, lay: QVBoxLayout):
        """Large PV / SV live values."""
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:{self._CELL};"
                        f"border:1px solid {self._BORDER};border-radius:4px;}}")
        f.setFixedHeight(58)
        h = QHBoxLayout(f); h.setContentsMargins(14, 4, 14, 4); h.setSpacing(0)

        def _big(tag, clr):
            col = QVBoxLayout(); col.setSpacing(0)
            lbl = QLabel(tag)
            lbl.setStyleSheet(f"color:{self._LBL2};font-size:7.5pt;font-weight:600;"
                              f"background:transparent;border:none;"
                              f"font-family:'Microsoft JhengHei','Segoe UI';")
            rw = QHBoxLayout(); rw.setSpacing(2); rw.setContentsMargins(0,0,0,0)
            val = QLabel("0.00")
            val.setStyleSheet(f"color:{clr};font-size:19pt;font-weight:700;"
                              f"background:transparent;border:none;"
                              f"font-family:Consolas,'Courier New';"
                              f"font-variant-numeric:tabular-nums;")
            pct = QLabel("%")
            pct.setStyleSheet(f"color:#606060;font-size:10pt;font-weight:600;"
                              f"background:transparent;border:none;"
                              f"font-family:'Segoe UI';padding-bottom:2px;")
            pct.setAlignment(Qt.AlignmentFlag.AlignBottom)
            rw.addWidget(val); rw.addWidget(pct); rw.addStretch()
            col.addWidget(lbl); col.addLayout(rw)
            return col, val

        pv_lay, self._pv_disp = _big("PV  現在值", self._PV_CLR)
        sv_lay, self._sv_disp = _big("SV  設定值", self._SV_CLR)
        h.addLayout(pv_lay, 1)
        h.addWidget(self._vline())
        h.addSpacing(12)
        h.addLayout(sv_lay, 1)
        lay.addWidget(f)

    def _build_ctrl_row(self, lay: QVBoxLayout):
        """Two-row control frame: (mode + SV + MV + reset) / (action mode + init SV)."""
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:{self._CELL};"
                        f"border:1px solid {self._BORDER};border-radius:4px;}}")
        v = QVBoxLayout(f); v.setContentsMargins(10, 6, 10, 6); v.setSpacing(5)

        # ── Row 1: Mode / SV / MV / Reset ────────────────
        r1 = QHBoxLayout(); r1.setSpacing(8)
        r1.addWidget(self._tag("模式  MODE", self._LBL2, 8))
        self._man_btn  = self._btn("手動  Manual", 80)
        self._auto_btn = self._btn("自動  Auto",   80)
        self._man_btn.clicked.connect(lambda: self._set_mode(True))
        self._auto_btn.clicked.connect(lambda: self._set_mode(False))
        r1.addWidget(self._man_btn); r1.addWidget(self._auto_btn)
        r1.addWidget(self._vline())

        r1.addWidget(self._tag("SV 設定值", self._LBL2, 8))
        self._sv_in = self._inp(f"{self._sv_pct:.1f}", self._SV_CLR, 72, 11)
        self._sv_in.editingFinished.connect(self._sv_changed)
        r1.addWidget(self._sv_in)
        r1.addWidget(self._tag("%", self._LBL2, 8))
        r1.addWidget(self._vline())

        r1.addWidget(self._tag("手動輸出  MV", self._LBL2, 8))
        self._man_cv_in = self._inp(f"{self._cv_manual:.1f}", self._INPUT, 64, 10)
        self._man_cv_in.editingFinished.connect(self._man_cv_changed)
        r1.addWidget(self._man_cv_in)
        r1.addWidget(self._tag("%", self._LBL2, 8))
        r1.addStretch()

        rst = self._btn("⟳ 重置  Reset", 100)
        rst.clicked.connect(self._reset_sim)
        r1.addWidget(rst)
        v.addLayout(r1)

        # ── Row 2: Action Mode / Initial SV ───────────────
        r2 = QHBoxLayout(); r2.setSpacing(8)

        r2.addWidget(self._tag("作用方向  Action", self._LBL2, 8))
        self._act_btn = QPushButton("正向  Direct")
        self._act_btn.setFixedHeight(24); self._act_btn.setFixedWidth(100)
        self._act_btn.clicked.connect(self._toggle_action)
        r2.addWidget(self._act_btn)
        r2.addWidget(self._vline())

        r2.addWidget(self._tag("初始設定值  Init SV", self._LBL2, 8))
        self._sv_init_in = self._inp(f"{self._sv_init:.1f}", self._INPUT, 72, 10)
        self._sv_init_in.editingFinished.connect(self._sv_init_changed)
        r2.addWidget(self._sv_init_in)
        r2.addWidget(self._tag("%  (reset → SV)", self._LBL2, 8))
        r2.addStretch()

        v.addLayout(r2)
        lay.addWidget(f)
        self._refresh_mode_btns()
        self._refresh_action_btn()

    def _build_mv_limit_row(self, lay: QVBoxLayout):
        """MV current value (large) + PV/MV MAX/MIN limit inputs."""
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:{self._CELL};"
                        f"border:1px solid {self._BORDER};border-radius:4px;}}")
        h = QHBoxLayout(f); h.setContentsMargins(14, 5, 14, 5); h.setSpacing(14)

        # Left: MV large readout
        mv_col = QVBoxLayout(); mv_col.setSpacing(0)
        self._mv_mode_lbl = QLabel("MV  現在值 (自動)")
        self._mv_mode_lbl.setStyleSheet(
            f"color:{self._LBL2};font-size:7.5pt;font-weight:600;"
            f"background:transparent;border:none;"
            f"font-family:'Microsoft JhengHei','Segoe UI';")
        mv_rw = QHBoxLayout(); mv_rw.setSpacing(2); mv_rw.setContentsMargins(0,0,0,0)
        self._mv_disp = QLabel("0.0")
        self._mv_disp.setStyleSheet(
            f"color:{self._RESULT};font-size:19pt;font-weight:700;"
            f"background:transparent;border:none;"
            f"font-family:Consolas,'Courier New';"
            f"font-variant-numeric:tabular-nums;")
        mv_pct = QLabel("%")
        mv_pct.setStyleSheet(f"color:#606060;font-size:10pt;font-weight:600;"
                             f"background:transparent;border:none;"
                             f"font-family:'Segoe UI';padding-bottom:2px;")
        mv_pct.setAlignment(Qt.AlignmentFlag.AlignBottom)
        mv_rw.addWidget(self._mv_disp); mv_rw.addWidget(mv_pct); mv_rw.addStretch()
        mv_col.addWidget(self._mv_mode_lbl); mv_col.addLayout(mv_rw)
        h.addLayout(mv_col, 1)

        # Centre: timer + peak
        info_col = QVBoxLayout(); info_col.setSpacing(2)
        self._t_disp = QLabel("t = 00:00")
        self._t_disp.setStyleSheet(
            f"color:{self._LBL2};font-size:8pt;font-weight:600;"
            f"background:transparent;border:none;"
            f"font-family:Consolas,'Courier New';")
        self._peak_disp = QLabel("peak  —")
        self._peak_disp.setStyleSheet(
            f"color:{self._ACC};font-size:8pt;font-weight:700;"
            f"background:transparent;border:none;"
            f"font-family:Consolas,'Courier New';")
        info_col.addWidget(self._t_disp)
        info_col.addWidget(self._peak_disp)
        h.addLayout(info_col)

        h.addWidget(self._vline())

        # Right: PV/MV limit grid (2×2)
        grid = QGridLayout(); grid.setSpacing(4); grid.setContentsMargins(0,0,0,0)

        def _badge(text: str, clr: str) -> QLabel:
            l = QLabel(text); l.setFixedSize(24, 16)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet(f"color:#000;background:{clr};font-size:6.5pt;"
                            f"font-weight:700;border-radius:2px;"
                            f"font-family:'Segoe UI';"); return l

        def _ll(txt: str) -> QLabel:
            l = QLabel(txt)
            l.setStyleSheet(f"color:{self._LBL2};font-size:7.5pt;font-weight:600;"
                            f"background:transparent;border:none;"
                            f"font-family:'Microsoft JhengHei','Segoe UI';"); return l

        def _pct_l() -> QLabel:
            l = QLabel("%")
            l.setStyleSheet(f"color:{self._LBL2};font-size:8pt;"
                            f"background:transparent;border:none;"); return l

        def _lim(val: float, attr: str) -> QLineEdit:
            e = self._inp(f"{val:.0f}", self._INPUT, 50, 9); e.setFixedHeight(20)
            def _c(a=attr, ie=e):
                try: v = max(0.0, min(200.0, float(ie.text())))
                except ValueError: v = getattr(self, f"_{a}")
                setattr(self, f"_{a}", v); ie.setText(f"{v:.0f}")
            e.editingFinished.connect(_c); return e

        # Row 0: PV MAX | MV MAX
        grid.addWidget(_badge("PV", self._PV_CLR),       0, 0)
        grid.addWidget(_ll("最大值  MAX"),                0, 1)
        self._pv_max_in = _lim(self._pv_max, "pv_max")
        grid.addWidget(self._pv_max_in,                   0, 2)
        grid.addWidget(_pct_l(),                          0, 3)
        grid.addWidget(_badge("MV", self._MV_CLR),       0, 4)
        grid.addWidget(_ll("最大值  MAX"),                0, 5)
        self._mv_max_in = _lim(self._mv_max, "mv_max")
        grid.addWidget(self._mv_max_in,                   0, 6)
        grid.addWidget(_pct_l(),                          0, 7)

        # Row 1: PV MIN | MV MIN
        grid.addWidget(_badge("PV", self._PV_CLR),       1, 0)
        grid.addWidget(_ll("最小值  MIN"),                1, 1)
        self._pv_min_in = _lim(self._pv_min, "pv_min")
        grid.addWidget(self._pv_min_in,                   1, 2)
        grid.addWidget(_pct_l(),                          1, 3)
        grid.addWidget(_badge("MV", self._MV_CLR),       1, 4)
        grid.addWidget(_ll("最小值  MIN"),                1, 5)
        self._mv_min_in = _lim(self._mv_min, "mv_min")
        grid.addWidget(self._mv_min_in,                   1, 6)
        grid.addWidget(_pct_l(),                          1, 7)

        h.addLayout(grid)
        lay.addWidget(f)

    def _build_param_cols(self, lay: QVBoxLayout):
        """PID | FOPDT two-column frames, each with params on left + formula panel on right."""
        lay.addWidget(self._sec_hdr("≡  主要參數  Controller & Process Parameters"))
        cols = QHBoxLayout(); cols.setSpacing(10)

        # ── Shared formula text styles ────────────────────
        _eq  = (f"color:#00E5A0;font-size:9pt;font-weight:700;"
                f"background:transparent;border:none;"
                f"font-family:Consolas,'Courier New';")
        _sep = (f"color:#2A4A3A;font-size:7pt;"
                f"background:transparent;border:none;"
                f"font-family:Consolas,'Courier New';")
        _ann = (f"color:#80C8A8;font-size:8.5pt;font-weight:600;"
                f"background:transparent;border:none;"
                f"font-family:'Microsoft JhengHei','Segoe UI';")

        def _div():
            d = QFrame(); d.setFrameShape(QFrame.Shape.VLine)
            d.setStyleSheet("QFrame{border:none;border-left:1px solid #242424;"
                            "background:transparent;}"); return d

        def _framed_col(hdr_text: str, formula_block: list) -> tuple:
            fr = QFrame()
            fr.setStyleSheet(f"QFrame{{background:{self._CELL};"
                             f"border:1px solid {self._ACC};border-radius:4px;}}")
            outer = QHBoxLayout(fr)
            outer.setContentsMargins(8, 6, 8, 6); outer.setSpacing(8)

            # Left: header + param rows
            lv = QVBoxLayout(); lv.setSpacing(3); lv.setContentsMargins(0, 0, 0, 0)
            hl = QLabel(hdr_text)
            hl.setStyleSheet(f"color:{self._ACC};font-size:8.5pt;font-weight:700;"
                             f"background:transparent;border:none;padding-bottom:3px;"
                             f"font-family:'Microsoft JhengHei','Segoe UI';")
            lv.addWidget(hl)
            outer.addLayout(lv, 0)

            outer.addWidget(_div())

            # Right: formula annotation panel
            rv = QVBoxLayout(); rv.setSpacing(1); rv.setContentsMargins(4, 0, 4, 0)
            for text, style in formula_block:
                fl = QLabel(text)
                fl.setStyleSheet(style)
                fl.setWordWrap(True)
                rv.addWidget(fl)
            rv.addStretch()
            outer.addLayout(rv, 1)

            return fr, lv

        pid_formula = [
            ("PID 控制核心  Control Core",                              _eq),
            ("────────────────────────────────────────",               _sep),
            ("比對 SV 與 PV 誤差，計算 MV 輸出以消除誤差",             _ann),
            ("P (比例)  ─  依據當前誤差即時反應",                      _ann),
            ("I (積分)  ─  累積誤差，消除穩態誤差",                    _ann),
            ("D (微分)  ─  預測誤差趨勢，抑制劇烈變動",               _ann),
            ("─  MV = Kp·[e + (1/Ti)·∫e dt + Td·de/dt]",            _sep),
        ]
        fopdt_formula = [
            ("FOPDT 物理模型  Process Model",                           _eq),
            ("────────────────────────────────────────",               _sep),
            ("簡化工業動態：一階延遲 + 純滯後數學模型",                _ann),
            ("K  (增益)    ─  MV 變化量造成的 PV 改變幅度",            _ann),
            ("τ  (時間常數) ─  達最終值 63.2% 所需時間",              _ann),
            ("L  (延遲)    ─  MV 改變到 PV 開始反應的時間",            _ann),
            ("─  PV = PV₀ + K·ΔMV·(1 − e^(−(t−L)/τ))",             _sep),
        ]

        pid_fr, pid_col = _framed_col("動態視覺  PID", pid_formula)
        for attr, label, lo, hi, dec in self._PID_SPECS:
            le = self._param_row(pid_col, attr, label, lo, hi, dec, "")
            self._pid_inputs[attr] = le

        fopdt_fr, fopdt_col = _framed_col("物理模型  FOPDT", fopdt_formula)
        for attr, label, lo, hi, dec, unit in self._FOPDT_SPECS:
            self._param_row(fopdt_col, attr, label, lo, hi, dec, unit)

        cols.addWidget(pid_fr, 1); cols.addWidget(fopdt_fr, 1)
        lay.addLayout(cols)

    def _build_zn_section(self, lay: QVBoxLayout):
        lay.addWidget(self._sec_hdr(
            "Z-N  一鍵算  Ziegler-Nichols  (最終換算法)"))

        box = QVBoxLayout(); box.setSpacing(5); box.setContentsMargins(2, 2, 2, 2)

        # ── Method + Ku/Pu row ────────────────────────────
        top = QHBoxLayout(); top.setSpacing(8)
        self._method_box = QComboBox()
        self._method_box.addItems([
            "Ziegler-Nichols (Z-N)  經典模式",
            "Tyreus-Luyben  (T-L)   穩健模式",
        ])
        self._method_box.setFixedHeight(24)
        self._method_box.setStyleSheet(
            f"QComboBox{{background:{self._INP_BG};color:{self._LBL};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:8.5pt;font-weight:700;padding:1px 6px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';}}"
            f"QComboBox:focus{{border:1px solid {self._ACC};}}"
            f"QComboBox::drop-down{{border:none;width:14px;}}"
            f"QComboBox QAbstractItemView{{"
            f"background:{self._CELL};color:{self._LBL};"
            f"border:1px solid {self._BORDER};"
            f"selection-background-color:{self._ACC};"
            f"selection-color:#fff;font-size:8.5pt;}}")
        self._method_box.currentIndexChanged.connect(self._on_method_changed)
        top.addWidget(self._method_box)
        top.addWidget(self._vline())

        top.addWidget(self._tag("Ku", self._LBL2, 8))
        self._ku_in = self._inp("2.000", self._INPUT, 72, 9); self._ku_in.setFixedHeight(24)
        top.addWidget(self._ku_in)
        top.addWidget(self._tag("Pu", self._LBL2, 8))
        self._pu_in = self._inp("10.00", self._INPUT, 72, 9); self._pu_in.setFixedHeight(24)
        top.addWidget(self._pu_in)
        top.addWidget(self._tag("s", self._LBL2, 8))

        calc = self._btn("一鍵換算  Calculate", 130)
        calc.setStyleSheet(
            f"QPushButton{{background:#1A2A0A;color:{self._OK};"
            f"border:1px solid #3A5A1A;border-radius:3px;"
            f"font-size:9pt;font-weight:700;padding:0 8px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';}}"
            f"QPushButton:hover{{background:#243A10;color:#fff;}}")
        calc.clicked.connect(self._zn_calculate)
        top.addWidget(calc); top.addStretch()
        box.addLayout(top)

        # ── Auto-capture + warning ────────────────────────
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
            f"background:transparent;border:none;"
            f"font-family:'Microsoft JhengHei','Segoe UI';")
        self._warn_lbl.setWordWrap(True)
        ac_row.addWidget(auto_btn); ac_row.addWidget(self._warn_lbl, 1)
        box.addLayout(ac_row)

        # ── Z-N vs T-L comparison strip ───────────────────
        prin = QLabel(
            "① 超調量與穩定性  Overshoot & Stability    "
            "Z-N: 增益大，響應快，易超調，震盪多 ─── "
            "T-L: 係數修正，響應保守，平穩趨近 SV，適合空調 / 精密溫壓製程        "
            "② 抗干擾能力  Disturbance Rejection    "
            "Z-N: 初期反應劇烈，適合頻繁負荷變化 ─── "
            "T-L: 阻尼效果佳，抑制雜訊，避免閥體劇烈抖動，延長機械壽命")
        prin.setStyleSheet(
            f"color:#00D890;font-size:8.5pt;font-weight:700;"
            f"background:#0D1A12;"
            f"border:1px solid #1A4A2A;border-radius:3px;"
            f"padding:5px 12px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';")
        prin.setWordWrap(True)
        box.addWidget(prin)

        # ── Results table ─────────────────────────────────
        tbl = QFrame()
        tbl.setStyleSheet(f"QFrame{{background:#0D0D0D;"
                          f"border:1px solid {self._BORDER};border-radius:4px;}}")
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
                f"border-bottom:1px solid #252525;padding:3px 8px;"
                f"background:transparent;")

        for ci, hdr in enumerate(["模式  Mode", "Kp", "Ki", "Kd", "套用  Apply"]):
            hl = QLabel(hdr); hl.setFixedHeight(22)
            hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hl.setStyleSheet(_hss); tg.addWidget(hl, 0, ci)
        tg.setColumnStretch(0, 1); tg.setColumnStretch(1, 1)
        tg.setColumnStretch(2, 1); tg.setColumnStretch(3, 1)

        self._zn_cells: dict = {}
        for ri, mode in enumerate(["P", "PI", "PID"], 1):
            ml = QLabel(mode); ml.setFixedHeight(26)
            ml.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ml.setStyleSheet(_mss); tg.addWidget(ml, ri, 0)
            cells = []
            for ci in range(1, 4):
                cl = QLabel("—"); cl.setFixedHeight(26)
                cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cl.setStyleSheet(_css); tg.addWidget(cl, ri, ci)
                cells.append(cl)
            self._zn_cells[mode] = cells
            ab = self._btn("套用", 58); ab.setFixedHeight(22)
            ab.clicked.connect(lambda _=False, m=mode: self._zn_apply(m))
            tg.addWidget(ab, ri, 4, Qt.AlignmentFlag.AlignCenter)

        # Formula hint
        self._formula_lbl = QLabel("")
        self._formula_lbl.setStyleSheet(
            f"color:#505050;font-size:7.5pt;padding:2px 6px;"
            f"font-family:Consolas,'Courier New';background:transparent;border:none;")
        self._formula_lbl.setWordWrap(True)

        box.addWidget(tbl)
        box.addWidget(self._formula_lbl)
        lay.addLayout(box)
        self._refresh_formula_lbl()

    @staticmethod
    def _draw_ys_logo(size: int = 30) -> QPixmap:
        """Load YS logo from file, or draw it programmatically as fallback."""
        import math, os as _os
        _LOGO = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "logo_ys.png")
        for _p in (_LOGO,):
            if _os.path.exists(_p):
                src = QPixmap(_p)
                if not src.isNull():
                    return src.scaled(size, size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
        # ── Fallback: draw ────────────────────────────
        pix = QPixmap(size, size)
        pix.fill(QColor(0, 0, 0, 0))  # transparent
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = cy = size / 2.0
        r_outer = cx - 1.0

        # ── Outer circle fill (dark navy) ─────────────────
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#1C2B4A"))
        p.drawEllipse(1, 1, size - 2, size - 2)

        # ── Wrench-stub marks around the ring (8 pairs) ───
        n = 8
        r_mark  = r_outer - 2.5
        mark_sz = max(2, size // 14)
        p.setBrush(QColor("#8FA8C8"))
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            angle = math.radians(i * 360.0 / n - 90)
            mx = cx + r_mark * math.cos(angle)
            my = cy + r_mark * math.sin(angle)
            # outer dot
            p.drawEllipse(int(mx - mark_sz / 2), int(my - mark_sz / 2),
                          mark_sz, mark_sz)
            # inner dot (smaller, lighter)
            r2 = r_mark - mark_sz - 1
            mx2 = cx + r2 * math.cos(angle)
            my2 = cy + r2 * math.sin(angle)
            p.setBrush(QColor("#4A6A8A"))
            p.drawEllipse(int(mx2 - mark_sz / 2), int(my2 - mark_sz / 2),
                          mark_sz - 1, mark_sz - 1)
            p.setBrush(QColor("#8FA8C8"))

        # ── Inner white circle ─────────────────────────────
        r_inner = r_outer * 0.60
        p.setBrush(QColor("#E8EEF5"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx - r_inner), int(cy - r_inner),
                      int(r_inner * 2), int(r_inner * 2))

        # ── "YS." text ────────────────────────────────────
        fsize = max(5, int(size * 0.28))
        font = QFont("Segoe UI", fsize, QFont.Weight.Black)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -0.5)
        p.setFont(font)
        p.setPen(QColor("#1C2B4A"))
        p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "YS.")

        p.end()
        return pix

    def _build_status_bar(self, lay: QVBoxLayout):
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:#0A1020;"
                        f"border:1px solid #1C2B4A;border-radius:4px;}}")
        f.setFixedHeight(38)
        h = QHBoxLayout(f); h.setContentsMargins(10, 4, 10, 4); h.setSpacing(8)

        # ── YS Logo (static) ──────────────────────────────
        logo_lbl = QLabel()
        logo_lbl.setFixedSize(30, 30)
        logo_lbl.setPixmap(self._draw_ys_logo(30))
        logo_lbl.setStyleSheet("background:transparent;border:none;")

        # ── Company + tool info ───────────────────────────
        name_lbl = QLabel("亞聖國際科技有限公司")
        name_lbl.setStyleSheet(
            f"color:#8FA8C8;font-size:8pt;font-weight:700;"
            f"background:transparent;border:none;"
            f"font-family:'Microsoft JhengHei','Segoe UI';")

        div = QLabel("│")
        div.setStyleSheet("color:#2A3A5A;background:transparent;border:none;")

        msg = QLabel(
            "PID Tuner Station 2.0  │  Stable Mode  "
            "───  Automation controls and timeline scrubbing updated!")
        msg.setStyleSheet(
            f"color:{self._ACC};font-size:8.5pt;font-weight:600;"
            f"background:transparent;border:none;"
            f"font-family:'Microsoft JhengHei','Segoe UI';")

        h.addWidget(logo_lbl)
        h.addWidget(name_lbl)
        h.addWidget(div)
        h.addWidget(msg)
        h.addStretch()
        lay.addWidget(f)

    def _build_timeline_slider(self, lay: QVBoxLayout):
        """Horizontal timeline scrubber linked to plot X-axis."""
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:#151515;"
                        f"border:1px solid {self._BORDER};border-radius:3px;}}")
        f.setFixedHeight(28)
        h = QHBoxLayout(f); h.setContentsMargins(8, 4, 8, 4); h.setSpacing(6)

        h.addWidget(self._tag("進度桿", self._LBL2, 7))

        self._timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self._timeline_slider.setRange(0, int(self._SPAN))
        self._timeline_slider.setValue(0)
        self._timeline_slider.setStyleSheet(
            "QSlider::groove:horizontal{"
            "background:#252525;height:4px;border-radius:2px;}"
            "QSlider::handle:horizontal{"
            f"background:{self._ACC};width:10px;height:10px;"
            "border-radius:5px;margin:-3px 0;}"
            "QSlider::sub-page:horizontal{"
            f"background:#7A3A00;border-radius:2px;}}")
        self._timeline_slider.sliderPressed.connect(self._slider_pressed)
        self._timeline_slider.sliderReleased.connect(self._slider_released)
        self._timeline_slider.valueChanged.connect(self._slider_moved)
        h.addWidget(self._timeline_slider, 1)

        self._follow_btn = QPushButton("⏩ 追蹤")
        self._follow_btn.setFixedHeight(20); self._follow_btn.setFixedWidth(62)
        self._follow_btn.setStyleSheet(
            f"QPushButton{{background:{self._CELL};color:{self._LBL2};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:7.5pt;font-weight:700;padding:0 4px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';}}"
            f"QPushButton:hover{{background:#2A2A2A;color:{self._LBL};}}")
        self._follow_btn.clicked.connect(self._slider_resume_follow)
        h.addWidget(self._follow_btn)

        lay.addWidget(f)

    # ════════════════════════════════════════════════════
    #  SHARED WIDGET FACTORIES
    # ════════════════════════════════════════════════════
    def _sec_hdr(self, text: str) -> QLabel:
        l = QLabel(f"  {text}"); l.setFixedHeight(21)
        l.setStyleSheet(
            f"color:{self._ACC};font-size:8.5pt;font-weight:700;"
            f"background:#1A1A1A;"
            f"border-top:1px solid {self._ACC};"
            f"border-left:3px solid {self._ACC};"
            f"border-bottom:none;border-right:none;padding-left:6px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';"); return l

    def _tag(self, text: str, color: str = None, size: int = 9,
             bold: bool = False) -> QLabel:
        c = color or self._LBL; w = "700" if bold else "600"
        l = QLabel(text)
        l.setStyleSheet(f"color:{c};font-size:{size}pt;font-weight:{w};"
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
            f"QLineEdit:focus{{border:1px solid {self._ACC};}}"); return e

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

    def _param_row(self, lay: QVBoxLayout,
                   attr: str, label: str, lo: float, hi: float,
                   dec: int, unit: str) -> QLineEdit:
        row = QHBoxLayout(); row.setSpacing(4)
        lb = QLabel(label); lb.setFixedWidth(130)
        lb.setStyleSheet(f"color:{self._LBL};font-size:8.5pt;font-weight:600;"
                         f"font-family:'Microsoft JhengHei','Segoe UI';"
                         f"background:transparent;border:none;")
        le = QLineEdit(f"{getattr(self, '_' + attr):.{dec}f}")
        le.setFixedWidth(80); le.setFixedHeight(22)
        le.setAlignment(Qt.AlignmentFlag.AlignRight)
        le.setStyleSheet(
            f"QLineEdit{{background:{self._INP_BG};color:{self._INPUT};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:9.5pt;font-weight:700;"
            f"font-family:Consolas,'Courier New';padding:1px 5px;}}"
            f"QLineEdit:focus{{border:1px solid {self._ACC};}}")
        ul = QLabel(unit or ""); ul.setFixedWidth(14)
        ul.setStyleSheet(f"color:{self._LBL2};font-size:8pt;"
                         f"background:transparent;border:none;")
        rl = QLabel(f"[{lo:.3g}–{hi:.4g}]")
        rl.setStyleSheet(f"color:#505050;font-size:7.5pt;"
                         f"background:transparent;border:none;")

        def _commit(a=attr, l=lo, h=hi, d=dec, e=le):
            try: v = float(e.text())
            except ValueError: v = getattr(self, f"_{a}")
            v = max(l, min(h, v)); e.setText(f"{v:.{d}f}")
            old = getattr(self, f"_{a}"); setattr(self, f"_{a}", v)
            if a == "pL" and abs(v - old) > 1e-9:
                self._rebuild_dead_buf()

        le.editingFinished.connect(_commit)
        row.addWidget(lb); row.addWidget(le); row.addWidget(ul); row.addWidget(rl)
        row.addStretch()
        lay.addLayout(row); return le

    # ════════════════════════════════════════════════════
    #  MODE / INPUT HANDLERS
    # ════════════════════════════════════════════════════
    def _toggle_action(self):
        self._reverse_action = not self._reverse_action
        self._integral = 0.0          # clear windup when direction flips
        self._prev_err = 0.0
        self._refresh_action_btn()

    def _refresh_action_btn(self):
        if self._reverse_action:
            self._act_btn.setText("反向  Reverse")
            self._act_btn.setStyleSheet(
                f"QPushButton{{background:#2A0A3A;color:#CC88FF;"
                f"border:1px solid #5A2A7A;border-radius:3px;"
                f"font-size:8.5pt;font-weight:700;"
                f"font-family:'Microsoft JhengHei','Segoe UI';}}"
                f"QPushButton:hover{{background:#3A1A4A;color:#fff;}}")
        else:
            self._act_btn.setText("正向  Direct")
            self._act_btn.setStyleSheet(
                f"QPushButton{{background:#0A2A1A;color:{self._OK};"
                f"border:1px solid #2A6A3A;border-radius:3px;"
                f"font-size:8.5pt;font-weight:700;"
                f"font-family:'Microsoft JhengHei','Segoe UI';}}"
                f"QPushButton:hover{{background:#1A3A2A;color:#fff;}}")

    def _sv_init_changed(self):
        try:
            v = max(0.0, min(200.0, float(self._sv_init_in.text())))
        except ValueError:
            v = self._sv_init
        self._sv_init = v
        self._sv_init_in.setText(f"{v:.1f}")

    def _set_mode(self, manual: bool):
        self._manual_mode = manual
        self._mv_mode_lbl.setText(
            "MV  現在值 (手動)" if manual else "MV  現在值 (自動)")
        self._refresh_mode_btns()
        self._refresh_hmi_mode_btns()

    def _refresh_mode_btns(self):
        _on = (f"QPushButton{{background:{self._ACC};color:#000;"
               f"border:none;border-radius:3px;"
               f"font-size:8.5pt;font-weight:700;"
               f"font-family:'Microsoft JhengHei','Segoe UI';}}")
        _off = (f"QPushButton{{background:{self._CELL};color:{self._LBL2};"
                f"border:1px solid {self._BORDER};border-radius:3px;"
                f"font-size:8.5pt;font-weight:600;"
                f"font-family:'Microsoft JhengHei','Segoe UI';}}"
                f"QPushButton:hover{{background:#2A2A2A;color:{self._LBL};}}")
        self._man_btn.setStyleSheet(_on  if self._manual_mode else _off)
        self._auto_btn.setStyleSheet(_off if self._manual_mode else _on)

    def _sv_changed(self):
        try:
            v = max(0.0, min(200.0, float(self._sv_in.text())))
        except ValueError:
            v = self._sv_pct
        self._sv_pct = v          # step: immediate, no ramp
        self._sv_in.setText(f"{v:.1f}")

    def _man_cv_changed(self):
        try:
            v = max(0.0, min(100.0, float(self._man_cv_in.text())))
        except ValueError:
            v = self._cv_manual
        self._cv_manual = v
        self._man_cv_in.setText(f"{v:.1f}")

    # ════════════════════════════════════════════════════
    #  Z-N / T-L WIZARD
    # ════════════════════════════════════════════════════
    def _zn_calculate(self):
        try:
            Ku = float(self._ku_in.text())
            Pu = float(self._pu_in.text())
        except ValueError: return
        if Ku <= 0 or Pu <= 0:
            self._warn_lbl.setText("⚠ Ku 和 Pu 必須大於 0  (must be > 0)"); return
        self._warn_lbl.setText("")

        tl = self._method_box.currentIndex() == 1
        if tl:
            # Tyreus-Luyben
            kp_b = Ku / 2.2
            results = {
                "P":   (kp_b, 0.0,                  0.0),
                "PI":  (kp_b, kp_b / (2.2 * Pu),    0.0),
                "PID": (kp_b, kp_b / (2.2 * Pu),    kp_b * (Pu / 6.3)),
            }
        else:
            # Ziegler-Nichols
            results = {
                "P":   (0.50 * Ku, 0.0,                         0.0),
                "PI":  (0.45 * Ku, 0.45 * Ku / (Pu / 1.2),     0.0),
                "PID": (0.60 * Ku, 0.60 * Ku / (Pu / 2.0),     0.60 * Ku * (Pu / 8.0)),
            }
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
        self._Kp = max(0.0, min(100.0, kp))
        self._Ki = max(0.0, min(50.0,  ki))
        self._Kd = max(0.0, min(20.0,  kd))
        for attr, val, dec in [("Kp", self._Kp, 3),
                                ("Ki", self._Ki, 4),
                                ("Kd", self._Kd, 4)]:
            if attr in self._pid_inputs:
                self._pid_inputs[attr].setText(f"{val:.{dec}f}")
        self._reset_sim()

    def _refresh_formula_lbl(self):
        tl = self._method_box.currentIndex() == 1
        if tl:
            txt = ("T-L：P → Kp=Ku/2.2"
                   "  │  PI → Ti=2.2·Pu, Ki=Kp/Ti"
                   "  │  PID → Td=Pu/6.3, Kd=Kp·Td")
        else:
            txt = ("Z-N：P → Kp=0.50·Ku"
                   "  │  PI → Kp=0.45·Ku, Ti=Pu/1.2, Ki=Kp/Ti"
                   "  │  PID → Kp=0.60·Ku, Ti=Pu/2, Td=Pu/8, Ki=Kp/Ti, Kd=Kp·Td")
        self._formula_lbl.setText(txt)

    def _on_method_changed(self):
        self._refresh_formula_lbl()
        if self._zn_results:
            self._zn_calculate()

    # ════════════════════════════════════════════════════
    #  TIMELINE SLIDER HANDLERS
    # ════════════════════════════════════════════════════
    def _slider_pressed(self):
        self._slider_dragging  = True
        self._slider_following = False

    def _slider_released(self):
        self._slider_dragging = False

    def _slider_resume_follow(self):
        self._slider_following = True
        if HAS_PG:
            x_hi = max(self._SPAN, self._t_now)
            x_lo = x_hi - self._SPAN
            self._pw.setXRange(x_lo, x_hi, padding=0)

    def _slider_moved(self, val: int):
        if self._slider_dragging and HAS_PG:
            lo = float(val)
            hi = lo + self._SPAN
            self._pw.setXRange(lo, hi, padding=0)

    # ════════════════════════════════════════════════════
    #  AUTO PEAK CAPTURE
    # ════════════════════════════════════════════════════
    def _auto_capture(self):
        N = min(1200, len(self._pv_data))
        if N < 200:
            self._warn_lbl.setText("資料不足 — 等待 PV 震盪建立後再擷取。"); return
        seg   = list(self._pv_data)[-N:]
        t_seg = list(self._t_data)[-N:]
        sm = list(seg)
        for i in range(1, N - 1):
            sm[i] = (seg[i-1] + 2*seg[i] + seg[i+1]) / 4.0
        min_sep, min_prom = 60, 1.0
        peaks: list = []; last = -min_sep; i = 1
        while i < N - 1:
            if sm[i] > sm[i-1] and sm[i] > sm[i+1] and i - last >= min_sep:
                lo = max(0, i - min_sep); hi = min(N, i + min_sep + 1)
                if sm[i] - min(sm[lo:hi]) >= min_prom:
                    peaks.append(i); last = i
            i += 1
        if len(peaks) < 3:
            self._warn_lbl.setText("峰值不足 — 請增加 Kp 直到等幅震盪。"); return
        rec  = peaks[-4:]; amps = [sm[j] for j in rec]
        mean = sum(amps) / len(amps)
        std  = (sum((a - mean)**2 for a in amps) / len(amps))**0.5
        if std / (abs(mean) + 1e-6) > 0.25:
            self._warn_lbl.setText("波型不穩定 — 重新調整 Kp 後再試。"); return
        periods = [t_seg[rec[j+1]] - t_seg[rec[j]] for j in range(len(rec)-1)]
        Pu = sum(periods) / len(periods)
        if Pu < 0.3:
            self._warn_lbl.setText("週期過短 — 確認模型參數。"); return
        Ku = self._Kp
        self._ku_in.setText(f"{Ku:.3f}"); self._pu_in.setText(f"{Pu:.2f}")
        self._warn_lbl.setStyleSheet(
            f"color:{self._OK};font-size:8.5pt;font-weight:600;"
            f"background:transparent;border:none;"
            f"font-family:'Microsoft JhengHei','Segoe UI';")
        self._warn_lbl.setText(f"✓  Ku={Ku:.3f}  Pu={Pu:.2f}s  → 點擊「一鍵換算」")
        self._zn_calculate()
        # Rescale X so captured segment fills first 1/3 of viewport
        if HAS_PG:
            cap_dur = N * self._DT
            x_lo = max(0.0, self._t_now - cap_dur)
            x_hi = x_lo + cap_dur * 3.0
            self._pw.setXRange(x_lo, x_hi, padding=0)
            self._slider_following = False
            self._timeline_slider.blockSignals(True)
            self._timeline_slider.setRange(0, int(max(self._SPAN, x_hi)))
            self._timeline_slider.setValue(int(x_lo))
            self._timeline_slider.blockSignals(False)

    # ════════════════════════════════════════════════════
    #  SIMULATION
    # ════════════════════════════════════════════════════
    def _rebuild_dead_buf(self):
        n = max(1, round(self._pL / self._DT))
        self._dead_buf = deque([self._last_cv] * n, maxlen=n)

    def _reset_sim(self):
        """
        Soft reset — clears trend history, PV starts at Init SV value.
        Preserves: live SV, Init SV, Manual MV, mode, action direction,
                   Kp/Ki/Kd, K/τ/L, Z-N table values, limits.
        Dead buffer pre-filled with steady-state MV so PV holds its
        starting level (no immediate drift toward zero).
        """
        if not hasattr(self, "_sim_timer"): return
        self._sim_timer.stop()
        n = max(1, round(self._pL / self._DT))

        # ── PV starts at Init SV baseline (normalised 0-1) ──
        pv_init_n = self._sv_init / 100.0
        mv_lo = self._mv_min / 100.0
        mv_hi = self._mv_max / 100.0

        # ── MV pre-fill: mode-aware ───────────────────────
        if self._manual_mode:
            # Manual: pre-load the dead buffer with the current
            # manual output so PV holds its level under open loop.
            mv_init_n = max(mv_lo, min(mv_hi, self._cv_manual / 100.0))
        else:
            # Auto: use the algebraic SS MV that sustains PV at
            # Init SV level (MV_ss = PV_ss / K). This gives the
            # controller zero initial error when SV == Init SV.
            mv_init_n = pv_init_n / max(self._pK, 1e-6)
            mv_init_n = max(mv_lo, min(mv_hi, mv_init_n))

        self._pv_n     = pv_init_n
        self._integral = 0.0
        self._prev_err = 0.0
        self._last_cv  = mv_init_n
        self._dead_buf = deque([mv_init_n] * n, maxlen=n)
        self._t_data.clear(); self._pv_data.clear()
        self._sv_data.clear(); self._cv_data.clear()
        self._t_now   = 0.0
        self._step    = 0
        self._peak_pv = 0.0
        if HAS_PG:
            self._sv_curve.setData([], [])
            self._pv_curve.setData([], [])
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

        # SV is a pure step — use directly, no ramp
        sp_n   = self._sv_pct  / 100.0
        mv_lo  = self._mv_min  / 100.0
        mv_hi  = self._mv_max  / 100.0

        # ── Controller ────────────────────────────────
        if self._manual_mode:
            cv_n = max(mv_lo, min(mv_hi, self._cv_manual / 100.0))
        else:
            # Direct 正向: err = SP - PV  |  Reverse 反向: err = PV - SP
            err = (self._pv_n - sp_n) if self._reverse_action else (sp_n - self._pv_n)
            self._integral = max(-20.0, min(20.0,
                                 self._integral + err * dt))
            deriv          = (err - self._prev_err) / dt
            cv_raw         = (self._Kp * err
                              + self._Ki * self._integral
                              + self._Kd * deriv)
            cv_n = max(mv_lo, min(mv_hi, cv_raw))
            self._prev_err = err

        # ── FOPDT: PV_new = α·K·MV_delayed + (1-α)·PV_old ──
        delayed_cv = self._dead_buf[0]; self._dead_buf.append(cv_n)
        alpha  = dt / (self._pT + dt)
        pv_raw = alpha * self._pK * delayed_cv + (1.0 - alpha) * self._pv_n

        # ── PV limits ─────────────────────────────────
        pv_lo      = self._pv_min / 100.0
        pv_hi      = self._pv_max / 100.0
        self._pv_n = max(pv_lo, min(pv_hi, pv_raw))

        if self._pv_n > self._peak_pv: self._peak_pv = self._pv_n
        self._last_cv = cv_n

        self._t_data.append(self._t_now)
        self._pv_data.append(self._pv_n  * 100.0)
        self._sv_data.append(self._sv_pct)
        self._cv_data.append(cv_n         * 100.0)
        self._t_now += dt; self._step += 1

        # ── Plot refresh (5 Hz) ───────────────────────
        if self._step % 4 == 0 and HAS_PG:
            ta   = list(self._t_data)
            x_hi = max(self._SPAN, self._t_now)
            x_lo = x_hi - self._SPAN
            if self._slider_following:
                self._pw.setXRange(x_lo, x_hi, padding=0)
                # Sync slider without triggering _slider_moved
                self._timeline_slider.blockSignals(True)
                self._timeline_slider.setRange(0, int(x_hi))
                self._timeline_slider.setValue(int(max(0.0, x_lo)))
                self._timeline_slider.blockSignals(False)
            self._sv_curve.setData(ta, list(self._sv_data))
            self._pv_curve.setData(ta, list(self._pv_data))
            self._cv_curve.setData(ta, list(self._cv_data))

        # ── Live strip (2 Hz) ─────────────────────────
        if self._step % 10 == 0:
            pv_pct = self._pv_n  * 100.0
            cv_pct = self._last_cv * 100.0
            self._pv_disp.setText(f"{pv_pct:6.2f}")
            self._sv_disp.setText(f"{self._sv_pct:6.1f}")
            self._mv_disp.setText(f"{cv_pct:5.1f}")
            m, s = divmod(int(self._t_now), 60)
            self._t_disp.setText(f"t = {m:02d}:{s:02d}")
            sp_n2 = self._sv_pct / 100.0
            if sp_n2 > 0.001:
                oss = max(0.0, (self._peak_pv - sp_n2) / sp_n2 * 100.0)
                self._peak_disp.setText(f"peak  {oss:.1f} %OS")
            else:
                self._peak_disp.setText(f"peak  {self._peak_pv*100:.2f}%")
            self._update_hmi()

    # ════════════════════════════════════════════════════
    #  INDUSTRIAL HMI PANEL
    # ════════════════════════════════════════════════════
    def _build_hmi_panel(self) -> QFrame:
        """Industrial HMI faceplate: editable PV/SV/mode/output/PID."""
        ROW_H = 56
        LBL_W = 88

        panel = QFrame()
        panel.setMinimumWidth(190)
        panel.setMaximumWidth(340)
        panel.setStyleSheet(
            "QFrame{background:#0A0A0A;"
            "border:3px solid #00AAAA;"
            "border-radius:5px;}")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(1)

        def _lbl_frame(label: str) -> QFrame:
            lf = QFrame(); lf.setMinimumWidth(LBL_W); lf.setMaximumWidth(LBL_W + 40)
            lf.setStyleSheet("QFrame{background:#1E1E1E;border:none;border-radius:2px;}")
            ll = QVBoxLayout(lf); ll.setContentsMargins(3, 2, 3, 2)
            lt = QLabel(label); lt.setWordWrap(True)
            lt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lt.setStyleSheet(
                "color:#DDDDDD;font-size:8.5pt;font-weight:700;"
                "background:transparent;border:none;"
                "font-family:'Microsoft JhengHei','Segoe UI';")
            ll.addWidget(lt)
            return lf

        def _wrap(lf, vf):
            rf = QFrame(); rf.setFixedHeight(ROW_H)
            rf.setStyleSheet("QFrame{background:transparent;border:none;}")
            h = QHBoxLayout(rf); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(1)
            h.addWidget(lf); h.addWidget(vf, 1)
            lay.addWidget(rf)

        def _row_ro(label: str, val_bg: str, val_clr: str) -> QLabel:
            lf = _lbl_frame(label)
            vf = QFrame()
            vf.setStyleSheet(f"QFrame{{background:{val_bg};border:none;border-radius:2px;}}")
            vl = QVBoxLayout(vf); vl.setContentsMargins(4, 2, 4, 2)
            vt = QLabel("—"); vt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vt.setStyleSheet(
                f"color:{val_clr};font-size:14pt;font-weight:700;"
                "background:transparent;border:none;"
                "font-family:Consolas,'Courier New';")
            vl.addWidget(vt)
            _wrap(lf, vf)
            return vt

        def _row_edit(label: str, val_bg: str, val_clr: str, init: str) -> QLineEdit:
            lf = _lbl_frame(label)
            vf = QFrame()
            vf.setStyleSheet(f"QFrame{{background:{val_bg};border:none;border-radius:2px;}}")
            vl = QVBoxLayout(vf); vl.setContentsMargins(4, 2, 4, 2)
            le = QLineEdit(init)
            le.setAlignment(Qt.AlignmentFlag.AlignCenter)
            le.setStyleSheet(
                f"QLineEdit{{background:transparent;color:{val_clr};"
                f"border:none;font-size:14pt;font-weight:700;"
                f"font-family:Consolas,'Courier New';}}"
                f"QLineEdit:focus{{border-bottom:2px solid #00AAAA;}}")
            vl.addWidget(le)
            _wrap(lf, vf)
            return le

        def _mode_row():
            lf = _lbl_frame("手自動")
            vf = QFrame()
            vf.setStyleSheet("QFrame{background:#0F0F0F;border:none;border-radius:2px;}")
            vh = QHBoxLayout(vf); vh.setContentsMargins(4, 8, 4, 8); vh.setSpacing(4)
            ba = QPushButton("Auto");   ba.setFixedHeight(34)
            bm = QPushButton("Manual"); bm.setFixedHeight(34)
            ba.clicked.connect(lambda: self._set_mode(False))
            bm.clicked.connect(lambda: self._set_mode(True))
            vh.addWidget(ba, 1); vh.addWidget(bm, 1)
            _wrap(lf, vf)
            return ba, bm

        self._hmi_pv       = _row_ro  ("PV",       "#FFFFFF", "#0044CC")
        self._hmi_sv_e     = _row_edit("SV 設定值", "#080820", "#5588FF", f"{self._sv_pct:.1f}")
        self._hmi_auto_btn, self._hmi_man_btn = _mode_row()
        self._hmi_man_e    = _row_edit("手動輸出",  "#1A1200", "#FFAA00", f"{self._cv_manual:.1f}")
        self._hmi_auto_out = _row_ro  ("自動輸出",  "#FFFFFF", "#0044CC")
        self._hmi_mv_max_e = _row_edit("MV Max",   "#1A1600", "#CCAA00", f"{self._mv_max:.0f}")
        self._hmi_mv_min_e = _row_edit("MV Min",   "#1A1600", "#CCAA00", f"{self._mv_min:.0f}")
        self._hmi_kp_e     = _row_edit("P",        "#1A1400", "#DDAA00", f"{self._Kp:.3f}")
        self._hmi_ki_e     = _row_edit("I",        "#1A1400", "#DDAA00", f"{self._Ki:.4f}")
        self._hmi_kd_e     = _row_edit("D",        "#1A1400", "#DDAA00", f"{self._Kd:.4f}")

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

    # ── HMI commit handlers (overridable by subclasses) ──────────
    def _hmi_commit_sv(self):
        try:    v = max(0.0, min(200.0, float(self._hmi_sv_e.text())))
        except: v = self._sv_pct
        self._sv_pct = v;  self._hmi_sv_e.setText(f"{v:.1f}")
        if hasattr(self, "_sv_in"): self._sv_in.setText(f"{v:.1f}")

    def _hmi_commit_man_out(self):
        try:    v = max(0.0, min(100.0, float(self._hmi_man_e.text())))
        except: v = self._cv_manual
        self._cv_manual = v;  self._hmi_man_e.setText(f"{v:.1f}")
        if hasattr(self, "_man_cv_in"): self._man_cv_in.setText(f"{v:.1f}")

    def _hmi_commit_mv_max(self):
        try:    v = max(0.0, min(200.0, float(self._hmi_mv_max_e.text())))
        except: v = self._mv_max
        self._mv_max = v;  self._hmi_mv_max_e.setText(f"{v:.0f}")
        if hasattr(self, "_mv_max_in"): self._mv_max_in.setText(f"{v:.0f}")

    def _hmi_commit_mv_min(self):
        try:    v = max(0.0, min(200.0, float(self._hmi_mv_min_e.text())))
        except: v = self._mv_min
        self._mv_min = v;  self._hmi_mv_min_e.setText(f"{v:.0f}")
        if hasattr(self, "_mv_min_in"): self._mv_min_in.setText(f"{v:.0f}")

    def _hmi_commit_kp(self):
        try:    v = max(0.0, min(100.0, float(self._hmi_kp_e.text())))
        except: v = self._Kp
        self._Kp = v;  self._hmi_kp_e.setText(f"{v:.3f}")
        if "Kp" in self._pid_inputs: self._pid_inputs["Kp"].setText(f"{v:.3f}")

    def _hmi_commit_ki(self):
        try:    v = max(0.0, min(50.0, float(self._hmi_ki_e.text())))
        except: v = self._Ki
        self._Ki = v;  self._hmi_ki_e.setText(f"{v:.4f}")
        if "Ki" in self._pid_inputs: self._pid_inputs["Ki"].setText(f"{v:.4f}")

    def _hmi_commit_kd(self):
        try:    v = max(0.0, min(20.0, float(self._hmi_kd_e.text())))
        except: v = self._Kd
        self._Kd = v;  self._hmi_kd_e.setText(f"{v:.4f}")
        if "Kd" in self._pid_inputs: self._pid_inputs["Kd"].setText(f"{v:.4f}")

    def _refresh_hmi_mode_btns(self):
        if not hasattr(self, "_hmi_auto_btn"): return
        _on  = ("QPushButton{background:#00BB44;color:#000;border:none;border-radius:3px;"
                "font-size:9.5pt;font-weight:700;"
                "font-family:'Microsoft JhengHei','Segoe UI';}")
        _off = ("QPushButton{background:#282828;color:#666;border:1px solid #444;"
                "border-radius:3px;font-size:9.5pt;font-weight:700;"
                "font-family:'Microsoft JhengHei','Segoe UI';}"
                "QPushButton:hover{background:#383838;color:#AAA;}")
        self._hmi_auto_btn.setStyleSheet(_on if not self._manual_mode else _off)
        self._hmi_man_btn.setStyleSheet (_on if     self._manual_mode else _off)

    def _update_hmi(self):
        if not hasattr(self, "_hmi_pv"): return
        pv_pct = self._pv_n * 100.0
        cv_pct = self._last_cv * 100.0
        self._hmi_pv.setText(f"{pv_pct:.1f} %")
        self._hmi_auto_out.setText(f"{cv_pct:.1f} %")
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
