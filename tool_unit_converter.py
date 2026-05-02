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
        tabs.addTab(self._tab(self._build_pipe_size),     "🔧  管材尺寸對照")
        tabs.addTab(self._tab(self._build_wire_ampacity), "🔌  電線安培容量")
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
    #  PIPE SIZE  (管材尺寸對照)  — full reference table
    # ════════════════════════════════════════════════════
    def _build_pipe_size(self, lay: QVBoxLayout) -> None:

        # (尺寸, 台規OD, 台規ID, 日規OD, 日規公稱, 美規OD, 美規ID, 德規OD, 另稱)
        PIPES = [
            ('1/8"',   '',    '',    '',    '',            '',       '',       '6',        '一分'),
            ('1/4"',   '',    '',    '',    '',            '',       '',       '10',       '二分'),
            ('3/8"',   '',    '',    '',    '13A',         '',       '',       '16',       '三分'),
            ('1/2"',   '22',  '17',  '22',  '15A / 16',   '21.34', '13.36',  '20',       '四分'),
            ('3/4"',   '27',  '22',  '26',  '20A / 20',   '26.67', '18.34',  '25',       '六分'),
            ('1"',     '34',  '28',  '32',  '25A / 25',   '33.4',  '23.77',  '32',       '1 吋'),
            ('1-1/4"', '42',  '35',  '38',  '30A / 31',   '42.16', '31.88',  '40',       '1 吋 2'),
            ('1-1/2"', '48',  '40',  '48',  '40A / 40',   '48.26', '37.49',  '50',       '1 吋半'),
            ('2"',     '60',  '51',  '60',  '50A / 51',   '60.33', '48.59',  '63',       '2 吋'),
            ('2-1/2"', '76',  '68',  '76',  '65A / 67',   '73.03', '58.17',  '75',       '2 吋半'),
            ('3"',     '89',  '79',  '89',  '75A / 77',   '88.9',  '72.75',  '90',       '3 吋'),
            ('4"',     '114', '103', '114', '100A / 100', '114.3', '96.16',  '110',      ''),
            ('5"',     '',    '',    '',    '125A',        '',       '',       '125',      ''),
            ('5-1/2"', '140', '127', '140', '',            '',       '',       '140',      ''),
            ('6"',     '165', '',    '165', '150A / 146',  '168.28','145.01', '160',      ''),
            ('8"',     '216', '',    '216', '200A / 194',  '219.08','192.15', '200/225',  ''),
            ('10"',    '267', '',    '',    '250A',        '273.05','241.12', '250',      ''),
            ('12"',    '318', '',    '',    '',            '323.85','286.87', '315',      ''),
            ('14"',    '',    '',    '',    '',            '',       '',       '',         ''),
            ('16"',    '',    '',    '',    '',            '',       '',       '',         ''),
        ]

        # ── Column layout (0=尺寸, 1=TW_OD, 2=TW_ID, 3=JIS_OD, 4=JIS_NOM,
        #                   5=ANSI_OD, 6=ANSI_ID, 7=DIN_OD, 8=另稱) ─────────
        GRP_HDR = [                           # (label, color, col_start, span)
            ("尺寸",      "#CCCCCC", 0, 1),
            ("台規 TW",   self._ACC, 1, 2),
            ("日規 JIS",  self._CYN, 3, 2),
            ("美規 ANSI", "#00FF88", 5, 2),
            ("德規 DIN",  self._YEL, 7, 1),
            ("另稱",      "#AAAAAA", 8, 1),
        ]
        SUB_HDR = ["尺寸", "外徑", "內徑", "外徑", "公稱", "外徑", "內徑", "外徑", "名稱"]

        BG_ODD  = "#181818"
        BG_EVEN = "#121212"
        BG_HDR  = "#0D0D0D"

        def _cell(text, fg, bg, bold=True, fs=8):
            l = QLabel(text)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet(
                f"color:{fg};font-size:{fs}pt;font-weight:{'700' if bold else '500'};"
                f"background:{bg};border:none;padding:3px 4px;"
                f"font-family:Consolas,'Courier New','Microsoft JhengHei';")
            return l

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame{{background:{self._DARK};"
            f"border:1px solid {self._BORDER};border-radius:6px;}}")
        grid = QGridLayout(frame)
        grid.setSpacing(1); grid.setContentsMargins(1, 1, 1, 1)

        # Row 0 — group headers
        for lbl, clr, cs, span in GRP_HDR:
            g = _cell(lbl, clr, BG_HDR, bold=True, fs=8)
            grid.addWidget(g, 0, cs, 1, span)

        # Row 1 — sub-headers
        for ci, sh in enumerate(SUB_HDR):
            grid.addWidget(_cell(sh, self._LBL2, BG_HDR, bold=False, fs=7), 1, ci)

        # Rows 2+ — data
        for ri, p in enumerate(PIPES):
            bg = BG_ODD if ri % 2 else BG_EVEN
            row_data = [p[0], p[1], p[2], p[3], p[4],
                        p[5], p[6], p[7], p[8]]
            fg_map   = ["#FFFFFF", self._ACC, self._ACC,
                        self._CYN, self._CYN,
                        "#00FF88", "#00FF88",
                        self._YEL, "#AAAAAA"]
            for ci, (val, fg) in enumerate(zip(row_data, fg_map)):
                grid.addWidget(
                    _cell(val or "—", fg, bg, bold=bool(val), fs=8),
                    ri + 2, ci)

        lay.addWidget(frame)
        lay.addWidget(self._formula(
            "台規 CNS  │  日規 JIS (公稱 A)  │  美規 ANSI / IPS  "
            "│  德規 DIN / EN  │  單位：mm  │  ※ 管材外徑為例"))

    # ════════════════════════════════════════════════════
    #  WIRE AMPACITY  (電線安培容量對照表)
    # ════════════════════════════════════════════════════
    def _build_wire_ampacity(self, lay: QVBoxLayout) -> None:

        # ── Main ampacity table ────────────────────────────────────
        # (mm², AWG, 管內1-3條(A), 空氣中(A), 建議斷路器(A), 用途說明)
        WIRES = [
            ("1.25",  "AWG 16", "13",  "18",  "15",  "插座分路 / 照明"),
            ("2.0",   "AWG 14", "18",  "25",  "20",  "一般插座"),
            ("3.5",   "AWG 12", "26",  "35",  "30",  "冷氣 1.5HP"),
            ("5.5",   "AWG 10", "35",  "47",  "40",  "冷氣 3HP"),
            ("8",     "AWG 8",  "46",  "63",  "50",  "冷氣 5HP / 小動力"),
            ("14",    "AWG 6",  "63",  "87",  "70",  "動力幹線"),
            ("22",    "AWG 4",  "84",  "112", "80",  "動力幹線"),
            ("30",    "AWG 2",  "100", "138", "100", "動力幹線"),
            ("38",    "AWG 1",  "123", "162", "125", "動力幹線"),
            ("50",    "AWG 1/0","145", "190", "150", "低壓幹線"),
            ("60",    "AWG 2/0","164", "216", "175", "低壓幹線"),
            ("80",    "AWG 3/0","199", "260", "200", "低壓幹線"),
            ("100",   "AWG 4/0","231", "297", "250", "低壓主幹線"),
            ("125",   "250MCM", "266", "344", "300", "低壓主幹線"),
            ("150",   "300MCM", "302", "386", "350", "低壓主幹線"),
            ("200",   "400MCM", "360", "456", "400", "低壓主幹線"),
        ]

        GRP_HDR = [
            ("線徑 mm²", "#CCCCCC", 0, 1),
            ("AWG 對照", "#AAAAAA", 1, 1),
            ("管內配線", self._CYN,  2, 1),
            ("空氣中",   "#00FF88", 3, 1),
            ("斷路器",   self._ACC, 4, 1),
            ("常見用途", self._YEL, 5, 1),
        ]
        SUB_HDR = ["mm²", "AWG", "A (管內)", "A (空氣)", "A (建議)", "用途"]

        BG_ODD  = "#181818"
        BG_EVEN = "#121212"
        BG_HDR  = "#0D0D0D"

        def _cell(text, fg, bg, bold=True, fs=8):
            l = QLabel(text)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet(
                f"color:{fg};font-size:{fs}pt;"
                f"font-weight:{'700' if bold else '500'};"
                f"background:{bg};border:none;padding:4px 5px;"
                f"font-family:Consolas,'Courier New','Microsoft JhengHei';")
            return l

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame{{background:{self._DARK};"
            f"border:1px solid {self._BORDER};border-radius:6px;}}")
        grid = QGridLayout(frame)
        grid.setSpacing(1); grid.setContentsMargins(1, 1, 1, 1)

        for lbl, clr, cs, span in GRP_HDR:
            grid.addWidget(_cell(lbl, clr, BG_HDR, bold=True, fs=8), 0, cs, 1, span)
        for ci, sh in enumerate(SUB_HDR):
            grid.addWidget(_cell(sh, self._LBL2, BG_HDR, bold=False, fs=7), 1, ci)

        FG = ["#FFFFFF", "#AAAAAA", self._CYN, "#00FF88", self._ACC, self._YEL]
        for ri, row in enumerate(WIRES):
            bg = BG_ODD if ri % 2 else BG_EVEN
            for ci, (val, fg) in enumerate(zip(row, FG)):
                grid.addWidget(_cell(val, fg, bg, bold=(ci < 4), fs=8), ri + 2, ci)

        lay.addWidget(frame)

        # ── Temperature derating table ────────────────────────────
        lay.addWidget(self._sec("溫度修正係數  Temperature Derating Factor"))
        df = QFrame()
        df.setStyleSheet(
            f"QFrame{{background:{self._DARK};"
            f"border:1px solid {self._BORDER};border-radius:6px;}}")
        dg = QGridLayout(df)
        dg.setSpacing(1); dg.setContentsMargins(1, 1, 1, 1)

        TEMPS = [
            ("環境溫度", "30°C", "35°C", "40°C", "45°C", "50°C"),
            ("修正係數", "1.00", "0.94", "0.87", "0.82", "0.75"),
        ]
        TCLR = ["#AAAAAA", "#00FF88", "#CCCC00", self._ACC, "#FF6622", "#FF2222"]
        for ri, row in enumerate(TEMPS):
            fg0 = self._LBL2 if ri == 0 else self._YEL
            for ci, val in enumerate(row):
                fg = fg0 if ci == 0 else TCLR[ci]
                bg = BG_HDR if ri == 0 else BG_EVEN
                dg.addWidget(_cell(val, fg, bg, bold=(ri == 0), fs=8), ri, ci)

        lay.addWidget(df)
        lay.addWidget(self._formula(
            "依據 CNS 1364 / CNS 1365  │  600V PVC 銅導線  │  基準溫度 30°C  "
            "│  管內 1~3 條  │  實際安培 = 表列值 × 溫度修正係數"))

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

    # ════════════════════════════════════════════════════
    #  TAB 4 — PIPE SIZE REFERENCE
    # ════════════════════════════════════════════════════
    def _build_pipe_size(self, lay: QVBoxLayout):
        HDR   = "#FF8800"
        COL_TW = "#FF8800"   # 台規
        COL_JP = "#00FFFF"   # 日規
        COL_US = "#00FF88"   # 美規
        COL_DE = "#FFFF00"   # 德規
        COL_AL = "#A0A0A0"   # 另稱

        def _hdr(txt, color="#FFFFFF"):
            l = QLabel(txt); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet(
                f"color:{color};font-size:8pt;font-weight:700;"
                f"background:#1A1A1A;padding:3px 2px;"
                f"font-family:'Microsoft JhengHei','Segoe UI';")
            return l

        def _cell(txt, color="#CCCCCC", bg="#1E1E1E"):
            l = QLabel(txt); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setWordWrap(True)
            l.setStyleSheet(
                f"color:{color};font-size:7.8pt;"
                f"background:{bg};padding:2px 2px;"
                f"font-family:'Segoe UI','Microsoft JhengHei';")
            return l

        note = QLabel(
            "管材尺寸對照表  Pipe Size Reference  │  單位 mm (外徑 OD / 內徑 ID)\n"
            "台規 CNS 12017  │  日規 JIS B 2311  │  美規 ASTM A53  │  德規 DIN 2440")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{self._LBL2};font-size:8pt;background:#1A1A1A;"
            f"border-left:3px solid {HDR};padding:4px 8px;border-radius:3px;")
        lay.addWidget(note)

        grid = QGridLayout(); grid.setSpacing(1); grid.setContentsMargins(0, 4, 0, 4)

        headers = [
            ("尺寸\nSize",     "#FFFFFF"),
            ("台規\nOD / ID",  COL_TW),
            ("日規\nOD / 公稱",COL_JP),
            ("美規\nOD / ID",  COL_US),
            ("德規\nOD",       COL_DE),
            ("另稱\nAlso",     COL_AL),
        ]
        for c, (txt, col) in enumerate(headers):
            grid.addWidget(_hdr(txt, col), 0, c)

        # size_name, tw_od/id, jp_od/nom, us_od/id, de_od, alias
        rows = [
            ("1/8\"",   "10.5 / 6.8",  "10.5 / DN6",   "10.3 / 6.8",   "—",           "PT1/8, G1/8"),
            ("1/4\"",   "13.8 / 9.6",  "13.8 / DN8",   "13.7 / 9.2",   "—",           "PT1/4"),
            ("3/8\"",   "17.3 / 12.7", "17.3 / DN10",  "17.1 / 12.5",  "—",           "PT3/8"),
            ("1/2\"",   "21.7 / 16.1", "21.7 / DN15",  "21.3 / 15.8",  "21.3",        "4分管"),
            ("3/4\"",   "26.9 / 21.3", "26.9 / DN20",  "26.7 / 20.9",  "26.9",        "6分管"),
            ("1\"",     "33.4 / 27.1", "33.4 / DN25",  "33.4 / 26.6",  "33.7",        "1吋管"),
            ("1¼\"",    "42.2 / 35.9", "42.4 / DN32",  "42.2 / 35.1",  "42.4",        "1.25吋"),
            ("1½\"",    "48.3 / 41.9", "48.6 / DN40",  "48.3 / 40.9",  "48.3",        "1.5吋管"),
            ("2\"",     "60.3 / 52.5", "60.5 / DN50",  "60.3 / 52.5",  "60.3",        "2吋管"),
            ("2½\"",    "76.3 / 62.7", "76.3 / DN65",  "73.0 / 62.7",  "76.1",        "2.5吋"),
            ("3\"",     "89.1 / 80.7", "89.1 / DN80",  "88.9 / 77.9",  "88.9",        "3吋管"),
            ("3½\"",    "101.6 / 90.1","—",             "101.6 / 90.1", "—",           "3.5吋"),
            ("4\"",     "114.3/104.1", "114.3 / DN100","114.3/102.3",  "114.3",       "4吋管"),
            ("5\"",     "139.8/128.2", "—",             "141.3/128.2",  "—",           "5吋"),
            ("6\"",     "165.2/154.1", "165.2 / DN150","168.3/154.1",  "168.3",       "6吋管"),
            ("8\"",     "216.3/202.7", "216.3 / DN200","219.1/202.7",  "219.1",       "8吋管"),
            ("10\"",    "267.4/251.4", "267.4 / DN250","273.1/254.5",  "273.0",       "10吋"),
            ("12\"",    "318.5/300.8", "318.5 / DN300","323.8/303.2",  "323.9",       "12吋"),
            ("14\"",    "355.6/336.6", "355.6 / DN350","355.6/336.6",  "—",           "14吋"),
            ("16\"",    "406.4/385.9", "406.4 / DN400","406.4/385.9",  "—",           "16吋"),
        ]
        col_colors = [COL_TW, COL_JP, COL_US, COL_DE, COL_AL]
        for r, row in enumerate(rows):
            bg = "#191919" if r % 2 == 0 else "#212121"
            grid.addWidget(_cell(row[0], "#FFFFFF", bg), r + 1, 0)
            for c, (val, clr) in enumerate(zip(row[1:], col_colors)):
                grid.addWidget(_cell(val, clr, bg), r + 1, c + 1)

        frame = QFrame()
        frame.setStyleSheet(f"QFrame{{background:{self._CELL};border:1px solid {self._BORDER};border-radius:4px;}}")
        fl = QVBoxLayout(frame); fl.setContentsMargins(2, 2, 2, 2)
        fl.addLayout(grid)
        lay.addWidget(frame)

    # ════════════════════════════════════════════════════
    #  TAB 5 — WIRE AMPACITY REFERENCE
    # ════════════════════════════════════════════════════
    def _build_wire_ampacity(self, lay: QVBoxLayout):
        HDR_CLR  = "#FF8800"
        MM2_CLR  = "#FFFFFF"
        AWG_CLR  = "#00FFFF"
        IN_CLR   = "#FF8800"
        AIR_CLR  = "#00FF88"
        CB_CLR   = "#FFFF00"
        USE_CLR  = "#A0A0A0"

        def _hdr(txt, color="#FF8800"):
            l = QLabel(txt); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setWordWrap(True)
            l.setStyleSheet(
                f"color:{color};font-size:8pt;font-weight:700;"
                f"background:#1A1A1A;padding:3px 2px;"
                f"font-family:'Microsoft JhengHei','Segoe UI';")
            return l

        def _cell(txt, color="#CCCCCC", bg="#1E1E1E"):
            l = QLabel(txt); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setWordWrap(True)
            l.setStyleSheet(
                f"color:{color};font-size:7.8pt;"
                f"background:{bg};padding:2px 2px;"
                f"font-family:'Segoe UI','Microsoft JhengHei';")
            return l

        note = QLabel(
            "電線安培容量對照表  Wire Ampacity Reference\n"
            "依據 CNS 1364 / CNS 1365  600V PVC 銅導線  基準溫度 30°C  管內配線 1~3 條")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{self._LBL2};font-size:8pt;background:#1A1A1A;"
            f"border-left:3px solid {HDR_CLR};padding:4px 8px;border-radius:3px;")
        lay.addWidget(note)

        # ── Main ampacity table ──────────────────────────
        grid = QGridLayout(); grid.setSpacing(1); grid.setContentsMargins(0, 4, 0, 4)

        hdrs = [
            ("mm²",             MM2_CLR),
            ("AWG\n(近似)",     AWG_CLR),
            ("管內\n配線 A",    IN_CLR),
            ("空氣中\n敷設 A",  AIR_CLR),
            ("建議\n斷路器 A",  CB_CLR),
            ("常見用途",        USE_CLR),
        ]
        for c, (txt, clr) in enumerate(hdrs):
            grid.addWidget(_hdr(txt, clr), 0, c)

        # mm2, awg, conduit_A, air_A, breaker_A, usage
        rows = [
            ("1.25",  "AWG 16", "15",  "19",  "15",   "照明 控制迴路"),
            ("2.0",   "AWG 14", "20",  "27",  "20",   "插座 一般迴路"),
            ("3.5",   "AWG 12", "27",  "35",  "30",   "冷氣 空調"),
            ("5.5",   "AWG 10", "37",  "49",  "40",   "大型冷氣 小馬達"),
            ("8.0",   "AWG 8",  "50",  "65",  "50",   "馬達 幹線"),
            ("14",    "AWG 6",  "67",  "91",  "75",   "幹線 配電盤"),
            ("22",    "AWG 4",  "90",  "120", "100",  "主幹線"),
            ("30",    "AWG 3",  "105", "138", "110",  "主幹線"),
            ("38",    "AWG 2",  "120", "162", "125",  "主幹線"),
            ("50",    "AWG 1",  "140", "190", "150",  "主幹線 變壓器"),
            ("60",    "AWG 1/0","155", "212", "175",  "大型幹線"),
            ("80",    "AWG 2/0","180", "245", "200",  "大型幹線"),
            ("100",   "AWG 3/0","205", "280", "225",  "主幹線 引進線"),
            ("125",   "AWG 4/0","235", "320", "250",  "引進線"),
            ("150",   "250 kcmil","260","355","300",  "大型引進線"),
            ("200",   "350 kcmil","305","415","350",  "變電設備 引進線"),
        ]
        col_colors = [MM2_CLR, AWG_CLR, IN_CLR, AIR_CLR, CB_CLR, USE_CLR]
        for r, row in enumerate(rows):
            bg = "#191919" if r % 2 == 0 else "#212121"
            for c, (val, clr) in enumerate(zip(row, col_colors)):
                grid.addWidget(_cell(val, clr, bg), r + 1, c)

        frame1 = QFrame()
        frame1.setStyleSheet(f"QFrame{{background:{self._CELL};border:1px solid {self._BORDER};border-radius:4px;}}")
        fl1 = QVBoxLayout(frame1); fl1.setContentsMargins(2, 2, 2, 2)
        fl1.addLayout(grid)
        lay.addWidget(frame1)

        # ── Temperature derating table ───────────────────
        sec = QLabel("  溫度修正係數  Temperature Correction Factor")
        sec.setFixedHeight(22)
        sec.setStyleSheet(
            f"color:{HDR_CLR};font-size:9pt;font-weight:700;"
            f"background:#1A1A1A;border-left:3px solid {HDR_CLR};padding-left:6px;"
            f"font-family:'Segoe UI','Microsoft JhengHei';")
        lay.addWidget(sec)

        dgrid = QGridLayout(); dgrid.setSpacing(1); dgrid.setContentsMargins(0, 4, 0, 4)
        derating = [
            ("環境溫度°C", "30", "35", "40", "45", "50"),
            ("修正係數",   "1.00","0.94","0.87","0.82","0.75"),
        ]
        d_colors = ["#FF8800", "#00FF88", "#FFFF44", "#FFA040", "#FF6040", "#FF3030"]
        for r, row in enumerate(derating):
            for c, val in enumerate(row):
                clr = "#FFFFFF" if c == 0 else d_colors[c]
                bg  = "#1A1A1A" if r == 0 else "#1E1E1E"
                fw  = "font-weight:700;" if r == 0 else ""
                l   = QLabel(val); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                l.setStyleSheet(
                    f"color:{clr};font-size:8pt;{fw}"
                    f"background:{bg};padding:4px 6px;"
                    f"font-family:'Segoe UI','Microsoft JhengHei';")
                dgrid.addWidget(l, r, c)

        frame2 = QFrame()
        frame2.setStyleSheet(f"QFrame{{background:{self._CELL};border:1px solid {self._BORDER};border-radius:4px;}}")
        fl2 = QVBoxLayout(frame2); fl2.setContentsMargins(2, 2, 2, 2)
        fl2.addLayout(dgrid)
        lay.addWidget(frame2)

        src = QLabel("資料來源：CNS 1364 / CNS 1365，台灣線材業參考值。實際配線依現場條件與工程師判斷。")
        src.setWordWrap(True)
        src.setStyleSheet(
            f"color:#606060;font-size:7.5pt;padding:2px 4px;"
            f"font-family:'Microsoft JhengHei','Segoe UI';")
        lay.addWidget(src)
