"""Tests for the physics overrides added for the UQ study."""
import pytest

from vawt_core import create_sim_from_params
from tests.conftest import BASE_QUICK


class TestTipLossBounds:

    def test_bounded_tip_loss_floor_applies(self):
        """At AR = 3.18, un-bounded correction would be ~0.59. We cap at 0.85."""
        s = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14})
        # AR = 0.445 / 0.14 = 3.18  →  raw f_ar ≈ 0.59
        # bounded should be 0.85
        assert s.f_ar == pytest.approx(0.85, abs=0.01)

    def test_high_AR_gives_high_f_ar(self):
        """Higher aspect ratio must give a higher (closer to 1) f_ar."""
        s_lo = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14})
        s_hi = create_sim_from_params({**BASE_QUICK, 'H': 3.0, 'c': 0.10})
        # AR 3.18 vs 30: raw f_ar 0.59 vs 0.93
        assert s_hi.f_ar > s_lo.f_ar
        assert s_hi.f_ar < 1.0
        assert s_lo.f_ar >= 0.85   # bounded floor


class TestCScaleOverride:

    def test_c_scale_default_used_when_zero(self):
        """c_scale_override = 0 (default) → use geometry-derived value."""
        # For R = 0.6, c = 0.14: c_scale = min(1, 0.233/0.418) = 0.558
        s = create_sim_from_params({**BASE_QUICK, 'c': 0.14, 'R': 0.60,
                                    'c_scale_override': 0.0})
        assert s.c_scale == pytest.approx(0.558, abs=0.01)

    def test_c_scale_override_applied(self):
        s = create_sim_from_params({**BASE_QUICK, 'c_scale_override': 0.42})
        assert s.c_scale == pytest.approx(0.42)


class TestEnergyLedger:

    def test_energy_ledger_closes_for_passive_run(self):
        """Passive run: |resid| < 5 %."""
        r = create_sim_from_params({
            **BASE_QUICK, 'T_max': 15.0, 'stride': 5,
        }).run()
        assert r['energy_balance_valid'] is True
        assert abs(r['energy_balance']) < 0.05

    def test_reproducibility(self):
        """Same seed + same params → same Cp."""
        p = {**BASE_QUICK, 'T_max': 10.0, 'turb_I': 0.12, 'seed': 3}
        r1 = create_sim_from_params(p).run()
        r2 = create_sim_from_params(p).run()
        assert r1['cp'] == pytest.approx(r2['cp'], abs=1e-9)
