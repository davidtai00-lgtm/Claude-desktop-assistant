# tool_advanced_calc.py — Advanced Industrial Calculator Suite
# Siemens S7-1200/1500 PLC Engineer Edition
# Bilingual: English Primary / Traditional Chinese Secondary
# Tabs: Motion | Scaling | Electrical | Logic & Comm

from math import pi, sqrt
from typing import Callable, List, Optional

from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtWidgets import (QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
                              QGridLayout, QLineEdit, QScrollArea, QComboBox,
                              QPushButton, QTabWidget, QSlider, QCheckBox)

from styles import BaseToolWindow

_KW_PER_HP  = 0.745_699_872
_NM_PER_KW  = 9_549.296_585   # N·m = _NM_PER_KW × kW / RPM
_SQRT3      = sqrt(3)

# ═══════════════════════════════════════════════════════
#  ADVANCED CALCULATOR — Industrial Suite
# ═══════════════════════════════════════════════════════
class AdvancedCalcTool(BaseToolWindow):

    # ── Palette ────────────────────────────────────────
    _BG     = "#121212"
    _CELL   = "#1E1E1E"
    _DARK   = "#0D0D0D"
    _BORDER = "#3D3D3D"
    _LBL    = "#FFFFFF"
    _LBL2   = "#A0A0A0"
    _YEL    = "#FFFF00"   # editable inputs
    _CYN    = "#00FFFF"   # computed results
    _ACC    = "#FF8800"
    _OK     = "#00FF88"
    _WARN   = "#FF4444"
    _DEC    = 4

    def __init__(self, on_thinking: Callable = None):
        super().__init__("🔬 Advanced Calc (進階計算器)", 540, 800)
        self.setMinimumSize(440, 560)
        self._on_thinking = on_thinking
        self.content.setStyleSheet(f"background:{self._BG};")

        root = QVBoxLayout(self.content)
        root.setContentsMargins(6, 4, 6, 2); root.setSpacing(4)

        # ── Tab widget ─────────────────────────────────
        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane{{background:{self._BG};"
            f"border:1px solid {self._BORDER};border-radius:4px;margin-top:-1px;}}"
            f"QTabBar::tab{{background:#1A1A1A;color:{self._LBL2};"
            f"padding:6px 14px;font-size:9pt;font-weight:700;"
            f"font-family:'Segoe UI','Microsoft JhengHei';"
            f"border-top-left-radius:4px;border-top-right-radius:4px;margin-right:2px;}}"
            f"QTabBar::tab:selected{{background:{self._BG};color:{self._ACC};"
            f"border-top:2px solid {self._ACC};}}"
            f"QTabBar::tab:hover:!selected{{background:#2A2A2A;color:{self._LBL};}}")

        tabs.addTab(self._tab(self._build_motion),     "⚙️  Motion (動力傳動)")
        tabs.addTab(self._tab(self._build_scaling),    "📊  Scaling (量程換算)")
        tabs.addTab(self._tab(self._build_electrical), "⚡  Electrical (電力)")
        tabs.addTab(self._tab(self._build_logic),      "🔣  Logic & Comm (位元)")

        root.addWidget(tabs, 1)

        # ── Status bar ─────────────────────────────────
        sb = QLabel(
            "Bang Bang Cat (邦邦貓)  │  Network & Motor Power Diagnostic  │  Formula Verified")
        sb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb.setFixedHeight(20)
        sb.setStyleSheet(
            f"color:#404040;font-size:7.5pt;font-weight:600;"
            f"background:#0A0A0A;border-top:1px solid {self._BORDER};"
            f"border-bottom:none;border-left:none;border-right:none;"
            f"font-family:'Segoe UI','Microsoft JhengHei';padding:0 6px;")
        root.addWidget(sb)

    # ════════════════════════════════════════════════════
    #  SOLID PAINT
    # ════════════════════════════════════════════════════
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 13, 13)
        p.fillPath(path, QColor(0x12, 0x12, 0x12))
        p.setPen(QPen(QColor(0x3D, 0x3D, 0x3D), 1))
        p.drawPath(path)

    # ════════════════════════════════════════════════════
    #  SHARED HELPERS
    # ════════════════════════════════════════════════════
    def _tab(self, builder) -> QScrollArea:
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{self._BG};border:none;}}"
            f"QScrollBar:vertical{{background:#1A1A1A;width:8px;border:none;margin:0;}}"
            f"QScrollBar::handle:vertical{{background:#3D3D3D;border-radius:4px;min-height:20px;}}"
            f"QScrollBar::handle:vertical:hover{{background:{self._ACC};}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}")
        inner = QWidget(); inner.setStyleSheet(f"background:{self._BG};")
        vbox  = QVBoxLayout(inner)
        vbox.setSpacing(8); vbox.setContentsMargins(8, 8, 10, 8)
        builder(vbox); vbox.addStretch()
        scroll.setWidget(inner); return scroll

    def _sec(self, text: str) -> QLabel:
        l = QLabel(f"  {text}"); l.setFixedHeight(22)
        l.setStyleSheet(
            f"color:{self._ACC};font-size:9pt;font-weight:700;"
            f"background:#1A1A1A;"
            f"border-top:1px solid {self._ACC};"
            f"border-left:3px solid {self._ACC};"
            f"border-bottom:none;border-right:none;padding-left:6px;"
            f"font-family:'Segoe UI','Microsoft JhengHei',sans-serif;")
        return l

    def _frm(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(
            f"QFrame{{background:{self._CELL};"
            f"border:1px solid {self._BORDER};border-radius:4px;}}")
        v = QVBoxLayout(f); v.setContentsMargins(10, 7, 10, 9); v.setSpacing(5)
        return f

    def _inp(self, c: str = None, ph: str = "0.0000",
             w: int = None, ro: bool = False) -> QLineEdit:
        col = c or self._YEL
        e = QLineEdit(); e.setPlaceholderText(ph)
        e.setFixedHeight(24); e.setAlignment(Qt.AlignmentFlag.AlignRight)
        e.setReadOnly(ro)
        if w: e.setFixedWidth(w)
        if ro:
            e.setStyleSheet(
                f"QLineEdit{{background:{self._DARK};color:{col};"
                f"border:1px solid #252525;border-radius:3px;"
                f"font-size:10pt;font-weight:bold;"
                f"font-family:Consolas,'Courier New';padding:1px 6px;}}")
        else:
            e.setStyleSheet(
                f"QLineEdit{{background:{self._DARK};color:{col};"
                f"border:2px solid {self._BORDER};border-radius:3px;"
                f"font-size:10pt;font-weight:bold;"
                f"font-family:Consolas,'Courier New';padding:1px 6px;}}"
                f"QLineEdit:focus{{border:2px solid {self._ACC};}}")
        return e

    def _sm(self, default: str = "", c: str = None, w: int = 80) -> QLineEdit:
        """Small config input."""
        e = QLineEdit(default); e.setFixedHeight(22); e.setFixedWidth(w)
        e.setAlignment(Qt.AlignmentFlag.AlignRight)
        e.setStyleSheet(
            f"QLineEdit{{background:#1A1A1A;color:{c or self._LBL};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:9pt;font-weight:bold;"
            f"font-family:Consolas,'Courier New';padding:1px 5px;}}"
            f"QLineEdit:focus{{border:1px solid {self._ACC};}}")
        return e

    def _lbl(self, txt: str, w: int = 160, c: str = None) -> QLabel:
        l = QLabel(txt); l.setFixedWidth(w)
        l.setStyleSheet(
            f"color:{c or self._LBL};font-size:9pt;font-weight:700;"
            f"background:transparent;border:none;"
            f"font-family:'Segoe UI','Microsoft JhengHei';")
        return l

    def _dim(self, txt: str, wrap: bool = False) -> QLabel:
        l = QLabel(txt); l.setWordWrap(wrap)
        l.setStyleSheet(
            f"color:{self._LBL2};font-size:8pt;font-weight:600;"
            f"background:transparent;border:none;"
            f"font-family:'Segoe UI','Microsoft JhengHei';")
        return l

    def _formula(self, txt: str) -> QLabel:
        """Formula label — dim cyan, monospace, visually distinct from _dim."""
        l = QLabel(txt); l.setWordWrap(True)
        l.setStyleSheet(
            f"color:#2ABFBF;font-size:8pt;font-weight:600;"
            f"background:#0F1A1A;border:1px solid #1A3030;border-radius:3px;"
            f"padding:3px 8px;margin-top:2px;"
            f"font-family:Consolas,'Courier New';")
        return l

    def _hsep(self) -> QFrame:
        s = QFrame(); s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet(
            f"border:none;border-top:1px solid {self._BORDER};background:transparent;")
        return s

    def _cbo(self, items: List[str], default: int = 0) -> QComboBox:
        cb = QComboBox()
        for it in items: cb.addItem(it)
        cb.setCurrentIndex(default); cb.setFixedHeight(24)
        cb.setStyleSheet(
            f"QComboBox{{background:#2A2A2A;color:{self._LBL};"
            f"border:2px solid {self._BORDER};border-radius:3px;"
            f"font-size:9pt;font-weight:700;padding:1px 6px;"
            f"font-family:'Segoe UI','Microsoft JhengHei';}}"
            f"QComboBox:focus{{border:2px solid {self._ACC};}}"
            f"QComboBox::drop-down{{border:none;width:16px;}}"
            f"QComboBox QAbstractItemView{{background:#1E1E1E;color:{self._LBL};"
            f"border:1px solid {self._BORDER};"
            f"selection-background-color:{self._ACC};selection-color:#fff;"
            f"font-size:9pt;font-weight:700;}}")
        return cb

    def _btn(self, txt: str, w: int = None) -> QPushButton:
        b = QPushButton(txt); b.setFixedHeight(24)
        if w: b.setFixedWidth(w)
        b.setStyleSheet(
            f"QPushButton{{background:{self._CELL};color:{self._LBL};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:9pt;font-weight:700;padding:0 10px;"
            f"font-family:'Segoe UI','Microsoft JhengHei';}}"
            f"QPushButton:hover{{background:{self._ACC};color:#fff;}}")
        return b

    def _row(self, lbl_txt: str, field: QLineEdit,
             layout: QVBoxLayout, unit: str = "") -> None:
        r = QHBoxLayout(); r.setSpacing(8)
        r.addWidget(self._lbl(lbl_txt))
        r.addWidget(field, 1)
        if unit:
            u = QLabel(unit)
            u.setFixedWidth(36)
            u.setStyleSheet(
                f"color:{self._LBL2};font-size:8pt;background:transparent;border:none;")
            r.addWidget(u)
        layout.addLayout(r)

    # ════════════════════════════════════════════════════
    #  TAB 1 — MOTION & MECHANICS  (動力傳動)
    # ════════════════════════════════════════════════════
    def _build_motion(self, lay: QVBoxLayout) -> None:

        # ── Motor Speed (馬達轉速) ──────────────────────
        lay.addWidget(self._sec("Motor Speed (馬達轉速)  —  One-Sync"))
        f1 = self._frm(); fl = f1.layout()

        # Config
        cfg = QGridLayout(); cfg.setSpacing(6); cfg.setContentsMargins(0,0,0,0)
        poles_cb = self._cbo([f"{p}P  ({p} Poles)" for p in (2,4,6,8,10,12)], 1)
        ratio_e  = self._sm("1.000", self._YEL, 90)
        cfg.addWidget(self._dim("Poles (極數)"),      0, 0)
        cfg.addWidget(self._dim("Gear Ratio (減速比)"),0, 1)
        cfg.addWidget(poles_cb,  1, 0)
        cfg.addWidget(ratio_e,   1, 1)
        fl.addLayout(cfg); fl.addWidget(self._hsep())

        M  = {}   # speed fields dict
        ml = [False]

        def gP() -> int:   return (poles_cb.currentIndex()+1)*2
        def gR() -> float:
            try: return max(1e-6, float(ratio_e.text()))
            except: return 1.0

        def msync(src: str, txt: str) -> None:
            if ml[0]: return
            try: v = float(txt)
            except: return
            P = gP(); R = gR()
            if   src == "hz":   hz = v
            elif src == "rm":   hz = v * P / 120.0
            elif src == "ro":   hz = v * R * P / 120.0
            else:               hz = v
            rpm_m = hz * 120.0 / P
            rpm_o = rpm_m / R
            ml[0] = True
            for k, val in (("hz",hz),("rm",rpm_m),("ro",rpm_o)):
                if k != src:
                    M[k].blockSignals(True)
                    M[k].setText(f"{val:.{self._DEC}f}")
                    M[k].blockSignals(False)
            ml[0] = False

        def mcfg(_=None):
            for k in ("hz","rm","ro"):
                if M.get(k) and M[k].text().strip():
                    msync(k, M[k].text()); break

        poles_cb.currentIndexChanged.connect(mcfg)
        ratio_e.textEdited.connect(mcfg)

        spec = [
            ("hz", "Hz  (Frequency 頻率)",    self._YEL),
            ("rm", "RPM  (Motor Shaft 馬達)",  self._YEL),
            ("ro", "RPM  (Output 輸出)",       self._CYN),
        ]
        for k, lbl, c in spec:
            e = self._inp(c); e.textEdited.connect(lambda t, sk=k: msync(sk, t))
            self._row(lbl, e, fl); M[k] = e

        fl.addWidget(self._formula(
            "RPM_motor = 120 × Hz ÷ Poles  │  RPM_output = RPM_motor ÷ Gear_Ratio"))
        lay.addWidget(f1)

        # ── Conveyor Line Speed (輸送線速度) ───────────
        lay.addWidget(self._sec("Line Speed (輸送線速度)  —  Linked to RPM(output)"))
        f2 = self._frm(); fl2 = f2.layout()

        dcfg = QHBoxLayout(); dcfg.setSpacing(8)
        dcfg.addWidget(self._dim("Roller Diameter D (滾輪直徑):"))
        diam_e = self._sm("200", self._YEL, 80)
        dcfg.addWidget(diam_e); dcfg.addWidget(self._dim("mm")); dcfg.addStretch()
        fl2.addLayout(dcfg); fl2.addWidget(self._hsep())

        CV = {}; cl = [False]

        def gD() -> float:
            try: return max(1e-4, float(diam_e.text())) / 1000.0
            except: return 0.2

        def cvsync(src: str, txt: str) -> None:
            if cl[0]: return
            try: v = float(txt)
            except: return
            D = gD()
            mpm = v if src == "mpm" else v * 60.0
            rpm_o = mpm / (pi * D) if D > 0 else 0
            mps   = mpm / 60.0
            cl[0] = True
            for k, val in (("mpm", mpm), ("mps", mps)):
                if k != src:
                    CV[k].blockSignals(True)
                    CV[k].setText(f"{val:.{self._DEC}f}")
                    CV[k].blockSignals(False)
            # push back to RPM output
            if "ro" in M:
                ml[0] = True
                M["ro"].blockSignals(True)
                M["ro"].setText(f"{rpm_o:.{self._DEC}f}")
                M["ro"].blockSignals(False)
                ml[0] = False
            cl[0] = False

        def dcfg_chg(_=None):
            if CV.get("mpm") and CV["mpm"].text().strip():
                cvsync("mpm", CV["mpm"].text())
        diam_e.textEdited.connect(dcfg_chg)

        for k, lbl, c in (("mpm","m/min  (Line Speed 線速度)",self._CYN),
                           ("mps","m/s   (Line Speed 線速度)", self._CYN)):
            e = self._inp(c); e.textEdited.connect(lambda t, sk=k: cvsync(sk, t))
            self._row(lbl, e, fl2); CV[k] = e

        fl2.addWidget(self._formula(
            "v (m/min) = RPM_output × π × D(mm) ÷ 1000  │  v (m/s) = v(m/min) ÷ 60"))
        lay.addWidget(f2)

        # ── Torque (力矩換算) ──────────────────────────
        lay.addWidget(self._sec("Torque (力矩換算)  —  Power / RPM / N·m"))
        f3 = self._frm(); fl3 = f3.layout()

        TR = {}; tr_recent: List[str] = []; tl = [False]

        def torque_solve(k1,v1,k2,v2) -> Optional[dict]:
            pair = frozenset((k1,k2))
            try:
                if   pair == frozenset(("kW","RPM")):
                    kw,rpm = (v1,v2) if k1=="kW" else (v2,v1)
                    return {"kW":kw,"HP":kw/_KW_PER_HP,"RPM":rpm,"N·m":_NM_PER_KW*kw/rpm}
                elif pair == frozenset(("kW","N·m")):
                    kw,nm  = (v1,v2) if k1=="kW" else (v2,v1)
                    return {"kW":kw,"HP":kw/_KW_PER_HP,"RPM":_NM_PER_KW*kw/nm,"N·m":nm}
                elif pair == frozenset(("RPM","N·m")):
                    rpm,nm = (v1,v2) if k1=="RPM" else (v2,v1)
                    kw = nm*rpm/_NM_PER_KW
                    return {"kW":kw,"HP":kw/_KW_PER_HP,"RPM":rpm,"N·m":nm}
                elif pair == frozenset(("HP","RPM")):
                    hp,rpm = (v1,v2) if k1=="HP" else (v2,v1)
                    kw = hp*_KW_PER_HP
                    return {"kW":kw,"HP":hp,"RPM":rpm,"N·m":_NM_PER_KW*kw/rpm}
                elif pair == frozenset(("HP","N·m")):
                    hp,nm  = (v1,v2) if k1=="HP" else (v2,v1)
                    kw = hp*_KW_PER_HP
                    return {"kW":kw,"HP":hp,"RPM":_NM_PER_KW*kw/nm,"N·m":nm}
            except (ZeroDivisionError, ValueError): pass
            return None

        def trsync(key: str, txt: str) -> None:
            if tl[0]: return
            if key in tr_recent: tr_recent.remove(key)
            tr_recent.append(key)
            if len(tr_recent) > 2: tr_recent.pop(0)
            if len(tr_recent) < 2: return
            try:
                v1 = float(TR[tr_recent[0]].text()); v2 = float(txt)
            except ValueError: return
            res = torque_solve(tr_recent[0], v1, tr_recent[1], v2)
            if not res: return
            tl[0] = True
            for k, e in TR.items():
                if k != key:
                    e.blockSignals(True); e.setText(f"{res[k]:.{self._DEC}f}")
                    e.blockSignals(False)
            tl[0] = False

        for k, lbl, c in (
                ("kW",  "Power (功率)  kW",        self._YEL),
                ("HP",  "Power (功率)  HP (馬力)",  self._YEL),
                ("RPM", "Speed (轉速)  RPM",        self._YEL),
                ("N·m", "Torque (力矩) N·m",        self._CYN)):
            e = self._inp(c); e.textEdited.connect(lambda t, k=k: trsync(k, t))
            self._row(lbl, e, fl3); TR[k] = e

        clear_t = self._btn("Clear", 60)
        clear_t.clicked.connect(lambda: [e.clear() for e in TR.values()] or tr_recent.clear())
        cr = QHBoxLayout(); cr.addStretch(); cr.addWidget(clear_t); fl3.addLayout(cr)
        fl3.addWidget(self._formula(
            "T (N·m) = 9549.3 × P(kW) ÷ RPM  │  1 HP = 0.74570 kW  │  Input any 2 → all 4"))
        lay.addWidget(f3)

        # ── Motor Start-up Calc (馬達起動電流計算) ───────
        lay.addWidget(self._sec(
            "Motor Start-up (馬達起動電流)  —  I_rated · I_start · Breaker Sizing"))
        f4 = self._frm(); fl4 = f4.layout()

        _METHODS = [
            ("DOL  (直接起動)",              6.0),
            ("Star-Delta  (星三角 Y-Δ)",     2.0),
            ("Soft Starter  (軟起動器)",     3.0),
            ("VFD  (變頻器)",                1.2),
            ("Auto-Transformer 65%  (自耦)", 2.5),
        ]
        _BREAKERS = [6,10,16,20,25,32,40,50,63,80,100,125,160,200,250,315,400,630,800]

        cfg_g = QGridLayout(); cfg_g.setSpacing(6); cfg_g.setContentsMargins(0,0,0,0)
        ms_method = self._cbo([m[0] for m in _METHODS]); ms_method.setFixedWidth(250)
        ms_mult   = self._sm(f"{_METHODS[0][1]:.1f}", self._YEL, 58)
        cfg_g.addWidget(self._dim("Start Method (起動方式)"),    0, 0)
        cfg_g.addWidget(self._dim("Multiplier × I_rated (倍率)"),0, 1)
        cfg_g.addWidget(ms_method, 1, 0)
        cfg_g.addWidget(ms_mult,   1, 1)
        fl4.addLayout(cfg_g)
        fl4.addWidget(self._hsep())

        MS = {}
        for k, lbl, c in (
                ("P",   "P   Motor Power (額定功率 kW)",      self._YEL),
                ("VL",  "VL  Line Voltage (線電壓 V)",        self._YEL),
                ("PF",  "PF  Power Factor cosφ (功率因數)",   self._YEL),
                ("EFF", "η   Efficiency (效率 %)",            self._YEL)):
            e = self._inp(c, "0.0000"); self._row(lbl, e, fl4); MS[k] = e
        MS["PF"].setText("0.85"); MS["EFF"].setText("90.0")
        fl4.addWidget(self._hsep())

        for k, lbl, c, ro in (
                ("IR", "I_rated  額定電流 (A)",             self._YEL, False),
                ("IS", "I_start  Starting Current (A)",    self._YEL, False),
                ("BK", "Suggested Breaker ≥  (A)",         self._CYN, True)):
            e = self._inp(c, "—", ro=ro); self._row(lbl, e, fl4); MS[k] = e

        warn_lbl = QLabel(
            "⚠  Hardworking Ox/Horse (苦命牛馬) — "
            "Breaker capacity is for reference only! (僅供參考)")
        warn_lbl.setWordWrap(True)
        warn_lbl.setStyleSheet(
            f"color:{self._WARN};font-size:8pt;font-weight:700;"
            f"background:#1A0D0D;border:1px solid #3A1A1A;border-radius:3px;"
            f"padding:3px 8px;margin-top:2px;"
            f"font-family:'Segoe UI','Microsoft JhengHei';")
        fl4.addWidget(warn_lbl)

        ms_btn = self._btn("⚡ Calculate (計算)", 160)
        cr4 = QHBoxLayout(); cr4.addStretch(); cr4.addWidget(ms_btn); fl4.addLayout(cr4)

        fl4.addWidget(self._formula(
            "I_rated = P×1000 ÷ (√3 × VL × cosφ × η)  "
            "│  I_start = I_rated × Multiplier  "
            "│  η: enter as % (e.g. 90 → 0.90 internally)"))

        def ms_method_changed(idx):
            ms_mult.setText(f"{_METHODS[idx][1]:.1f}")
            _ms_calculate()
        ms_method.currentIndexChanged.connect(ms_method_changed)

        def _ms_calculate(_=None):
            try:
                P   = float(MS["P"].text())
                VL  = float(MS["VL"].text())
                PF  = float(MS["PF"].text())
                EFF = float(MS["EFF"].text()) / 100.0
                mult= float(ms_mult.text())
                if VL <= 0 or PF <= 0 or EFF <= 0: raise ValueError("Zero/negative input")
                I_r = P * 1000.0 / (_SQRT3 * VL * PF * EFF)
                I_s = I_r * mult
                bk  = next((b for b in _BREAKERS if b >= I_s * 1.1), _BREAKERS[-1])
                MS["IR"].setText(f"{I_r:.{self._DEC}f}")
                MS["IS"].setText(f"{I_s:.{self._DEC}f}")
                MS["BK"].setText(f"{bk} A  (next std. ≥ {I_s*1.1:.1f} A)")
            except (ValueError, ZeroDivisionError):
                pass

        ms_btn.clicked.connect(_ms_calculate)
        for k in ("P", "VL", "PF", "EFF"):
            MS[k].textEdited.connect(_ms_calculate)
        ms_mult.textEdited.connect(_ms_calculate)

        lay.addWidget(f4)

    # ════════════════════════════════════════════════════
    #  TAB 2 — ANALOG SCALING  (PLC NORM_X / SCALE_X)
    # ════════════════════════════════════════════════════
    def _build_scaling(self, lay: QVBoxLayout) -> None:

        lay.addWidget(self._sec("PLC Analog Scaling (類比量換算)  —  NORM_X / SCALE_X"))
        f1 = self._frm(); fl = f1.layout()

        # Range definition
        fl.addWidget(self._dim("  Define Range (定義量程):"))
        rg = QGridLayout(); rg.setSpacing(6); rg.setContentsMargins(0,0,0,0)
        raw_lo = self._sm("0",     self._LBL, 80)
        raw_hi = self._sm("27648", self._LBL, 80)
        eng_lo = self._sm("0.0",   self._LBL, 80)
        eng_hi = self._sm("100.0", self._LBL, 80)
        for ci,(lbl,w) in enumerate([
                ("Raw Min",raw_lo),("Raw Max",raw_hi),
                ("Eng Min",eng_lo),("Eng Max",eng_hi)]):
            rg.addWidget(self._dim(lbl), 0, ci)
            rg.addWidget(w,              1, ci)
        fl.addLayout(rg)

        # Presets
        pr = QHBoxLayout(); pr.setSpacing(5)
        pr.addWidget(self._dim("Presets:"))
        PRESETS = [
            ("4–20 mA",  ("0","27648","4.000","20.000")),
            ("0–10 V",   ("0","27648","0.000","10.000")),
            ("±10 V",    ("0","27648","-10.000","10.000")),
            ("0–100 %",  ("0","27648","0.000","100.000")),
        ]
        for lbl, vals in PRESETS:
            b = self._btn(lbl); b.setFixedHeight(20)
            def load(v=vals):
                raw_lo.setText(v[0]); raw_hi.setText(v[1])
                eng_lo.setText(v[2]); eng_hi.setText(v[3])
            b.clicked.connect(load); pr.addWidget(b)
        pr.addStretch(); fl.addLayout(pr)
        fl.addWidget(self._hsep())

        # Bidirectional live conversion
        fl.addWidget(self._dim("  Live Conversion (即時換算):"))
        sl = [False]

        def get_rng():
            return (float(raw_lo.text()), float(raw_hi.text()),
                    float(eng_lo.text()), float(eng_hi.text()))

        raw_v = self._inp(self._YEL, "Enter Raw value")
        eng_v = self._inp(self._CYN, "Enter Engineering value")
        pct_v = self._inp(self._CYN, "—", ro=True)

        def r2e(txt: str) -> None:
            if sl[0]: return
            try:
                r0,r1,e0,e1 = get_rng()
                if r1 == r0: return
                raw = float(txt)
                eng = (raw-r0)*(e1-e0)/(r1-r0)+e0
                pct = (raw-r0)/(r1-r0)*100.0
            except ValueError: return
            sl[0] = True
            eng_v.blockSignals(True); eng_v.setText(f"{eng:.{self._DEC}f}"); eng_v.blockSignals(False)
            pct_v.setText(f"{pct:.2f} %")
            slider.setValue(int(max(0, min(10_000, (raw-float(raw_lo.text()))
                                          / max(1e-9, float(raw_hi.text())-float(raw_lo.text())) * 10_000))))
            sl[0] = False

        def e2r(txt: str) -> None:
            if sl[0]: return
            try:
                r0,r1,e0,e1 = get_rng()
                if e1 == e0: return
                eng = float(txt)
                raw = (eng-e0)*(r1-r0)/(e1-e0)+r0
                pct = (raw-r0)/(r1-r0)*100.0
            except ValueError: return
            sl[0] = True
            raw_v.blockSignals(True); raw_v.setText(f"{raw:.{self._DEC}f}"); raw_v.blockSignals(False)
            pct_v.setText(f"{pct:.2f} %")
            sl[0] = False

        def rng_chg(_):
            if raw_v.text().strip(): r2e(raw_v.text())
            elif eng_v.text().strip(): e2r(eng_v.text())

        raw_v.textEdited.connect(r2e); eng_v.textEdited.connect(e2r)
        for e in (raw_lo, raw_hi, eng_lo, eng_hi): e.textEdited.connect(rng_chg)

        self._row("Raw Value (原始值)",  raw_v, fl)
        self._row("Eng Value (工程值)",  eng_v, fl)
        self._row("Percentage (百分比)", pct_v, fl)
        fl.addWidget(self._hsep())

        # Slider simulation
        fl.addWidget(self._dim("  Slider Simulation (滑桿模擬):"))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 10_000); slider.setValue(0)
        slider.setStyleSheet(
            f"QSlider::groove:horizontal{{height:6px;background:#2A2A2A;border-radius:3px;}}"
            f"QSlider::handle:horizontal{{background:{self._ACC};"
            f"width:16px;height:16px;margin:-5px 0;border-radius:8px;}}"
            f"QSlider::sub-page:horizontal{{background:{self._ACC};border-radius:3px;}}")

        def on_slider(v: int) -> None:
            if sl[0]: return
            try:
                r0,r1,e0,e1 = get_rng()
                raw = r0 + (r1-r0)*v/10_000.0
                eng = e0 + (e1-e0)*v/10_000.0
            except ValueError: return
            sl[0] = True
            raw_v.setText(f"{raw:.{self._DEC}f}")
            eng_v.setText(f"{eng:.{self._DEC}f}")
            pct_v.setText(f"{v/100.0:.2f} %")
            sl[0] = False

        slider.valueChanged.connect(on_slider)
        fl.addWidget(slider)
        fl.addWidget(self._formula(
            "Scaled = (Raw − RawMin) × (EngMax − EngMin) ÷ (RawMax − RawMin) + EngMin"))
        lay.addWidget(f1)

        # ── Signal Reference (快速參考) ─────────────────
        lay.addWidget(self._sec("Signal Reference (訊號快速參考)"))
        f2 = self._frm(); fl2 = f2.layout()
        REF_HDR = ["Signal (訊號)", "0 % Raw", "25 %", "50 %", "75 %", "100 % Raw"]
        REF_DAT = [
            ("4–20 mA  (S7-1200/1500)", "0", "6912", "13824", "20736", "27648"),
            ("0–10 V",                   "0", "6912", "13824", "20736", "27648"),
            ("−10 V ~ +10 V",            "0", "8192", "16383", "24575", "32767"),
            ("0–20 mA  (generic)",       "0", "6912", "13824", "20736", "27648"),
        ]
        tbl = QGridLayout(); tbl.setSpacing(1); tbl.setContentsMargins(0,0,0,0)
        hss = (f"color:{self._ACC};font-size:8pt;font-weight:700;"
               f"background:#181818;border-bottom:1px solid {self._BORDER};"
               f"padding:2px 6px;font-family:'Segoe UI','Microsoft JhengHei';")
        css = (f"color:{self._LBL};font-size:8pt;font-weight:600;"
               f"border-bottom:1px solid #252525;padding:2px 6px;"
               f"background:transparent;font-family:Consolas,'Courier New';")
        for ci, h in enumerate(REF_HDR):
            hl = QLabel(h); hl.setStyleSheet(hss); tbl.addWidget(hl, 0, ci)
        for ri, row_data in enumerate(REF_DAT, 1):
            for ci, cell in enumerate(row_data):
                cl = QLabel(cell); cl.setStyleSheet(css)
                tbl.addWidget(cl, ri, ci)
        tbl.setColumnStretch(0, 2)
        fl2.addLayout(tbl)
        lay.addWidget(f2)

    # ════════════════════════════════════════════════════
    #  TAB 3 — ELECTRICAL & POWER  (電力與電熱)
    # ════════════════════════════════════════════════════
    def _build_electrical(self, lay: QVBoxLayout) -> None:

        # ── Ohm's Law (歐姆定律) ────────────────────────
        lay.addWidget(self._sec("Ohm's Law (歐姆定律)  —  Enter any 2 fields"))
        f1 = self._frm(); fl = f1.layout()
        OHM = {}; o_rec: List[str] = []; ol = [False]

        def ohm_solve(k1,v1,k2,v2) -> Optional[dict]:
            p = frozenset((k1,k2))
            try:
                if   p==frozenset(("V","I")): V,I=v1 if k1=="V" else v2, v1 if k1=="I" else v2; return{"V":V,"I":I,"R":V/I,"W":V*I}
                elif p==frozenset(("V","R")): V,R=v1 if k1=="V" else v2, v1 if k1=="R" else v2; return{"V":V,"I":V/R,"R":R,"W":V**2/R}
                elif p==frozenset(("V","W")): V,W=v1 if k1=="V" else v2, v1 if k1=="W" else v2; return{"V":V,"I":W/V,"R":V**2/W,"W":W}
                elif p==frozenset(("I","R")): I,R=v1 if k1=="I" else v2, v1 if k1=="R" else v2; return{"V":I*R,"I":I,"R":R,"W":I**2*R}
                elif p==frozenset(("I","W")): I,W=v1 if k1=="I" else v2, v1 if k1=="W" else v2; return{"V":W/I,"I":I,"R":W/I**2,"W":W}
                elif p==frozenset(("R","W")): R,W=v1 if k1=="R" else v2, v1 if k1=="W" else v2; I=sqrt(W/R); return{"V":sqrt(W*R),"I":I,"R":R,"W":W}
            except (ZeroDivisionError, ValueError): pass
            return None

        def osync(key: str, txt: str) -> None:
            if ol[0]: return
            if key in o_rec: o_rec.remove(key)
            o_rec.append(key)
            if len(o_rec)>2: o_rec.pop(0)
            if len(o_rec)<2: return
            try: v1=float(OHM[o_rec[0]].text()); v2=float(txt)
            except ValueError: return
            res=ohm_solve(o_rec[0],v1,o_rec[1],v2)
            if not res: return
            ol[0]=True
            for k,e in OHM.items():
                if k!=key:
                    e.blockSignals(True); e.setText(f"{res[k]:.{self._DEC}f}"); e.blockSignals(False)
            ol[0]=False

        for k,lbl,c in (
                ("V","V  Voltage (電壓)",     self._YEL),
                ("I","I  Current (電流)",     self._YEL),
                ("R","R  Resistance (電阻 Ω)",self._CYN),
                ("W","W  Power (功率 W)",      self._CYN)):
            e=self._inp(c,"Enter any two…"); e.textEdited.connect(lambda t,k=k: osync(k,t))
            self._row(lbl,e,fl); OHM[k]=e

        cb=self._btn("Clear",60); cb.clicked.connect(lambda:[e.clear() for e in OHM.values()] or o_rec.clear())
        cr=QHBoxLayout(); cr.addStretch(); cr.addWidget(cb); fl.addLayout(cr)
        fl.addWidget(self._formula(
            "V = I×R  │  P = V×I  │  P = I²×R  │  P = V²÷R  │  Input any 2 → solve all 4"))
        lay.addWidget(f1)

        # ── 3-Phase Power (三相功率) ────────────────────
        lay.addWidget(self._sec("3-Phase Power (三相功率)  —  P = √3 × VL × IL × PF"))
        f2 = self._frm(); fl2 = f2.layout()
        PH = {}; ph_l = [False]

        def phsync(*_) -> None:
            if ph_l[0]: return
            try:
                V  = float(PH["VL"].text())
                I  = float(PH["IL"].text())
                PF = max(0.0, min(1.0, float(PH["PF"].text())))
            except ValueError: return
            ph_l[0] = True
            S = _SQRT3 * V * I / 1000.0
            P = S * PF
            Q = S * sqrt(max(0.0, 1.0 - PF**2))
            for k, val in (("S",S),("P",P),("Q",Q)):
                PH[k].setText(f"{val:.{self._DEC}f}")
            ph_l[0] = False

        for k,lbl,c,ro in (
                ("VL","VL  Line Voltage (線電壓 V)",   self._YEL, False),
                ("IL","IL  Line Current (線電流 A)",    self._YEL, False),
                ("PF","PF  Power Factor (功率因數)",    self._YEL, False),
                ("S", "S   Apparent (視在功率 kVA)",    self._CYN, True),
                ("P", "P   Active (有功功率 kW)",        self._OK,  True),
                ("Q", "Q   Reactive (無功功率 kVAR)",    self._WARN,True)):
            e=self._inp(c,"",ro=ro); PH[k]=e
            if not ro: e.textEdited.connect(phsync)
            self._row(lbl,e,fl2)

        PH["PF"].setText("0.8500")
        fl2.addWidget(self._formula(
            "S (kVA) = √3 × VL × IL ÷ 1000  │  P (kW) = S × PF  │  Q (kVAR) = S × √(1−PF²)"))
        lay.addWidget(f2)

        # ── Heater Calculator (電熱元件計算) ───────────
        lay.addWidget(self._sec("Heater Calc (電熱元件)  —  V / R / P  (PF = 1)"))
        f3 = self._frm(); fl3 = f3.layout()
        HT = {}; ht_rec: List[str] = []; hl_flag = [False]

        def ht_solve(k1,v1,k2,v2) -> Optional[dict]:
            p = frozenset((k1,k2))
            try:
                if   p==frozenset(("V","R")): V,R=v1 if k1=="V" else v2, v1 if k1=="R" else v2; return{"V":V,"R":R,"W":V**2/R,"I":V/R}
                elif p==frozenset(("V","W")): V,W=v1 if k1=="V" else v2, v1 if k1=="W" else v2; return{"V":V,"R":V**2/W,"W":W,"I":W/V}
                elif p==frozenset(("R","W")): R,W=v1 if k1=="R" else v2, v1 if k1=="W" else v2; V=sqrt(W*R); return{"V":V,"R":R,"W":W,"I":V/R}
            except (ZeroDivisionError, ValueError): pass
            return None

        def htsync(key: str, txt: str) -> None:
            if hl_flag[0]: return
            if key in ht_rec: ht_rec.remove(key)
            ht_rec.append(key)
            if len(ht_rec)>2: ht_rec.pop(0)
            if len(ht_rec)<2: return
            try: v1=float(HT[ht_rec[0]].text()); v2=float(txt)
            except ValueError: return
            res=ht_solve(ht_rec[0],v1,ht_rec[1],v2)
            if not res: return
            hl_flag[0]=True
            for k,e in HT.items():
                if k!=key:
                    e.blockSignals(True); e.setText(f"{res[k]:.{self._DEC}f}"); e.blockSignals(False)
            hl_flag[0]=False

        for k,lbl,c in (
                ("V","V  Supply Voltage (電源電壓 V)",  self._YEL),
                ("R","R  Element Resistance (電阻 Ω)",  self._YEL),
                ("W","W  Power Output (加熱功率 W)",     self._CYN),
                ("I","I  Current Draw (工作電流 A)",     self._CYN)):
            e=self._inp(c,"Input any 2 of V/R/W")
            e.textEdited.connect(lambda t,k=k: htsync(k,t))
            self._row(lbl,e,fl3); HT[k]=e
        HT["I"].setReadOnly(True)

        # Parallel heaters
        fl3.addWidget(self._hsep())
        ph_row = QHBoxLayout(); ph_row.setSpacing(8)
        ph_row.addWidget(self._dim("Heaters in Parallel (並聯數量 N):"))
        n_e  = self._sm("1", self._YEL, 50)
        tot_w = self._inp(self._CYN, "—", ro=True)
        tot_a = self._inp(self._CYN, "—", ro=True)
        ph_row.addWidget(n_e); ph_row.addStretch()
        fl3.addLayout(ph_row)
        for lbl,e in (("Total Power (總功率 W)",tot_w),("Total Current (總電流 A)",tot_a)):
            self._row(lbl,e,fl3)

        def update_parallel(_=None):
            try:
                n=max(1,int(n_e.text()))
                w=float(HT["W"].text()); i=float(HT["I"].text())
                tot_w.setText(f"{n*w:.{self._DEC}f}")
                tot_a.setText(f"{n*i:.{self._DEC}f}")
            except ValueError: pass

        for e in list(HT.values())+[n_e]:
            e.textEdited.connect(update_parallel)

        fl3.addWidget(self._formula(
            "P_total = Σ(V²÷Rₙ)  │  I_total = Σ(V÷Rₙ)  │  Parallel N units: P_total = N × P_each"))
        lay.addWidget(f3)

    # ════════════════════════════════════════════════════
    #  TAB 4 — LOGIC & COMM  (位元與通訊)
    # ════════════════════════════════════════════════════
    def _build_logic(self, lay: QVBoxLayout) -> None:

        # ── 16-Bit Word Decoder (16位元解碼) ────────────
        lay.addWidget(self._sec("16-Bit Word Decoder (16位元狀態字解碼)"))
        f1 = self._frm(); fl = f1.layout()

        dl = [False]; BIT_BTNS: List[QPushButton] = []

        dec_e = self._inp(self._YEL, "Unsigned DEC  (0–65535)")
        hex_e = self._inp(self._CYN, "HEX  (0x0000)")
        sin_e = self._inp(self._OK,  "—", ro=True)
        bin_e = self._inp(self._LBL2,"—", ro=True)
        hb_e  = self._inp(self._CYN, "—", ro=True)
        lb_e  = self._inp(self._CYN, "—", ro=True)

        for lbl,e in (("DEC  Unsigned (無號)",    dec_e),
                      ("HEX  (十六進位)",           hex_e),
                      ("INT16  Signed (有號)",      sin_e),
                      ("BIN  (二進位 4×4)",         bin_e),
                      ("High Byte  (高位元組)",     hb_e),
                      ("Low Byte   (低位元組)",     lb_e)):
            self._row(lbl, e, fl)

        fl.addWidget(self._hsep())
        fl.addWidget(self._dim("  Bit Display (位元顯示) — Click to Toggle:"))

        # Bit buttons (15 down to 0)
        bit_frm = QFrame()
        bit_frm.setStyleSheet(
            f"QFrame{{background:{self._DARK};"
            f"border:1px solid {self._BORDER};border-radius:3px;}}")
        bl = QVBoxLayout(bit_frm); bl.setContentsMargins(6,6,6,4); bl.setSpacing(2)

        btn_row = QHBoxLayout(); btn_row.setSpacing(2)
        idx_row = QHBoxLayout(); idx_row.setSpacing(2)

        def update_from_word(word: int, skip: str = "") -> None:
            word &= 0xFFFF
            dl[0] = True
            if skip != "dec":
                dec_e.blockSignals(True); dec_e.setText(str(word)); dec_e.blockSignals(False)
            if skip != "hex":
                hex_e.blockSignals(True); hex_e.setText(f"0x{word:04X}"); hex_e.blockSignals(False)
            sint = word if word < 32768 else word - 65536
            sin_e.setText(str(sint))
            b = f"{word:016b}"
            bin_e.setText(f"{b[0:4]} {b[4:8]} {b[8:12]} {b[12:16]}")
            hb_e.setText(f"0x{word>>8:02X}  ({word>>8})")
            lb_e.setText(f"0x{word&0xFF:02X}  ({word&0xFF})")
            for i, btn in enumerate(BIT_BTNS):
                bit_val = (word >> (15-i)) & 1
                btn.setChecked(bit_val == 1)
            dl[0] = False

        def from_dec(txt: str) -> None:
            if dl[0]: return
            try: update_from_word(int(txt)&0xFFFF, "dec")
            except ValueError: pass

        def from_hex(txt: str) -> None:
            if dl[0]: return
            try: update_from_word(int(txt.replace("0x","").replace("0X",""),16), "hex")
            except ValueError: pass

        dec_e.textEdited.connect(from_dec)
        hex_e.textEdited.connect(from_hex)

        for i in range(16):
            btn = QPushButton("0")
            btn.setCheckable(True); btn.setFixedSize(26, 26)
            btn.setStyleSheet(
                f"QPushButton{{background:#1A1A1A;color:#3A3A3A;"
                f"border:1px solid #2A2A2A;border-radius:3px;"
                f"font-size:9pt;font-weight:700;font-family:Consolas,'Courier New';}}"
                f"QPushButton:checked{{background:#00AA00;color:#000;"
                f"border-color:#00FF00;}}"
                f"QPushButton:hover:!checked{{background:#2A2A2A;}}")

            def on_bit_click(checked: bool, idx: int = i) -> None:
                if dl[0]: return
                try: word = int(dec_e.text()) & 0xFFFF
                except ValueError: word = 0
                if checked: word |=  (1 << (15-idx))
                else:       word &= ~(1 << (15-idx)) & 0xFFFF
                update_from_word(word)

            btn.toggled.connect(on_bit_click)
            BIT_BTNS.append(btn); btn_row.addWidget(btn)
            if i in (3, 7, 11):
                sp = QLabel("|"); sp.setFixedWidth(8)
                sp.setStyleSheet(f"color:#3D3D3D;background:transparent;border:none;")
                btn_row.addWidget(sp)
                sp2 = QLabel(" "); sp2.setFixedWidth(8)
                sp2.setStyleSheet("background:transparent;border:none;")
                idx_row.addWidget(sp2)

            il = QLabel(str(15-i)); il.setFixedWidth(26)
            il.setAlignment(Qt.AlignmentFlag.AlignCenter)
            il.setStyleSheet(f"color:#3A3A3A;font-size:7pt;background:transparent;border:none;")
            idx_row.addWidget(il)

        bl.addLayout(btn_row); bl.addLayout(idx_row)
        fl.addWidget(bit_frm)
        update_from_word(0)
        lay.addWidget(f1)

        # ── Bitmask Generator (位元遮罩產生器) ────────────
        lay.addWidget(self._sec("Bitmask Generator (位元遮罩產生器)  —  PLC AND/OR Logic"))
        f2 = self._frm(); fl2 = f2.layout()

        CHECKS: List[QCheckBox] = []

        or_e   = self._inp(self._CYN, "—", ro=True)
        and_e  = self._inp(self._WARN,"—", ro=True)
        or_d   = self._inp(self._CYN, "—", ro=True)

        def mask_update() -> None:
            mask = 0
            for i, cb in enumerate(CHECKS):
                if cb.isChecked(): mask |= (1 << i)
            or_e .setText(f"0x{mask:04X}")
            and_e.setText(f"0x{(~mask & 0xFFFF):04X}")
            or_d .setText(str(mask))

        # 2 rows: bit 15-8 top, bit 7-0 bottom
        for row_start, row_end in ((15, 7), (7, -1)):
            gr = QHBoxLayout(); gr.setSpacing(4)
            for bit in range(row_start, row_end, -1):
                col_frame = QVBoxLayout(); col_frame.setSpacing(1)
                cb = QCheckBox(); cb.setFixedWidth(20)
                cb.setStyleSheet(
                    f"QCheckBox{{background:transparent;border:none;}}"
                    f"QCheckBox::indicator{{width:16px;height:16px;"
                    f"background:#1A1A1A;border:1px solid {self._BORDER};border-radius:2px;}}"
                    f"QCheckBox::indicator:checked{{background:{self._ACC};"
                    f"border-color:#FFB000;}}")
                cb.stateChanged.connect(mask_update)
                CHECKS.insert(0, cb)   # prepend so CHECKS[0] = bit0
                bl_lbl = QLabel(str(bit)); bl_lbl.setFixedWidth(20)
                bl_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                bl_lbl.setStyleSheet(
                    f"color:#404040;font-size:7pt;background:transparent;border:none;")
                col_frame.addWidget(bl_lbl); col_frame.addWidget(cb)
                gr.addLayout(col_frame)
            gr.addStretch(); fl2.addLayout(gr)

        fl2.addWidget(self._hsep())
        for lbl, e in (("OR Mask  (置位 SET bits)",      or_e),
                        ("AND Mask (清位 CLEAR others)",   and_e),
                        ("OR Mask  DEC (十進位)",          or_d)):
            self._row(lbl, e, fl2)
        fl2.addWidget(self._dim(
            "OR Mask: bits to SET (1→1).  AND Mask: use with W#AND to clear selected bits.", True))
        lay.addWidget(f2)

        # ── Modbus Exception Reference (異常碼參考) ───────
        lay.addWidget(self._sec("Modbus Exception Codes (Modbus 異常碼參考)"))
        f3 = self._frm(); fl3 = f3.layout()

        MODBUS = [
            ("01","0x01","Illegal Function",         "函數碼不支援 (FC not supported)"),
            ("02","0x02","Illegal Data Address",      "資料位址不存在 (Address out of range)"),
            ("03","0x03","Illegal Data Value",        "資料值不合法 (Value out of range)"),
            ("04","0x04","Server Device Failure",     "從站裝置故障 (Slave internal error)"),
            ("05","0x05","Acknowledge",               "確認中，等待 (Long processing, retry)"),
            ("06","0x06","Server Device Busy",        "從站忙碌中 (Try again later)"),
            ("07","0x07","Negative Acknowledge",      "否定確認 (Slave rejects request)"),
            ("08","0x08","Memory Parity Error",       "記憶體奇偶校驗錯誤"),
            ("10","0x0A","Gateway Path Unavailable",  "閘道路徑不可用 (No route)"),
            ("11","0x0B","Gateway Target Failed",     "目標裝置無回應 (Device offline)"),
        ]
        hss = (f"color:{self._ACC};font-size:8pt;font-weight:700;"
               f"background:#181818;border-bottom:1px solid {self._BORDER};"
               f"padding:2px 5px;font-family:'Segoe UI','Microsoft JhengHei';")
        cssl= (f"color:{self._LBL};font-size:8pt;font-weight:600;"
               f"border-bottom:1px solid #252525;padding:2px 5px;"
               f"background:transparent;font-family:Consolas,'Courier New';")
        css2= (f"color:{self._LBL2};font-size:7.5pt;font-weight:600;"
               f"border-bottom:1px solid #252525;padding:2px 5px;"
               f"background:transparent;font-family:'Segoe UI','Microsoft JhengHei';")

        tbl = QGridLayout(); tbl.setSpacing(0); tbl.setContentsMargins(0,0,0,0)
        for ci, h in enumerate(("DEC","HEX","Exception","Description (說明)")):
            hl = QLabel(h); hl.setStyleSheet(hss); tbl.addWidget(hl,0,ci)
        for ri,(dec,hex_,exc,desc) in enumerate(MODBUS,1):
            for ci,(txt,ss) in enumerate(((dec,cssl),(hex_,cssl),(exc,cssl),(desc,css2))):
                l = QLabel(txt); l.setStyleSheet(ss); tbl.addWidget(l,ri,ci)
        tbl.setColumnStretch(2,1); tbl.setColumnStretch(3,2)
        fl3.addLayout(tbl)
        lay.addWidget(f3)
