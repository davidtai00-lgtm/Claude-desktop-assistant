# tool_unit_converter.py — Ultimate Bilingual Categorized Unit Converter
# 20+ unit groups | 3 Tabs: Physical · Electrical · Science & Data
# Instant bidirectional sync | QSizeGrip | Solid Dark Theme
# Part of the Clawde Industrial Engineering Suite

from math import pi
from typing import Callable, List, Tuple

from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtWidgets import (QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
                              QLineEdit, QScrollArea, QTabWidget, QComboBox,
                              QGridLayout)

from styles import BaseToolWindow

_MS_PER_BFT = 0.836   # Beaufort: v(m/s) = 0.836 × B^1.5

# ═══════════════════════════════════════════════════════
#  UNIT CONVERTER TOOL
# ═══════════════════════════════════════════════════════
class UnitConverterTool(BaseToolWindow):

    _BG     = "#121212"
    _CELL   = "#1E1E1E"
    _DARK   = "#0D0D0D"
    _BORDER = "#3D3D3D"
    _LBL    = "#FFFFFF"
    _LBL2   = "#A0A0A0"
    _YEL    = "#FFFF00"
    _CYN    = "#00FFFF"
    _ACC    = "#FF8800"
    _DEC    = 6

    def __init__(self, on_thinking: Callable = None):
        super().__init__("📐 Unit Converter (單位換算器)", 500, 780)
        self.setMinimumSize(420, 520)
        self._on_thinking = on_thinking
        self.content.setStyleSheet(f"background:{self._BG};")

        root = QVBoxLayout(self.content)
        root.setContentsMargins(6, 4, 6, 2); root.setSpacing(4)

        sop = QLabel(
            "邦邦貓提醒：輸入任意欄位全組即時同步。"
            "共 20+ 單位組，Physical / Electrical / Science 三大類。苦命牛馬加油！")
        sop.setWordWrap(True)
        sop.setStyleSheet(
            f"color:{self._LBL};font-size:8.5pt;font-weight:700;"
            f"background:#1A1A1A;border:1px solid {self._BORDER};"
            f"border-left:3px solid {self._ACC};"
            f"border-radius:3px;padding:4px 10px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';")
        root.addWidget(sop)

        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane{{background:{self._BG};"
            f"border:1px solid {self._BORDER};border-radius:4px;margin-top:-1px;}}"
            f"QTabBar::tab{{background:#1A1A1A;color:{self._LBL2};"
            f"padding:6px 8px;font-size:8.5pt;font-weight:700;"
            f"font-family:'Segoe UI','Microsoft JhengHei';"
            f"border-top-left-radius:4px;border-top-right-radius:4px;margin-right:2px;}}"
            f"QTabBar::tab:selected{{background:{self._BG};color:{self._ACC};"
            f"border-top:2px solid {self._ACC};}}"
            f"QTabBar::tab:hover:!selected{{background:#2A2A2A;color:{self._LBL};}}")

        tabs.addTab(self._tab(self._build_physical),   "⚖️  Physical (物理類)")
        tabs.addTab(self._tab(self._build_electrical), "⚡  Electrical (電氣類)")
        tabs.addTab(self._tab(self._build_science),    "🔬  Science & Data (科學)")
        root.addWidget(tabs, 1)

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
        v = QVBoxLayout(f); v.setContentsMargins(10, 6, 10, 8); v.setSpacing(4)
        return f

    def _inp(self, color: str = None) -> QLineEdit:
        e = QLineEdit(); e.setPlaceholderText("0.000000")
        e.setFixedHeight(24); e.setAlignment(Qt.AlignmentFlag.AlignRight)
        e.setStyleSheet(
            f"QLineEdit{{background:{self._DARK};color:{color or self._YEL};"
            f"border:2px solid {self._BORDER};border-radius:3px;"
            f"font-size:10pt;font-weight:bold;"
            f"font-family:Consolas,'Courier New';padding:1px 6px;}}"
            f"QLineEdit:focus{{border:2px solid {self._ACC};}}")
        return e

    def _lbl(self, text: str) -> QLabel:
        l = QLabel(text); l.setMinimumWidth(172)
        l.setStyleSheet(
            f"color:{self._LBL};font-size:9pt;font-weight:700;"
            f"background:transparent;border:none;"
            f"font-family:'Microsoft JhengHei','Segoe UI';")
        return l

    def _dim(self, text: str) -> QLabel:
        l = QLabel(text); l.setWordWrap(True)
        l.setStyleSheet(
            f"color:{self._LBL2};font-size:8pt;font-weight:600;"
            f"background:transparent;border:none;"
            f"font-family:'Microsoft JhengHei','Segoe UI';")
        return l

    def _formula(self, text: str) -> QLabel:
        l = QLabel(text); l.setWordWrap(True)
        l.setStyleSheet(
            f"color:#2ABFBF;font-size:7.5pt;font-weight:600;"
            f"background:#0F1A1A;border:1px solid #1A3030;border-radius:3px;"
            f"padding:3px 8px;margin-top:2px;"
            f"font-family:Consolas,'Courier New';")
        return l

    def _fmt(self, v: float) -> str:
        """Scientific notation for very large / very small values."""
        if v == 0.0: return "0.000000"
        av = abs(v)
        if av >= 1e12 or av < 1e-4:
            return f"{v:.6e}"
        return f"{v:.{self._DEC}f}"

    # ════════════════════════════════════════════════════
    #  LINEAR GROUP FACTORY
    # ════════════════════════════════════════════════════
    def _linear_group(self, lay: QVBoxLayout, title: str,
                      units: List[Tuple[str, float]],
                      color: str = None,
                      formula: str = "") -> None:
        lay.addWidget(self._sec(title))
        frame = self._frm(); flay = frame.layout()
        fields: List[QLineEdit] = []
        lock = [False]

        def sync(src: int, txt: str) -> None:
            if lock[0]: return
            try:    base = float(txt) * units[src][1]
            except ValueError: return
            lock[0] = True
            for i, (_, f) in enumerate(units):
                if i != src:
                    fields[i].blockSignals(True)
                    fields[i].setText(self._fmt(base / f))
                    fields[i].blockSignals(False)
            lock[0] = False

        for i, (lbl, _) in enumerate(units):
            row = QHBoxLayout(); row.setSpacing(8)
            row.addWidget(self._lbl(lbl))
            e = self._inp(color)
            e.textEdited.connect(lambda t, idx=i: sync(idx, t))
            row.addWidget(e, 1); fields.append(e); flay.addLayout(row)

        if formula:
            flay.addWidget(self._formula(formula))
        lay.addWidget(frame)

    # ════════════════════════════════════════════════════
    #  TEMPERATURE  (non-linear)
    # ════════════════════════════════════════════════════
    def _build_temperature(self, lay: QVBoxLayout) -> None:
        lay.addWidget(self._sec("Temperature (溫度)"))
        frame = self._frm(); flay = frame.layout()
        lock = [False]; TF = {}

        def to_c(v, u):
            if u == "C": return v
            if u == "F": return (v - 32.0) * 5.0 / 9.0
            return v - 273.15

        def from_c(c, u):
            if u == "C": return c
            if u == "F": return c * 9.0 / 5.0 + 32.0
            return c + 273.15

        def sync(src, txt):
            if lock[0]: return
            try:    c = to_c(float(txt), src)
            except ValueError: return
            lock[0] = True
            for u, e in TF.items():
                if u != src:
                    e.blockSignals(True)
                    e.setText(f"{from_c(c, u):.{self._DEC}f}")
                    e.blockSignals(False)
            lock[0] = False

        for u, lbl in (("C", "°C   Celsius (攝氏)"),
                        ("F", "°F   Fahrenheit (華氏)"),
                        ("K", "K    Kelvin (克耳文)")):
            row = QHBoxLayout(); row.setSpacing(8)
            row.addWidget(self._lbl(lbl))
            e = self._inp(self._CYN)
            e.textEdited.connect(lambda t, su=u: sync(su, t))
            row.addWidget(e, 1); TF[u] = e; flay.addLayout(row)

        flay.addWidget(self._formula(
            "°F = °C × 9/5 + 32  │  K = °C + 273.15  │  0°C = 32°F = 273.15 K"))
        lay.addWidget(frame)

    # ════════════════════════════════════════════════════
    #  WIND SPEED  (Beaufort non-linear)
    # ════════════════════════════════════════════════════
    def _build_wind_speed(self, lay: QVBoxLayout) -> None:
        lay.addWidget(self._sec("Wind Speed (風速)"))
        frame = self._frm(); flay = frame.layout()
        lock = [False]; W = {}

        def sync_wind(src: str, txt: str) -> None:
            if lock[0]: return
            try: v = float(txt)
            except ValueError: return
            if src == "ms":    ms = v
            elif src == "kmh": ms = v / 3.6
            else:              ms = _MS_PER_BFT * (max(0.0, v) ** 1.5)
            kmh = ms * 3.6
            bft = (ms / _MS_PER_BFT) ** (2.0 / 3.0) if ms > 0 else 0.0
            lock[0] = True
            for k, val in (("ms", ms), ("kmh", kmh), ("bft", bft)):
                if k != src:
                    W[k].blockSignals(True)
                    W[k].setText(f"{val:.{self._DEC}f}")
                    W[k].blockSignals(False)
            lock[0] = False

        for k, lbl in (("ms",  "m/s         (公尺/秒)"),
                        ("kmh", "km/h        (公里/小時)"),
                        ("bft", "Beaufort    (蒲福風級 0–12)")):
            row = QHBoxLayout(); row.setSpacing(8)
            row.addWidget(self._lbl(lbl))
            e = self._inp(self._YEL)
            e.textEdited.connect(lambda t, sk=k: sync_wind(sk, t))
            row.addWidget(e, 1); W[k] = e; flay.addLayout(row)

        flay.addWidget(self._formula(
            "v(m/s) = 0.836 × B^1.5  │  B = (v ÷ 0.836)^(2/3)  "
            "│  B6 ≈ 12.3 m/s  │  B12 ≈ 32.7 m/s"))
        lay.addWidget(frame)

    # ════════════════════════════════════════════════════
    #  SCREW SIZE  (dropdown lookup reference)
    # ════════════════════════════════════════════════════
    def _build_screw_size(self, lay: QVBoxLayout) -> None:
        lay.addWidget(self._sec(
            "Screw Size (螺絲尺寸)  —  Metric ↔ Imperial Reference"))
        frame = self._frm(); flay = frame.layout()

        # Metric, Dia(mm), Pitch(mm), Imperial-equiv, Decimal-inch, Fractional-inch
        SCREWS = [
            ("M1.6", "1.6",  "0.35", "#0",     "0.060\"", "1/16\""),
            ("M2",   "2.0",  "0.40", "#2",     "0.086\"", "3/32\""),
            ("M2.5", "2.5",  "0.45", "#4",     "0.112\"", "7/64\""),
            ("M3",   "3.0",  "0.50", "#6",     "0.138\"", "9/64\""),
            ("M4",   "4.0",  "0.70", "#8",     "0.164\"", "5/32\""),
            ("M5",   "5.0",  "0.80", "#10",    "0.190\"", "3/16\""),
            ("M6",   "6.0",  "1.00", "1/4\"",  "0.250\"", "1/4\""),
            ("M8",   "8.0",  "1.25", "5/16\"", "0.313\"", "5/16\""),
            ("M10",  "10.0", "1.50", "3/8\"",  "0.375\"", "3/8\""),
            ("M12",  "12.0", "1.75", "1/2\"",  "0.500\"", "1/2\""),
            ("M16",  "16.0", "2.00", "5/8\"",  "0.625\"", "5/8\""),
            ("M20",  "20.0", "2.50", "3/4\"",  "0.750\"", "3/4\""),
            ("M24",  "24.0", "3.00", "1\"",    "1.000\"", "1\""),
        ]

        cb = QComboBox()
        for s in SCREWS: cb.addItem(f"{s[0]}  (ø {s[1]} mm · pitch {s[2]} mm)")
        cb.setFixedHeight(26)
        cb.setStyleSheet(
            f"QComboBox{{background:#2A2A2A;color:{self._LBL};"
            f"border:2px solid {self._BORDER};border-radius:3px;"
            f"font-size:9pt;font-weight:700;padding:1px 6px;"
            f"font-family:'Segoe UI','Microsoft JhengHei';}}"
            f"QComboBox:focus{{border:2px solid {self._ACC};}}"
            f"QComboBox::drop-down{{border:none;width:16px;}}"
            f"QComboBox QAbstractItemView{{background:#1E1E1E;color:{self._LBL};"
            f"border:1px solid {self._BORDER};"
            f"selection-background-color:{self._ACC};selection-color:#fff;}}")
        flay.addWidget(cb)

        HDR = ["Metric", "Dia (mm)", "Pitch (mm)", "Imperial", "Decimal\"", "Fractional\""]
        css_h = (f"color:{self._ACC};font-size:8.5pt;font-weight:700;"
                 f"background:transparent;border:none;"
                 f"font-family:'Segoe UI','Microsoft JhengHei';padding:1px 3px;")
        css_v = (f"color:{self._YEL};font-size:9.5pt;font-weight:700;"
                 f"background:transparent;border:none;"
                 f"font-family:Consolas,'Courier New';padding:1px 3px;")

        tbl = QGridLayout(); tbl.setSpacing(4); tbl.setContentsMargins(4, 4, 4, 4)
        val_lbls = []
        for ci, h in enumerate(HDR):
            hl = QLabel(h); hl.setStyleSheet(css_h); tbl.addWidget(hl, 0, ci)
            vl = QLabel("—"); vl.setStyleSheet(css_v); tbl.addWidget(vl, 1, ci)
            val_lbls.append(vl)

        info_f = QFrame()
        info_f.setStyleSheet(
            f"QFrame{{background:{self._DARK};"
            f"border:1px solid {self._BORDER};border-radius:3px;}}")
        info_f.setLayout(tbl); flay.addWidget(info_f)

        def on_select(idx):
            for ci, v in enumerate(SCREWS[idx]):
                val_lbls[ci].setText(v)

        cb.currentIndexChanged.connect(on_select); on_select(0)
        flay.addWidget(self._formula(
            "M-size ≈ outer diameter in mm  │  1 inch = 25.4 mm  "
            "│  Use nearest standard thread pitch"))
        lay.addWidget(frame)

    # ════════════════════════════════════════════════════
    #  TAB 1 — PHYSICAL  (物理類)
    # ════════════════════════════════════════════════════
    def _build_physical(self, lay: QVBoxLayout) -> None:

        self._linear_group(lay, "Length (長度)", [
            ("µm          (微米)",            1.0),
            ("mm          (毫米)",            1_000.0),
            ("cm          (公分)",            10_000.0),
            ("m           (公尺)",            1_000_000.0),
            ("km          (公里)",            1_000_000_000.0),
            ("inch        (英吋)",            25_400.0),
            ("ft          (英尺)",            304_800.0),
            ("yard        (碼)",              914_400.0),
            ("mil         (密耳 1/1000\")",   25.4),
        ], formula='1 m = 1,000 mm = 39.3701"  │  1 inch = 25.4 mm  │  1 ft = 304.8 mm')

        self._linear_group(lay, "Area (面積)", [
            ("mm²         (平方毫米)",         1.0),
            ("cm²         (平方公分)",         100.0),
            ("m²          (平方公尺)",         1_000_000.0),
            ("in²         (平方英吋)",         645.16),
            ("ft²         (平方英尺)",         92_903.04),
        ], formula="1 m² = 10,000 cm² = 10.7639 ft²  │  1 in² = 645.16 mm²")

        self._linear_group(lay, "Volume (體積)", [
            ("mL          (毫升)",             1.0),
            ("L           (公升)",             1_000.0),
            ("m³          (立方公尺)",         1_000_000.0),
            ("Gallon US   (美制加侖)",         3_785.411_784),
            ("Gallon UK   (英制加侖)",         4_546.09),
        ], formula="1 L = 1,000 mL  │  1 Gal(US) = 3.785 L  │  1 Gal(UK) = 4.546 L")

        self._linear_group(lay, "Mass (質量)", [
            ("g           (公克)",             1.0),
            ("kg          (公斤)",             1_000.0),
            ("Metric Ton  (公噸)",             1_000_000.0),
            ("lb          (磅)",               453.592_37),
            ("oz          (盎司)",             28.349_523),
        ], formula="1 kg = 2.20462 lb  │  1 lb = 453.592 g  │  1 oz = 28.3495 g")

        self._linear_group(lay, "Pressure (壓力)", [
            ("Pa          (帕斯卡)",           1.0),
            ("kPa         (千帕)",             1_000.0),
            ("MPa         (百萬帕)",           1_000_000.0),
            ("bar         (巴)",               100_000.0),
            ("psi         (磅/平方吋)",        6_894.757_293),
            ("kgf/cm²     (公斤力/cm²)",      98_066.5),
            ("mmH₂O       (水柱毫米)",         9.806_65),
            ("inHg        (汞柱英吋)",         3_386.389),
            ("Torr / mmHg (毫米汞柱)",         133.322_387),
            ("atm         (標準大氣壓)",       101_325.0),
        ], formula="1 bar = 100,000 Pa = 14.5038 psi  │  1 atm = 101,325 Pa = 1.01325 bar")

        self._linear_group(lay, "Acceleration (加速度)", [
            ("m/s²        (公尺/秒²)",         1.0),
            ("G-Force     (重力加速度)",        9.806_65),
        ], formula="1 G = 9.80665 m/s²  (standard gravity 標準重力加速度)")

        self._linear_group(lay, "Velocity (速度)", [
            ("m/s         (公尺/秒)",           1.0),
            ("km/h        (公里/小時)",         1.0 / 3.6),
            ("ft/s        (英尺/秒)",           0.304_8),
            ("mph         (英里/小時)",         0.447_04),
            ("Knot        (節/海里每時)",        0.514_444),
        ], formula="1 m/s = 3.6 km/h  │  1 mph = 1.60934 km/h  │  1 Knot = 1.852 km/h")

        self._build_temperature(lay)

    # ════════════════════════════════════════════════════
    #  TAB 2 — ELECTRICAL  (電氣類)
    # ════════════════════════════════════════════════════
    def _build_electrical(self, lay: QVBoxLayout) -> None:

        self._linear_group(lay, "Power (功率)", [
            ("W           (瓦特)",             1.0),
            ("kW          (千瓦)",             1_000.0),
            ("MW          (百萬瓦)",           1_000_000.0),
            ("HP Imperial (英制馬力)",         745.699_872),
            ("PS Metric   (公制馬力)",         735.499),
        ], color=self._CYN,
           formula="1 kW = 1,000 W  │  1 HP = 745.70 W  │  1 PS = 735.50 W")

        self._linear_group(lay, "Energy (能量)", [
            ("J           (焦耳)",             1.0),
            ("Wh          (瓦時)",             3_600.0),
            ("kWh         (千瓦時)",           3_600_000.0),
            ("BTU         (英熱單位)",         1_055.055_85),
            ("Cal         (卡路里)",           4.184),
        ], formula="1 kWh = 3,600,000 J  │  1 BTU = 1,055.06 J  │  1 Cal = 4.184 J")

        self._linear_group(lay, "Charge (電荷)", [
            ("C / Coulomb (庫侖)",             1.0),
            ("Ah          (安培時)",           3_600.0),
            ("mAh         (毫安培時)",         3.6),
        ], formula="1 Ah = 3,600 C  │  1 mAh = 3.6 C  │  Q = I × t")

        self._linear_group(lay, "Frequency (頻率)", [
            ("Hz          (赫茲)",             1.0),
            ("kHz         (千赫茲)",           1_000.0),
            ("MHz         (百萬赫茲)",         1_000_000.0),
            ("GHz         (十億赫茲)",         1_000_000_000.0),
        ], color=self._CYN,
           formula="1 GHz = 1,000 MHz = 1×10⁶ kHz = 1×10⁹ Hz")

        self._linear_group(lay, "Resistance (電阻)", [
            ("Ω           (歐姆)",             1.0),
            ("kΩ          (千歐姆)",           1_000.0),
            ("MΩ          (百萬歐姆)",         1_000_000.0),
        ], formula="1 kΩ = 1,000 Ω  │  1 MΩ = 1,000 kΩ  │  R = V ÷ I  (Ohm's Law)")

        self._linear_group(lay, "Voltage (電位差)", [
            ("mV          (毫伏特)",           1.0),
            ("V           (伏特)",             1_000.0),
            ("kV          (千伏特)",           1_000_000.0),
        ], color=self._CYN,
           formula="1 V = 1,000 mV  │  1 kV = 1,000 V  │  V = I × R")

        self._linear_group(lay, "Current (電流)", [
            ("mA          (毫安培)",           1.0),
            ("A           (安培)",             1_000.0),
            ("kA          (千安培)",           1_000_000.0),
        ], formula="1 A = 1,000 mA  │  1 kA = 1,000 A  │  I = V ÷ R")

    # ════════════════════════════════════════════════════
    #  TAB 3 — SCIENCE & DATA  (科學與資訊類)
    # ════════════════════════════════════════════════════
    def _build_science(self, lay: QVBoxLayout) -> None:

        self._linear_group(lay, "Angle (角度)", [
            ("Degree      (度)",               1.0),
            ("Radian      (弧度)",             180.0 / pi),
            ("Grad        (梯度/百分度)",       0.9),
        ], formula="1 rad = 180°/π ≈ 57.296°  │  360° = 2π rad = 400 Grad")

        self._linear_group(lay, "Duration (時長)", [
            ("ms          (毫秒)",             1.0),
            ("s           (秒)",               1_000.0),
            ("min         (分鐘)",             60_000.0),
            ("hr          (小時)",             3_600_000.0),
            ("day         (天)",               86_400_000.0),
        ], formula="1 hr = 3,600 s = 3,600,000 ms  │  1 day = 24 hr = 86,400 s")

        self._linear_group(lay, "Data Storage (資訊儲存)", [
            ("bit         (位元)",             1.0),
            ("Byte        (位元組)",           8.0),
            ("KB          (千位元組 KiB)",     8_192.0),
            ("MB          (兆位元組 MiB)",     8_388_608.0),
            ("GB          (吉位元組 GiB)",     8_589_934_592.0),
            ("TB          (太位元組 TiB)",     8_796_093_022_208.0),
        ], formula="1 Byte = 8 bits  │  1 KB = 1,024 B  │  1 GB = 1,024 MB  (IEC binary)")

        self._linear_group(lay, "Concentration (濃度質量)", [
            ("g/L         (克/升)",            1.0),
            ("mg/L        (毫克/升)",          0.001),
            ("ppm         (mg/kg ≈ mg/L)",     0.001),
        ], formula="1 g/L = 1,000 mg/L ≈ 1,000 ppm  (dilute aqueous 稀薄水溶液近似)")

        self._build_wind_speed(lay)

        self._linear_group(lay, "Illuminance (照度)", [
            ("lux / lx       (勒克斯 lm/m²)",      1.0),
            ("foot-candle / fc  (英尺燭光 lm/ft²)", 10.763_9),
        ], color=self._CYN,
           formula="1 fc = 10.7639 lx  │  lux = lm/m²  │  fc = lm/ft²")

        self._linear_group(lay, "Bandwidth (網路頻寬)", [
            ("bps         (位元/秒)",           1.0),
            ("kbps        (千位元/秒)",         1_000.0),
            ("Mbps        (百萬位元/秒)",       1_000_000.0),
            ("Gbps        (十億位元/秒)",       1_000_000_000.0),
        ], formula="1 Gbps = 1,000 Mbps = 1×10⁶ kbps  (SI decimal, not binary)")

        self._build_screw_size(lay)
