# tool_pid_vfd.py — VFD Pressure Control Station
# Extends PID Tuner Station 2.0 with physical-unit mapping:
#   PV   0–100 %   →  Pressure  0–5 Pa
#   MV  50–100 %   →  VFD Freq 30–60 Hz  (50 % = min speed = 30 Hz)
# Defaults: K=0.85, τ=5 s, L=2 s, Kp=1.0, Ki=0.5, MV-MIN=50 %

from PyQt6.QtCore    import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout,
                              QLabel, QPushButton)

from tool_pid          import PidTunerBuddy, HAS_PG
from tool_pid_vfd_anim import _PumpCanvas


# ══════════════════════════════════════════════════════════
#  VFD PRESSURE TUNER
# ══════════════════════════════════════════════════════════
class VfdPressureTuner(PidTunerBuddy):
    """PID Tuner adapted for VFD-driven differential-pressure (0–5 Pa) control."""

    # ── Physical-unit constants ──────────────────────────────────
    _PRESS_MIN  = 0.0    # Pa
    _PRESS_MAX  = 5.0    # Pa
    _FREQ_MIN   = 30.0   # Hz — MV 50 %
    _FREQ_MAX   = 60.0   # Hz — MV 100 %
    _MV_FREQ_LO = 50.0   # % MV → FREQ_MIN
    _MV_FREQ_HI = 100.0  # % MV → FREQ_MAX
    _PA_SCALE   = 0.05   # % → Pa  (5 / 100)

    def __init__(self, on_thinking=None):
        super().__init__(on_thinking)
        self.resize(1060, self.height())
        self.setMinimumWidth(860)
        # _h_lay already contains [hmi_panel | scroll | right_frame] from parent
        self._anim_panel = self._build_anim_panel()
        self._h_lay.addWidget(self._anim_panel, 1)

    # ── Conversion helpers ───────────────────────────────────────
    def _pv_to_pa(self, pv_pct: float) -> float:
        return self._PRESS_MIN + pv_pct / 100.0 * (self._PRESS_MAX - self._PRESS_MIN)

    def _pa_to_pct(self, pa: float) -> float:
        return pa / self._PRESS_MAX * 100.0

    def _mv_to_hz(self, mv_pct: float) -> float:
        """Linear: 0%→0 Hz, 50%→30 Hz, 100%→60 Hz  (Hz = MV% × 0.6)."""
        return max(0.0, min(self._FREQ_MAX,
                            mv_pct / self._MV_FREQ_HI * self._FREQ_MAX))

    # ── Embedded animation panel ─────────────────────────────────
    def _build_anim_panel(self) -> QFrame:
        panel = QFrame(self.content)
        panel.setMinimumWidth(280)
        panel.setStyleSheet(
            f"QFrame{{background:#040A18;"
            f"border-left:1px solid {self._BORDER};}}")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(6)

        # Title
        title = QLabel("⚡  VFD 泵浦動畫  Pump Simulation")
        title.setStyleSheet(
            f"color:{self._ACC};font-size:9.5pt;font-weight:700;"
            "background:transparent;border:none;"
            "font-family:'Microsoft JhengHei','Segoe UI';")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        # Pump canvas
        self._pump_canvas = _PumpCanvas()
        lay.addWidget(self._pump_canvas, 1)

        # Info strip: Pa / SV / Hz
        info = QFrame()
        info.setFixedHeight(58)
        info.setStyleSheet(
            f"QFrame{{background:#08101E;"
            f"border:1px solid {self._BORDER};border-radius:4px;}}")
        ih = QHBoxLayout(info)
        ih.setContentsMargins(10, 6, 10, 6)
        ih.setSpacing(0)

        def _val_col(tag: str, init: str, clr: str):
            col = QVBoxLayout(); col.setSpacing(1); col.setContentsMargins(4, 0, 4, 0)
            t = QLabel(tag)
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t.setStyleSheet(f"color:{self._LBL2};font-size:7pt;font-weight:600;"
                            "background:transparent;border:none;"
                            "font-family:'Microsoft JhengHei','Segoe UI';")
            v = QLabel(init)
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.setStyleSheet(f"color:{clr};font-size:12pt;font-weight:700;"
                            "background:transparent;border:none;"
                            "font-family:Consolas,'Courier New';")
            col.addWidget(t); col.addWidget(v)
            return v, col

        def _sep():
            f = QFrame(); f.setFrameShape(QFrame.Shape.VLine)
            f.setStyleSheet(f"QFrame{{border:none;border-left:1px solid {self._BORDER};"
                            "background:transparent;}")
            return f

        self._anim_pa_val, pa_lay = _val_col("壓力  PV", "0.00 Pa", self._PV_CLR)
        self._anim_sv_val, sv_lay = _val_col("設定  SV", "2.50 Pa", self._SV_CLR)
        self._anim_hz_val, hz_lay = _val_col("頻率  Hz", "30.0 Hz", self._MV_CLR)

        ih.addLayout(pa_lay, 1)
        ih.addWidget(_sep())
        ih.addLayout(sv_lay, 1)
        ih.addWidget(_sep())
        ih.addLayout(hz_lay, 1)
        lay.addWidget(info)

        # Pause button
        self._pp_paused = False
        self._pp_btn = QPushButton("⏸   暫停動畫  Pause")
        self._pp_btn.setFixedHeight(34)
        self._pp_btn.setStyleSheet(self._pp_qss(False))
        self._pp_btn.clicked.connect(self._toggle_pause)
        lay.addWidget(self._pp_btn)

        return panel

    def _pp_qss(self, paused: bool) -> str:
        if paused:
            return (f"QPushButton{{background:#040E04;color:{self._OK};"
                    f"border:1px solid #0A2A0A;border-radius:6px;"
                    "font-size:10pt;font-weight:700;"
                    "font-family:'Microsoft JhengHei','Segoe UI';}"
                    "QPushButton:hover{background:#0A1E0A;color:#FFF;}")
        return (f"QPushButton{{background:{self._CELL};color:{self._ACC};"
                f"border:1px solid {self._BORDER};border-radius:6px;"
                "font-size:10pt;font-weight:700;"
                "font-family:'Microsoft JhengHei','Segoe UI';}"
                f"QPushButton:hover{{background:{self._BG};color:#FFF;}}")

    def _toggle_pause(self):
        self._pp_paused = not self._pp_paused
        self._pump_canvas.set_paused(self._pp_paused)
        if self._pp_paused:
            self._pp_btn.setText("▶   啟動動畫  Resume")
        else:
            self._pp_btn.setText("⏸   暫停動畫  Pause")
        self._pp_btn.setStyleSheet(self._pp_qss(self._pp_paused))

    def _hmi_commit_sv(self):
        try:    v_pa = max(self._PRESS_MIN, min(self._PRESS_MAX, float(self._hmi_sv_e.text())))
        except: v_pa = self._pv_to_pa(self._sv_pct)
        self._sv_pct = self._pa_to_pct(v_pa)
        self._hmi_sv_e.setText(f"{v_pa:.2f}")
        if hasattr(self, "_sv_in"): self._sv_in.setText(f"{v_pa:.2f}")

    def _update_hmi(self):
        if not hasattr(self, "_hmi_pv"): return
        pa    = self._pv_to_pa(self._pv_n * 100.0)
        sv_pa = self._pv_to_pa(self._sv_pct)
        hz    = self._mv_to_hz(self._last_cv * 100.0)
        self._hmi_pv.setText(f"{pa:.2f} Pa")
        self._hmi_auto_out.setText(f"{hz:.1f} Hz")
        if not self._hmi_sv_e.hasFocus():     self._hmi_sv_e.setText(f"{sv_pa:.2f}")
        if not self._hmi_man_e.hasFocus():    self._hmi_man_e.setText(f"{self._cv_manual:.1f}")
        if not self._hmi_mv_max_e.hasFocus(): self._hmi_mv_max_e.setText(f"{self._mv_max:.0f}")
        if not self._hmi_mv_min_e.hasFocus(): self._hmi_mv_min_e.setText(f"{self._mv_min:.0f}")
        if not self._hmi_kp_e.hasFocus():     self._hmi_kp_e.setText(f"{self._Kp:.3f}")
        if not self._hmi_ki_e.hasFocus():     self._hmi_ki_e.setText(f"{self._Ki:.4f}")
        if not self._hmi_kd_e.hasFocus():     self._hmi_kd_e.setText(f"{self._Kd:.4f}")
        self._refresh_hmi_mode_btns()

    # ════════════════════════════════════════════════════
    #  BUILD OVERRIDES
    # ════════════════════════════════════════════════════

    def _build_param_cols(self, lay):
        """VFD-specific param panel — goes into the right_frame from parent."""
        # ── VFD defaults (set before parent reads them for UI init) ──
        self._pK, self._pT, self._pL = 0.85, 5.0, 2.0
        self._Kp, self._Ki, self._Kd = 1.0,  0.5, 0.0

        _sep = (f"color:{self._BORDER};font-size:7pt;"
                f"background:transparent;border:none;"
                f"font-family:Consolas,'Courier New';")
        _ann = (f"color:{self._LBL};font-size:8.5pt;font-weight:600;"
                f"background:transparent;border:none;"
                f"font-family:'Microsoft JhengHei','Segoe UI';")

        lay.addWidget(self._sec_hdr("≡  主要參數  Parameters"))

        def _framed_section(hdr_text: str, formula_block: list) -> tuple:
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
            ("P  ─  依據當前誤差即時反應",              _ann),
            ("I  ─  累積誤差，消除穩態誤差",            _ann),
            ("D  ─  預測誤差趨勢，抑制劇烈變動",       _ann),
            ("MV = Kp·[e + Ki·∫e + Kd·de/dt]",       _sep),
        ]
        fopdt_formula = [
            ("────────────────────────",               _sep),
            ("K  ─  MV 變化量造成的 PV 改變幅度",      _ann),
            ("τ  ─  達最終值 63.2% 所需時間",          _ann),
            ("L  ─  MV 改變到 PV 開始反應的時間",      _ann),
            ("PV = K·MV·(1 − e^(−(t−L)/τ))",         _sep),
        ]

        pid_fr,   pid_col   = _framed_section("PID 控制核心", pid_formula)
        fopdt_fr, fopdt_col = _framed_section("FOPDT 物理模型", fopdt_formula)

        for attr, label, lo, hi, dec in self._PID_SPECS:
            le = self._param_row(pid_col, attr, label, lo, hi, dec, "")
            self._pid_inputs[attr] = le

        for attr, label, lo, hi, dec, unit in self._FOPDT_SPECS:
            self._param_row(fopdt_col, attr, label, lo, hi, dec, unit)

        lay.addWidget(pid_fr)
        lay.addWidget(fopdt_fr)
        lay.addStretch()

    def _build_plot(self, lay):
        super()._build_plot(lay)
        if HAS_PG and hasattr(self, '_pw'):
            self._pw.setYRange(-0.2, 5.5, padding=0)
            self._pw.setLabel("left", "壓力 Pressure (Pa)", color=self._LBL2)

    def _on_hover(self, evt):
        """Override parent hover: show Pa / Hz instead of %."""
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

        idx   = min(range(len(ta)), key=lambda i: abs(ta[i] - t))
        pv_pa = list(self._pv_data)[idx] * self._PA_SCALE
        sv_pa = list(self._sv_data)[idx] * self._PA_SCALE
        hz    = self._mv_to_hz(list(self._cv_data)[idx])

        self._hover_lbl.setHtml(
            f'<span style="color:#888888">t = {ta[idx]:.1f} s</span><br/>'
            f'<span style="color:{self._PV_CLR}">PV = {pv_pa:.2f} Pa</span><br/>'
            f'<span style="color:{self._SV_CLR}">SV = {sv_pa:.2f} Pa</span><br/>'
            f'<span style="color:{self._MV_CLR}">Hz = {hz:.1f}</span>')

        xr, yr = (self._pw.plotItem.vb.viewRange()[0],
                  self._pw.plotItem.vb.viewRange()[1])
        anchor_x = 1.0 if t > xr[0] + (xr[1] - xr[0]) * 0.6 else 0.0
        try:
            self._hover_lbl.setAnchor((anchor_x, 0))
        except Exception:
            pass
        self._hover_lbl.setPos(t, yr[0] + (yr[1] - yr[0]) * 0.98)
        self._hover_lbl.setVisible(True)

    def _build_live_strip(self, lay):
        """Pa-labelled PV/SV strip  →  large Pa/Hz panel."""
        # ── Pa live strip ─────────────────────────────────────────
        f = QFrame()
        f.setStyleSheet(f"QFrame{{background:{self._CELL};"
                        f"border:1px solid {self._BORDER};border-radius:4px;}}")
        f.setFixedHeight(58)
        h = QHBoxLayout(f); h.setContentsMargins(14, 4, 14, 4); h.setSpacing(0)

        def _big(tag, clr):
            col = QVBoxLayout(); col.setSpacing(0)
            lbl = QLabel(tag)
            lbl.setStyleSheet(
                f"color:{self._LBL2};font-size:7.5pt;font-weight:600;"
                f"background:transparent;border:none;"
                f"font-family:'Microsoft JhengHei','Segoe UI';")
            rw = QHBoxLayout(); rw.setSpacing(2); rw.setContentsMargins(0, 0, 0, 0)
            val = QLabel("0.00")
            val.setStyleSheet(
                f"color:{clr};font-size:19pt;font-weight:700;"
                f"background:transparent;border:none;"
                f"font-family:Consolas,'Courier New';"
                f"")
            unit = QLabel("Pa")
            unit.setStyleSheet(
                f"color:{self._LBL2};font-size:10pt;font-weight:600;"
                f"background:transparent;border:none;"
                f"font-family:'Segoe UI';padding-bottom:2px;")
            unit.setAlignment(Qt.AlignmentFlag.AlignBottom)
            rw.addWidget(val); rw.addWidget(unit); rw.addStretch()
            col.addWidget(lbl); col.addLayout(rw)
            return col, val

        pv_lay, self._pv_disp = _big("PV  現在值", self._PV_CLR)
        sv_lay, self._sv_disp = _big("SV  設定值", self._SV_CLR)
        h.addLayout(pv_lay, 1)
        h.addWidget(self._vline())
        h.addSpacing(12)
        h.addLayout(sv_lay, 1)
        lay.addWidget(f)

        # ── Large Pa / Hz readout panel ───────────────────────────
        self._build_vfd_panel(lay)

    def _build_vfd_panel(self, lay: QVBoxLayout):
        """Large Pa / Hz display with range labels."""
        f = QFrame()
        f.setStyleSheet(
            f"QFrame{{background:{self._CELL};"
            f"border:1px solid {self._BORDER};border-radius:4px;}}")
        f.setFixedHeight(82)
        outer = QHBoxLayout(f)
        outer.setContentsMargins(14, 6, 14, 6)
        outer.setSpacing(0)

        def _col(label, unit, color, lo, hi):
            col = QVBoxLayout(); col.setSpacing(1)
            hdr = QLabel(label)
            hdr.setStyleSheet(
                f"color:{self._LBL2};font-size:7.5pt;font-weight:600;"
                "background:transparent;border:none;"
                "font-family:'Microsoft JhengHei','Segoe UI';")
            rw = QHBoxLayout(); rw.setSpacing(4); rw.setContentsMargins(0, 0, 0, 0)
            val = QLabel("  0.00")
            val.setStyleSheet(
                f"color:{color};font-size:22pt;font-weight:700;"
                "background:transparent;border:none;"
                "font-family:Consolas,'Courier New';"
                "")
            utag = QLabel(unit)
            utag.setStyleSheet(
                f"color:{color};font-size:13pt;font-weight:700;"
                "background:transparent;border:none;"
                "font-family:'Segoe UI';padding-bottom:5px;")
            utag.setAlignment(Qt.AlignmentFlag.AlignBottom)
            rw.addWidget(val); rw.addWidget(utag); rw.addStretch()
            rng = QLabel(f"MAX {hi:.0f} {unit}    MIN {lo:.0f} {unit}")
            rng.setStyleSheet(
                f"color:{self._LBL2};font-size:7.5pt;font-weight:600;"
                "background:transparent;border:none;"
                "font-family:'Segoe UI';")
            col.addWidget(hdr); col.addLayout(rw); col.addWidget(rng)
            return col, val

        pa_col, self._pa_disp = _col(
            "壓力  Pressure", "Pa", self._PV_CLR,
            self._PRESS_MIN, self._PRESS_MAX)
        hz_col, self._hz_disp = _col(
            "VFD 頻率  Frequency", "Hz", self._MV_CLR,
            self._FREQ_MIN, self._FREQ_MAX)

        outer.addLayout(pa_col, 1)
        outer.addWidget(self._vline())
        outer.addSpacing(12)
        outer.addLayout(hz_col, 1)
        lay.addWidget(f)

    def _build_ctrl_row(self, lay):
        """SV and Init SV accept Pa values; default SV=2.5 Pa, init=0 Pa."""
        self._sv_init = 0.0
        super()._build_ctrl_row(lay)
        self._sv_in.setText(f"{self._pv_to_pa(self._sv_pct):.2f}")
        self._sv_init_in.setText(f"{self._pv_to_pa(self._sv_init):.2f}")

    def _build_mv_limit_row(self, lay):
        """Set MV MIN to 50 % (VFD minimum-speed threshold) before building."""
        self._mv_min = 50.0
        super()._build_mv_limit_row(lay)

    # ── SV / Init SV: accept Pa, store as % ──────────────────────
    def _sv_changed(self):
        try:
            v_pa = max(self._PRESS_MIN, min(self._PRESS_MAX,
                       float(self._sv_in.text())))
        except ValueError:
            v_pa = self._pv_to_pa(self._sv_pct)
        self._sv_pct = self._pa_to_pct(v_pa)
        self._sv_in.setText(f"{v_pa:.2f}")

    def _sv_init_changed(self):
        try:
            v_pa = max(self._PRESS_MIN, min(self._PRESS_MAX,
                       float(self._sv_init_in.text())))
        except ValueError:
            v_pa = self._pv_to_pa(self._sv_init)
        self._sv_init = self._pa_to_pct(v_pa)
        self._sv_init_in.setText(f"{v_pa:.2f}")

    # ════════════════════════════════════════════════════
    #  SIM TICK
    # ════════════════════════════════════════════════════
    def _sim_tick(self):
        super()._sim_tick()

        # Rescale all plot curves to Pa domain
        if self._step % 4 == 0 and HAS_PG:
            ta = list(self._t_data)
            self._pv_curve.setData(ta, [v * self._PA_SCALE for v in self._pv_data])
            self._sv_curve.setData(ta, [v * self._PA_SCALE for v in self._sv_data])
            self._cv_curve.setData(ta, [v * self._PA_SCALE for v in self._cv_data])

        # Update all physical-unit displays every 10 ticks (~2 Hz)
        if self._step % 10 == 0:
            pa    = self._pv_to_pa(self._pv_n * 100.0)
            sv_pa = self._pv_to_pa(self._sv_pct)
            hz    = self._mv_to_hz(self._last_cv * 100.0)

            self._pv_disp.setText(f"{pa:5.2f}")
            self._sv_disp.setText(f"{sv_pa:5.2f}")
            self._pa_disp.setText(f"{pa:6.2f}")
            self._hz_disp.setText(f"{hz:5.1f}")

            # Update embedded animation panel
            self._pump_canvas.update_values(pa, hz, sv_pa)
            self._anim_pa_val.setText(f"{pa:.2f} Pa")
            self._anim_sv_val.setText(f"{sv_pa:.2f} Pa")
            self._anim_hz_val.setText(f"{hz:.1f} Hz")
