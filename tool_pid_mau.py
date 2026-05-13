# tool_pid_mau.py — MAU 7-Stage PID Simulator  V2
# OA → HTC-1 → CC-1 → Washer → CC-2 → HTC-2 → Fan
# All stages have FOPDT; click-to-select; manual MV; editable PV range

import math
from collections import deque
from dataclasses import dataclass

from PyQt6.QtCore    import (Qt, QTimer, QThread, QRect, QPoint, QPointF,
                              pyqtSignal, pyqtSlot, QPropertyAnimation, QEasingCurve)
from PyQt6.QtGui     import (QPainter, QColor, QPen, QPainterPath,
                              QFont, QPolygonF, QBrush, QLinearGradient)
from PyQt6.QtCore    import QObject
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QComboBox,
    QScrollArea, QStackedWidget, QFileDialog,
)
from styles import (BaseToolWindow, load_config, save_config,
                    THEMES, get_theme_idx, ThemePicker)


# ═══════════════════════════════════════════════════════
#  PSYCHROMETRIC PHYSICS
# ═══════════════════════════════════════════════════════
class Psych:
    P = 101.325
    @staticmethod
    def pws(T):  return 0.61078 * math.exp(17.27 * T / (T + 237.3))
    @staticmethod
    def omega(T, RH):
        pw = Psych.pws(T) * max(0.0, min(100.0, RH)) / 100.0
        return 0.62198 * pw / max(1e-9, Psych.P - pw)
    @staticmethod
    def omega_sat(T):  return Psych.omega(T, 100.0)
    @staticmethod
    def rh(T, w):
        pw = w * Psych.P / (0.62198 + w)
        return min(100.0, pw / max(1e-9, Psych.pws(T)) * 100.0)
    @staticmethod
    def enthalpy(T, w):  return 1.006 * T + w * (2501.0 + 1.86 * T)
    @staticmethod
    def t_dp(w):
        pw = w * Psych.P / (0.62198 + w)
        if pw <= 0: return -50.0
        r = math.log(pw / 0.61078)
        return 237.3 * r / (17.27 - r)
    @staticmethod
    def t_wb(T_db, w):
        h_in = Psych.enthalpy(T_db, w)
        lo = max(-10.0, Psych.t_dp(w)); hi = T_db
        for _ in range(40):
            mid = (lo + hi) * 0.5
            if Psych.enthalpy(mid, Psych.omega_sat(mid)) < h_in: lo = mid
            else: hi = mid
        return (lo + hi) * 0.5


@dataclass
class AirState:
    T: float = 20.0;  w: float = 0.008
    def copy(self):       return AirState(self.T, self.w)
    @property
    def RH(self):         return Psych.rh(self.T, self.w)
    @property
    def h(self):          return Psych.enthalpy(self.T, self.w)
    @property
    def T_dp(self):       return Psych.t_dp(self.w)
    @property
    def T_wb(self):       return Psych.t_wb(self.T, self.w)
    @property
    def w_gkg(self):      return self.w * 1000.0


# ═══════════════════════════════════════════════════════
#  PID CONTROLLER
# ═══════════════════════════════════════════════════════
class PidCtrl:
    def __init__(self, Kp, Ki, Kd, reverse=False, mv_lo=0.0, mv_hi=100.0):
        self.Kp = Kp; self.Ki = Ki; self.Kd = Kd
        self.reverse = reverse; self.mv_lo = mv_lo; self.mv_hi = mv_hi
        self._int = 0.0; self._prev_e = 0.0
        self.auto = True; self.manual_mv = (mv_lo + mv_hi) / 2.0
        self._mv = self.manual_mv
    def reset(self, mv=None):
        self._int = 0.0; self._prev_e = 0.0
        self._mv = mv if mv is not None else self.manual_mv
    def compute(self, PV, SP, dt):
        if not self.auto:
            self._mv = max(self.mv_lo, min(self.mv_hi, self.manual_mv)); return self._mv
        e = (SP - PV) if self.reverse else (PV - SP)
        if self.Ki > 1e-9:
            ilim = (self.mv_hi - self.mv_lo) / self.Ki
            self._int = max(-ilim, min(ilim, self._int + e * dt))
        de = (e - self._prev_e) / max(dt, 1e-6); self._prev_e = e
        self._mv = max(self.mv_lo, min(self.mv_hi,
                       self.Kp * e + self.Ki * self._int + self.Kd * de))
        return self._mv
    @property
    def mv(self): return self._mv


# ═══════════════════════════════════════════════════════
#  FOPDT COIL / STAGE MODEL
# ═══════════════════════════════════════════════════════
class FopdtCoil:
    def __init__(self, Kp, tau, L, heating=True, dt=0.05):
        self.Kp = Kp; self.tau = tau; self.L = L; self.heating = heating
        self._dT = 0.0
        n = max(1, round(L / dt))
        self._buf: deque = deque([0.0] * n, maxlen=n)
    def reset(self):
        self._dT = 0.0
        n = self._buf.maxlen; self._buf = deque([0.0] * n, maxlen=n)
    def step(self, MV, dt, fan_scale=1.0):
        self._buf.append(MV); mv_d = self._buf[0]
        alpha = min(1.0, dt / max(self.tau, 1e-3))
        sign = 1.0 if self.heating else -1.0
        self._dT += alpha * (self.Kp * fan_scale * mv_d * sign - self._dT)
        return self._dT


# ═══════════════════════════════════════════════════════
#  STAGE METADATA
# ═══════════════════════════════════════════════════════
_SNAMES = ["OA\nINLET", "HTC-1\nPREHEAT", "CC-1\nPRECOOL",
           "WASHER\nHUMIDIFY", "CC-2\nDEHUMID", "HTC-2\nREHEAT", "SUPPLY\nFAN"]
_SBGCLR = ["#060C1C","#1C0A04","#040C1C","#041410","#040A1C","#14090A","#07051A"]
_SACCNT = ["#3D8EFF","#FF6B35","#00D4FF","#00FF9F","#2E86FF","#FFB300","#BB77FF"]


# ═══════════════════════════════════════════════════════
#  SCHEMATIC  (top painter widget)
# ═══════════════════════════════════════════════════════
class _MauSchematic(QWidget):
    def __init__(self, select_cb=None, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220); self._states = [AirState(6.0, 0.003)] * 7
        self._mvs = [0.0]*6; self._p_static = 2000.0; self._fan_hz = 45.0
        self._angle = 0.0; self._sel = -1; self._select_cb = select_cb

    def set_selected(self, stage_idx: int):
        self._sel = stage_idx; self.update()

    def stage_connect_points(self):
        """Return (center_x, box_bottom_y) for each of the 7 stage boxes in widget coords."""
        W, H = self.width(), self.height()
        n = 7; mg = 10; GAP = 22
        LBL_H = 30; STRIP_H = 85; STAT_H = 26; PIPE_H = 85
        avail_bw = W - 2*mg - (n-1)*GAP
        bw = max(60, avail_bw // n)
        box_bot = H - STRIP_H - STAT_H - 2
        return [(mg + i*(bw+GAP) + bw//2, box_bot) for i in range(n)]

    def isa_instrument_positions(self):
        """Return 6 (cx, cy) in widget coords for ISA circles — one per faceplate (fp[0..5])."""
        W, H = self.width(), self.height()
        n = 7; mg = 10; GAP = 22
        LBL_H = 30; STRIP_H = 85; STAT_H = 26; PIPE_H = 85
        avail_bw = W - 2*mg - (n-1)*GAP
        bw = max(60, avail_bw // n)
        box_top = mg + PIPE_H + LBL_H + 2
        box_bot = H - STRIP_H - STAT_H - 2
        bh = max(80, box_bot - box_top)
        r_s = 9
        isa_y = box_top + bh // 2
        # fp[0..2]: gap positions 2-4 (outlet of HTC1, CC1, Washer)
        pts = [(mg + i*(bw+GAP) - GAP//2, isa_y) for i in range(2, 5)]
        # fp[3] (CC-2 DP), fp[4] (HTC-2 T), fp[5] (Fan P) at far right
        ix_fan  = W - mg - r_s - 2
        ix_htc2 = ix_fan  - 2*r_s - 6
        ix_cc2  = ix_htc2 - 2*r_s - 6
        pts.append((ix_cc2,  isa_y))
        pts.append((ix_htc2, isa_y))
        pts.append((ix_fan,  isa_y))
        return pts

    def refresh(self, states, mvs, p_static, fan_hz):
        self._states = states; self._mvs = mvs
        self._p_static = p_static; self._fan_hz = fan_hz
        self._angle = (self._angle + fan_hz * 0.5) % 360.0
        self.update()

    def mousePressEvent(self, e):
        W = self.width(); n = 7; mg = 6; sp = 4
        bw = max(50, (W - 2*mg - (n-1)*sp) // n)
        xi = int((e.position().x() - mg) / (bw + sp))
        xi = max(0, min(n-1, xi))
        if self._select_cb: self._select_cb(xi)
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        p.fillRect(0, 0, W, H, QColor("#060A1A"))

        n = 7; mg = 10; GAP = 22
        LBL_H = 30; STRIP_H = 85; STAT_H = 26; PIPE_H = 85
        avail_bw = W - 2*mg - (n-1)*GAP
        bw = max(60, avail_bw // n)
        box_top = mg + PIPE_H + LBL_H + 2
        box_bot = H - STRIP_H - STAT_H - 2
        bh = max(60, box_bot - box_top)
        lbl_y = mg + PIPE_H  # stage label rect top

        # Stage center X array (used for pipe routing)
        scx = [mg + i*(bw+GAP) + bw//2 for i in range(n)]

        # ── WATER PIPE NETWORK ──────────────────────────────────────────
        V_R      = 18
        PIPE_W   = 12
        DX       = V_R + 10
        STUB_TOP = mg + 3
        VAL_CY   = lbl_y - V_R - 5

        HW_S  = QColor("#FF4444"); HW_R  = QColor("#CC2222")
        CHW_S = QColor("#2299FF"); CHW_R = QColor("#1166CC")
        WSH_C = QColor("#00CC88")

        mvs = self._mvs if self._mvs else [0.0] * 6

        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        fm8    = p.fontMetrics()
        lbl_off = STUB_TOP + fm8.height() + 1

        # ── nested helpers ────────────────────────────────────────────────
        def _flow_arrows(px, y1, y2, mv_pct, going_down: bool):
            """Filled triangle arrows scrolling inside a thick pipe."""
            if mv_pct < 1.0 or y2 - y1 < 16:
                return
            spacing = 36
            raw_off = int(self._angle * 0.12) % spacing
            offset  = raw_off if going_down else (spacing - raw_off) % spacing
            aw = PIPE_W // 2 - 2
            ah = aw + 3
            p.save()
            p.setClipRect(QRect(px - PIPE_W // 2, y1, PIPE_W, y2 - y1))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, min(230, 100 + int(mv_pct * 1.3))))
            pos = y1 + offset
            while pos < y2:
                if going_down:
                    pts = [QPoint(px, pos), QPoint(px-aw, pos-ah), QPoint(px+aw, pos-ah)]
                else:
                    pts = [QPoint(px, pos), QPoint(px-aw, pos+ah), QPoint(px+aw, pos+ah)]
                p.drawPolygon(pts)
                pos += spacing
            p.restore()

        def _pipe_lbl(px, txt, clr):
            """Pipe label with dark background patch."""
            tw = fm8.horizontalAdvance(txt); th = fm8.height()
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(0, 0, 0, 160))
            p.drawRect(px - tw//2 - 2, lbl_off - th, tw + 4, th + 1)
            p.setPen(QPen(clr)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawText(px - tw//2, lbl_off, txt)

        def _ret_valve(rx, ry, clr, mv_pct):
            """Animated return valve: bottom-fill level + pulse glow ring."""
            p.setPen(QPen(clr, 2.0)); p.setBrush(QColor("#040C18"))
            p.drawEllipse(rx-V_R, ry-V_R, 2*V_R, 2*V_R)
            fill_h = max(1, int((2*V_R - 2) * mv_pct / 100.0))
            p.save()
            p.setClipRect(QRect(rx-V_R+1, ry+V_R-1-fill_h, 2*V_R-2, fill_h))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(clr.red(), clr.green(), clr.blue(), 170))
            p.drawEllipse(rx-V_R+1, ry-V_R+1, 2*V_R-2, 2*V_R-2)
            p.restore()
            pulse = abs(math.sin(math.radians(self._angle * 4)))
            p.setPen(QPen(QColor(clr.red(), clr.green(), clr.blue(), int(110 * pulse)), 2.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(rx-V_R-3, ry-V_R-3, 2*V_R+6, 2*V_R+6)
            p.setPen(QPen(QColor("#FFFFFF")))
            p.drawText(QRect(rx-V_R, ry-V_R, 2*V_R, 2*V_R),
                       Qt.AlignmentFlag.AlignCenter, f"{mv_pct:.0f}%")

        def _coil_pipes(vx, sup_clr, ret_clr, sup_lbl, ret_lbl, mv_pct):
            """Supply + return pipes with labels and animated return valve."""
            sx = vx - DX; rx = vx + DX
            p.setPen(QPen(sup_clr, PIPE_W, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(sx, STUB_TOP, sx, lbl_y)
            _flow_arrows(sx, STUB_TOP, lbl_y, mv_pct, going_down=True)
            p.setPen(QPen(ret_clr, PIPE_W, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(rx, STUB_TOP, rx, VAL_CY - V_R)
            p.drawLine(rx, VAL_CY + V_R, rx, lbl_y)
            _flow_arrows(rx, STUB_TOP, VAL_CY - V_R, mv_pct, going_down=False)
            _flow_arrows(rx, VAL_CY + V_R, lbl_y,    mv_pct, going_down=False)
            _pipe_lbl(sx, sup_lbl, sup_clr)
            _pipe_lbl(rx, ret_lbl, ret_clr)
            _ret_valve(rx, VAL_CY, ret_clr, mv_pct)

        def _wash_pipe(vx, clr, lbl, mv_pct):
            """Single supply pipe (washer) with animated valve."""
            p.setPen(QPen(clr, PIPE_W, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(vx, STUB_TOP, vx, VAL_CY - V_R)
            p.drawLine(vx, VAL_CY + V_R, vx, lbl_y)
            _flow_arrows(vx, STUB_TOP, VAL_CY - V_R, mv_pct, going_down=True)
            _flow_arrows(vx, VAL_CY + V_R, lbl_y,    mv_pct, going_down=True)
            _pipe_lbl(vx, lbl, clr)
            _ret_valve(vx, VAL_CY, clr, mv_pct)

        # ── per-stage pipe calls ──────────────────────────────────────────
        _coil_pipes(scx[1], HW_S,  HW_R,  "HWS", "HWR", mvs[0])
        _coil_pipes(scx[2], CHW_S, CHW_R, "CWS", "CWR", mvs[1])
        _wash_pipe( scx[3], WSH_C,         "WS",          mvs[2])
        _coil_pipes(scx[4], CHW_S, CHW_R, "CWS", "CWR", mvs[3])
        _coil_pipes(scx[5], HW_S,  HW_R,  "HWS", "HWR", mvs[4])

        # ── STAGE LABEL RECTANGLES ───────────────────────────────────────
        stage_lbls = ["OA INLET","HTC-1","CC-1","WASHER","CC-2","HTC-2","SUPPLY FAN"]
        for i in range(n):
            x = mg + i*(bw+GAP)
            p.setPen(QPen(QColor("#263850"), 1))
            p.setBrush(QColor("#0C1826"))
            p.drawRoundedRect(x, lbl_y, bw, LBL_H-2, 3, 3)
            p.setPen(QPen(QColor("#B8C8D8")))
            p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            p.drawText(QRect(x, lbl_y, bw, LBL_H-2), Qt.AlignmentFlag.AlignCenter, stage_lbls[i])

        # Stage boxes + graphics + MV bar
        MV_BW = 8   # MV indicator bar width
        for i in range(n):
            x = mg + i*(bw+GAP); sel = (i == self._sel)
            acc = QColor(_SACCNT[i])
            p.setPen(QPen(acc if sel else QColor("#1A2A3E"), 2.0 if sel else 1.0))
            p.setBrush(QColor("#07101C"))
            p.drawRoundedRect(x, box_top, bw, bh, 3, 3)
            if sel:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(acc)
                p.drawRoundedRect(x+2, box_top+bh-5, bw-4, 5, 2, 2)
            mv_i = (self._mvs[i-1] if 1 <= i <= 5 else
                    (self._mvs[5] if i == 6 else 0.0))
            self._draw_unit(p, i, x, box_top, bw, bh, mv_i)

            # MV fill bar — right edge, fills bottom-up proportional to MV%
            if 1 <= i <= 6:
                bx_mv = x + bw - MV_BW - 3
                track_y = box_top + 6; track_h = bh - 12
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#040810"))
                p.drawRoundedRect(bx_mv, track_y, MV_BW, track_h, 2, 2)
                fill_h = max(2, int(track_h * mv_i / 100.0))
                gv = QLinearGradient(bx_mv, track_y+track_h-fill_h, bx_mv, track_y+track_h)
                gv.setColorAt(0, QColor(acc.red(), acc.green(), acc.blue(), 220))
                gv.setColorAt(1, QColor(acc.red()//2, acc.green()//2, acc.blue()//2, 140))
                p.setBrush(QBrush(gv))
                p.drawRoundedRect(bx_mv, track_y+track_h-fill_h, MV_BW, fill_h, 2, 2)
                p.setFont(QFont("Consolas", 6, QFont.Weight.Bold))
                p.setPen(QPen(QColor(acc.red(), acc.green(), acc.blue(), 200)))
                p.drawText(QRect(bx_mv-8, track_y+track_h+1, MV_BW+16, 10),
                           Qt.AlignmentFlag.AlignCenter, f"{mv_i:.0f}%")

        # Data strip
        strip_y = H - STRIP_H - STAT_H
        p.fillRect(0, strip_y, W, STRIP_H, QColor("#050810"))
        p.setPen(QPen(QColor("#1A2840"), 1)); p.drawLine(0, strip_y, W, strip_y)
        main_lbls = ["OUTDOOR AIR","DRY BULB","DRY BULB","HUMIDITY","DEW POINT","DRY BULB","STATIC PRESSURE"]
        for i in range(n):
            x = mg + i*(bw+GAP); s = self._states[i]; sel = (i == self._sel)
            acc = QColor(_SACCNT[i])
            if i < n-1:
                p.setPen(QPen(QColor("#1A2840"), 1))
                p.drawLine(x+bw+GAP//2, strip_y+4, x+bw+GAP//2, strip_y+STRIP_H-4)
            # Row 1 — label
            p.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
            p.setPen(QPen(QColor("#5A7090")))
            p.drawText(QRect(x, strip_y+5, bw, 15), Qt.AlignmentFlag.AlignCenter, main_lbls[i])
            # Row 2 — primary value (large)
            if i == 0:   pv = f"{s.T:.1f}°C"
            elif i == 3: pv = f"{s.RH:.0f}% RH"
            elif i == 6: pv = f"{self._p_static:.0f} Pa"
            else:        pv = f"{s.T:.1f}°C"
            p.setFont(QFont("Consolas", 15, QFont.Weight.Bold))
            p.setPen(QPen(QColor("#FFFFFF") if sel else acc))
            p.drawText(QRect(x, strip_y+18, bw, 34), Qt.AlignmentFlag.AlignCenter, pv)
            # Row 3+4 — secondary values
            if i == 0:   sv1, sv2 = f"{s.RH:.0f} % RH", f"{s.w_gkg:.1f} g/kg"
            elif i == 1: sv1, sv2 = f"{s.h:.1f} kJ/kg", f"{s.w_gkg:.1f} g/kg"
            elif i == 2: sv1, sv2 = f"{s.h:.1f} kJ/kg", f"{s.w_gkg:.1f} g/kg"
            elif i == 3: sv1, sv2 = f"{s.T:.1f} °C DB", f"{s.w_gkg:.1f} g/kg"
            elif i == 4: sv1, sv2 = f"{s.w_gkg:.1f} g/kg", f"{s.T_dp:.1f} °C DB"
            elif i == 5: sv1, sv2 = f"{s.h:.1f} kJ/kg", f"{s.w_gkg:.1f} g/kg"
            else:        sv1, sv2 = f"{self._fan_hz:.1f} Hz", ""
            p.setFont(QFont("Consolas", 8)); p.setPen(QPen(QColor("#7A8EA8")))
            p.drawText(QRect(x, strip_y+52, bw, 16), Qt.AlignmentFlag.AlignCenter, sv1)
            if sv2:
                p.drawText(QRect(x, strip_y+68, bw, 16), Qt.AlignmentFlag.AlignCenter, sv2)

        # Status bar
        sb_y = H - STAT_H
        p.fillRect(0, sb_y, W, STAT_H, QColor("#040710"))
        p.setPen(QPen(QColor("#1A2840"), 1)); p.drawLine(0, sb_y, W, sb_y)
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(QPen(QColor("#3A5A7A")))
        p.drawText(QRect(mg, sb_y, 200, STAT_H), Qt.AlignmentFlag.AlignVCenter, "STAGE CONTROLLERS")
        fm = p.fontMetrics()
        parts = [("● SYSTEM STATIC PRESSURE:  ","#3A5A7A"),
                 (f"{self._p_static:.0f} PA","#00D4FF"),
                 ("   ● FAN SPEED:  ","#3A5A7A"),
                 (f"{self._fan_hz:.1f} HZ","#FFBB00")]
        tw = sum(fm.horizontalAdvance(t) for t,_ in parts)
        cx2 = W - mg - tw
        ty = sb_y + (STAT_H - fm.height())//2 + fm.ascent()
        for txt, clr in parts:
            p.setPen(QPen(QColor(clr))); p.drawText(cx2, ty, txt)
            cx2 += fm.horizontalAdvance(txt)

        # Company watermark — in status bar at bottom, small size
        wm_txt = "亞聖國際科技有限公司"
        p.setFont(QFont("Microsoft JhengHei", 9, QFont.Weight.Bold))
        fm_wm = p.fontMetrics()
        wm_x = (W - fm_wm.horizontalAdvance(wm_txt)) // 2
        wm_y = H - STAT_H // 2 + fm_wm.ascent() // 2 - 2
        p.setPen(QPen(QColor(0, 180, 220, 55)))
        p.drawText(wm_x, wm_y, wm_txt)
        p.end()

    def _draw_unit(self, p, idx, x, y, w, h, mv):
        cx = x + w // 2; cy = y + h // 2
        pad = 8  # uniform inner padding for all boxes

        def _draw_coil(bx, by, bw2, bh2, tube_clr, n_tubes=6):
            """Serpentine heat-exchanger coil: horizontal tubes + alternating U-bends."""
            marg = 8
            x1, x2 = bx + marg, bx + bw2 - marg
            avail_h = bh2 - 2 * marg
            t_gap = max(6, avail_h // max(1, n_tubes - 1))
            br = max(3, min(t_gap // 2, 8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(tube_clr, 2.2, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            for ti in range(n_tubes):
                ty = by + marg + ti * t_gap
                p.drawLine(x1, ty, x2, ty)
                if ti < n_tubes - 1:
                    if ti % 2 == 0:
                        p.drawArc(QRect(x2 - br, ty, 2*br, t_gap), 90*16, -180*16)
                    else:
                        p.drawArc(QRect(x1 - br, ty, 2*br, t_gap), 90*16, 180*16)

        def _draw_airflow(bx, by, bw2, bh2):
            """Floating particle airflow: small dots drifting L→R like washer spray."""
            fan_mv = (self._mvs[5] if self._mvs else 0)
            if fan_mv < 2:
                return
            n_lanes    = max(3, int(2 + fan_mv / 22))   # 3–7 horizontal lanes
            n_per_lane = max(2, int(fan_mv / 18))        # 2–6 particles per lane
            speed      = 0.12 + fan_mv * 0.008
            alpha_base = min(155, int(fan_mv * 1.55))
            spacing    = bw2 // max(1, n_per_lane)

            p.save()
            p.setClipRect(bx, by, bw2, bh2)
            p.setPen(Qt.PenStyle.NoPen)

            for lane in range(n_lanes):
                lane_y  = by + int(bh2 * (lane + 0.5) / n_lanes)
                spd_v   = speed * (0.82 + (lane % 3) * 0.12)

                for pi in range(n_per_lane + 2):
                    raw_x = int(self._angle * spd_v
                                + pi * spacing
                                + lane * (spacing // 3)) % bw2
                    px_x = bx + raw_x
                    # slight vertical wobble
                    ry = lane_y + int(
                        math.sin(math.radians(pi * 73 + lane * 51)) * 4)
                    sz = 3 if pi % 2 == 0 else 2
                    a  = int(alpha_base * (
                        0.45 + 0.55 * abs(math.sin(
                            math.radians(pi * 97 + lane * 43)))))
                    a  = max(35, min(alpha_base, a))
                    p.setBrush(QColor(200, 235, 255, a))
                    p.drawEllipse(px_x - sz // 2, ry - sz // 2, sz, sz)

            p.restore()

        if idx == 0:  # OA INLET — chevron arrows (airflow left→right)
            rows = 6
            rh = (h - 2*pad) // rows
            for r in range(rows):
                ry = y + pad + r * rh + rh // 2
                for col_off in (-w//4, w//4):
                    tip = cx + col_off + 10
                    p.setPen(QPen(QColor("#3A5878"), 1.8, Qt.PenStyle.SolidLine,
                                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                    p.drawLine(tip-10, ry-6, tip, ry)
                    p.drawLine(tip,    ry,   tip-10, ry+6)

        elif idx in (1, 5):  # HTC-1 / HTC-2 — wide coil + ⊕ circle
            bx = x + pad; by = y + pad
            bw2 = w - 2*pad; bh2 = h - 2*pad

            if idx == 1:
                c0, c1, c2 = "#140200", "#8B1800", "#CC2800"
                circ_clr = QColor("#FF3300")
            else:
                c0, c1, c2 = "#140200", "#8B1800", "#CC2800"
                circ_clr = QColor("#FF3300")

            grad = QLinearGradient(cx, by, cx, by + bh2)
            grad.setColorAt(0.0, QColor(c0)); grad.setColorAt(0.3, QColor(c1))
            grad.setColorAt(0.5, QColor(c2)); grad.setColorAt(0.7, QColor(c1))
            grad.setColorAt(1.0, QColor(c0))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(grad))
            p.drawRoundedRect(bx, by, bw2, bh2, 4, 4)

            # Fin lines (thin horizontal)
            n_fins = max(8, bh2 // 6)
            p.setPen(QPen(QColor(255, 255, 255, 18), 0.6))
            for fi in range(n_fins):
                fy = by + 3 + fi * ((bh2 - 6) // n_fins)
                p.drawLine(bx + 4, fy, bx + bw2 - 4, fy)

            # Serpentine coil tubes
            tube_clr = QColor(255, 150, 70, 170)
            _draw_coil(bx, by, bw2, bh2, tube_clr)

            rv = min(22, w // 4, h // 5)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(circ_clr)
            p.drawEllipse(cx - rv, cy - rv, 2*rv, 2*rv)
            p.setPen(QPen(QColor("#FFFFFF"), 2.5))
            p.drawLine(cx - rv + 5, cy, cx + rv - 5, cy)
            p.drawLine(cx, cy - rv + 5, cx, cy + rv - 5)

        elif idx in (2, 4):  # CC-1 / CC-2 — identical blue cooling coil + ⊖ circle
            bx = x + pad; by = y + pad
            bw2 = w - 2*pad; bh2 = h - 2*pad
            cv = int(60 + 120 * (mv / 100.0))

            # Same blue gradient for both CC-1 and CC-2
            grad = QLinearGradient(cx, by, cx, by + bh2)
            grad.setColorAt(0.0, QColor(0, 8, 40))
            grad.setColorAt(0.3, QColor(0, cv // 2, 150))
            grad.setColorAt(0.5, QColor(0, cv, 210))
            grad.setColorAt(0.7, QColor(0, cv // 2, 150))
            grad.setColorAt(1.0, QColor(0, 8, 40))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(grad))
            p.drawRoundedRect(bx, by, bw2, bh2, 4, 4)

            # Fin lines
            n_fins = max(8, bh2 // 6)
            p.setPen(QPen(QColor(255, 255, 255, 18), 0.6))
            for fi in range(n_fins):
                fy = by + 3 + fi * ((bh2 - 6) // n_fins)
                p.drawLine(bx + 4, fy, bx + bw2 - 4, fy)

            # Serpentine coil tubes
            _draw_coil(bx, by, bw2, bh2, QColor(60, 190, 255, 175))

            rv = min(22, w // 4, h // 5)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(0, int(80 + 140*(mv/100.0)), 220))
            p.drawEllipse(cx - rv, cy - rv, 2*rv, 2*rv)
            p.setPen(QPen(QColor("#FFFFFF"), 2.5))
            p.drawLine(cx - rv + 5, cy, cx + rv - 5, cy)  # minus sign only

        elif idx == 3:  # WASHER — animated spray nozzles
            bx = x + pad; by = y + pad
            bw2 = w - 2*pad; bh2 = h - 2*pad

            # Background panel
            p.setPen(QPen(QColor("#3A4A5A"), 1.5)); p.setBrush(QColor("#0D1A28"))
            p.drawRoundedRect(bx, by, bw2, bh2, 4, 4)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#080F1A"))
            p.drawRoundedRect(bx+4, by+4, bw2-8, bh2-8, 2, 2)

            # Nozzle pipe bar at top
            nz_bar_y = by + 10
            p.setPen(QPen(QColor("#4A8ABB"), 1.5)); p.setBrush(QColor("#1E4A6A"))
            p.drawRoundedRect(bx + 6, nz_bar_y - 4, bw2 - 12, 8, 2, 2)

            # 3 nozzle positions
            n_nz = 3
            nz_xs = [bx + (i+1) * bw2 // (n_nz+1) for i in range(n_nz)]
            p.setPen(Qt.PenStyle.NoPen)
            for nz_x in nz_xs:
                p.setBrush(QColor("#70CCFF"))
                p.drawEllipse(nz_x - 4, nz_bar_y - 4, 8, 8)

            # Animated spray streams (fan of drops from each nozzle)
            spray_top = nz_bar_y + 5
            spray_bot = by + bh2 - 8
            spray_h   = max(1, spray_bot - spray_top)
            max_reach = max(4, int(spray_h * mv / 100.0))
            spray_a   = min(230, int(mv * 2.3))

            if mv > 1:
                angles_deg = [-14, -7, 0, 7, 14]
                p.save()
                p.setClipRect(bx + 2, spray_top, bw2 - 4, spray_h)
                for ni, nz_x in enumerate(nz_xs):
                    for ai, adeg in enumerate(angles_deg):
                        arad  = math.radians(adeg)
                        dxs   = math.sin(arad)
                        dys   = math.cos(arad)
                        phase = (ni * 37 + ai * 13) % 20
                        spd   = 1.8 + mv * 0.025
                        t_off = int(self._angle * spd + phase) % 20
                        gap   = 18
                        pos   = float(t_off)
                        while pos < max_reach:
                            fade   = 1.0 - pos / max_reach
                            a      = int(spray_a * (0.25 + 0.75 * fade))
                            sz     = max(2, int(3.5 * fade + 0.5))
                            drop_x = int(nz_x + pos * dxs) - sz // 2
                            drop_y = int(spray_top + pos * dys) - sz // 2
                            p.setBrush(QColor(80, 165, 245, a))
                            p.drawEllipse(drop_x, drop_y, sz, sz)
                            pos += gap
                p.restore()

            # Water pool at bottom (height ∝ MV)
            pool_h = max(3, int((spray_h * 0.22) * mv / 100.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(30, 90, 170, 180))
            p.drawRoundedRect(bx + 4, spray_bot - pool_h, bw2 - 8, pool_h, 2, 2)
            # ripple lines on pool surface
            if mv > 5:
                rip_y = spray_bot - pool_h
                rip_phase = int(self._angle * 2) % 8
                p.setPen(QPen(QColor(100, 180, 255, 80), 1.0))
                for ri in range(2):
                    ry = rip_y + rip_phase + ri * 4
                    if spray_bot - 2 > ry > spray_bot - pool_h:
                        p.drawLine(bx + 8, ry, bx + bw2 - 8, ry)

        elif idx == 6:  # SUPPLY FAN — large cyan circle + rotating blade
            rf = min(w, h) // 2 - 10
            fan_cx = cx; fan_cy = cy

            # Outer circle
            p.setPen(QPen(QColor("#00B4D8"), 2.5)); p.setBrush(QColor("#040C18"))
            p.drawEllipse(fan_cx - rf, fan_cy - rf, 2*rf, 2*rf)

            # Rotating blade
            ang = math.radians(self._angle)
            bx0 = fan_cx + int(rf * 0.82 * math.cos(ang + math.pi))
            by0 = fan_cy + int(rf * 0.82 * math.sin(ang + math.pi))
            bx1 = fan_cx + int(rf * 0.82 * math.cos(ang))
            by1 = fan_cy + int(rf * 0.82 * math.sin(ang))
            p.setPen(QPen(QColor("#8ACCE0"), 3.0)); p.drawLine(bx0, by0, bx1, by1)

            # Hub
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#60AAC8"))
            p.drawEllipse(fan_cx - 5, fan_cy - 5, 10, 10)

            # Motor housing (bottom center of circle)
            mh_w = max(30, rf // 2); mh_h = max(16, rf // 4)
            mh_x = fan_cx - mh_w // 2; mh_y = fan_cy + rf - mh_h + 2
            p.setPen(QPen(QColor("#2A4A5A"), 1.2)); p.setBrush(QColor("#0A1828"))
            p.drawRect(mh_x, mh_y, mh_w, mh_h)
            p.setFont(QFont("Microsoft JhengHei", 7)); p.setPen(QPen(QColor("#4A7A9A")))
            p.drawText(QRect(mh_x, mh_y, mh_w, mh_h), Qt.AlignmentFlag.AlignCenter, "馬達")

            # Triangular indicators at box bottom
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#CC9900"))
            for ti in range(2):
                tx = fan_cx - rf // 3 + ti * (rf * 2 // 3)
                p.drawPolygon(QPolygonF([QPointF(float(tx-7), float(y+h-3)),
                                         QPointF(float(tx+7), float(y+h-3)),
                                         QPointF(float(tx),   float(y+h-12))]))

        # ── Airflow overlay: all stages including OA inlet and supply fan ──
        if 0 <= idx <= 6:
            _draw_airflow(x + pad, y + pad, w - 2*pad, h - 2*pad)


# ═══════════════════════════════════════════════════════
#  PSYCHROMETRIC CHART
# ═══════════════════════════════════════════════════════
class _PsychrometricChart(QWidget):
    T_MIN, T_MAX = 0.0, 50.0
    W_MIN, W_MAX = 0.0, 0.030

    def __init__(self, parent=None):
        super().__init__(parent); self.setMinimumSize(300, 280)
        self._states = [AirState(6.0, 0.003)] * 7
        self._T_sp = 22.0; self._RH_sp = 50.0
        self._T_tol = 2.0; self._RH_tol = 5.0
        self._sel = -1

    def refresh(self, states, T_sp, RH_sp, T_tol, RH_tol, sel=-1):
        self._states = states; self._T_sp = T_sp; self._RH_sp = RH_sp
        self._T_tol = T_tol; self._RH_tol = RH_tol; self._sel = sel
        self.update()

    def _xy(self, T, w):
        lm, rm, tm, bm = 42, 10, 10, 32
        W, H = self.width(), self.height()
        pw = W-lm-rm; ph = H-tm-bm
        x = lm + (T-self.T_MIN)/(self.T_MAX-self.T_MIN)*pw
        y = (H-bm) - (w-self.W_MIN)/(self.W_MAX-self.W_MIN)*ph
        return int(x), int(y)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        p.fillRect(0, 0, W, H, QColor("#04091A"))

        # Grid
        p.setPen(QPen(QColor(14, 30, 58), 1))
        for T in range(0, 55, 5):
            x, _ = self._xy(T, 0); _, y0 = self._xy(0, 0); _, y1 = self._xy(0, self.W_MAX)
            p.drawLine(x, y1, x, y0)
        for wg in range(0, 32, 5):
            _, y = self._xy(0, wg/1000); x0, _ = self._xy(0, 0); x1, _ = self._xy(50, 0)
            p.drawLine(x0, y, x1, y)

        # RH isolines — closer colour steps, dashed
        rh_levels = [(10,"#0A1220"),(20,"#0C1628"),(30,"#0D1A30"),(40,"#0F1E38"),
                     (50,"#111F3C"),(60,"#122240"),(70,"#142545"),(80,"#162848"),(100,"#0070AA")]
        for rh_pct, clr in rh_levels:
            pts = []
            for Ti in range(0, 52, 1):
                ww = Psych.omega(float(Ti), float(rh_pct))
                if ww > self.W_MAX + 0.001: break
                pts.append(QPointF(*self._xy(float(Ti), min(ww, self.W_MAX))))
            if len(pts) < 2: continue
            is_sat = (rh_pct == 100)
            pen = QPen(QColor(clr), 1.6 if is_sat else 0.8)
            if not is_sat: pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            for i in range(len(pts)-1): p.drawLine(pts[i], pts[i+1])
            if pts and not is_sat:
                lp = pts[-1]; p.setPen(QPen(QColor("#4080B0")))
                p.setFont(QFont("Consolas", 8))
                p.drawText(int(lp.x())-22, int(lp.y())-1, f"{rh_pct}%")

        # Target zone — proper curved psychrometric shape
        T_lo = self._T_sp - self._T_tol; T_hi = self._T_sp + self._T_tol
        RH_lo = max(1.0, self._RH_sp - self._RH_tol)
        RH_hi = min(99.0, self._RH_sp + self._RH_tol)
        N = 20; T_steps = [T_lo + i*(T_hi-T_lo)/(N-1) for i in range(N)]
        bot = [QPointF(*self._xy(T, Psych.omega(T, RH_lo))) for T in T_steps]
        top = [QPointF(*self._xy(T, Psych.omega(T, RH_hi))) for T in reversed(T_steps)]
        zone = QPainterPath(); zone.moveTo(bot[0])
        for pt in bot[1:]: zone.lineTo(pt)
        for pt in top: zone.lineTo(pt)
        zone.closeSubpath()
        p.fillPath(zone, QColor(0, 180, 255, 22))
        p.setPen(QPen(QColor("#0088FF"), 1.3, Qt.PenStyle.DashLine)); p.drawPath(zone)

        # Company watermark — auto-sized to span chart width
        wm = "亞聖國際科技有限公司"
        lm = 60; rm = 10
        avail_w = W - lm - rm
        for fs in range(48, 10, -2):
            p.setFont(QFont("Microsoft JhengHei", fs, QFont.Weight.Bold))
            if p.fontMetrics().horizontalAdvance(wm) <= avail_w:
                break
        fm_wm = p.fontMetrics()
        p.setPen(QPen(QColor(0, 180, 220, 42)))
        wm_x = lm + (avail_w - fm_wm.horizontalAdvance(wm)) // 2
        _, cy_w = self._xy(25.0, 0.013)
        p.drawText(wm_x, cy_w + 5, wm)

        # Process path — each segment interpolated & clamped below saturation curve
        pts_path = []
        for s in self._states:
            Tc = max(self.T_MIN, min(self.T_MAX, s.T))
            wc = max(self.W_MIN, min(self.W_MAX, s.w))
            pts_path.append(self._xy(Tc, wc))

        # Build per-segment traced sub-paths (16 sub-points, w clamped to ω_sat)
        N_SUB = 16
        segs = []
        for i in range(len(self._states) - 1):
            sa = self._states[i]; sb = self._states[i+1]
            seg = []
            for k in range(N_SUB + 1):
                t = k / N_SUB
                T = sa.T + t*(sb.T - sa.T)
                w = sa.w + t*(sb.w - sa.w)
                w = min(w, Psych.omega_sat(T))          # never above saturation
                Tc2 = max(self.T_MIN, min(self.T_MAX, T))
                wc2 = max(self.W_MIN, min(self.W_MAX, w))
                seg.append(self._xy(Tc2, wc2))
            segs.append(seg)

        # Glow pass
        p.setPen(QPen(QColor(0, 180, 230, 50), 7))
        for seg in segs:
            for j in range(len(seg)-1): p.drawLine(*seg[j], *seg[j+1])
        # Main line
        p.setPen(QPen(QColor("#00CCEE"), 2.2))
        for seg in segs:
            for j in range(len(seg)-1): p.drawLine(*seg[j], *seg[j+1])
        # Arrowhead at midpoint of each segment
        p.setBrush(QColor("#00CCEE")); p.setPen(Qt.PenStyle.NoPen)
        for seg in segs:
            mid = len(seg)//2
            x1, y1 = seg[mid-1]; x2, y2 = seg[mid]
            mx, my = (x1+x2)//2, (y1+y2)//2
            ang = math.atan2(y2-y1, x2-x1); sz = 6
            p.drawPolygon(QPolygonF([
                QPointF(mx + sz*math.cos(ang),     my + sz*math.sin(ang)),
                QPointF(mx + sz*math.cos(ang+2.4), my + sz*math.sin(ang+2.4)),
                QPointF(mx + sz*math.cos(ang-2.4), my + sz*math.sin(ang-2.4)),
            ]))

        # Segment process labels (Chinese + English, offset perpendicular to path)
        seg_labels = [
            "① 預熱 Preheat",
            "② 預冷 PreCool",
            "③ 等焓加濕 Adiabatic",
            "④ 冷卻除濕 Dehumid",
            "⑤ 再熱 Reheat",
            "⑥ 供氣 Supply",
        ]
        seg_offsets = [(0, -18), (0, -18), (14, 8), (0, 18), (0, -18), (14, -18)]
        p.setFont(QFont("Microsoft JhengHei", 10, QFont.Weight.Bold))
        for i, (seg, lbl, (ox, oy)) in enumerate(zip(segs, seg_labels, seg_offsets)):
            if len(seg) < 2: continue
            mx = (seg[0][0] + seg[-1][0]) // 2 + ox
            my = (seg[0][1] + seg[-1][1]) // 2 + oy
            clr = QColor(_SACCNT[i]) if i < len(_SACCNT) else QColor("#AAAAAA")
            # Subtle dark shadow for depth, no opaque background box
            p.setPen(QPen(QColor(0, 0, 0, 180)))
            p.drawText(mx + 1, my + 1, lbl)
            p.setPen(QPen(clr))
            p.drawText(mx, my, lbl)

        # State points
        acc_clrs = ["#3D8EFF","#FF6B35","#00D4FF","#00FF9F","#2E86FF","#FFB300","#BB77FF"]
        lbls = ["OA","①","②","W","③","④","SA"]
        for i, (px, py) in enumerate(pts_path):
            sel_pt = (i - 1 == self._sel) if self._sel >= 0 else False
            clr = QColor(acc_clrs[i])
            r = 9 if sel_pt else 5
            if sel_pt:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(255,255,255,50))
                p.drawEllipse(px-r-4, py-r-4, 2*(r+4), 2*(r+4))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(clr)
            p.drawEllipse(px-r, py-r, 2*r, 2*r)
            if sel_pt:
                p.setPen(QPen(QColor("#FFFFFF"), 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(px-r, py-r, 2*r, 2*r)
            p.setPen(QPen(QColor("#FFFFFF") if sel_pt else QColor("#E0E0E0")))
            p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            p.drawText(px+r+3, py-r+2, lbls[i])

        # Axes
        x0a, y_ax = self._xy(0, 0); x1a, _ = self._xy(50, 0); _, y_top = self._xy(0, self.W_MAX)
        p.setPen(QPen(QColor("#1E3A60"), 1)); p.drawLine(x0a, y_ax, x1a, y_ax); p.drawLine(x0a, y_ax, x0a, y_top)
        p.setFont(QFont("Consolas", 8)); p.setPen(QPen(QColor("#6090CC")))
        for T in range(0, 55, 10):
            x, _ = self._xy(T, 0); p.drawText(x-10, y_ax+14, f"{T}")
        for wg in range(0, 32, 5):
            _, y = self._xy(0, wg/1000); p.drawText(2, y+4, f"{wg}")
        p.setFont(QFont("Microsoft JhengHei", 8)); p.setPen(QPen(QColor("#6090CC")))
        p.drawText(W//2-24, H-4, "乾球溫度 (°C)")
        p.save(); p.translate(12, H//2+30); p.rotate(-90); p.drawText(0, 0, "ω (g/kg)"); p.restore()
        p.end()


# ═══════════════════════════════════════════════════════
#  STAGE FACEPLATE
# ═══════════════════════════════════════════════════════
class _StageFaceplate(QFrame):
    _BG  = "#060E1E"; _CELL = "#0A1630"; _BDR = "#162845"
    _ACC = "#00B4D8"; _PVC = "#00D4FF"; _SPC = "#00FF9F"; _MVC = "#FF7700"
    TH = 80

    def __init__(self, name: str, pid: PidCtrl, fopdt: FopdtCoil,
                 pv_lo: float, pv_hi: float, select_cb=None, pv_modes=None, on_change=None):
        super().__init__()
        self._name = name; self._pid = pid; self._fopdt = fopdt
        # pv_modes: list of (label, lo, hi, default_sp)
        self._pv_modes = pv_modes or []
        self._pv_mode_idx = 0
        if self._pv_modes:
            _, pv_lo, pv_hi, sp0 = self._pv_modes[0]
            self._sp = sp0
        else:
            self._sp = (pv_lo + pv_hi) / 2.0
        self._pv_lo = pv_lo; self._pv_hi = pv_hi
        self._select_cb = select_cb; self._selected = False
        self._on_change = on_change
        self.setMinimumWidth(210); self.setMaximumWidth(280); self.setMinimumHeight(360)
        self._update_border(); self._build()

    def _update_border(self):
        clr = "#00FFCC" if self._selected else self._ACC
        w = "2px" if self._selected else "1px"
        self.setStyleSheet(f"QFrame{{background:{self._BG};border:{w} solid {clr};"
                           f"border-radius:6px;}}")

    def set_selected(self, sel: bool):
        self._selected = sel; self._update_border()

    def mousePressEvent(self, e):
        if self._select_cb: self._select_cb()
        super().mousePressEvent(e)

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(7, 7, 7, 7); lay.setSpacing(4)

        # Header
        hdr = QHBoxLayout(); hdr.setSpacing(4)
        nl = QLabel(self._name.replace("\n", "  "))
        nl.setStyleSheet(f"color:{self._ACC};font-size:10pt;font-weight:700;"
                         f"background:transparent;border:none;"
                         f"font-family:'Microsoft JhengHei','Segoe UI';")
        self._mode_btn = QPushButton("AUTO")
        self._mode_btn.setFixedSize(52, 24); self._mode_btn.setCheckable(True); self._mode_btn.setChecked(True)
        self._mode_btn.clicked.connect(self._toggle_mode); self._mode_btn.setStyleSheet(self._mode_qss(True))
        hdr.addWidget(nl, 1); hdr.addWidget(self._mode_btn); lay.addLayout(hdr)

        # PV mode selector (only when multiple modes provided, e.g. HTC-1)
        self._pv_mode_btns = []
        if len(self._pv_modes) > 1:
            sel_row = QHBoxLayout(); sel_row.setSpacing(3); sel_row.setContentsMargins(0,0,0,0)
            for idx, (lbl, *_) in enumerate(self._pv_modes):
                btn = QPushButton(lbl); btn.setFixedHeight(22)
                i = idx
                btn.clicked.connect(lambda _, i=i: self._set_pv_mode(i))
                self._pv_mode_btns.append(btn); sel_row.addWidget(btn, 1)
            lay.addLayout(sel_row)
            self._refresh_pv_mode_btns()

        # Bars
        bar_wrap = QFrame()
        bar_wrap.setFixedHeight(self.TH + 48)
        bar_wrap.setStyleSheet(f"QFrame{{background:{self._CELL};border:none;border-radius:4px;}}")
        bl = QHBoxLayout(bar_wrap); bl.setContentsMargins(14, 6, 14, 5); bl.setSpacing(20)
        bl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self._pv_fill = self._sp_fill = self._mv_fill = None
        self._pv_num = QLabel("—"); self._sp_num = QLabel("—"); self._mv_num = QLabel("—")
        for attr, clr, txt, num in (("_pv_fill",self._PVC,"PV",self._pv_num),
                                     ("_sp_fill",self._SPC,"SP",self._sp_num),
                                     ("_mv_fill",self._MVC,"MV",self._mv_num)):
            col = QVBoxLayout(); col.setSpacing(3)
            col.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            cap = QLabel(txt); cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap.setStyleSheet(f"color:{clr};font-size:8pt;font-weight:700;"
                              f"background:transparent;border:none;font-family:Consolas;")
            col.addWidget(cap)
            track = QFrame(); track.setFixedSize(22, self.TH)
            track.setStyleSheet("QFrame{background:#060F22;border:1px solid #1A3060;border-radius:3px;}")
            fill = QFrame(track)
            fill.setStyleSheet(f"QFrame{{background:{clr};border-radius:2px;border:none;}}")
            fill.setGeometry(2, self.TH-2, 18, 2); setattr(self, attr, fill)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet(f"color:{clr};font-size:9pt;font-weight:700;"
                              f"background:transparent;border:none;font-family:Consolas;")
            col.addWidget(track); col.addWidget(num); bl.addLayout(col)
        lay.addWidget(bar_wrap)

        # SP row
        spr = QHBoxLayout(); spr.setSpacing(4)
        spr.addWidget(self._lbl("SP:")); self._sp_in = self._inp(f"{self._sp:.1f}", self._SPC)
        self._sp_in.editingFinished.connect(self._commit_sp); spr.addWidget(self._sp_in, 1)
        lay.addLayout(spr)

        # Manual MV row (hidden in AUTO)
        mvr = QHBoxLayout(); mvr.setSpacing(4)
        mvr.addWidget(self._lbl("MV:")); self._mv_in = self._inp(f"{self._pid.manual_mv:.1f}", self._MVC)
        self._mv_in.editingFinished.connect(self._commit_mv); mvr.addWidget(self._mv_in, 1)
        self._mv_widget = QWidget(); self._mv_widget.setLayout(mvr)
        self._mv_widget.setStyleSheet("QWidget{background:transparent;border:none;}")
        self._mv_widget.setVisible(False); lay.addWidget(self._mv_widget)

        # PV range
        lay.addWidget(self._sec("PV RANGE  Lo / Hi"))
        pvr = QHBoxLayout(); pvr.setSpacing(3)
        self._pvlo_in = self._inp(f"{self._pv_lo:.1f}", "#66CCEE")
        self._pvhi_in = self._inp(f"{self._pv_hi:.1f}", "#66CCEE")
        for e in (self._pvlo_in, self._pvhi_in):
            e.editingFinished.connect(self._commit_pv_range); pvr.addWidget(e, 1)
        lay.addLayout(pvr)

        # PID
        lay.addWidget(self._sec("PID  Kp / Ki / Kd"))
        pidr = QHBoxLayout(); pidr.setSpacing(3)
        self._kp_in = self._inp(f"{self._pid.Kp:.3g}", "#FFCC44")
        self._ki_in = self._inp(f"{self._pid.Ki:.3g}", "#FFCC44")
        self._kd_in = self._inp(f"{self._pid.Kd:.3g}", "#FFCC44")
        for e in (self._kp_in, self._ki_in, self._kd_in):
            e.editingFinished.connect(self._commit_pid); pidr.addWidget(e, 1)
        lay.addLayout(pidr)

        # FOPDT (always shown)
        lay.addWidget(self._sec("FOPDT  Gain / τ(s) / L(s)"))
        fo_row = QHBoxLayout(); fo_row.setSpacing(3)
        self._fkp = self._inp(f"{self._fopdt.Kp:.3g}", "#77BBFF")
        self._fta = self._inp(f"{self._fopdt.tau:.1f}", "#77BBFF")
        self._fL  = self._inp(f"{self._fopdt.L:.1f}", "#77BBFF")
        for e in (self._fkp, self._fta, self._fL):
            e.editingFinished.connect(self._commit_fopdt); fo_row.addWidget(e, 1)
        lay.addLayout(fo_row)
        lay.addStretch()

    def _lbl(self, t):
        l = QLabel(t); l.setStyleSheet("color:#B0C8D8;font-size:9pt;font-weight:600;background:transparent;"
                                        "border:none;font-family:'Segoe UI';"); return l

    def _sec(self, t):
        l = QLabel(t); l.setFixedHeight(18)
        l.setStyleSheet(f"color:#55AADD;font-size:8pt;font-weight:700;"
                        f"background:{self._CELL};border:none;padding-left:3px;"
                        f"font-family:Consolas;letter-spacing:0.8px;"); return l

    def _set_pv_mode(self, idx: int):
        self._pv_mode_idx = idx
        _, lo, hi, sp0 = self._pv_modes[idx]
        self._pv_lo = lo; self._pv_hi = hi; self._sp = sp0
        self._pvlo_in.setText(f"{lo:.1f}"); self._pvhi_in.setText(f"{hi:.1f}")
        self._sp_in.setText(f"{sp0:.1f}")
        self._pid.reset()
        self._refresh_pv_mode_btns()

    def _refresh_pv_mode_btns(self):
        _on  = ("QPushButton{background:#003A55;color:#00D4FF;border:1px solid #006688;"
                "border-radius:3px;font-size:7pt;font-weight:700;font-family:Consolas;}")
        _off = ("QPushButton{background:#0A0F18;color:#3A5570;border:1px solid #182030;"
                "border-radius:3px;font-size:7pt;font-weight:700;font-family:Consolas;}")
        for i, btn in enumerate(self._pv_mode_btns):
            btn.setStyleSheet(_on if i == self._pv_mode_idx else _off)

    @property
    def pv_mode_idx(self): return self._pv_mode_idx

    def _inp(self, txt, clr):
        e = QLineEdit(txt); e.setFixedHeight(26); e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e.setStyleSheet(f"QLineEdit{{background:#050C1C;color:{clr};"
                        f"border:1px solid {self._BDR};border-radius:3px;"
                        f"font-size:10pt;font-weight:700;font-family:Consolas;}}"
                        f"QLineEdit:focus{{border:1px solid {self._ACC};}}"); return e

    def _mode_qss(self, auto):
        if auto:
            return ("QPushButton{background:#003A55;color:#00D4FF;border:1px solid #006688;"
                    "border-radius:3px;font-size:9pt;font-weight:700;font-family:Consolas;}"
                    "QPushButton:hover{background:#004A6A;}")
        return ("QPushButton{background:#3A2200;color:#FFB300;border:1px solid #775500;"
                "border-radius:3px;font-size:9pt;font-weight:700;font-family:Consolas;}"
                "QPushButton:hover{background:#4A2C00;}")

    def _toggle_mode(self, checked):
        self._pid.auto = checked
        self._mode_btn.setText("AUTO" if checked else "MAN")
        self._mode_btn.setStyleSheet(self._mode_qss(checked))
        self._mv_widget.setVisible(not checked)
        if self._on_change: self._on_change()

    def _commit_sp(self):
        try: v = float(self._sp_in.text())
        except: v = self._sp
        self._sp = max(self._pv_lo, min(self._pv_hi, v)); self._sp_in.setText(f"{self._sp:.1f}")
        if self._on_change: self._on_change()

    def _commit_mv(self):
        try: v = float(self._mv_in.text())
        except: return
        self._pid.manual_mv = max(self._pid.mv_lo, min(self._pid.mv_hi, v))
        self._mv_in.setText(f"{self._pid.manual_mv:.1f}")

    def _commit_pv_range(self):
        try: lo = float(self._pvlo_in.text()); self._pv_lo = lo
        except: pass
        try: hi = float(self._pvhi_in.text()); self._pv_hi = max(self._pv_lo+1, hi)
        except: pass
        if self._on_change: self._on_change()

    def _commit_pid(self):
        try: self._pid.Kp = max(0.0, float(self._kp_in.text()))
        except: pass
        try: self._pid.Ki = max(0.0, float(self._ki_in.text()))
        except: pass
        try: self._pid.Kd = max(0.0, float(self._kd_in.text()))
        except: pass
        if self._on_change: self._on_change()

    def _commit_fopdt(self):
        try: self._fopdt.Kp  = max(0.001, float(self._fkp.text()))
        except: pass
        try: self._fopdt.tau = max(0.5,   float(self._fta.text()))
        except: pass
        try: self._fopdt.L   = max(0.0,   float(self._fL.text()))
        except: pass
        if self._on_change: self._on_change()

    def get_state(self) -> dict:
        return {
            "sp": self._sp, "pv_lo": self._pv_lo, "pv_hi": self._pv_hi,
            "pid_kp": self._pid.Kp, "pid_ki": self._pid.Ki, "pid_kd": self._pid.Kd,
            "fo_kp": self._fopdt.Kp, "fo_tau": self._fopdt.tau, "fo_l": self._fopdt.L,
            "auto": self._pid.auto, "pv_mode_idx": self._pv_mode_idx,
        }

    def set_state(self, d: dict):
        if "pv_mode_idx" in d and self._pv_modes and d["pv_mode_idx"] != self._pv_mode_idx:
            self._set_pv_mode(d["pv_mode_idx"])
        if "sp"     in d: self._sp = d["sp"];              self._sp_in.setText(f"{self._sp:.1f}")
        if "pv_lo"  in d: self._pv_lo = d["pv_lo"];        self._pvlo_in.setText(f"{self._pv_lo:.4g}")
        if "pv_hi"  in d: self._pv_hi = d["pv_hi"];        self._pvhi_in.setText(f"{self._pv_hi:.4g}")
        if "pid_kp" in d: self._pid.Kp = d["pid_kp"];      self._kp_in.setText(f"{self._pid.Kp:.4g}")
        if "pid_ki" in d: self._pid.Ki = d["pid_ki"];      self._ki_in.setText(f"{self._pid.Ki:.4g}")
        if "pid_kd" in d: self._pid.Kd = d["pid_kd"];      self._kd_in.setText(f"{self._pid.Kd:.4g}")
        if "fo_kp"  in d: self._fopdt.Kp = d["fo_kp"];     self._fkp.setText(f"{self._fopdt.Kp:.4g}")
        if "fo_tau" in d: self._fopdt.tau = d["fo_tau"];   self._fta.setText(f"{self._fopdt.tau:.1f}")
        if "fo_l"   in d: self._fopdt.L = d["fo_l"];       self._fL.setText(f"{self._fopdt.L:.1f}")
        if "auto" in d:
            self._pid.auto = d["auto"]
            self._mode_btn.setChecked(d["auto"])
            self._mode_btn.setText("AUTO" if d["auto"] else "MAN")
            self._mode_btn.setStyleSheet(self._mode_qss(d["auto"]))
            self._mv_widget.setVisible(not d["auto"])

    def update_display(self, pv: float, mv: float):
        span = max(1e-6, self._pv_hi - self._pv_lo)
        TH = self.TH
        def sb(fill, ratio):
            bh = max(2, int(max(0.0,min(1.0,ratio))*TH)); fill.setGeometry(2, TH-bh, 18, bh)
        sb(self._pv_fill, (pv-self._pv_lo)/span)
        sb(self._sp_fill, (self._sp-self._pv_lo)/span)
        sb(self._mv_fill, mv/100.0)
        self._pv_num.setText(f"{pv:.1f}"); self._sp_num.setText(f"{self._sp:.1f}")
        self._mv_num.setText(f"{mv:.0f}%")
        if not self._pid.auto and not self._mv_in.hasFocus():
            self._mv_in.setText(f"{self._pid.manual_mv:.1f}")

    @property
    def sp(self): return self._sp


# ═══════════════════════════════════════════════════════
#  CONNECTION-LINE OVERLAY
# ═══════════════════════════════════════════════════════
class _ConnectionOverlay(QWidget):
    """Transparent overlay that draws dim wires from stage boxes → faceplates.
    When a stage is selected the corresponding wire lights up with glow."""

    def __init__(self, content_widget):
        super().__init__(content_widget)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setStyleSheet("background:transparent;")
        self._schematic: _MauSchematic | None = None
        self._fps: list = []
        self._sel = -1          # faceplate index (0-5), -1 = none

    def setup(self, schematic, faceplates):
        self._schematic = schematic
        self._fps = list(faceplates)

    def set_sel(self, fp_idx: int):
        if self._sel != fp_idx:
            self._sel = fp_idx; self.update()

    def paintEvent(self, _):
        return  # overlay lines removed per user request
        if not self._schematic or not self._fps:
            return
        content = self.parent()
        try:
            isa_pts = self._schematic.isa_instrument_positions()
        except Exception:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        for fi, fp in enumerate(self._fps):
            if fi >= len(isa_pts):
                continue
            acc = QColor(_SACCNT[fi + 1])
            sel = (fi == self._sel)

            ix, iy = isa_pts[fi]
            # Map ISA circle center and faceplate top-center into overlay coords
            # (overlay is parented to content and covers content.rect() exactly)
            src = self._schematic.mapTo(content, QPoint(ix, iy))
            dst = fp.mapTo(content, QPoint(fp.width() // 2, 0))

            # L-shaped routing: vertical ↓ from ISA → horizontal → vertical ↓ to faceplate
            bus_y = dst.y() - 14
            p1 = QPoint(src.x(), bus_y)
            p2 = QPoint(dst.x(), bus_y)

            if sel:
                gpen = QPen(QColor(acc.red(), acc.green(), acc.blue(), 55), 10)
                gpen.setCapStyle(Qt.PenCapStyle.RoundCap)
                gpen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(gpen)
                p.drawLine(src, p1); p.drawLine(p1, p2); p.drawLine(p2, dst)
                cp = QPen(acc, 2, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                p.setPen(cp)
                p.drawLine(src, p1); p.drawLine(p1, p2); p.drawLine(p2, dst)
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(acc)
                p.drawEllipse(src, 4, 4); p.drawEllipse(dst, 4, 4)
            else:
                pen = QPen(QColor(acc.red(), acc.green(), acc.blue(), 38), 1)
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setDashPattern([5.0, 7.0])
                p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawLine(src, p1); p.drawLine(p1, p2); p.drawLine(p2, dst)

        p.end()


# ═══════════════════════════════════════════════════════
#  SIMULATION WORKER  (runs in QThread, owns sim state)
# ═══════════════════════════════════════════════════════
class _SimWorker(QObject):
    """All heavy simulation math runs here; emits results to the UI thread."""
    stepped = pyqtSignal(list, list, float, float)  # states, mvs, p_static, fan_hz
    _DT = 0.05

    def __init__(self, pid, fo, fp, oa_fn):
        super().__init__()
        self._pid = pid; self._fo = fo; self._fp = fp; self._oa_fn = oa_fn
        self._states: list = []; self._fan_hz = 45.0; self._p_static = 2000.0
        self._speed = 1

    @pyqtSlot()
    def start_sim(self):
        if not hasattr(self, '_timer'):
            self._timer = QTimer()
            self._timer.timeout.connect(self._tick)
        if not self._timer.isActive():
            self._timer.start(50)

    @pyqtSlot()
    def stop_sim(self):
        if hasattr(self, '_timer'): self._timer.stop()

    @pyqtSlot()
    def reset_sim(self):
        oa = self._oa_fn()
        self._states = [oa.copy() for _ in range(7)]
        self._fan_hz = 45.0; self._p_static = 2000.0
        for p in self._pid: p.reset()
        for f in self._fo: f.reset()

    @pyqtSlot(int)
    def set_speed(self, v): self._speed = v

    def _tick(self):
        for _ in range(self._speed):
            self._step(self._DT)
        self.stepped.emit(
            [s.copy() for s in self._states],
            [p.mv for p in self._pid],
            self._p_static, self._fan_hz,
        )

    def _step(self, dt):
        if not self._states: return
        oa = self._oa_fn(); s = [oa.copy() for _ in range(7)]

        mv_fan = self._pid[5].compute(self._p_static, self._fp[5].sp, dt)
        self._fan_hz = 30.0 + (mv_fan / 100.0) * 30.0
        fan_sc = 45.0 / max(self._fan_hz, 1.0)
        self._p_static = max(100.0, self._fo[5].step(mv_fan, dt, 1.0))

        # Low-airflow interlock: coil effectiveness capped to 5% when fan MV < 8%
        coil_ilock = 0.05 if mv_fan < 8.0 else 1.0

        pv_htc1 = self._states[1].h if self._fp[0].pv_mode_idx == 1 else self._states[1].T
        mv1 = self._pid[0].compute(pv_htc1, self._fp[0].sp, dt)
        T1 = min(40.0, oa.T + self._fo[0].step(mv1, dt, fan_sc) * coil_ilock)
        s[1] = AirState(T=T1, w=oa.w)

        mv2 = self._pid[1].compute(self._states[2].T, self._fp[1].sp, dt)
        T2 = max(7.0, s[1].T + self._fo[1].step(mv2, dt, fan_sc) * coil_ilock)
        w2 = s[1].w
        if T2 < Psych.t_dp(w2): w2 = max(0.0, Psych.omega_sat(T2))
        s[2] = AirState(T=T2, w=w2)

        mv3 = self._pid[2].compute(self._states[3].RH, self._fp[2].sp, dt)
        eta = min(0.92, max(0.0, self._fo[2].step(mv3, dt, 1.0) / 100.0)) * coil_ilock
        T_wb = Psych.t_wb(s[2].T, s[2].w); w_sat_wb = Psych.omega_sat(T_wb)
        T3 = s[2].T - eta * (s[2].T - T_wb)
        w3 = min(s[2].w + eta * (w_sat_wb - s[2].w), Psych.omega_sat(T3))
        s[3] = AirState(T=T3, w=w3)

        mv4 = self._pid[3].compute(self._states[4].T_dp, self._fp[3].sp, dt)
        T4 = max(7.0, s[3].T + self._fo[3].step(mv4, dt, fan_sc) * coil_ilock)
        w4 = s[3].w
        if T4 < Psych.t_dp(s[3].w): w4 = max(0.0, Psych.omega_sat(T4))
        s[4] = AirState(T=T4, w=w4)

        mv5 = self._pid[4].compute(self._states[5].T, self._fp[4].sp, dt)
        T5 = min(40.0, s[4].T + self._fo[4].step(mv5, dt, fan_sc) * coil_ilock)
        s[5] = AirState(T=T5, w=s[4].w)

        s[6] = s[5].copy(); self._states = s


# ═══════════════════════════════════════════════════════
#  TREND CHART  (QPainter rolling buffer, no pyqtgraph)
# ═══════════════════════════════════════════════════════
class _TrendChart(QWidget):
    """Rolling trend chart: auto Y-axis, dual Y-axis (PV left / MV right),
    wheel-zoom X, hover crosshair tooltip, PV/SP/MV toggle buttons."""
    _BG   = "#040C18"
    _GRID = "#0A1830"
    NPTS  = 300        # 300 × 50 ms = 15 s at speed=1
    PL, PR, PT, PB = 44, 40, 18, 16   # plot margins

    def __init__(self):
        super().__init__()
        self._bufs = {i: (deque(maxlen=self.NPTS),
                          deque(maxlen=self.NPTS),
                          deque(maxlen=self.NPTS))
                      for i in range(6)}
        self._sel      = -1
        self._pv_lo    = 0.0;  self._pv_hi = 100.0
        self._name     = "";   self._acc   = "#00B4D8"
        self._zoom_pts = self.NPTS    # visible X window (wheel-controlled)
        self._hover_x  = -1.0         # mouse X pixel (-1 = no hover)
        self._show_pv  = True
        self._show_sp  = True
        self._show_mv  = True

        self.setFixedHeight(110)
        self.setStyleSheet("background:#040C18;border:1px solid #0A1830;border-radius:4px;")
        self.setMouseTracking(True)

        # Toggle buttons (child widgets, positioned in resizeEvent)
        def _tbtn(label, fg, checked_bg):
            b = QPushButton(label, self)
            b.setCheckable(True); b.setChecked(True); b.setFixedSize(24, 13)
            b.setStyleSheet(
                f"QPushButton{{background:#080F1C;color:{fg};border:1px solid #1A3050;"
                f"border-radius:2px;font-size:6pt;font-family:Consolas;font-weight:700;padding:0;}}"
                f"QPushButton:checked{{background:{checked_bg};color:#000;border:1px solid {checked_bg};}}"
                f"QPushButton:!checked{{color:#333;border-color:#111;}}"
            )
            return b
        self._btn_pv = _tbtn("PV", "#00B4D8", "#00B4D8")
        self._btn_sp = _tbtn("SP", "#AAAAAA", "#888888")
        self._btn_mv = _tbtn("MV", "#FF7700", "#FF7700")
        for btn, attr in [(self._btn_pv,"_show_pv"),
                          (self._btn_sp,"_show_sp"),
                          (self._btn_mv,"_show_mv")]:
            btn.toggled.connect(lambda v, a=attr: (setattr(self, a, v), self.update()))

    # ── external API ────────────────────────────────────
    def push(self, idx: int, pv: float, sp: float, mv: float):
        b = self._bufs[idx]; b[0].append(pv); b[1].append(sp); b[2].append(mv)

    def select(self, fp_idx: int, name: str, pv_lo: float, pv_hi: float, acc: str):
        self._sel = fp_idx; self._name = name.replace("\n", " ")
        self._pv_lo = pv_lo; self._pv_hi = pv_hi; self._acc = acc
        # Sync PV button colour to stage accent
        self._btn_pv.setStyleSheet(
            f"QPushButton{{background:#080F1C;color:{acc};border:1px solid #1A3050;"
            f"border-radius:2px;font-size:6pt;font-family:Consolas;font-weight:700;padding:0;}}"
            f"QPushButton:checked{{background:{acc};color:#000;border:1px solid {acc};}}"
            f"QPushButton:!checked{{color:#333;border-color:#111;}}"
        )
        self.update()

    def clear_selection(self):
        self._sel = -1; self.update()

    # ── Qt events ───────────────────────────────────────
    def resizeEvent(self, e):
        super().resizeEvent(e)
        W = self.width()
        for i, btn in enumerate((self._btn_pv, self._btn_sp, self._btn_mv)):
            btn.move(W - 4 - (3 - i) * 27, 2)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if delta > 0:
            self._zoom_pts = max(30, int(self._zoom_pts * 0.78))
        else:
            self._zoom_pts = min(self.NPTS, int(self._zoom_pts * 1.28))
        self.update()

    def mouseMoveEvent(self, e):
        self._hover_x = e.position().x()
        self.update()

    def leaveEvent(self, e):
        self._hover_x = -1.0
        self.update()

    # ── paint ───────────────────────────────────────────
    def paintEvent(self, _):
        W, H = self.width(), self.height()
        PL, PR, PT, PB = self.PL, self.PR, self.PT, self.PB
        pw = W - PL - PR
        ph = H - PT - PB
        if pw < 10 or ph < 10: return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(self._BG))

        if self._sel < 0:
            p.setFont(QFont("Consolas", 8))
            p.setPen(QPen(QColor("#1A3A5A")))
            p.drawText(PL, PT, pw, ph, Qt.AlignmentFlag.AlignCenter,
                       "Click a stage to show trend")
            p.end(); return

        pv_b, sp_b, mv_b = self._bufs[self._sel]
        n = min(len(pv_b), self._zoom_pts)
        pv_win = list(pv_b)[-n:] if n else []
        sp_win = list(sp_b)[-n:] if n else []
        mv_win = list(mv_b)[-n:] if n else []

        # ── Auto Y-axis for PV/SP ───────────────────────
        all_pv_sp = []
        if self._show_pv and pv_win: all_pv_sp.extend(pv_win)
        if self._show_sp and sp_win: all_pv_sp.extend(sp_win)
        if all_pv_sp:
            y_min = min(all_pv_sp); y_max = max(all_pv_sp)
            pad = max(0.5, (y_max - y_min) * 0.15)
            y_min -= pad; y_max += pad
        else:
            y_min, y_max = self._pv_lo, self._pv_hi
        y_span = max(1e-4, y_max - y_min)

        # ── Background + grid ───────────────────────────
        p.fillRect(PL, PT, pw, ph, QColor("#03090F"))
        p.setPen(QPen(QColor(self._GRID), 1))
        NGRID = 4
        for gi in range(NGRID + 1):
            gy = PT + int(gi * ph / NGRID)
            p.drawLine(PL, gy, PL + pw, gy)
        for gi in range(6):
            gx = PL + int(gi * pw / 5)
            p.drawLine(gx, PT, gx, PT + ph)

        # ── Left Y-axis labels (PV/SP scale) ────────────
        p.setFont(QFont("Consolas", 7))
        p.setPen(QPen(QColor("#2A5A7A")))
        for gi in range(NGRID + 1):
            val = y_max - gi * y_span / NGRID
            gy  = PT + int(gi * ph / NGRID)
            p.drawText(0, gy - 6, PL - 3, 12,
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{val:.1f}")

        # ── Right Y-axis labels (MV 0-100%) ─────────────
        if self._show_mv:
            p.setPen(QPen(QColor("#7A4A1A")))
            for gi in range(3):
                val = 100 - gi * 50
                gy  = PT + int(gi * ph / 2)
                p.drawText(PL + pw + 3, gy - 6, PR - 3, 12,
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           f"{val:.0f}%")

        # ── Coordinate helpers ───────────────────────────
        def _px_pv(k, v):
            x = PL + int(k * pw / max(1, n - 1))
            r = (v - y_min) / y_span
            return QPoint(x, PT + ph - max(0, min(ph, int(r * ph))))

        def _px_mv(k, v):
            x = PL + int(k * pw / max(1, n - 1))
            r = max(0.0, min(1.0, v / 100.0))
            return QPoint(x, PT + ph - int(r * ph))

        def _draw_line(win, to_pt, clr, width, style=Qt.PenStyle.SolidLine):
            if len(win) < 2: return
            pen = QPen(QColor(clr), width, style)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            prev = None
            for k, v in enumerate(win):
                pt = to_pt(k, v)
                if prev: p.drawLine(prev, pt)
                prev = pt

        # ── Draw curves ──────────────────────────────────
        if self._show_sp:
            _draw_line(sp_win, _px_pv, "#778888", 1, Qt.PenStyle.DashLine)
        if self._show_mv:
            _draw_line(mv_win, _px_mv, "#CC5500", 1, Qt.PenStyle.DotLine)
        if self._show_pv:
            _draw_line(pv_win, _px_pv, self._acc, 2)

        # ── Hover crosshair + tooltip ────────────────────
        hx = self._hover_x
        if PL <= hx <= PL + pw and n > 1:
            ix = int((hx - PL) / pw * (n - 1) + 0.5)
            ix = max(0, min(ix, n - 1))
            cross_x = PL + int(ix * pw / max(1, n - 1))

            p.setPen(QPen(QColor("#FFFFFF50"), 1, Qt.PenStyle.DashLine))
            p.drawLine(cross_x, PT, cross_x, PT + ph)

            # Marker dots
            if self._show_pv and ix < len(pv_win):
                dp = _px_pv(ix, pv_win[ix])
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(self._acc)))
                p.drawEllipse(dp, 3, 3)
            if self._show_mv and ix < len(mv_win):
                dm = _px_mv(ix, mv_win[ix])
                p.setBrush(QBrush(QColor("#FF7700")))
                p.drawEllipse(dm, 3, 3)
            p.setBrush(Qt.BrushStyle.NoBrush)

            # Tooltip box
            tip_lines, tip_clrs = [], []
            if self._show_pv and ix < len(pv_win):
                tip_lines.append(f"PV  {pv_win[ix]:.2f}"); tip_clrs.append(self._acc)
            if self._show_sp and ix < len(sp_win):
                tip_lines.append(f"SP  {sp_win[ix]:.2f}"); tip_clrs.append("#888888")
            if self._show_mv and ix < len(mv_win):
                tip_lines.append(f"MV  {mv_win[ix]:.1f}%"); tip_clrs.append("#FF7700")

            if tip_lines:
                p.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                lh, bw_box, bpad = 13, 80, 4
                bh = len(tip_lines) * lh + bpad * 2
                bx = cross_x + 8
                by = PT + 4
                if bx + bw_box > PL + pw: bx = cross_x - bw_box - 6
                p.fillRect(bx, by, bw_box, bh, QColor("#0D1E33E0"))
                p.setPen(QPen(QColor("#2A4A6A"), 1))
                p.drawRect(bx, by, bw_box, bh)
                for i, (line, clr) in enumerate(zip(tip_lines, tip_clrs)):
                    p.setPen(QPen(QColor(clr)))
                    p.drawText(bx + bpad, by + bpad + i * lh, bw_box - bpad, lh,
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                               line)

        # ── Header label ─────────────────────────────────
        pv_now = pv_b[-1] if pv_b else 0.0
        sp_now = sp_b[-1] if sp_b else 0.0
        mv_now = mv_b[-1] if mv_b else 0.0
        zoom_s = f"  [{n}pt]" if n < self.NPTS else ""
        p.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        p.setPen(QPen(QColor(self._acc)))
        p.drawText(PL + 2, 0, pw - 85, PT, Qt.AlignmentFlag.AlignVCenter,
                   f"{self._name}   PV {pv_now:.1f}  SP {sp_now:.1f}  MV {mv_now:.0f}%{zoom_s}")

        # ── Bottom time label ─────────────────────────────
        secs = n * 0.05
        p.setFont(QFont("Consolas", 6))
        p.setPen(QPen(QColor("#2A4A6A")))
        p.drawText(PL, PT + ph + 1, pw, PB - 1, Qt.AlignmentFlag.AlignCenter,
                   f"← {secs:.0f} s →  (wheel to zoom)")

        p.end()


# ── Stage configuration table ──────────────────────────────────────────────
# (name, pv_lo, pv_hi, default_sp,
#  pid=(Kp,Ki,Kd,reverse), fo=(Kp,tau,L,heating), pv_modes_or_None)
_STAGE_DEFS = [
    ("HTC-1\nPREHEAT",   0.0,    40.0,   22.0,
     (2.5,  0.08, 0.0, True),  (0.28, 55.0,  5.0, True),
     [("T °C", 0.0, 40.0, 22.0), ("H kJ/kg", 0.0, 100.0, 40.0)]),
    ("CC-1\nPRECOOL",    7.0,    40.0,   24.0,
     (1.8,  0.05, 0.0, False), (0.22, 65.0,  6.0, False), None),
    ("WASHER\nHUMIDIFY", 50.0,  100.0,  100.0,
     (2.0,  0.10, 0.0, True),  (3.0,  30.0,  3.0, True),  None),
    ("CC-2\nDEHUMID",    7.0,    30.0,   10.0,
     (3.0,  0.15, 0.0, False), (0.22, 35.0,  4.0, False), None),
    ("HTC-2\nREHEAT",    7.0,    40.0,   22.0,
     (2.0,  0.10, 0.0, True),  (0.28, 45.0,  5.0, True),  None),
    ("SUPPLY\nFAN",      500.0, 4000.0, 2000.0,
     (0.05, 0.03, 0.0, True),  (40.0, 10.0,  1.0, True),  None),
]

# ═══════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════
class MauSimulator(BaseToolWindow):
    _BG = "#050B18"; _CELL = "#0A1428"; _BDR = "#162440"; _ACC = "#00B4D8"
    _DT = 0.05
    _sig_pause  = pyqtSignal()   # → worker.stop_sim
    _sig_resume = pyqtSignal()   # → worker.start_sim

    def __init__(self):
        super().__init__("🌬️ MAU PRO-SIM 7X   Industrial Psychrometrics Engine", 1400, 900)
        self._theme_idx = get_theme_idx()
        t = THEMES[self._theme_idx]
        self._BG = t["bg"]; self._CELL = t["cell"]; self._BDR = t["bdr"]; self._ACC = t["acc"]
        self.setMinimumSize(900, 600); self.content.setStyleSheet(f"background:{self._BG};")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._climate = "Winter"; self._speed = 1; self._sel = -1
        self._custom_T = 20.0; self._custom_RH = 60.0
        self._states = [AirState(6.0, Psych.omega(6.0, 50.0))] * 7
        self._fan_hz = 45.0; self._p_static = 2000.0

        self._pid = [PidCtrl(*d[4][:3], reverse=d[4][3]) for d in _STAGE_DEFS]
        self._fo  = [FopdtCoil(*d[5][:3], heating=d[5][3]) for d in _STAGE_DEFS]

        root = QVBoxLayout(self.content); root.setContentsMargins(4,4,4,4); root.setSpacing(4)
        root.addWidget(self._build_toolbar())

        # Paged body: page 0 = live sim, page 1 = formula sheet
        self._fv = {}           # live-value labels for formula page
        self._pages = QStackedWidget()
        self._pages.setStyleSheet(f"background:{self._BG};")

        p0 = QWidget(); p0.setStyleSheet(f"background:{self._BG};")
        mid = QHBoxLayout(p0); mid.setContentsMargins(0,0,0,0); mid.setSpacing(6)
        mid.addWidget(self._build_left(), 5); mid.addWidget(self._build_right(), 5)
        self._pages.addWidget(p0)
        self._pages.addWidget(self._build_formula_page())   # page 1

        body_row = QHBoxLayout(); body_row.setContentsMargins(0,0,0,0); body_row.setSpacing(0)
        body_row.addWidget(self._pages, 1)
        body_row.addWidget(self._build_nav_panel())
        root.addLayout(body_row, 3)
        root.addWidget(self._build_faceplates(), 2)

        # Connection-line overlay (covers full content, sits on top)
        self._overlay = _ConnectionOverlay(self.content)
        self._overlay.setup(self._schematic, self._fp)
        self._overlay.setGeometry(self.content.rect())
        self._overlay.raise_()

        self._ui_tick = 0; self._alarm_ticks = 0
        self._states: list = []; self._latest_mvs: list = [0.0] * 6
        self._p_static = 2000.0; self._fan_hz = 45.0

        # Simulation runs in a dedicated QThread; UI receives results via signal
        self._sim_thread = QThread(self)
        self._worker = _SimWorker(self._pid, self._fo, self._fp, self._oa)
        self._worker.moveToThread(self._sim_thread)
        self._worker.stepped.connect(self._on_sim_stepped)
        self._sim_thread.started.connect(self._worker.start_sim)
        self._sig_pause.connect(self._worker.stop_sim)
        self._sig_resume.connect(self._worker.start_sim)
        # Thread and timers start in showEvent (not here)

        # UI repaint timer (schematic animation only)
        self._ui_timer = QTimer(self); self._ui_timer.timeout.connect(self._refresh_anim)

        self._reset()
        self._load_mau_config()

    # ── layout ──────────────────────────────────────────
    def _build_toolbar(self):
        f = QFrame(); f.setFixedHeight(138)
        f.setStyleSheet("QFrame{background:#06091A;border-bottom:1px solid #162440;border-radius:0px;}")
        h = QHBoxLayout(f); h.setContentsMargins(18, 10, 18, 10); h.setSpacing(18)

        # ── CLIMATE PROFILE ──────────────────────────────
        cp_v = QVBoxLayout(); cp_v.setSpacing(6); cp_v.setContentsMargins(0,0,0,0)
        cap_cp = QLabel("CLIMATE PROFILE")
        cap_cp.setStyleSheet("color:#4A6A8A;font-size:8pt;font-weight:700;background:transparent;"
                             "border:none;font-family:Consolas;letter-spacing:2px;")
        cp_v.addWidget(cap_cp)
        br = QHBoxLayout(); br.setSpacing(8); br.setContentsMargins(0,0,0,0)
        self._btn_summer = QPushButton("SUMMER"); self._btn_summer.setFixedHeight(34)
        self._btn_winter = QPushButton("WINTER"); self._btn_winter.setFixedHeight(34)
        self._btn_custom = QPushButton("CUSTOM"); self._btn_custom.setFixedHeight(34)
        self._btn_summer.clicked.connect(lambda: self._set_climate("Summer"))
        self._btn_winter.clicked.connect(lambda: self._set_climate("Winter"))
        self._btn_custom.clicked.connect(lambda: self._set_climate("Custom"))
        br.addWidget(self._btn_summer); br.addWidget(self._btn_winter); br.addWidget(self._btn_custom)
        cp_v.addLayout(br)

        # Custom OA input row (shown only when CUSTOM is active)
        self._custom_row = QWidget()
        self._custom_row.setStyleSheet("QWidget{background:transparent;border:none;}")
        cr = QHBoxLayout(self._custom_row)
        cr.setContentsMargins(2, 2, 0, 0); cr.setSpacing(5)
        def _clbl(t):
            l = QLabel(t); l.setStyleSheet("color:#7AAABB;font-size:9pt;font-weight:700;"
                                           "background:transparent;border:none;font-family:Consolas;")
            return l
        def _cinp(val, clr, w=62):
            e = QLineEdit(val); e.setFixedSize(w, 24); e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e.setStyleSheet(f"QLineEdit{{background:#060E1A;color:{clr};"
                            f"border:1px solid #1A3050;border-radius:3px;"
                            f"font-size:10pt;font-weight:700;font-family:Consolas;}}"
                            f"QLineEdit:focus{{border:1px solid #00B4D8;}}")
            return e
        def _arrows(le, step, lo, hi, fmt=".1f"):
            vw = QWidget(); vl = QVBoxLayout(vw)
            vl.setContentsMargins(0,0,0,0); vl.setSpacing(1)
            def _adj(d):
                try: cur = float(le.text())
                except: return
                le.setText(format(max(lo, min(hi, cur + d)), fmt))
                self._commit_custom()
            for sym, d in [("▲", step), ("▼", -step)]:
                b = QPushButton(sym); b.setFixedSize(18, 11)
                b.setStyleSheet("QPushButton{background:#0E1C2E;color:#7AAFDF;"
                                "border:1px solid #1A3050;border-radius:2px;font-size:7px;padding:0;}"
                                "QPushButton:hover{background:#1A3050;color:#AADDFF;}"
                                "QPushButton:pressed{background:#2A5080;}")
                b.clicked.connect(lambda _, d=d: _adj(d))
                vl.addWidget(b)
            return vw
        self._custom_T_in  = _cinp(f"{self._custom_T:.1f}",  "#FFAA55")
        self._custom_RH_in = _cinp(f"{self._custom_RH:.0f}", "#55DDEE", 54)
        self._custom_T_in.editingFinished.connect(self._commit_custom)
        self._custom_RH_in.editingFinished.connect(self._commit_custom)
        cr.addWidget(_clbl("T")); cr.addWidget(self._custom_T_in)
        cr.addWidget(_arrows(self._custom_T_in, 0.5, -20.0, 55.0))
        cr.addWidget(_clbl("°C")); cr.addSpacing(10)
        cr.addWidget(_clbl("RH")); cr.addWidget(self._custom_RH_in)
        cr.addWidget(_arrows(self._custom_RH_in, 1.0, 10.0, 100.0, ".0f"))
        cr.addWidget(_clbl("%")); cr.addStretch()
        self._custom_row.setVisible(False)
        cp_v.addWidget(self._custom_row)
        h.addLayout(cp_v)
        self._update_clim_btns()

        # ── Divider ──────────────────────────────────────
        h.addWidget(self._vsep())

        # ── OA TEMP + OA RH ──────────────────────────────
        oa_v = QVBoxLayout(); oa_v.setSpacing(6); oa_v.setContentsMargins(0,0,0,0)
        oa_row = QHBoxLayout(); oa_row.setSpacing(28); oa_row.setContentsMargins(0,0,0,0)
        def _oa_col(cap_txt, cap_clr):
            c = QVBoxLayout(); c.setSpacing(2); c.setContentsMargins(0,0,0,0)
            cap = QLabel(cap_txt)
            cap.setStyleSheet(f"color:#4A6A8A;font-size:8pt;font-weight:700;background:transparent;"
                              f"border:none;font-family:Consolas;letter-spacing:1px;")
            lbl = QLabel("—")
            lbl.setStyleSheet(f"color:{cap_clr};font-size:22pt;font-weight:700;background:transparent;"
                              f"border:none;font-family:'Segoe UI',Consolas;")
            c.addWidget(cap); c.addWidget(lbl); return c, lbl
        T_col, self._oa_T_lbl = _oa_col("OA TEMP", "#E0ECF8")
        RH_col, self._oa_RH_lbl = _oa_col("OA RH",  "#E0ECF8")
        oa_row.addLayout(T_col); oa_row.addLayout(RH_col)
        oa_v.addLayout(oa_row); h.addLayout(oa_v)

        # ── Speed + Reset (compact) ───────────────────────
        h.addWidget(self._vsep())
        ctrl_v = QVBoxLayout(); ctrl_v.setSpacing(4); ctrl_v.setContentsMargins(0,0,0,0)
        spd = QComboBox()
        for v in ("1×","2×","5×","10×"): spd.addItem(v)
        spd.setFixedSize(62, 28)
        spd.setStyleSheet(f"QComboBox{{background:#0A1428;color:#CCC;border:1px solid #1A2A40;"
                          f"border-radius:3px;font-size:9pt;font-weight:700;padding:1px 4px;"
                          f"font-family:Consolas;}}QComboBox::drop-down{{border:none;width:10px;}}"
                          f"QComboBox QAbstractItemView{{background:#0A1428;color:#CCC;"
                          f"border:1px solid #1A2A40;}}")
        spd.currentIndexChanged.connect(lambda i: self._set_speed([1,2,5,10][i]))
        rst = QPushButton("⟳ RESET"); rst.setFixedSize(82, 28)
        rst.setStyleSheet("QPushButton{background:#181800;color:#AAAA00;border:1px solid #333300;"
                          "border-radius:3px;font-size:9pt;font-weight:700;font-family:Consolas;}"
                          "QPushButton:hover{background:#222200;color:#FFFF00;}")
        rst.clicked.connect(self._reset)
        exp = QPushButton("↓ EXPORT"); exp.setFixedSize(82, 28)
        exp.setStyleSheet("QPushButton{background:#0A1C10;color:#44CC66;border:1px solid #1A4020;"
                          "border-radius:3px;font-size:9pt;font-weight:700;font-family:Consolas;}"
                          "QPushButton:hover{background:#102810;color:#66FF88;}")
        exp.clicked.connect(self._export_report)
        tp_row = QHBoxLayout(); tp_row.setContentsMargins(0,0,0,0); tp_row.setSpacing(3)
        tp_lbl = QLabel("THEME:")
        tp_lbl.setStyleSheet("color:#3A5A7A;font-size:8pt;font-weight:600;background:transparent;"
                             "border:none;font-family:Consolas;")
        self._theme_picker = ThemePicker(self._apply_theme)
        tp_row.addWidget(tp_lbl); tp_row.addWidget(self._theme_picker); tp_row.addStretch()
        ctrl_v.addWidget(spd); ctrl_v.addWidget(rst); ctrl_v.addWidget(exp)
        ctrl_v.addLayout(tp_row)
        h.addLayout(ctrl_v)

        h.addStretch()

        # ── FINAL SUPPLY AIR card ─────────────────────────
        sa_card = QFrame()
        sa_card.setStyleSheet("QFrame{background:#09122A;border:1px solid #1E3060;border-radius:8px;}")
        sa_l = QVBoxLayout(sa_card); sa_l.setContentsMargins(20, 8, 20, 8); sa_l.setSpacing(6)
        sa_cap = QLabel("FINAL SUPPLY AIR"); sa_cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sa_cap.setStyleSheet("color:#00B4D8;font-size:9pt;font-weight:700;background:transparent;"
                             "border:none;font-family:Consolas;letter-spacing:2px;")
        sa_l.addWidget(sa_cap)
        sa_row = QHBoxLayout(); sa_row.setSpacing(26); sa_row.setContentsMargins(0,0,0,0)
        def _sa_col(sub_lbl, val_clr):
            c = QVBoxLayout(); c.setSpacing(2); c.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c.setContentsMargins(0,0,0,0)
            sc = QLabel(sub_lbl); sc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sc.setStyleSheet("color:#4A6A8A;font-size:8pt;font-weight:700;background:transparent;"
                             "border:none;font-family:Consolas;")
            vl = QLabel("—"); vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vl.setStyleSheet(f"color:{val_clr};font-size:22pt;font-weight:700;background:transparent;"
                             f"border:none;font-family:'Segoe UI',Consolas;")
            c.addWidget(sc); c.addWidget(vl); return c, vl
        Tc, self._final_T_lbl = _sa_col("TEMP", "#00D4FF")
        Rc, self._final_lbl   = _sa_col("RH",   "#00FF9F")
        sa_row.addLayout(Tc); sa_row.addLayout(Rc)
        sa_l.addLayout(sa_row); h.addWidget(sa_card)

        h.addStretch()

        # ── Title ─────────────────────────────────────────
        title_v = QVBoxLayout(); title_v.setSpacing(4); title_v.setContentsMargins(0,0,0,0)
        title_v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        t1 = QLabel("MAU UNIT SCHEMATIC"); t1.setAlignment(Qt.AlignmentFlag.AlignRight)
        t1.setStyleSheet("color:#E0ECF8;font-size:18pt;font-weight:700;background:transparent;"
                         "border:none;font-family:'Segoe UI',Consolas;letter-spacing:1px;")
        t2 = QLabel("PROCESS VISUALIZATION"); t2.setAlignment(Qt.AlignmentFlag.AlignRight)
        t2.setStyleSheet("color:#3A5A7A;font-size:9pt;font-weight:600;background:transparent;"
                         "border:none;font-family:Consolas;letter-spacing:2px;")
        title_v.addWidget(t1); title_v.addWidget(t2); h.addLayout(title_v)
        return f

    def _apply_theme(self, idx: int):
        old_t = THEMES[self._theme_idx]
        new_t = THEMES[idx]
        self._theme_idx = idx
        self._BG   = new_t["bg"];   self._CELL = new_t["cell"]
        self._BDR  = new_t["bdr"]; self._ACC  = new_t["acc"]
        mapping = [
            (old_t["bg"],         new_t["bg"]),
            (old_t["toolbar_bg"], new_t["toolbar_bg"]),
            (old_t["cell"],       new_t["cell"]),
            (old_t["card_bg"],    new_t["card_bg"]),
            (old_t["bdr"],        new_t["bdr"]),
            (old_t["acc"],        new_t["acc"]),
        ]
        for w in [self] + list(self.findChildren(QWidget)):
            ss = w.styleSheet()
            if not ss:
                continue
            changed = False
            for old_c, new_c in mapping:
                if old_c in ss:
                    ss = ss.replace(old_c, new_c)
                    changed = True
            if changed:
                w.setStyleSheet(ss)

    def _build_left(self):
        f = QFrame(); f.setStyleSheet(f"QFrame{{background:{self._BG};border:none;}}")
        lay = QVBoxLayout(f); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)
        self._schematic = _MauSchematic(select_cb=self._on_schematic_click)
        self._schematic.setMinimumHeight(300)
        self._schematic.setMaximumHeight(380)
        lay.addWidget(self._schematic, 1)
        # ── trend chart + zoom toggle ─────────────────────
        trend_wrap = QFrame()
        trend_wrap.setStyleSheet("QFrame{background:transparent;border:none;}")
        tw_lay = QVBoxLayout(trend_wrap); tw_lay.setContentsMargins(0,0,0,0); tw_lay.setSpacing(0)

        zoom_bar = QWidget(); zoom_bar.setFixedHeight(20)
        zoom_bar.setStyleSheet("background:transparent;")
        zb_lay = QHBoxLayout(zoom_bar); zb_lay.setContentsMargins(0,0,4,0)
        self._zoom_btn = QPushButton("⛶")
        self._zoom_btn.setFixedSize(20, 16)
        self._zoom_btn.setToolTip("展開 / 收合趨勢圖")
        self._zoom_btn.setStyleSheet(
            "QPushButton{background:#0A1830;color:#4A7A9A;border:1px solid #1A3050;"
            "border-radius:3px;font-size:9pt;padding:0;}"
            "QPushButton:hover{color:#00B4D8;border-color:#00B4D8;}"
        )
        self._zoom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        zb_lay.addStretch(); zb_lay.addWidget(self._zoom_btn)
        tw_lay.addWidget(zoom_bar)

        self._trend = _TrendChart()
        tw_lay.addWidget(self._trend)
        self._trend_expanded = False
        self._zoom_btn.clicked.connect(self._toggle_trend_zoom)
        lay.addWidget(trend_wrap)
        return f

    def _toggle_trend_zoom(self):
        self._trend_expanded = not self._trend_expanded
        target = 260 if self._trend_expanded else 110
        self._zoom_btn.setText("⊟" if self._trend_expanded else "⛶")
        # Allow widget to resize during animation
        self._trend.setMinimumHeight(0)
        self._trend.setMaximumHeight(9999)
        anim = QPropertyAnimation(self._trend, b"maximumHeight", self)
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(self._trend.height())
        anim.setEndValue(target)
        anim.finished.connect(lambda t=target: self._trend.setFixedHeight(t))
        self._trend_anim = anim   # prevent GC
        anim.start()

    def _build_strip(self):
        f = QFrame(); f.setFixedHeight(88)
        f.setStyleSheet(f"QFrame{{background:{self._CELL};border:1px solid {self._BDR};border-radius:3px;}}")
        h = QHBoxLayout(f); h.setContentsMargins(6,3,6,3); h.setSpacing(0)
        hdrs = ["OA INLET","HTC-1","CC-1","WASHER","CC-2","HTC-2","SUPPLY FAN"]
        self._strip = []
        for i, hdr in enumerate(hdrs):
            col = QVBoxLayout(); col.setSpacing(1); col.setContentsMargins(2,0,2,0)
            hl = QLabel(hdr); hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hl.setStyleSheet(f"color:{_SACCNT[i]};font-size:8.5pt;font-weight:700;"
                             f"background:transparent;border:none;font-family:'Microsoft JhengHei',Consolas;")
            col.addWidget(hl); row = []
            for _ in range(3):
                l = QLabel("—"); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                l.setStyleSheet("color:#D8E4EE;font-size:8pt;font-weight:600;"
                                "background:transparent;border:none;font-family:Consolas;")
                col.addWidget(l); row.append(l)
            self._strip.append(row); h.addLayout(col, 1)
            if i < len(hdrs)-1:
                d = QFrame(); d.setFrameShape(QFrame.Shape.VLine)
                d.setStyleSheet(f"QFrame{{border:none;border-left:1px solid {self._BDR};background:transparent;}}"); h.addWidget(d)
        return f

    def _build_faceplates(self):
        f = QFrame(); f.setStyleSheet(f"QFrame{{background:{self._BG};border:none;}}")
        h = QHBoxLayout(f); h.setContentsMargins(3, 3, 3, 3); h.setSpacing(5)

        self._fp: list[_StageFaceplate] = []
        for i, (name, lo, hi, sp, _, _, modes) in enumerate(_STAGE_DEFS):
            fp = _StageFaceplate(name, self._pid[i], self._fo[i], lo, hi,
                                 select_cb=lambda i=i: self._set_selected(i),
                                 pv_modes=modes,
                                 on_change=self._save_mau_config)
            if not modes:
                fp._sp = sp; fp._sp_in.setText(f"{sp:.1f}")
            self._fp.append(fp); h.addWidget(fp, 1)
        return f

    # ── Page navigation ─────────────────────────────────
    def _build_nav_panel(self):
        _SS = ("QPushButton{background:#001A2E;color:#009EC8;border:2px solid #005577;"
               "border-radius:6px;font-size:22pt;font-weight:900;}"
               "QPushButton:hover{background:#003A55;color:#00EEFF;"
               "border:2px solid #00D4FF;}"
               "QPushButton:pressed{background:#00D4FF;color:#000A14;"
               "border:2px solid #00FFFF;}")
        f = QFrame(); f.setFixedWidth(46)
        f.setStyleSheet("QFrame{background:#04091A;border-left:2px solid #005577;}")
        v = QVBoxLayout(f); v.setContentsMargins(5,12,5,12); v.setSpacing(8)

        self._pg_up = QPushButton("▲"); self._pg_up.setFixedSize(36,90)
        self._pg_dn = QPushButton("▼"); self._pg_dn.setFixedSize(36,90)
        self._pg_up.setStyleSheet(_SS); self._pg_dn.setStyleSheet(_SS)
        self._pg_up.clicked.connect(lambda: self._set_page(-1))
        self._pg_dn.clicked.connect(lambda: self._set_page(+1))

        self._pg_dots = []
        for _ in range(2):
            d = QLabel("●"); d.setAlignment(Qt.AlignmentFlag.AlignCenter)
            d.setFixedHeight(12); d.setStyleSheet("background:transparent;border:none;font-size:8pt;")
            self._pg_dots.append(d); v.addWidget(d)

        v.insertWidget(0, self._pg_up)
        v.addStretch()
        v.addWidget(self._pg_dn)
        self._refresh_pg_dots()
        return f

    def _set_page(self, delta):
        n = self._pages.count()
        self._pages.setCurrentIndex((self._pages.currentIndex() + delta) % n)
        self._refresh_pg_dots()

    def _refresh_pg_dots(self):
        cur = self._pages.currentIndex()
        for i, d in enumerate(self._pg_dots):
            d.setStyleSheet("background:transparent;border:none;font-size:8pt;"
                            + ("color:#00D4FF;" if i == cur else "color:#1A3050;"))

    # ── Formula page ─────────────────────────────────────
    def _fl(self, key, color="#A8C4DC"):
        l = QLabel("—")
        l.setStyleSheet(f"color:{color};font:500 7.5pt Consolas;background:transparent;"
                        "border:none;letter-spacing:0.2px;")
        l.setWordWrap(True); self._fv[key] = l; return l

    def _fsec(self, txt, color="#3A6080"):
        l = QLabel(txt)
        l.setStyleSheet(f"color:{color};font:700 7pt Consolas;background:transparent;"
                        "border:none;letter-spacing:1.5px;margin-top:2px;")
        return l

    def _fcard(self, title, accent, builder_fn):
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:#060C1C;border:1px solid {accent};"
                        "border-radius:5px;}}")
        v = QVBoxLayout(f); v.setContentsMargins(7,5,7,5); v.setSpacing(2)
        hdr = QLabel(title)
        hdr.setStyleSheet(f"color:{accent};font:700 8.5pt Consolas;background:transparent;"
                          "border:none;letter-spacing:1px;")
        v.addWidget(hdr)
        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{accent};border:none;max-width:9999px;")
        v.addWidget(sep)
        builder_fn(v)
        v.addStretch()
        return f

    def _build_formula_page(self):
        outer = QWidget(); outer.setStyleSheet(f"background:{self._BG};")
        vroot = QVBoxLayout(outer); vroot.setContentsMargins(4,4,4,4); vroot.setSpacing(4)

        ttl = QLabel("  PSYCHROMETRIC PROCESS FORMULA SHEET  ─  REAL-TIME SUBSTITUTED VALUES")
        ttl.setStyleSheet(f"color:#4A6A8A;font:700 9pt Consolas;letter-spacing:2px;"
                          f"background:{self._CELL};border:1px solid {self._BDR};"
                          "border-radius:3px;padding:5px 10px;")
        vroot.addWidget(ttl)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}"
                             f"QScrollBar:vertical{{width:8px;background:{self._BG};}}"
                             "QScrollBar::handle:vertical{background:#1A3050;border-radius:4px;}"
                             "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        g = QGridLayout(inner); g.setContentsMargins(0,0,4,4); g.setSpacing(5)
        g.setColumnStretch(0,1); g.setColumnStretch(1,1); g.setColumnStretch(2,1)

        cards = [
            self._fcard("① OA INLET",       _SACCNT[0], self._fbuild_oa),
            self._fcard("② HTC-1 PREHEAT",  _SACCNT[1], self._fbuild_htc1),
            self._fcard("③ CC-1 PRECOOL",   _SACCNT[2], self._fbuild_cc1),
            self._fcard("④ WASHER HUMIDIFY", _SACCNT[3], self._fbuild_washer),
            self._fcard("⑤ CC-2 DEHUMID",   _SACCNT[4], self._fbuild_cc2),
            self._fcard("⑥ HTC-2 REHEAT",   _SACCNT[5], self._fbuild_htc2),
            self._fcard("⑦ SUPPLY FAN",      _SACCNT[6], self._fbuild_fan),
        ]
        positions = [(0,0),(0,1),(0,2),(1,0),(1,1),(1,2),(2,0)]
        spans     = [(1,1),(1,1),(1,1),(1,1),(1,1),(1,1),(1,3)]
        for card, (r,c), (rs,cs) in zip(cards, positions, spans):
            g.addWidget(card, r, c, rs, cs)

        scroll.setWidget(inner); vroot.addWidget(scroll, 1)
        return outer

    # ── Formula card content builders ────────────────────
    def _fbuild_oa(self, v):
        v.addWidget(self._fsec("INLET STATE"))
        v.addWidget(self._fl("oa_state", "#00D4FF"))
        v.addWidget(self._fsec("SAT. PRESSURE  Pws(T) = 0.611·exp(17.27T/(T+237.3))"))
        v.addWidget(self._fl("oa_pws"))
        v.addWidget(self._fsec("PARTIAL PRESSURE  Pw = ω·P / (0.622 + ω),   P=101.325 kPa"))
        v.addWidget(self._fl("oa_pw"))
        v.addWidget(self._fsec("ENTHALPY  h = 1.006·T + ω·(2501 + 1.86·T)  [kJ/kg]"))
        v.addWidget(self._fl("oa_h"))
        v.addWidget(self._fsec("DEW POINT  Tdp = 237.3·r/(17.27−r),  r = ln(Pw/0.611)"))
        v.addWidget(self._fl("oa_tdp"))
        v.addWidget(self._fsec("WET BULB  Twb (bisection on adiabatic saturation line)"))
        v.addWidget(self._fl("oa_twb"))

    def _fbuild_htc1(self, v):
        v.addWidget(self._fsec("INLET STATE (= OA)"))
        v.addWidget(self._fl("htc1_in", "#FF6B35"))
        v.addWidget(self._fsec("PID — REVERSE ACTION  (SP−PV), Kp=2.5  Ki=0.08"))
        v.addWidget(self._fl("htc1_pid"))
        v.addWidget(self._fsec("SENSIBLE HEATING — ω CONSTANT"))
        v.addWidget(self._fl("htc1_fopdt"))
        v.addWidget(self._fl("htc1_dT"))
        v.addWidget(self._fsec("HEAT ENERGY  Q = ṁ·Cpa·ΔT  (ṁ=1 kg/s dry air)"))
        v.addWidget(self._fl("htc1_Q"))
        v.addWidget(self._fsec("OUTLET STATE"))
        v.addWidget(self._fl("htc1_out", "#00FF88"))

    def _fbuild_cc1(self, v):
        v.addWidget(self._fsec("INLET STATE (= HTC-1 OUT)"))
        v.addWidget(self._fl("cc1_in", "#00D4FF"))
        v.addWidget(self._fsec("PID — DIRECT ACTION  (PV−SP), Kp=1.8  Ki=0.05"))
        v.addWidget(self._fl("cc1_pid"))
        v.addWidget(self._fsec("DEW POINT CHECK  Tdp_in vs T_out"))
        v.addWidget(self._fl("cc1_dpcheck"))
        v.addWidget(self._fsec("CONDENSATION  ω_out = ω_sat(T_out) if T_out < Tdp"))
        v.addWidget(self._fl("cc1_cond"))
        v.addWidget(self._fsec("COOLING LOAD  Q = ṁ·(h_in − h_out)"))
        v.addWidget(self._fl("cc1_Q"))
        v.addWidget(self._fsec("OUTLET STATE"))
        v.addWidget(self._fl("cc1_out", "#00FF88"))

    def _fbuild_washer(self, v):
        v.addWidget(self._fsec("INLET STATE (= CC-1 OUT)"))
        v.addWidget(self._fl("ws_in", "#00FF9F"))
        v.addWidget(self._fsec("PID — REVERSE ACTION  (SP−PV on RH), Kp=1.5  Ki=0.10"))
        v.addWidget(self._fl("ws_pid"))
        v.addWidget(self._fsec("ADIABATIC HUMIDIFICATION  (等焓加濕 — h ≈ const)"))
        v.addWidget(self._fl("ws_twb"))
        v.addWidget(self._fsec("ω_sat(Twb) = 0.622·Pws(Twb) / (P − Pws(Twb))"))
        v.addWidget(self._fl("ws_wsat"))
        v.addWidget(self._fsec("EFFECTIVENESS  η = FOPDT_out/100  (capped 0.92)"))
        v.addWidget(self._fl("ws_eta"))
        v.addWidget(self._fsec("ω_out = ω_in + η·(ω_sat(Twb) − ω_in)"))
        v.addWidget(self._fl("ws_wout"))
        v.addWidget(self._fsec("T_out ≈ Twb + (1−η)·(T_in − Twb)"))
        v.addWidget(self._fl("ws_Tout"))
        v.addWidget(self._fsec("MOISTURE ADDED  Δω = ω_out − ω_in"))
        v.addWidget(self._fl("ws_dw"))
        v.addWidget(self._fsec("OUTLET STATE"))
        v.addWidget(self._fl("ws_out", "#00FF88"))

    def _fbuild_cc2(self, v):
        v.addWidget(self._fsec("INLET STATE (= WASHER OUT)"))
        v.addWidget(self._fl("cc2_in", "#2E86FF"))
        v.addWidget(self._fsec("PID — DIRECT ACTION  PV = Tdp_out (出風露點)  SP = target Tdp"))
        v.addWidget(self._fl("cc2_pid"))
        v.addWidget(self._fsec("OUTLET DEW POINT  Tdp_out = 237.3·r/(17.27−r), r=ln(Pw_out/0.611)"))
        v.addWidget(self._fl("cc2_dpformula"))
        v.addWidget(self._fsec("CONDENSATION  T_out vs Tdp_in — if T_out<Tdp_in: wet coil"))
        v.addWidget(self._fl("cc2_dpcheck"))
        v.addWidget(self._fsec("ω_out = ω_sat(T_out) = 0.622·Pws(T_out)/(P−Pws(T_out))"))
        v.addWidget(self._fl("cc2_cond"))
        v.addWidget(self._fsec("DEHUMID LOAD  Q = ṁ·(h_in − h_out)"))
        v.addWidget(self._fl("cc2_Q"))
        v.addWidget(self._fsec("OUTLET STATE  [SAMPLE: 出風口]"))
        v.addWidget(self._fl("cc2_out", "#00FF88"))

    def _fbuild_htc2(self, v):
        v.addWidget(self._fsec("INLET STATE (= CC-2 OUT)"))
        v.addWidget(self._fl("htc2_in", "#FFB300"))
        v.addWidget(self._fsec("PID — REVERSE ACTION  PV = T_out (出風乾球溫度)  SP = target T"))
        v.addWidget(self._fl("htc2_pid"))
        v.addWidget(self._fsec("SENSIBLE REHEATING — ω CONSTANT (無冷凝)"))
        v.addWidget(self._fl("htc2_fopdt"))
        v.addWidget(self._fl("htc2_dT"))
        v.addWidget(self._fsec("REHEAT ENERGY  Q = ṁ·(1.006+1.86ω)·ΔT  [kW]"))
        v.addWidget(self._fl("htc2_Q"))
        v.addWidget(self._fsec("OUTLET STATE  [SAMPLE: 出風口 乾球溫度]"))
        v.addWidget(self._fl("htc2_out", "#00FF88"))

    def _fbuild_fan(self, v):
        v.addWidget(self._fsec("INLET STATE (= HTC-2 OUT)"))
        v.addWidget(self._fl("fan_in", "#BB77FF"))
        v.addWidget(self._fsec("PID — REVERSE ACTION  (SP−PV on Pa), Kp=0.5  Ki=0.03"))
        v.addWidget(self._fl("fan_pid"))
        v.addWidget(self._fsec("STATIC PRESSURE MODEL  P_static = FOPDT(MV_fan)"))
        v.addWidget(self._fl("fan_ps"))
        v.addWidget(self._fsec("FAN SPEED  Hz ∝ MV%  (rated 50 Hz @ 100%)"))
        v.addWidget(self._fl("fan_hz"))
        v.addWidget(self._fsec("SUPPLY AIR (fan heat gain negligible in model)"))
        v.addWidget(self._fl("fan_out", "#00FF88"))

    def _update_formula_page(self):
        if not self._fv: return
        s = self._states
        mvs = [p.mv for p in self._pid]
        fo = self._fo

        # ── OA ───────────────────────────────────────────
        oa = s[0]
        pws0 = Psych.pws(oa.T)
        pw0  = oa.w * Psych.P / (0.62198 + oa.w)
        self._fv['oa_state'].setText(
            f"T={oa.T:.1f}°C   ω={oa.w*1000:.2f} g/kg   φ={oa.RH:.1f}%   "
            f"h={oa.h:.2f} kJ/kg")
        self._fv['oa_pws'].setText(
            f"Pws({oa.T:.1f}) = 0.611·exp(17.27×{oa.T:.1f}/({oa.T:.1f}+237.3)) = {pws0:.4f} kPa")
        self._fv['oa_pw'].setText(
            f"Pw = {oa.w:.5f}×101.325/(0.622+{oa.w:.5f}) = {pw0:.4f} kPa  →  "
            f"φ = {pw0:.4f}/{pws0:.4f}×100 = {oa.RH:.1f}%")
        self._fv['oa_h'].setText(
            f"h = 1.006×{oa.T:.1f} + {oa.w:.5f}×(2501+1.86×{oa.T:.1f}) = {oa.h:.2f} kJ/kg")
        self._fv['oa_tdp'].setText(
            f"r = ln({pw0:.4f}/0.611) = {math.log(max(pw0,1e-9)/0.611):.4f}  →  "
            f"Tdp = {oa.T_dp:.1f}°C")
        self._fv['oa_twb'].setText(f"Twb = {oa.T_wb:.1f}°C")

        # ── HTC-1 ─────────────────────────────────────────
        s0, s1 = s[0], s[1]
        mv1 = mvs[0]
        pv_htc1 = s1.h if self._fp[0].pv_mode_idx == 1 else s1.T
        sp_htc1 = self._fp[0].sp
        e1 = sp_htc1 - pv_htc1
        dT1 = s1.T - s0.T
        Cpa1 = 1.006 + 1.86 * s0.w
        Q1 = Cpa1 * abs(dT1)
        self._fv['htc1_in'].setText(
            f"T={s0.T:.1f}°C  ω={s0.w*1000:.2f} g/kg  φ={s0.RH:.1f}%  "
            f"Tdp={s0.T_dp:.1f}°C  h={s0.h:.2f} kJ/kg")
        self._fv['htc1_pid'].setText(
            f"e = {sp_htc1:.1f} − {pv_htc1:.1f} = {e1:.1f}    MV = {mv1:.1f}%")
        self._fv['htc1_fopdt'].setText(
            f"FOPDT: Gain={fo[0].Kp:.2f}  τ={fo[0].tau:.0f}s  L={fo[0].L:.1f}s  "
            f"heating={'YES' if fo[0].heating else 'NO'}")
        self._fv['htc1_dT'].setText(
            f"T_out = T_in+ΔT = {s0.T:.1f}+{dT1:.1f} = {s1.T:.1f}°C   "
            f"ω_out = ω_in = {s1.w*1000:.2f} g/kg")
        self._fv['htc1_Q'].setText(
            f"Q = 1×{Cpa1:.3f}×|{dT1:.1f}| = {Q1:.2f} kW")
        self._fv['htc1_out'].setText(
            f"T={s1.T:.1f}°C  ω={s1.w*1000:.2f} g/kg  φ={s1.RH:.1f}%  "
            f"Tdp={s1.T_dp:.1f}°C  h={s1.h:.2f} kJ/kg")

        # ── CC-1 ──────────────────────────────────────────
        s1i, s2 = s[1], s[2]
        mv2 = mvs[1]
        e2 = s2.T - self._fp[1].sp
        dT2 = s2.T - s1i.T
        tdp1 = s1i.T_dp
        dry2 = s2.T >= tdp1
        dw2 = (s1i.w - s2.w) * 1000
        Q2 = abs(s1i.h - s2.h)
        self._fv['cc1_in'].setText(
            f"T={s1i.T:.1f}°C  ω={s1i.w*1000:.2f} g/kg  φ={s1i.RH:.1f}%  "
            f"Tdp={tdp1:.1f}°C  h={s1i.h:.2f} kJ/kg")
        self._fv['cc1_pid'].setText(
            f"e = {s2.T:.1f} − {self._fp[1].sp:.1f} = {e2:.1f}    MV = {mv2:.1f}%")
        self._fv['cc1_dpcheck'].setText(
            f"Tdp_in={tdp1:.1f}°C   T_out={s2.T:.1f}°C   "
            f"→ {'DRY (T_out≥Tdp, ω=const)' if dry2 else 'WET (T_out<Tdp, condensation)'}")
        self._fv['cc1_cond'].setText(
            f"ω_out = {'ω_in=' if dry2 else 'ω_sat(T_out)='}{s2.w*1000:.2f} g/kg   "
            f"Condensate Δω={dw2:.2f} g/kg")
        self._fv['cc1_Q'].setText(f"Q_cool = |{s1i.h:.2f}−{s2.h:.2f}| = {Q2:.2f} kW")
        self._fv['cc1_out'].setText(
            f"T={s2.T:.1f}°C  ω={s2.w*1000:.2f} g/kg  φ={s2.RH:.1f}%  "
            f"Tdp={s2.T_dp:.1f}°C  h={s2.h:.2f} kJ/kg")

        # ── WASHER ────────────────────────────────────────
        s2i, s3 = s[2], s[3]
        mv3 = mvs[2]
        twb2 = s2i.T_wb
        wsat_wb = Psych.omega_sat(twb2)
        eta3 = min(0.92, max(0.0, mv3 / 100.0))
        dw3 = (s3.w - s2i.w) * 1000
        self._fv['ws_in'].setText(
            f"T={s2i.T:.1f}°C  ω={s2i.w*1000:.2f} g/kg  φ={s2i.RH:.1f}%  "
            f"Tdp={s2i.T_dp:.1f}°C  h={s2i.h:.2f} kJ/kg")
        self._fv['ws_pid'].setText(
            f"PV(RH)={s3.RH:.1f}%   SP={self._fp[2].sp:.0f}%   "
            f"e={self._fp[2].sp-s3.RH:.1f}   MV={mv3:.1f}%")
        self._fv['ws_twb'].setText(f"Twb_in = {twb2:.1f}°C  (bisection)")
        self._fv['ws_wsat'].setText(
            f"ω_sat({twb2:.1f}) = {wsat_wb*1000:.3f} g/kg  "
            f"[Pws={Psych.pws(twb2):.4f} kPa]")
        self._fv['ws_eta'].setText(f"η = MV/100 = {mv3:.1f}/100 = {eta3:.3f}")
        self._fv['ws_wout'].setText(
            f"ω_out = {s2i.w*1000:.3f} + {eta3:.3f}×({wsat_wb*1000:.3f}−{s2i.w*1000:.3f})"
            f" = {s3.w*1000:.3f} g/kg")
        self._fv['ws_Tout'].setText(
            f"T_out = {twb2:.1f}+(1−{eta3:.3f})×({s2i.T:.1f}−{twb2:.1f}) = {s3.T:.1f}°C")
        self._fv['ws_dw'].setText(f"Δω = {dw3:.2f} g/kg  added")
        self._fv['ws_out'].setText(
            f"T={s3.T:.1f}°C  ω={s3.w*1000:.2f} g/kg  φ={s3.RH:.1f}%  "
            f"Tdp={s3.T_dp:.1f}°C  h={s3.h:.2f} kJ/kg")

        # ── CC-2 ──────────────────────────────────────────
        s3i, s4 = s[3], s[4]
        mv4 = mvs[3]
        tdp4_out = s4.T_dp                        # PV = 出風口露點
        e4 = tdp4_out - self._fp[3].sp            # direct: PV-SP
        tdp3 = s3i.T_dp
        dry4 = s4.T >= tdp3
        dw4 = (s3i.w - s4.w) * 1000
        Q4 = abs(s3i.h - s4.h)
        pw4_out = s4.w * Psych.P / (0.62198 + s4.w)
        r4 = math.log(max(pw4_out, 1e-9) / 0.611)
        self._fv['cc2_in'].setText(
            f"T={s3i.T:.1f}°C  ω={s3i.w*1000:.2f} g/kg  φ={s3i.RH:.1f}%  "
            f"Tdp={tdp3:.1f}°C  h={s3i.h:.2f} kJ/kg")
        self._fv['cc2_pid'].setText(
            f"PV(Tdp_out)={tdp4_out:.1f}°C  SP={self._fp[3].sp:.1f}°C  "
            f"e={e4:.1f}  MV={mv4:.1f}%")
        self._fv['cc2_dpformula'].setText(
            f"Pw_out={pw4_out:.4f} kPa  r=ln(Pw/0.611)={r4:.4f}  "
            f"Tdp_out=237.3×{r4:.4f}/(17.27−{r4:.4f}) = {tdp4_out:.1f}°C")
        self._fv['cc2_dpcheck'].setText(
            f"Tdp_in={tdp3:.1f}°C  T_out={s4.T:.1f}°C  "
            f"→ {'DRY (T_out≥Tdp_in)' if dry4 else 'WET: T_out<Tdp_in → 冷凝除濕'}")
        self._fv['cc2_cond'].setText(
            f"ω_out = {'ω_in (無冷凝)=' if dry4 else 'ω_sat(T_out)='}"
            f"{s4.w*1000:.3f} g/kg   Δω removed={dw4:.2f} g/kg")
        self._fv['cc2_Q'].setText(f"Q_dehumid = |{s3i.h:.2f}−{s4.h:.2f}| = {Q4:.2f} kW")
        self._fv['cc2_out'].setText(
            f"T={s4.T:.1f}°C  ω={s4.w*1000:.2f} g/kg  φ={s4.RH:.1f}%  "
            f"Tdp={tdp4_out:.1f}°C  h={s4.h:.2f} kJ/kg")

        # ── HTC-2 ─────────────────────────────────────────
        s4i, s5 = s[4], s[5]
        mv5 = mvs[4]
        e5 = self._fp[4].sp - s5.T              # reverse: SP-PV
        dT5 = s5.T - s4i.T
        Cpa5 = 1.006 + 1.86 * s4i.w
        Q5 = Cpa5 * abs(dT5)
        self._fv['htc2_in'].setText(
            f"T={s4i.T:.1f}°C  ω={s4i.w*1000:.2f} g/kg  φ={s4i.RH:.1f}%  "
            f"Tdp={s4i.T_dp:.1f}°C  h={s4i.h:.2f} kJ/kg")
        self._fv['htc2_pid'].setText(
            f"PV(T_out)={s5.T:.1f}°C  SP={self._fp[4].sp:.1f}°C  "
            f"e={e5:.1f}  MV={mv5:.1f}%")
        self._fv['htc2_fopdt'].setText(
            f"FOPDT: Gain={fo[4].Kp:.2f}  τ={fo[4].tau:.0f}s  L={fo[4].L:.1f}s")
        self._fv['htc2_dT'].setText(
            f"T_out = T_in+ΔT = {s4i.T:.1f}+{dT5:.1f} = {s5.T:.1f}°C   "
            f"ω_out = ω_in = {s5.w*1000:.2f} g/kg")
        self._fv['htc2_Q'].setText(
            f"Q = 1×(1.006+1.86×{s4i.w:.4f})×|{dT5:.1f}| = {Q5:.2f} kW")
        self._fv['htc2_out'].setText(
            f"T={s5.T:.1f}°C  ω={s5.w*1000:.2f} g/kg  φ={s5.RH:.1f}%  "
            f"Tdp={s5.T_dp:.1f}°C  h={s5.h:.2f} kJ/kg")

        # ── FAN ───────────────────────────────────────────
        s5i, s6 = s[5], s[6]
        mv6 = mvs[5]
        sp_fan = self._fp[5].sp
        e6 = sp_fan - self._p_static
        hz = mv6 / 100.0 * 50.0
        self._fv['fan_in'].setText(
            f"T={s5i.T:.1f}°C  ω={s5i.w*1000:.2f} g/kg  φ={s5i.RH:.1f}%  "
            f"Tdp={s5i.T_dp:.1f}°C  h={s5i.h:.2f} kJ/kg")
        self._fv['fan_pid'].setText(
            f"e = SP−PV = {sp_fan:.0f}−{self._p_static:.0f} = {e6:.0f} Pa    MV = {mv6:.1f}%")
        self._fv['fan_ps'].setText(
            f"P_static = FOPDT(MV={mv6:.1f}%, Gain=40, τ=10s) = {self._p_static:.0f} Pa")
        self._fv['fan_hz'].setText(
            f"Hz = MV%×50 = {mv6:.1f}%×50 = {hz:.1f} Hz  (actual: {self._fan_hz:.1f} Hz)")
        self._fv['fan_out'].setText(
            f"T={s6.T:.1f}°C  ω={s6.w*1000:.2f} g/kg  φ={s6.RH:.1f}%  "
            f"Tdp={s6.T_dp:.1f}°C  h={s6.h:.2f} kJ/kg  P_static={self._p_static:.0f} Pa")

    def _build_right(self):
        f = QFrame(); f.setStyleSheet(f"QFrame{{background:{self._BG};border:none;}}")
        lay = QVBoxLayout(f); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)
        lay.addWidget(self._build_target())
        self._chart = _PsychrometricChart(); lay.addWidget(self._chart, 1); return f

    def _build_target(self):
        f = QFrame(); f.setFixedHeight(130)
        f.setStyleSheet(f"QFrame{{background:{self._CELL};border:1px solid {self._BDR};border-radius:4px;}}")
        g = QGridLayout(f); g.setContentsMargins(10,8,10,8); g.setSpacing(6)
        def hdr(t, clr="#7AAABB"):
            l = QLabel(t); l.setStyleSheet(f"color:{clr};font-size:9pt;font-weight:700;"
                                            f"background:transparent;border:none;"
                                            f"font-family:'Microsoft JhengHei','Segoe UI';"); return l
        def vi(v, clr):
            e = QLineEdit(str(v)); e.setFixedSize(80, 26); e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e.setStyleSheet(f"QLineEdit{{background:#060E1A;color:{clr};"
                            f"border:1px solid {self._BDR};border-radius:3px;"
                            f"font-size:11pt;font-weight:700;font-family:Consolas;}}"
                            f"QLineEdit:focus{{border:1px solid {self._ACC};}}"); return e
        def _mk_spin(le: QLineEdit, step: float, lo: float, hi: float,
                     is_pm: bool = False) -> QWidget:
            """Wrap a QLineEdit with ▲ / ▼ buttons that step by `step`."""
            cw = QWidget(); hl = QHBoxLayout(cw)
            hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(2)
            hl.addWidget(le)
            vw = QWidget(); vl = QVBoxLayout(vw)
            vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(1)
            def _adj(delta):
                txt = le.text().replace("±", "").strip()
                try: cur = float(txt)
                except: return
                val = round(max(lo, min(hi, cur + delta)), 2)
                le.setText(f"±{val:.1f}" if is_pm else f"{val:.1f}")
                self._commit_targets()
            for sym, d in [("▲", step), ("▼", -step)]:
                b = QPushButton(sym); b.setFixedSize(20, 12)
                b.setStyleSheet(
                    "QPushButton{background:#0E1C2E;color:#7AAFDF;"
                    "border:1px solid #1A3050;border-radius:2px;"
                    "font-size:8px;padding:0;}"
                    "QPushButton:hover{background:#1A3050;color:#AADDFF;}"
                    "QPushButton:pressed{background:#2A5080;}")
                b.clicked.connect(lambda _, d=d: _adj(d))
                vl.addWidget(b)
            hl.addWidget(vw)
            return cw

        # column 0: label, 1: SP spin, 2: tol spin, 3: unit, 4: stretch
        g.setColumnStretch(0, 0); g.setColumnStretch(1, 0)
        g.setColumnStretch(2, 0); g.setColumnStretch(3, 0)
        g.setColumnStretch(4, 1)

        g.addWidget(hdr("TARGET ZONE CONFIG", self._ACC), 0, 0, 1, 5)
        g.addWidget(hdr("TEMP SETPOINT"), 1, 0)
        self._T_sp_in = vi("22","#FF6B6B"); self._T_tol_in = vi("±2","#FF9999")
        g.addWidget(_mk_spin(self._T_sp_in,  0.1, -20.0, 50.0),          1, 1)
        g.addWidget(_mk_spin(self._T_tol_in, 0.1,   0.1, 20.0, True),    1, 2)
        g.addWidget(hdr("°C"), 1, 3)
        g.addWidget(hdr("RH SETPOINT"), 2, 0)
        self._RH_sp_in = vi("50","#00B4D8"); self._RH_tol_in = vi("±5","#55CCEE")
        g.addWidget(_mk_spin(self._RH_sp_in,  0.1,   0.0, 100.0),        2, 1)
        g.addWidget(_mk_spin(self._RH_tol_in, 0.1,   0.1, 30.0,  True),  2, 2)
        g.addWidget(hdr("%"), 2, 3)
        for e in (self._T_sp_in, self._T_tol_in, self._RH_sp_in, self._RH_tol_in):
            e.editingFinished.connect(self._commit_targets)
        self._cur_lbl = QLabel("—")
        self._cur_lbl.setStyleSheet(f"color:{self._ACC};font-size:10pt;font-weight:700;"
                                    f"background:transparent;border:none;font-family:Consolas;")
        g.addWidget(hdr("CURRENT STATUS"), 3, 0); g.addWidget(self._cur_lbl, 3, 1, 1, 4)
        self._ilock_lbl = QLabel("—")
        self._ilock_lbl.setStyleSheet("color:#888;font-size:8pt;font-weight:600;"
                                      "background:transparent;border:none;font-family:Consolas;")
        g.addWidget(hdr("INTERLOCKS"), 4, 0); g.addWidget(self._ilock_lbl, 4, 1, 1, 4)
        self._T_sp = 22.0; self._RH_sp = 50.0; self._T_tol = 2.0; self._RH_tol = 5.0
        return f

    # ── helpers ─────────────────────────────────────────
    def _lbl_w(self, t):
        l = QLabel(t); l.setStyleSheet(f"color:#BBCCDD;font-size:10pt;font-weight:600;background:transparent;"
                                        f"border:none;font-family:'Microsoft JhengHei';"); return l

    def _vsep(self):
        f = QFrame(); f.setFrameShape(QFrame.Shape.VLine)
        f.setStyleSheet(f"QFrame{{border:none;border-left:1px solid {self._BDR};background:transparent;}}"); return f

    # ── selection ────────────────────────────────────────
    def _set_selected(self, idx: int):
        self._sel = idx
        for i, fp in enumerate(self._fp): fp.set_selected(i == idx)
        self._schematic.set_selected(idx + 1)
        self._overlay.set_sel(idx)
        name, lo, hi = _STAGE_DEFS[idx][0], _STAGE_DEFS[idx][1], _STAGE_DEFS[idx][2]
        self._trend.select(idx, name, lo, hi, _SACCNT[idx + 1])

    def _on_schematic_click(self, stage_idx: int):
        fp_idx = stage_idx - 1
        if 0 <= fp_idx <= 5: self._set_selected(fp_idx)
        else: self._clear_selection()

    def _clear_selection(self):
        self._sel = -1
        for fp in self._fp: fp.set_selected(False)
        self._schematic.set_selected(-1)
        self._overlay.set_sel(-1)
        self._trend.clear_selection()

    # ── climate ──────────────────────────────────────────
    def _export_report(self):
        if not self._states: return
        import csv, os
        from datetime import datetime

        path, _ = QFileDialog.getSaveFileName(
            self, "匯出報告 Export Report",
            os.path.expanduser(f"~/MAU_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"),
            "CSV Files (*.csv);;HTML Files (*.html);;All Files (*)"
        )
        if not path: return

        sa   = self._states[6]
        oa   = self._states[0]
        mvs  = self._latest_mvs
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        in_T  = abs(sa.T  - self._T_sp) <= self._T_tol
        in_RH = abs(sa.RH - self._RH_sp) <= self._RH_tol
        status = "ON TARGET" if (in_T and in_RH) else "OFF TARGET"

        pv_vals = [
            self._states[1].h if self._fp[0].pv_mode_idx == 1 else self._states[1].T,
            self._states[2].T, self._states[3].RH,
            self._states[4].T_dp, self._states[5].T, self._p_static,
        ]
        pv_units = [
            "kJ/kg" if self._fp[0].pv_mode_idx == 1 else "°C",
            "°C", "%RH", "°C dp", "°C", "Pa",
        ]

        if path.lower().endswith(".html"):
            self._export_html(path, now, oa, sa, mvs, pv_vals, pv_units, status)
        else:
            self._export_csv(path, now, oa, sa, mvs, pv_vals, pv_units, status)

    def _export_csv(self, path, now, oa, sa, mvs, pv_vals, pv_units, status):
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["MAU PRO-SIM Report", now])
            w.writerow([])
            w.writerow(["OUTDOOR AIR", "T (°C)", f"{oa.T:.2f}",
                        "RH (%)", f"{oa.RH:.1f}", "w (g/kg)", f"{oa.w_gkg:.2f}"])
            w.writerow(["CLIMATE MODE", self._climate])
            w.writerow([])
            w.writerow(["TARGET ZONE", f"T = {self._T_sp:.1f} ± {self._T_tol:.1f} °C",
                        f"RH = {self._RH_sp:.1f} ± {self._RH_tol:.1f} %"])
            w.writerow([])
            w.writerow(["Stage", "SP", "PV", "Unit", "MV (%)",
                        "Kp", "Ki", "Kd", "FO Gain", "FO τ(s)", "FO L(s)"])
            for i, (name, _, _, _, _, _, _) in enumerate(_STAGE_DEFS):
                fp = self._fp[i]
                w.writerow([name.replace("\n", " "),
                            f"{fp.sp:.2f}", f"{pv_vals[i]:.2f}", pv_units[i],
                            f"{mvs[i]:.1f}",
                            fp._pid.Kp, fp._pid.Ki, fp._pid.Kd,
                            fp._fopdt.Kp, fp._fopdt.tau, fp._fopdt.L])
            w.writerow([])
            w.writerow(["FINAL SUPPLY AIR",
                        f"T = {sa.T:.2f} °C", f"RH = {sa.RH:.1f} %",
                        f"w = {sa.w_gkg:.2f} g/kg", f"h = {sa.h:.1f} kJ/kg"])
            w.writerow(["STATUS", status])

    def _export_html(self, path, now, oa, sa, mvs, pv_vals, pv_units, status):
        clr = "#00CC55" if status == "ON TARGET" else "#FF3322"
        rows = ""
        for i, (name, _, _, _, _, _, _) in enumerate(_STAGE_DEFS):
            fp = self._fp[i]
            rows += (f"<tr><td>{name.replace(chr(10),' ')}</td>"
                     f"<td>{fp.sp:.2f}</td><td>{pv_vals[i]:.2f} {pv_units[i]}</td>"
                     f"<td>{mvs[i]:.1f}%</td>"
                     f"<td>{fp._pid.Kp} / {fp._pid.Ki} / {fp._pid.Kd}</td>"
                     f"<td>{fp._fopdt.Kp} / {fp._fopdt.tau:.1f} / {fp._fopdt.L:.1f}</td></tr>\n")
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>MAU Report {now}</title>
<style>
  body{{font-family:Consolas,monospace;background:#050B18;color:#C8D8E8;padding:24px}}
  h2{{color:#00B4D8}} h3{{color:#4A8AB8;margin-top:18px}}
  table{{border-collapse:collapse;width:100%;margin-top:8px}}
  th{{background:#0A1428;color:#00B4D8;padding:6px 10px;text-align:left;border:1px solid #162440}}
  td{{padding:5px 10px;border:1px solid #0D1C30}}
  tr:nth-child(even){{background:#080F1E}}
  .status{{font-size:1.3em;font-weight:bold;color:{clr}}}
</style></head><body>
<h2>MAU PRO-SIM — Report</h2>
<p style="color:#4A6A8A">{now} &nbsp;|&nbsp; Climate: {self._climate}</p>
<h3>Outdoor Air</h3>
<table><tr><th>T (°C)</th><th>RH (%)</th><th>w (g/kg)</th><th>h (kJ/kg)</th></tr>
<tr><td>{oa.T:.2f}</td><td>{oa.RH:.1f}</td><td>{oa.w_gkg:.2f}</td><td>{oa.h:.1f}</td></tr></table>
<h3>Target Zone</h3>
<p>T = {self._T_sp:.1f} ± {self._T_tol:.1f} °C &nbsp;&nbsp; RH = {self._RH_sp:.1f} ± {self._RH_tol:.1f} %</p>
<h3>Stage Data</h3>
<table><tr><th>Stage</th><th>SP</th><th>PV</th><th>MV</th><th>PID Kp/Ki/Kd</th><th>FOPDT Kp/τ/L</th></tr>
{rows}</table>
<h3>Final Supply Air</h3>
<table><tr><th>T (°C)</th><th>RH (%)</th><th>w (g/kg)</th><th>h (kJ/kg)</th></tr>
<tr><td>{sa.T:.2f}</td><td>{sa.RH:.1f}</td><td>{sa.w_gkg:.2f}</td><td>{sa.h:.1f}</td></tr></table>
<h3>Status</h3><p class="status">{status}</p>
</body></html>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        import webbrowser; webbrowser.open(path)

    def _save_mau_config(self):
        cfg = load_config()
        cfg["mau_sim"] = {
            "climate": self._climate,
            "custom_T": self._custom_T, "custom_RH": self._custom_RH,
            "T_sp": self._T_sp, "T_tol": self._T_tol,
            "RH_sp": self._RH_sp, "RH_tol": self._RH_tol,
            "fp": [fp.get_state() for fp in self._fp],
        }
        save_config(cfg)

    def _load_mau_config(self):
        d = load_config().get("mau_sim", {})
        if not d: return
        if "climate"   in d: self._climate    = d["climate"];    self._update_clim_btns()
        if "custom_T"  in d:
            self._custom_T  = d["custom_T"];  self._custom_T_in.setText(f"{self._custom_T:.1f}")
        if "custom_RH" in d:
            self._custom_RH = d["custom_RH"]; self._custom_RH_in.setText(f"{self._custom_RH:.0f}")
        if "T_sp"  in d: self._T_sp  = d["T_sp"];  self._T_sp_in.setText(f"{self._T_sp:.1f}")
        if "T_tol" in d: self._T_tol = d["T_tol"]; self._T_tol_in.setText(f"±{self._T_tol:.1f}")
        if "RH_sp"  in d: self._RH_sp  = d["RH_sp"];  self._RH_sp_in.setText(f"{self._RH_sp:.1f}")
        if "RH_tol" in d: self._RH_tol = d["RH_tol"]; self._RH_tol_in.setText(f"±{self._RH_tol:.1f}")
        for i, st in enumerate(d.get("fp", [])):
            if i < len(self._fp): self._fp[i].set_state(st)

    def _set_climate(self, mode: str):
        self._climate = mode; self._update_clim_btns(); self._reset(); self._save_mau_config()

    def _update_clim_btns(self):
        clim = self._climate
        _pill = "border-radius:18px;font-size:10pt;font-weight:700;font-family:Consolas;padding:0 14px;"
        _as  = (f"QPushButton{{background:#FF6B00;color:#FFFFFF;border:none;{_pill}}}"
                f"QPushButton:hover{{background:#FF8822;}}")
        _aw  = (f"QPushButton{{background:#003A6A;color:#00B4D8;border:none;{_pill}}}"
                f"QPushButton:hover{{background:#004A8A;}}")
        _ac  = (f"QPushButton{{background:#1A5A2A;color:#44FF88;border:none;{_pill}}}"
                f"QPushButton:hover{{background:#2A7A3A;}}")
        _off = (f"QPushButton{{background:#0E1828;color:#3A5570;border:none;{_pill}}}")
        self._btn_summer.setStyleSheet(_as if clim == "Summer" else _off)
        self._btn_winter.setStyleSheet(_aw if clim == "Winter" else _off)
        self._btn_custom.setStyleSheet(_ac if clim == "Custom" else _off)
        self._custom_row.setVisible(clim == "Custom")

    def _commit_custom(self):
        try: self._custom_T  = max(-20.0, min(55.0,  float(self._custom_T_in.text())))
        except: pass
        try: self._custom_RH = max(10.0,  min(100.0, float(self._custom_RH_in.text())))
        except: pass
        self._save_mau_config()

    def _commit_targets(self):
        try: self._T_sp   = float(self._T_sp_in.text())
        except: pass
        try: self._T_tol  = abs(float(self._T_tol_in.text().replace("±","")))
        except: pass
        try: self._RH_sp  = float(self._RH_sp_in.text())
        except: pass
        try: self._RH_tol = abs(float(self._RH_tol_in.text().replace("±","")))
        except: pass
        self._save_mau_config()

    # ── simulation ───────────────────────────────────────
    def _oa(self):
        if self._climate == "Summer": return AirState(37.0, Psych.omega(37.0, 65.0))
        if self._climate == "Custom": return AirState(self._custom_T, Psych.omega(self._custom_T, self._custom_RH))
        return AirState(6.0, Psych.omega(6.0, 50.0))

    def _set_speed(self, v: int):
        self._speed = v
        self._worker.set_speed(v)

    def _reset(self):
        if not hasattr(self, "_worker"): return
        self._alarm_ticks = 0
        self._worker.reset_sim()

    @pyqtSlot(list, list, float, float)
    def _on_sim_stepped(self, states, mvs, p_static, fan_hz):
        self._states      = states
        self._latest_mvs  = mvs
        self._p_static    = p_static
        self._fan_hz      = fan_hz
        self._update_ui()

    def _refresh_anim(self):
        """Keeps schematic animation ticking even between sim signals."""
        if self._states:
            self._schematic.refresh(self._states, self._latest_mvs,
                                    self._p_static, self._fan_hz)

    def _update_ui(self):
        if not self._states: return
        self._ui_tick = (self._ui_tick + 1) % 4
        mvs = self._latest_mvs

        # Every tick: schematic animation + numeric labels + trend push (cheap)
        self._schematic.refresh(self._states, mvs, self._p_static, self._fan_hz)
        pv_htc1_push = self._states[1].h if self._fp[0].pv_mode_idx == 1 else self._states[1].T
        push_pvs = [pv_htc1_push, self._states[2].T, self._states[3].RH,
                    self._states[4].T_dp, self._states[5].T, self._p_static]
        for i, (pv, mv) in enumerate(zip(push_pvs, mvs)):
            self._trend.push(i, pv, self._fp[i].sp, mv)
        if self._sel >= 0: self._trend.update()

        oa = self._states[0]
        self._oa_T_lbl.setText(f"{oa.T:.1f}°C")
        self._oa_RH_lbl.setText(f"{oa.RH:.0f}%")

        pv_htc1_disp = self._states[1].h if self._fp[0].pv_mode_idx == 1 else self._states[1].T
        pv_vals = [pv_htc1_disp, self._states[2].T, self._states[3].RH,
                   self._states[4].T_dp, self._states[5].T, self._p_static]
        for fp, pv, mv in zip(self._fp, pv_vals, mvs): fp.update_display(pv, mv)

        sa = self._states[6]
        self._final_T_lbl.setText(f"{sa.T:.1f}°C")
        self._final_lbl.setText(f"{sa.RH:.0f}%")
        in_T  = abs(sa.T  - self._T_sp)  <= self._T_tol
        in_RH = abs(sa.RH - self._RH_sp) <= self._RH_tol
        ok = in_T and in_RH
        if ok:
            self._alarm_ticks = 0
            clr  = "#00FF88"
            text = f"{sa.T:.1f} °C   {sa.RH:.0f}% RH   ✓ ON TARGET"
        else:
            self._alarm_ticks += 1
            if self._alarm_ticks >= 200:                # ≥ 10 s — flashing alarm
                flash = self._ui_tick % 4 < 2
                clr  = "#FF2200" if flash else "#FF8800"
                text = f"⚠ ALARM   {sa.T:.1f}°C {'✓' if in_T else '✗'}  {sa.RH:.0f}% RH {'✓' if in_RH else '✗'}"
            else:                                        # < 10 s — warning
                clr  = "#FFCC00"
                text = f"{sa.T:.1f} °C   {sa.RH:.0f}% RH   ⚠ OFF TARGET"
        self._cur_lbl.setStyleSheet(
            f"color:{clr};font-size:8.5pt;font-weight:700;"
            f"background:transparent;border:none;font-family:Consolas;")
        self._cur_lbl.setText(text)

        # Interlock detection
        active = []
        if mvs[5] < 8.0:
            active.append(("LOW FAN", "#FF4400"))
        if mvs[0] > 70.0 and mvs[1] > 30.0:
            active.append(("HTC+CC CONFLICT", "#FF8800"))
        if mvs[2] > 60.0 and mvs[3] > 60.0:
            active.append(("WASH+CC2 CONFLICT", "#FF8800"))
        if self._states[5].T > 35.0:
            active.append(("HIGH SUPPLY T", "#FF2200"))
        if active:
            parts = "  |  ".join(f'<span style="color:{c}">{n}</span>' for n, c in active)
            self._ilock_lbl.setText(parts)
            self._ilock_lbl.setTextFormat(Qt.TextFormat.RichText)
        else:
            self._ilock_lbl.setTextFormat(Qt.TextFormat.PlainText)
            self._ilock_lbl.setStyleSheet("color:#00CC66;font-size:8pt;font-weight:600;"
                                          "background:transparent;border:none;font-family:Consolas;")
            self._ilock_lbl.setText("OK — no active interlocks")

        # Every 4 ticks (~5fps): heavy static charts
        if self._ui_tick == 0:
            self._chart.refresh(self._states, self._T_sp, self._RH_sp,
                                self._T_tol, self._RH_tol, sel=self._sel)
            self._update_formula_page()

    # ── lifecycle ────────────────────────────────────────
    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Space:
            self._reset()
        elif Qt.Key.Key_1 <= k <= Qt.Key.Key_6:
            self._set_selected(k - Qt.Key.Key_1)
        elif k == Qt.Key.Key_Escape:
            self._clear_selection()
        elif k == Qt.Key.Key_S:
            self._set_climate("Summer")
        elif k == Qt.Key.Key_W:
            self._set_climate("Winter")
        elif k == Qt.Key.Key_C:
            self._set_climate("Custom")
        else:
            super().keyPressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, '_overlay'):
            self._overlay.setGeometry(self.content.rect())
            self._overlay.raise_()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._sim_thread.isRunning():
            self._sim_thread.start()   # first open: thread emits started → start_sim
        else:
            self._sig_resume.emit()    # subsequent open: resume worker timer
        if not self._ui_timer.isActive(): self._ui_timer.start(50)
        scr = QApplication.primaryScreen()
        if scr:
            ag = scr.availableGeometry()
            self.resize(ag.width(), ag.height()); self.move(ag.left(), ag.top())
        if hasattr(self, '_overlay'):
            self._overlay.setGeometry(self.content.rect())
            self._overlay.raise_()

    def hideEvent(self, e):
        self._sig_pause.emit()         # pause worker computation
        self._ui_timer.stop(); super().hideEvent(e)

    def closeEvent(self, e):
        self._sig_pause.emit()
        self._ui_timer.stop()
        self._sim_thread.quit(); self._sim_thread.wait(500)
        super().closeEvent(e)
