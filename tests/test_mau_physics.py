"""Unit tests for MAU physics: Psych, AirState, PidCtrl, FopdtCoil"""
import sys, math
from pathlib import Path
from unittest.mock import MagicMock

# Mock Qt + styles so we can import physics without a display
for _m in ('PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets'):
    sys.modules.setdefault(_m, MagicMock())
sys.modules.setdefault('styles', MagicMock())

sys.path.insert(0, str(Path(__file__).parent.parent))
from tool_pid_mau import Psych, AirState, PidCtrl, FopdtCoil

import pytest


# ─────────────────────────────────────────────
#  Psych
# ─────────────────────────────────────────────
class TestPsych:
    def test_pws_at_0c(self):
        assert abs(Psych.pws(0.0) - 0.6108) < 0.002

    def test_pws_at_20c(self):
        assert abs(Psych.pws(20.0) - 2.338) < 0.05

    def test_omega_100rh_equals_omega_sat(self):
        for T in [-5, 0, 15, 25, 40]:
            assert abs(Psych.omega(T, 100.0) - Psych.omega_sat(T)) < 1e-9

    def test_omega_zero_rh_is_zero(self):
        assert Psych.omega(20.0, 0.0) == 0.0

    @pytest.mark.parametrize("T,RH", [(20, 50), (35, 80), (5, 30), (15, 99)])
    def test_rh_roundtrip(self, T, RH):
        w = Psych.omega(T, RH)
        assert abs(Psych.rh(T, w) - RH) < 0.05

    @pytest.mark.parametrize("T,RH", [(25, 60), (35, 80), (10, 50)])
    def test_t_dp_less_than_dbt(self, T, RH):
        w = Psych.omega(T, RH)
        assert Psych.t_dp(w) <= T + 1e-6

    @pytest.mark.parametrize("T", [5, 15, 25])
    def test_t_dp_equals_dbt_at_saturation(self, T):
        w = Psych.omega_sat(T)
        assert abs(Psych.t_dp(w) - T) < 0.1

    def test_enthalpy_increases_with_temperature(self):
        w = 0.01
        assert Psych.enthalpy(30, w) > Psych.enthalpy(20, w)

    def test_t_wb_between_dp_and_dbt(self):
        T, RH = 30, 50
        w = Psych.omega(T, RH)
        dp = Psych.t_dp(w)
        wb = Psych.t_wb(T, w)
        assert dp <= wb <= T + 1e-6


# ─────────────────────────────────────────────
#  AirState
# ─────────────────────────────────────────────
class TestAirState:
    def test_rh_property(self):
        T, RH = 25.0, 60.0
        s = AirState(T, Psych.omega(T, RH))
        assert abs(s.RH - RH) < 0.05

    def test_copy_is_independent(self):
        s = AirState(20.0, 0.01)
        c = s.copy()
        c.T = 99.0
        assert s.T == 20.0

    def test_enthalpy_property_matches_psych(self):
        s = AirState(20.0, Psych.omega(20.0, 50.0))
        assert abs(s.h - Psych.enthalpy(s.T, s.w)) < 1e-9

    def test_w_gkg_is_w_times_1000(self):
        s = AirState(20.0, 0.010)
        assert abs(s.w_gkg - 10.0) < 1e-9

    def test_t_dp_property(self):
        T, RH = 20.0, 50.0
        s = AirState(T, Psych.omega(T, RH))
        assert abs(s.T_dp - Psych.t_dp(s.w)) < 1e-9


# ─────────────────────────────────────────────
#  PidCtrl
# ─────────────────────────────────────────────
class TestPidCtrl:
    def test_reverse_action_heats_when_pv_low(self):
        pid = PidCtrl(2.0, 0.0, 0.0, reverse=True)
        mv = pid.compute(PV=10.0, SP=20.0, dt=0.05)
        assert mv > 0

    def test_direct_action_positive_when_pv_above_sp(self):
        pid = PidCtrl(2.0, 0.0, 0.0, reverse=False)
        mv = pid.compute(PV=25.0, SP=20.0, dt=0.05)
        assert mv > 0

    def test_mv_clamped_at_hi(self):
        pid = PidCtrl(100.0, 0.0, 0.0, reverse=True, mv_lo=0.0, mv_hi=100.0)
        mv = pid.compute(PV=0.0, SP=100.0, dt=0.05)
        assert mv == 100.0

    def test_mv_clamped_at_lo(self):
        pid = PidCtrl(100.0, 0.0, 0.0, reverse=False, mv_lo=0.0, mv_hi=100.0)
        mv = pid.compute(PV=0.0, SP=100.0, dt=0.05)
        assert mv == 0.0

    def test_zero_error_zero_mv_proportional_only(self):
        pid = PidCtrl(2.0, 0.0, 0.0, reverse=True)
        mv = pid.compute(PV=20.0, SP=20.0, dt=0.05)
        assert mv == 0.0

    def test_manual_mode_ignores_pv_sp(self):
        pid = PidCtrl(2.0, 0.1, 0.0, reverse=True)
        pid.auto = False; pid.manual_mv = 42.0
        mv = pid.compute(PV=0.0, SP=100.0, dt=0.05)
        assert mv == 42.0

    def test_integral_accumulates_over_time(self):
        pid = PidCtrl(0.0, 1.0, 0.0, reverse=True)
        mv1 = pid.compute(10.0, 20.0, 0.05)
        mv2 = pid.compute(10.0, 20.0, 0.05)
        assert mv2 > mv1

    def test_reset_clears_integral(self):
        pid = PidCtrl(0.0, 1.0, 0.0, reverse=True)
        for _ in range(10):
            pid.compute(0.0, 100.0, 0.05)
        pid.reset()
        mv = pid.compute(0.0, 0.0, 0.05)
        assert mv == 0.0

    def test_proportional_scales_with_kp(self):
        pid1 = PidCtrl(1.0, 0.0, 0.0, reverse=True)
        pid2 = PidCtrl(3.0, 0.0, 0.0, reverse=True)
        mv1 = pid1.compute(10.0, 20.0, 0.05)
        mv2 = pid2.compute(10.0, 20.0, 0.05)
        assert abs(mv2 / mv1 - 3.0) < 1e-6


# ─────────────────────────────────────────────
#  FopdtCoil
# ─────────────────────────────────────────────
class TestFopdtCoil:
    def test_heating_coil_positive_output(self):
        fo = FopdtCoil(0.3, 10.0, 0.0, heating=True)
        for _ in range(100):
            out = fo.step(100.0, 0.05)
        assert out > 0

    def test_cooling_coil_negative_output(self):
        fo = FopdtCoil(0.3, 10.0, 0.0, heating=False)
        for _ in range(100):
            out = fo.step(100.0, 0.05)
        assert out < 0

    def test_zero_mv_zero_output(self):
        fo = FopdtCoil(0.3, 10.0, 0.0, heating=True)
        for _ in range(100):
            out = fo.step(0.0, 0.05)
        assert abs(out) < 1e-6

    def test_steady_state_approaches_kp_times_mv(self):
        Kp, MV = 0.5, 100.0
        fo = FopdtCoil(Kp, 5.0, 0.0, heating=True)
        for _ in range(500):
            out = fo.step(MV, 0.05)
        assert abs(out - Kp * MV) < 1.0

    def test_dead_time_delays_response(self):
        fo = FopdtCoil(1.0, 5.0, L=1.0, heating=True, dt=0.05)
        for _ in range(9):   # 0.45s < 1s dead time
            out = fo.step(100.0, 0.05)
        assert abs(out) < 2.0

    def test_reset_clears_state(self):
        fo = FopdtCoil(0.3, 5.0, 0.0, heating=True)
        for _ in range(50):
            fo.step(100.0, 0.05)
        fo.reset()
        out = fo.step(0.0, 0.05)
        assert abs(out) < 1e-6

    def test_fan_scale_reduces_output(self):
        fo1 = FopdtCoil(0.3, 5.0, 0.0, heating=True)
        fo2 = FopdtCoil(0.3, 5.0, 0.0, heating=True)
        for _ in range(50):
            out1 = fo1.step(100.0, 0.05, fan_scale=1.0)
            out2 = fo2.step(100.0, 0.05, fan_scale=0.5)
        assert out1 > out2
