# tool_network.py — IP Monitor + Network Scanner + Modbus TCP Viewer
# Part of the Clawde Industrial Engineering Suite
# Bilingual: English Primary / Traditional Chinese Secondary

import subprocess, sys, time
from datetime import datetime
from typing import Callable, Optional, Dict, List

from PyQt6.QtCore    import Qt, QTimer, QThread, QObject, pyqtSignal
from PyQt6.QtGui     import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtWidgets import (QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLineEdit, QTextEdit, QScrollArea,
                              QTabWidget, QComboBox, QGridLayout, QSizePolicy)

from styles import BaseToolWindow, load_config, save_config, IP_LOG_FILE, _DEFAULT_CONFIG

# ── Optional: pymodbus ──────────────────────────────────────────────────────
try:
    from pymodbus.client import ModbusTcpClient as _MTC
    _MODBUS_OK = True
except ImportError:
    try:
        from pymodbus.client.sync import ModbusTcpClient as _MTC  # type: ignore
        _MODBUS_OK = True
    except ImportError:
        _MODBUS_OK = False

_MAX_SWEEP = 24   # max concurrent ping workers

# ═══════════════════════════════════════════════════════
#  PING WORKER
# ═══════════════════════════════════════════════════════
class PingWorker(QThread):
    done = pyqtSignal(str, bool, float)   # ip, alive, ms

    def __init__(self, ip: str):
        super().__init__(); self.ip = ip

    def run(self):
        t0 = time.monotonic()
        try:
            if sys.platform == "win32":
                r = subprocess.run(
                    ["ping", "-n", "1", "-w", "1000", self.ip],
                    capture_output=True, timeout=4,
                    creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                r = subprocess.run(
                    ["ping", "-c", "1", "-W", "1", self.ip],
                    capture_output=True, timeout=4)
            alive = r.returncode == 0
        except Exception:
            alive = False
        self.done.emit(self.ip, alive, (time.monotonic() - t0) * 1000)


# ═══════════════════════════════════════════════════════
#  SWEEP MANAGER
# ═══════════════════════════════════════════════════════
class SweepManager(QObject):
    result   = pyqtSignal(str, bool, float)
    finished = pyqtSignal()

    def __init__(self, ips: list):
        super().__init__()
        self._queue = list(ips)
        self._active: Dict[str, PingWorker] = {}
        self._stopped = False

    def start(self):
        self._stopped = False
        for _ in range(min(_MAX_SWEEP, len(self._queue))):
            self._launch()

    def stop(self):
        self._stopped = True
        self._queue.clear()
        for w in self._active.values():
            try: w.terminate()
            except Exception: pass
        self._active.clear()

    def _launch(self):
        if not self._queue or self._stopped: return
        ip = self._queue.pop(0)
        w = PingWorker(ip)
        w.done.connect(self._on_done)
        self._active[ip] = w; w.start()

    def _on_done(self, ip: str, alive: bool, ms: float):
        self._active.pop(ip, None)
        self.result.emit(ip, alive, ms)
        if self._queue and not self._stopped:
            self._launch()
        elif not self._active:
            self.finished.emit()


# ═══════════════════════════════════════════════════════
#  MODBUS READ WORKER
# ═══════════════════════════════════════════════════════
class ModbusReadWorker(QThread):
    result = pyqtSignal(list, str)   # registers_list, error_msg

    def __init__(self, ip: str, port: int, unit_id: int,
                 reg_type: str, start: int, count: int):
        super().__init__()
        self.ip = ip; self.port = port; self.unit_id = unit_id
        self.reg_type = reg_type; self.start = start; self.count = count

    def run(self):
        if not _MODBUS_OK:
            self.result.emit([], "pymodbus not installed.\nRun:  pip install pymodbus")
            return
        try:
            client = _MTC(self.ip, port=self.port, timeout=3)
            client.connect()
            kw = {"slave": self.unit_id}
            try:
                rr = (client.read_holding_registers(self.start, self.count, **kw)
                      if self.reg_type == "Holding"
                      else client.read_input_registers(self.start, self.count, **kw))
            except TypeError:
                kw = {"unit": self.unit_id}
                rr = (client.read_holding_registers(self.start, self.count, **kw)
                      if self.reg_type == "Holding"
                      else client.read_input_registers(self.start, self.count, **kw))
            client.close()
            if hasattr(rr, "registers"):
                self.result.emit(list(rr.registers), "")
            else:
                self.result.emit([], f"Modbus Error: {rr}")
        except Exception as ex:
            self.result.emit([], str(ex))


# ═══════════════════════════════════════════════════════
#  IP CHANNEL ROW  (Monitor tab)
# ═══════════════════════════════════════════════════════
class IPChannelRow(QWidget):
    log_event = pyqtSignal(str)
    _DOT  = {"idle": "#363636", "ok": "#00c853", "fail": "#f44336", "checking": "#FF8000"}
    _TEXT = {"idle": "待機", "ok": "Online ✅", "fail": "Offline ❌", "checking": "…"}

    def __init__(self, idx: int):
        super().__init__()
        self.index = idx; self._status = "idle"
        self._down_since: Optional[datetime] = None
        self._worker: Optional[PingWorker]   = None
        self.setFixedHeight(32)
        lay = QHBoxLayout(self); lay.setContentsMargins(2, 1, 2, 1); lay.setSpacing(5)
        self.dot = QLabel("●"); self.dot.setFixedWidth(16)
        self.dot.setStyleSheet("color:#363636;font-size:13px;background:transparent;")
        self.lbl_in = QLineEdit(f"CH{idx+1:02d}")
        self.lbl_in.setFixedWidth(68); self.lbl_in.setFixedHeight(24)
        self.ip_in  = QLineEdit()
        self.ip_in.setFixedWidth(130); self.ip_in.setFixedHeight(24)
        self.ip_in.setPlaceholderText("192.168.1.xxx")
        self.st_lbl = QLabel("待機"); self.st_lbl.setFixedWidth(76)
        self.st_lbl.setStyleSheet("color:#363636;font-size:10px;background:transparent;")
        self.info = QLabel("")
        self.info.setStyleSheet("color:#484848;font-size:10px;background:transparent;")
        self.info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.dot); lay.addWidget(self.lbl_in)
        lay.addWidget(self.ip_in); lay.addWidget(self.st_lbl); lay.addWidget(self.info)

    def get_config(self): return {"label": self.lbl_in.text(), "ip": self.ip_in.text()}
    def set_config(self, c):
        self.lbl_in.setText(c.get("label", "")); self.ip_in.setText(c.get("ip", ""))

    def ping_once(self):
        ip = self.ip_in.text().strip()
        if not ip: return
        if self._worker and self._worker.isRunning(): return
        self._worker = PingWorker(ip)
        self._worker.done.connect(self._on_ping); self._worker.start()
        self._apply("checking")

    def reset_idle(self):
        self._status = "idle"; self._down_since = None
        self.info.setText(""); self._apply("idle")

    def _on_ping(self, ip: str, alive: bool, ms: float):
        lbl = self.lbl_in.text(); now = datetime.now()
        ts  = now.strftime("%Y-%m-%d %H:%M:%S")
        if alive:
            if self._status == "fail" and self._down_since:
                secs = int((now - self._down_since).total_seconds())
                self.log_event.emit(f"[{ts}] ✅ UP   {ip} ({lbl})  停機 {secs}s")
            self._down_since = None
            self.info.setText(f"{ms:.0f} ms"); self._apply("ok")
        else:
            if self._status != "fail":
                self._down_since = now
                self.log_event.emit(f"[{ts}] ❌ DOWN {ip} ({lbl})")
            else:
                secs = int((now - self._down_since).total_seconds()) if self._down_since else 0
                self.info.setText(f"Down {secs}s")
            self._apply("fail")

    def _apply(self, s: str):
        self._status = s; c = self._DOT.get(s, "#363636")
        self.dot.setStyleSheet(f"color:{c};font-size:13px;background:transparent;")
        self.st_lbl.setText(self._TEXT.get(s, s))
        self.st_lbl.setStyleSheet(f"color:{c};font-size:10px;background:transparent;")


# ═══════════════════════════════════════════════════════
#  IP MONITOR  (main tool window — 3 tabs)
# ═══════════════════════════════════════════════════════
class IPMonitor(BaseToolWindow):

    _BG     = "#121212"
    _CELL   = "#1E1E1E"
    _DARK   = "#0D0D0D"
    _BORDER = "#3D3D3D"
    _LBL    = "#FFFFFF"
    _LBL2   = "#A0A0A0"
    _YEL    = "#FFFF00"
    _CYN    = "#00FFFF"
    _ACC    = "#FF8800"
    _OK     = "#00FF88"
    _WARN   = "#FF4444"

    def __init__(self, on_thinking: Callable = None):
        super().__init__("🌐 Network Suite (網路診斷套件)", 580, 700)
        self.setMinimumSize(480, 500)
        self._on_thinking = on_thinking
        self._log: list = []
        self._poll = QTimer(self); self._poll.timeout.connect(self._poll_all)
        self._sweeper: Optional[SweepManager] = None
        self._scan_rows: Dict[str, dict] = {}
        self._scan_online = 0; self._scan_total = 0; self._sw_done_count = 0
        self._mb_worker: Optional[ModbusReadWorker] = None

        self.content.setStyleSheet(f"background:{self._BG};")
        root = QVBoxLayout(self.content)
        root.setContentsMargins(6, 4, 6, 2); root.setSpacing(4)

        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane{{background:{self._BG};"
            f"border:1px solid {self._BORDER};border-radius:4px;margin-top:-1px;}}"
            f"QTabBar::tab{{background:#1A1A1A;color:{self._LBL2};"
            f"padding:6px 12px;font-size:9pt;font-weight:700;"
            f"font-family:'Segoe UI','Microsoft JhengHei';"
            f"border-top-left-radius:4px;border-top-right-radius:4px;margin-right:2px;}}"
            f"QTabBar::tab:selected{{background:{self._BG};color:{self._ACC};"
            f"border-top:2px solid {self._ACC};}}"
            f"QTabBar::tab:hover:!selected{{background:#2A2A2A;color:{self._LBL};}}")

        tabs.addTab(self._wrap(self._build_monitor_tab), "🔵  Monitor (IP監控)")
        tabs.addTab(self._wrap(self._build_scanner_tab), "🔍  Scanner (範圍掃描)")
        tabs.addTab(self._wrap(self._build_modbus_tab),  "📡  Modbus TCP")
        root.addWidget(tabs, 1)

        sb = QLabel(
            "Bang Bang Cat (邦邦貓)  │  Network & Motor Power Diagnostic  │  Formula Verified")
        sb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb.setFixedHeight(20)
        sb.setStyleSheet(
            f"color:#404040;font-size:7.5pt;font-weight:600;"
            f"background:#0A0A0A;border-top:1px solid {self._BORDER};"
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
    def _wrap(self, builder) -> QScrollArea:
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
        vbox.setSpacing(6); vbox.setContentsMargins(8, 8, 10, 8)
        builder(vbox); vbox.addStretch()
        scroll.setWidget(inner); return scroll

    def _sec(self, txt: str) -> QLabel:
        l = QLabel(f"  {txt}"); l.setFixedHeight(22)
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

    def _inp(self, c: str = None, ph: str = "", w: int = None, ro: bool = False) -> QLineEdit:
        col = c or self._YEL
        e = QLineEdit(); e.setPlaceholderText(ph)
        e.setFixedHeight(24); e.setReadOnly(ro)
        if w: e.setFixedWidth(w)
        border = "border:1px solid #252525;" if ro else f"border:2px solid {self._BORDER};"
        e.setStyleSheet(
            f"QLineEdit{{background:{self._DARK};color:{col};"
            f"{border}border-radius:3px;"
            f"font-size:9.5pt;font-weight:bold;"
            f"font-family:Consolas,'Courier New';padding:1px 6px;}}"
            + (f"QLineEdit:focus{{border:2px solid {self._ACC};}}" if not ro else ""))
        return e

    def _sm(self, default: str = "", c: str = None, w: int = 80) -> QLineEdit:
        e = QLineEdit(default); e.setFixedHeight(22); e.setFixedWidth(w)
        e.setStyleSheet(
            f"QLineEdit{{background:#1A1A1A;color:{c or self._LBL};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:9pt;font-weight:bold;"
            f"font-family:Consolas,'Courier New';padding:1px 5px;}}"
            f"QLineEdit:focus{{border:1px solid {self._ACC};}}")
        return e

    def _lbl(self, txt: str, w: int = 170, c: str = None) -> QLabel:
        l = QLabel(txt); l.setMinimumWidth(w)
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
        l = QLabel(txt); l.setWordWrap(True)
        l.setStyleSheet(
            f"color:#2ABFBF;font-size:8pt;font-weight:600;"
            f"background:#0F1A1A;border:1px solid #1A3030;border-radius:3px;"
            f"padding:3px 8px;margin-top:2px;"
            f"font-family:Consolas,'Courier New';")
        return l

    def _btn(self, txt: str, w: int = None, bg: str = None) -> QPushButton:
        b = QPushButton(txt); b.setFixedHeight(26)
        if w: b.setFixedWidth(w)
        b.setStyleSheet(
            f"QPushButton{{background:{bg or self._CELL};color:{self._LBL};"
            f"border:1px solid {self._BORDER};border-radius:3px;"
            f"font-size:9pt;font-weight:700;padding:0 10px;"
            f"font-family:'Segoe UI','Microsoft JhengHei';}}"
            f"QPushButton:hover{{background:{self._ACC};color:#fff;}}"
            f"QPushButton:disabled{{background:#1A1A1A;color:#383838;border-color:#282828;}}")
        return b

    def _cbo(self, items: list, default: int = 0) -> QComboBox:
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
            f"selection-background-color:{self._ACC};selection-color:#fff;}}")
        return cb

    def _hsep(self) -> QFrame:
        s = QFrame(); s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet(
            f"border:none;border-top:1px solid {self._BORDER};background:transparent;")
        return s

    def _row(self, lbl_txt: str, field: QLineEdit,
             layout: QVBoxLayout, unit: str = "") -> None:
        r = QHBoxLayout(); r.setSpacing(8)
        r.addWidget(self._lbl(lbl_txt))
        r.addWidget(field, 1)
        if unit:
            u = QLabel(unit); u.setFixedWidth(36)
            u.setStyleSheet(
                f"color:{self._LBL2};font-size:8pt;background:transparent;border:none;")
            r.addWidget(u)
        layout.addLayout(r)

    # ════════════════════════════════════════════════════
    #  TAB 1 — IP MONITOR
    # ════════════════════════════════════════════════════
    def _build_monitor_tab(self, lay: QVBoxLayout) -> None:
        lay.addWidget(self._sec("IP Channel Monitor (IP 通道監控)  —  10 Channels Auto-Ping"))
        f1 = self._frm(); fl = f1.layout()

        ctrl = QHBoxLayout()
        self.start_btn = self._btn("▶ Start (開始)", 106, "#1A3A1A")
        self.stop_btn  = self._btn("■ Stop (停止)",  100)
        self.stop_btn.setEnabled(False)
        self.save_btn  = self._btn("💾 Save Log", 90)
        il = self._dim("Interval (間隔):"); il.setFixedWidth(100)
        self.int_in = self._sm("10", self._LBL, 40)
        ctrl.addWidget(self.start_btn); ctrl.addWidget(self.stop_btn)
        ctrl.addWidget(il); ctrl.addWidget(self.int_in); ctrl.addWidget(self._dim("s"))
        ctrl.addStretch(); ctrl.addWidget(self.save_btn)
        fl.addLayout(ctrl)

        hdr = QHBoxLayout(); hdr.setContentsMargins(4, 0, 4, 0)
        for txt, w in [("", 16), ("Label (標籤)", 68), ("IP Address", 130),
                       ("Status (狀態)", 76), ("Info", 0)]:
            l = QLabel(txt)
            l.setStyleSheet(
                f"color:{self._LBL2};font-size:9pt;font-weight:700;background:transparent;")
            if w: l.setFixedWidth(w)
            else: l.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            hdr.addWidget(l)
        fl.addLayout(hdr)
        fl.addWidget(self._hsep())

        self._channels: list = []
        ch_w = QWidget(); ch_w.setStyleSheet("background:transparent;")
        cl   = QVBoxLayout(ch_w); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(1)
        cfgs = load_config().get("ip_channels", _DEFAULT_CONFIG["ip_channels"])
        for i in range(10):
            row = IPChannelRow(i)
            if i < len(cfgs): row.set_config(cfgs[i])
            row.log_event.connect(self._on_log)
            self._channels.append(row); cl.addWidget(row)
        cl.addStretch()
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setWidget(ch_w)
        sc.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        sc.setFixedHeight(240)
        fl.addWidget(sc)

        lh = QHBoxLayout()
        lh.addWidget(self._dim("Event Log (事件記錄)")); lh.addStretch()
        cb = self._btn("Clear 清除", 80)
        cb.clicked.connect(self._clear_log); lh.addWidget(cb)
        fl.addLayout(lh)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True); self.log_box.setFixedHeight(100)
        self.log_box.setStyleSheet(
            f"background:{self._DARK};color:#585858;font-size:9.5pt;"
            f"border:1px solid {self._BORDER};border-radius:3px;padding:4px;"
            f"font-family:Consolas,'Courier New',monospace;")
        fl.addWidget(self.log_box)

        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.save_btn.clicked.connect(self._save)
        lay.addWidget(f1)

    # ════════════════════════════════════════════════════
    #  TAB 2 — NETWORK SCANNER
    # ════════════════════════════════════════════════════
    def _build_scanner_tab(self, lay: QVBoxLayout) -> None:
        lay.addWidget(self._sec(
            "Network Range Scanner (網路範圍掃描)  —  ICMP Ping Sweep"))
        f1 = self._frm(); fl = f1.layout()

        # Range input
        rng = QHBoxLayout(); rng.setSpacing(6)
        rng.addWidget(self._dim("IP Prefix (網段):"))
        self._sw_prefix = self._sm("192.168.1", self._YEL, 112)
        rng.addWidget(self._sw_prefix)
        rng.addWidget(self._dim("  ."))
        self._sw_start  = self._sm("1",   self._YEL, 42)
        rng.addWidget(self._sw_start)
        rng.addWidget(self._dim("—"))
        self._sw_end    = self._sm("254", self._YEL, 42)
        rng.addWidget(self._sw_end)
        rng.addStretch()
        fl.addLayout(rng)

        # Controls
        ctrl = QHBoxLayout(); ctrl.setSpacing(6)
        self._sw_btn      = self._btn("▶ Scan (掃描)", 110, "#1A2A1A")
        self._sw_stop_btn = self._btn("■ Stop (停止)", 90)
        self._sw_stop_btn.setEnabled(False)
        self._sw_prog    = QLabel("Ready (待機)")
        self._sw_prog.setStyleSheet(
            f"color:{self._LBL2};font-size:9pt;background:transparent;")
        self._sw_summary = QLabel("")
        self._sw_summary.setStyleSheet(
            f"color:{self._OK};font-size:9pt;font-weight:700;background:transparent;")
        ctrl.addWidget(self._sw_btn); ctrl.addWidget(self._sw_stop_btn)
        ctrl.addWidget(self._sw_prog, 1); ctrl.addWidget(self._sw_summary)
        fl.addLayout(ctrl)
        self._sw_btn.clicked.connect(self._start_sweep)
        self._sw_stop_btn.clicked.connect(self._stop_sweep)

        # Table header
        fl.addWidget(self._hsep())
        hdr = QHBoxLayout(); hdr.setSpacing(4); hdr.setContentsMargins(4, 0, 4, 0)
        for txt, w in [("IP Address (IP位址)", 122), ("Status (狀態)", 92),
                       ("Latency (延遲)", 72), ("Notes (備註)", 0)]:
            l = QLabel(txt)
            l.setStyleSheet(
                f"color:{self._ACC};font-size:8.5pt;font-weight:700;"
                f"background:{self._DARK};border-bottom:1px solid {self._BORDER};"
                f"padding:2px 4px;")
            if w: l.setFixedWidth(w)
            else: l.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            hdr.addWidget(l)
        fl.addLayout(hdr)

        # Scrollable result area
        self._scan_inner = QWidget()
        self._scan_inner.setStyleSheet("background:transparent;")
        self._scan_vbox  = QVBoxLayout(self._scan_inner)
        self._scan_vbox.setContentsMargins(0, 0, 0, 0); self._scan_vbox.setSpacing(0)
        self._scan_vbox.addStretch()

        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setWidget(self._scan_inner)
        sc.setStyleSheet(
            f"QScrollArea{{background:transparent;"
            f"border:1px solid {self._BORDER};border-radius:3px;}}"
            f"QScrollBar:vertical{{background:#1A1A1A;width:8px;border:none;margin:0;}}"
            f"QScrollBar::handle:vertical{{background:#3D3D3D;border-radius:4px;min-height:20px;}}"
            f"QScrollBar::handle:vertical:hover{{background:{self._ACC};}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}")
        sc.setMinimumHeight(300)
        fl.addWidget(sc, 1)
        fl.addWidget(self._formula(
            "Logic: ICMP Ping Sweep  │  Status: ICMP Echo Reply  "
            "│  Latency = Round-trip Time (RTT ms)"))
        lay.addWidget(f1)

    def _parse_sweep_range(self) -> Optional[List[str]]:
        try:
            prefix = self._sw_prefix.text().strip()
            s = int(self._sw_start.text()); e = int(self._sw_end.text())
            if not (1 <= s <= 254 and 1 <= e <= 254 and s <= e):
                raise ValueError("Range 1–254, start ≤ end")
            return [f"{prefix}.{i}" for i in range(s, e + 1)]
        except Exception as ex:
            self._sw_prog.setText(f"❌ {ex}")
            self._sw_prog.setStyleSheet(
                f"color:{self._WARN};font-size:9pt;background:transparent;")
            return None

    def _clear_scan_table(self):
        while self._scan_vbox.count() > 1:
            item = self._scan_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._scan_rows.clear()

    def _create_scan_row(self, ip: str):
        row_w = QWidget(); row_w.setFixedHeight(26)
        row_w.setStyleSheet(
            f"background:{self._CELL};"
            f"border-bottom:1px solid {self._DARK};"
            f"border-left:none;border-right:none;border-top:none;")
        rl = QHBoxLayout(row_w); rl.setContentsMargins(4, 1, 4, 1); rl.setSpacing(4)

        ip_l = QLabel(ip); ip_l.setFixedWidth(122)
        ip_l.setStyleSheet(
            f"color:{self._LBL};font-size:8.5pt;font-weight:600;"
            f"background:transparent;border:none;font-family:Consolas,'Courier New';")
        dot = QLabel("◉"); dot.setFixedWidth(14)
        dot.setStyleSheet("color:#3A3A3A;font-size:11px;background:transparent;border:none;")
        st = QLabel("…"); st.setFixedWidth(78)
        st.setStyleSheet(
            f"color:#3A3A3A;font-size:8.5pt;font-weight:600;"
            f"background:transparent;border:none;")
        lat = QLabel("—"); lat.setFixedWidth(72)
        lat.setStyleSheet(
            f"color:{self._LBL2};font-size:8.5pt;"
            f"background:transparent;border:none;font-family:Consolas,'Courier New';")
        notes = QLineEdit(); notes.setPlaceholderText("Notes…"); notes.setFixedHeight(22)
        notes.setStyleSheet(
            f"QLineEdit{{background:#151515;color:{self._LBL2};"
            f"border:1px solid #282828;border-radius:2px;"
            f"font-size:8.5pt;padding:0 4px;}}"
            f"QLineEdit:focus{{border-color:{self._ACC};}}")

        rl.addWidget(ip_l); rl.addWidget(dot); rl.addWidget(st)
        rl.addWidget(lat); rl.addWidget(notes, 1)
        self._scan_vbox.insertWidget(self._scan_vbox.count() - 1, row_w)
        self._scan_rows[ip] = {"dot": dot, "st": st, "lat": lat, "row": row_w}

    def _update_scan_row(self, ip: str, alive: bool, ms: float):
        row = self._scan_rows.get(ip)
        if not row: return
        if alive:
            row["dot"].setStyleSheet(
                f"color:{self._OK};font-size:11px;background:transparent;border:none;")
            row["st"].setText("✅ Online")
            row["st"].setStyleSheet(
                f"color:{self._OK};font-size:8.5pt;font-weight:700;"
                f"background:transparent;border:none;")
            row["lat"].setText(f"{ms:.0f} ms")
            row["row"].setStyleSheet(
                f"background:#0D1A0D;border-bottom:1px solid {self._DARK};"
                f"border-left:none;border-right:none;border-top:none;")
        else:
            row["dot"].setStyleSheet(
                f"color:{self._WARN};font-size:11px;background:transparent;border:none;")
            row["st"].setText("❌ Offline")
            row["st"].setStyleSheet(
                f"color:{self._WARN};font-size:8.5pt;font-weight:600;"
                f"background:transparent;border:none;")
            row["lat"].setText("—")

    def _start_sweep(self):
        ips = self._parse_sweep_range()
        if not ips: return
        self._clear_scan_table()
        self._scan_online = 0; self._scan_total = len(ips); self._sw_done_count = 0
        for ip in ips:
            self._create_scan_row(ip)
        self._sw_prog.setText(f"Scanning… 0 / {self._scan_total}")
        self._sw_prog.setStyleSheet(
            f"color:{self._YEL};font-size:9pt;background:transparent;")
        self._sw_summary.setText("")
        self._sw_btn.setEnabled(False); self._sw_stop_btn.setEnabled(True)
        self._sweeper = SweepManager(ips)
        self._sweeper.result.connect(self._on_sweep_result)
        self._sweeper.finished.connect(self._on_sweep_done)
        self._sweeper.start()

    def _on_sweep_result(self, ip: str, alive: bool, ms: float):
        self._sw_done_count += 1
        if alive: self._scan_online += 1
        self._update_scan_row(ip, alive, ms)
        pct = self._sw_done_count * 100 // max(1, self._scan_total)
        self._sw_prog.setText(
            f"Scanning… {self._sw_done_count} / {self._scan_total}  ({pct}%)")

    def _on_sweep_done(self):
        self._sw_prog.setText(f"✅ Complete (掃描完成)  {self._scan_total} IPs checked")
        self._sw_prog.setStyleSheet(
            f"color:{self._OK};font-size:9pt;background:transparent;")
        self._sw_summary.setText(f"Online: {self._scan_online} / {self._scan_total}")
        self._sw_btn.setEnabled(True); self._sw_stop_btn.setEnabled(False)

    def _stop_sweep(self):
        if self._sweeper: self._sweeper.stop()
        self._sw_prog.setText("■ Stopped (已停止)")
        self._sw_prog.setStyleSheet(
            f"color:{self._LBL2};font-size:9pt;background:transparent;")
        self._sw_btn.setEnabled(True); self._sw_stop_btn.setEnabled(False)

    # ════════════════════════════════════════════════════
    #  TAB 3 — MODBUS TCP VIEWER
    # ════════════════════════════════════════════════════
    def _build_modbus_tab(self, lay: QVBoxLayout) -> None:
        lay.addWidget(self._sec("Modbus TCP Viewer (Modbus TCP 讀取器)"))
        f1 = self._frm(); fl = f1.layout()

        # Connection config
        r1 = QHBoxLayout(); r1.setSpacing(8)
        r1.addWidget(self._dim("IP:"))
        self._mb_ip   = self._sm("192.168.1.1", self._YEL, 120)
        r1.addWidget(self._mb_ip)
        r1.addWidget(self._dim("Port:"))
        self._mb_port = self._sm("502", self._YEL, 52)
        r1.addWidget(self._mb_port)
        r1.addWidget(self._dim("Unit ID:"))
        self._mb_uid  = self._sm("1", self._YEL, 42)
        r1.addWidget(self._mb_uid); r1.addStretch()
        fl.addLayout(r1)

        r2 = QHBoxLayout(); r2.setSpacing(8)
        r2.addWidget(self._dim("Register Type (暫存器類型):"))
        self._mb_type = self._cbo(
            ["Holding Registers (保持暫存器 4x)", "Input Registers (輸入暫存器 3x)"])
        self._mb_type.setFixedWidth(260)
        r2.addWidget(self._mb_type)
        r2.addWidget(self._dim("Start Addr:"))
        self._mb_addr = self._sm("0", self._YEL, 60)
        r2.addWidget(self._mb_addr)
        r2.addWidget(self._dim("Count:"))
        self._mb_cnt  = self._sm("10", self._YEL, 50)
        r2.addWidget(self._mb_cnt); r2.addStretch()
        fl.addLayout(r2)

        r3 = QHBoxLayout(); r3.setSpacing(8)
        self._mb_read_btn = self._btn("▶ Read Registers (讀取暫存器)", 210, "#1A1A2A")
        self._mb_status   = QLabel("Ready (待機)")
        self._mb_status.setStyleSheet(
            f"color:{self._LBL2};font-size:9pt;background:transparent;")
        r3.addWidget(self._mb_read_btn); r3.addWidget(self._mb_status, 1)
        fl.addLayout(r3)
        self._mb_read_btn.clicked.connect(self._do_modbus_read)

        fl.addWidget(self._formula(
            "Logic: Modbus TCP Protocol  │  Unit ID & Register Address Verification  "
            "│  FC=0x03 (Holding 4x)  │  FC=0x04 (Input 3x)"))
        fl.addWidget(self._hsep())

        # Table header
        hdr = QHBoxLayout(); hdr.setSpacing(2); hdr.setContentsMargins(4, 0, 4, 0)
        for txt, w in [("Addr", 52), ("DEC (無號)", 80), ("HEX", 72),
                       ("INT16 (有號)", 74), ("BIN (16-bit)", 0)]:
            l = QLabel(txt)
            l.setStyleSheet(
                f"color:{self._ACC};font-size:8.5pt;font-weight:700;"
                f"background:{self._DARK};border-bottom:1px solid {self._BORDER};"
                f"padding:2px 4px;")
            if w: l.setFixedWidth(w)
            else: l.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            hdr.addWidget(l)
        fl.addLayout(hdr)

        # Scrollable result
        self._mb_inner = QWidget()
        self._mb_inner.setStyleSheet("background:transparent;")
        self._mb_vbox  = QVBoxLayout(self._mb_inner)
        self._mb_vbox.setContentsMargins(0, 0, 0, 0); self._mb_vbox.setSpacing(0)
        self._mb_vbox.addStretch()

        mb_sc = QScrollArea(); mb_sc.setWidgetResizable(True)
        mb_sc.setWidget(self._mb_inner)
        mb_sc.setStyleSheet(
            f"QScrollArea{{background:transparent;"
            f"border:1px solid {self._BORDER};border-radius:3px;}}"
            f"QScrollBar:vertical{{background:#1A1A1A;width:8px;border:none;margin:0;}}"
            f"QScrollBar::handle:vertical{{background:#3D3D3D;border-radius:4px;min-height:20px;}}"
            f"QScrollBar::handle:vertical:hover{{background:{self._ACC};}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}")
        mb_sc.setMinimumHeight(220)
        fl.addWidget(mb_sc, 1)

        if not _MODBUS_OK:
            warn = QLabel(
                "⚠  pymodbus not installed — run:  pip install pymodbus  "
                "to enable Modbus TCP reading.")
            warn.setWordWrap(True)
            warn.setStyleSheet(
                f"color:{self._WARN};font-size:8.5pt;font-weight:600;"
                f"background:#1A0D0D;border:1px solid #3A1A1A;border-radius:3px;"
                f"padding:4px 8px;")
            fl.addWidget(warn)

        lay.addWidget(f1)

    def _do_modbus_read(self):
        if self._mb_worker and self._mb_worker.isRunning():
            self._mb_status.setText("⚠ Already reading…"); return
        try:
            ip   = self._mb_ip.text().strip()
            port = int(self._mb_port.text())
            uid  = int(self._mb_uid.text())
            addr = int(self._mb_addr.text())
            cnt  = max(1, min(125, int(self._mb_cnt.text())))
            rtype = "Holding" if self._mb_type.currentIndex() == 0 else "Input"
        except ValueError as ex:
            self._mb_status.setText(f"❌ Input error: {ex}"); return

        self._mb_status.setText("⏳ Connecting…")
        self._mb_status.setStyleSheet(
            f"color:{self._YEL};font-size:9pt;background:transparent;")
        self._mb_read_btn.setEnabled(False)

        self._mb_worker = ModbusReadWorker(ip, port, uid, rtype, addr, cnt)
        self._mb_worker.result.connect(
            lambda regs, err, a=addr: self._on_modbus_result(regs, err, a))
        self._mb_worker.start()

    def _on_modbus_result(self, regs: list, err: str, start_addr: int):
        self._mb_read_btn.setEnabled(True)
        if err:
            self._mb_status.setText(f"❌ {err[:80]}")
            self._mb_status.setStyleSheet(
                f"color:{self._WARN};font-size:9pt;background:transparent;")
            return
        self._mb_status.setText(f"✅ {len(regs)} registers read OK")
        self._mb_status.setStyleSheet(
            f"color:{self._OK};font-size:9pt;background:transparent;")

        while self._mb_vbox.count() > 1:
            item = self._mb_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        for i, val in enumerate(regs):
            addr  = start_addr + i
            sint  = val if val < 32768 else val - 65536
            b     = f"{val:016b}"
            bdisp = f"{b[0:4]} {b[4:8]} {b[8:12]} {b[12:16]}"
            odd   = self._CELL if i % 2 == 0 else "#1A1A1A"

            row_w = QWidget(); row_w.setFixedHeight(24)
            row_w.setStyleSheet(
                f"background:{odd};border-bottom:1px solid {self._DARK};"
                f"border-left:none;border-right:none;border-top:none;")
            rl = QHBoxLayout(row_w); rl.setContentsMargins(4, 0, 4, 0); rl.setSpacing(2)

            def cell(txt, w, c=None):
                l = QLabel(txt)
                if w: l.setFixedWidth(w)
                else: l.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Preferred)
                l.setStyleSheet(
                    f"color:{c or self._LBL};font-size:8.5pt;font-weight:600;"
                    f"background:transparent;border:none;"
                    f"font-family:Consolas,'Courier New';padding:1px 2px;")
                return l

            rl.addWidget(cell(str(addr),      52, self._ACC))
            rl.addWidget(cell(str(val),       80, self._LBL))
            rl.addWidget(cell(f"0x{val:04X}", 72, self._CYN))
            rl.addWidget(cell(str(sint),      74, self._YEL if sint < 0 else self._LBL))
            rl.addWidget(cell(bdisp,           0, self._LBL2))
            self._mb_vbox.insertWidget(self._mb_vbox.count() - 1, row_w)

    # ════════════════════════════════════════════════════
    #  MONITOR TAB — LOGIC
    # ════════════════════════════════════════════════════
    def _start(self):
        try: s = max(3, int(self.int_in.text()))
        except ValueError: s = 10
        self._save_ch(); self._poll.start(s * 1000); self._poll_all()
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)

    def _stop(self):
        self._poll.stop()
        for ch in self._channels: ch.reset_idle()
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)

    def _poll_all(self):
        if callable(self._on_thinking): self._on_thinking()
        for ch in self._channels: ch.ping_once()

    def _on_log(self, msg: str):
        self._log.append(msg)
        self.log_box.setPlainText("\n".join(self._log[-200:]))
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum())

    def _clear_log(self): self._log.clear(); self.log_box.clear()

    def _save(self):
        if not self._log: return
        try:
            with open(IP_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*58}\n儲存：{datetime.now():%Y-%m-%d %H:%M:%S}\n")
                f.write("\n".join(self._log) + "\n")
            self._on_log(f"[{datetime.now():%H:%M:%S}] 📄 Saved → clawde_ip_log.txt")
        except Exception as e:
            self._on_log(f"[ERR] {e}")

    def _save_ch(self):
        cfg = load_config()
        cfg["ip_channels"] = [c.get_config() for c in self._channels]
        save_config(cfg)
