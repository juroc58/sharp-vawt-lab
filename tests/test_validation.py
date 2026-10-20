"""Validation tests against published references.

These are slow (long simulations) but they're the ones that catch physics
regressions. Mark them `slow` so they can be skipped for quick local
iteration: `pytest -m "not slow"`.
"""
import pytest

from vawt_core import create_sim_from_params
from scripts.validate_ham import (
    verdict, HAM_MID, HAM_BAND_LO, HAM_BAND_HI, HAM_BIAS_LO, HAM_BIAS_HI,
)


class TestHamVerdictContract:
    """The comparison contract in scripts/validate_ham.py, without running a sim.

    verdict() returns (status, bias, expected_lo, expected_hi). The model is
    expected to over-predict Ham's 3D band (2D solver, no tip loss), so a
    peak matching the midpoint exactly is *outside* the expected-bias window
    — that is intentional, not a bug.
    """

    def test_within_expected_window(self):
        status, bias, expected_lo, expected_hi = verdict(HAM_MID * 1.10)
        assert status == "comparison_expected"
        assert 0.05 <= bias <= 0.20
        assert expected_lo == pytest.approx(HAM_MID * (1.0 + HAM_BIAS_LO))
        assert expected_hi == pytest.approx(HAM_MID * (1.0 + HAM_BIAS_HI))

    def test_outside_expected_window_high(self):
        status, *_ = verdict(HAM_MID * 1.30)
        assert status == "comparison_out_of_expected_range"

    def test_outside_expected_window_low(self):
        # Matching the midpoint exactly is *not* expected for a 2D
        # no-tip-loss solver; it should over-predict instead.
        status, *_ = verdict(HAM_MID * 1.00)
        assert status == "comparison_out_of_expected_range"


@pytest.mark.slow
class TestHamPeakComparison:
    """Ham 1979 Pinson C2E geometry, Ham's own model class (no DS, no tip loss).

    The 2D static-only model is expected to over-predict Ham's 3D measured
    band because it has no finite-span (tip-loss) loss. These tests document
    the expected bias (5-20% over Ham's mid-band); they do NOT validate the
    model against Ham's experiment.
    """

    BASE_HAM = dict(
        R=1.83, c=0.305, H=1.37, N=3,
        ar=0.0, sp=0.25,
        mb=0.010, xbcg=0.20, mc=0.002, dcw=0.30,
        balance=0, bias_deg=0.0,
        prescribe_pitch=True, pp0_deg=0.0, pp1_deg=-10.0,
        pp2_deg=0.0, pp3_deg=0.0, pp_ph_deg=0.0,
        free=False, tsr=2.5, T_max=20.0, stride=5,
        use_dynamic_stall=False,
        use_flow_curvature=False,
        use_tip_loss=False,
        use_dmst=True,
        win_deg=89.0, cb=2e-5, mu_c=0.0,
        k_load=0.0004,
    )

    def test_ham_peak_bias_in_expected_window(self):
        r = create_sim_from_params(self.BASE_HAM).run()
        bias = (r['cp'] - HAM_MID) / HAM_MID
        # A 2D solver without tip loss is expected to over-predict Ham's
        # 3D measured band. The 5-20% window bounds gross regressions on
        # both sides; it is NOT a validation tolerance.
        assert 0.05 <= bias <= 0.20, (
            f"Ham peak Cp = {r['cp']:.4f} gives bias {bias*100:.1f}% vs "
            f"mid-band {HAM_MID}, outside expected 5-20% window"
        )

    def test_ham_peak_not_inside_measured_band(self):
        r = create_sim_from_params(self.BASE_HAM).run()
        # If this starts passing, either the solver or the polar tables
        # changed materially; re-examine before relaxing.
        assert not (HAM_BAND_LO <= r['cp'] <= HAM_BAND_HI), (
            f"Ham peak Cp = {r['cp']:.4f} is inside Ham's measured band "
            f"[{HAM_BAND_LO}, {HAM_BAND_HI}], unexpected for the 2D "
            "no-tip-loss model"
        )

    def test_ham_tsr_2_0_plausible(self):
        r = create_sim_from_params({**self.BASE_HAM, 'tsr': 2.0}).run()
        assert 0.32 < r['cp'] < 0.50


@pytest.mark.slow
class TestDynamicStallSensitivity:
    """Turning DS off should change Cp by less than 4 % at the design point."""

    # Prescribed-pitch design at the actuator optimiser's best point.
    # The passive optimiser's optimum is different; see
    # scripts/optimization_passive.json.  This test isolates DS
    # sensitivity at a below-stall, prescribed-pitch point.
    DESIGN = dict(
        R=0.60, H=0.40, N=3, c=0.117607,
        ar=0.31, sp=0.18,
        mb=0.010, xbcg=0.20, mc=0.040, dcw=-0.132,
        balance=0, bias_deg=-1.1,
        prescribe_pitch=True,
        pp0_deg=+5.156, pp1_deg=-6.329,
        pp2_deg=+2.758, pp3_deg=-0.085, pp_ph_deg=0.0,
        cd_add=0.002,
        use_flow_curvature=True,
        use_dmst=True, use_tip_loss=False,
        win_deg=45.0, cb=2e-5, mu_c=3e-4,
        free=True, T_max=30.0, stride=5,
        w0_frac=0.9, k_load=0.0015, tsr=2.14,
    )

    def test_ds_sensitivity_prescribed_design(self):
        """At the prescribed-pitch design point, DS changes Cp by < 4 %.

        With the XFOIL-derived polars the measured delta is ~1.8 %
        (Cp 0.497 with DS, 0.488 without), consistent with the README's
        claim that the prescribed result is driven by steady blade forces.
        The passive case is very different; see the next test.
        """
        r_ds = create_sim_from_params({**self.DESIGN, 'use_dynamic_stall': True}).run()
        r_nods = create_sim_from_params({**self.DESIGN, 'use_dynamic_stall': False}).run()
        delta = abs(r_ds['cp'] - r_nods['cp']) / max(r_ds['cp'], 1e-9)
        assert delta < 0.04, \
            f"DS sensitivity {delta*100:.1f}% > 4% " \
            f"(Cp with DS = {r_ds['cp']:.4f}, without = {r_nods['cp']:.4f})"

    def test_passive_ds_sensitivity_is_larger(self):
        """Passive operation is much more DS-sensitive than prescribed.

        Measured on the two passive headline anchors: switching DS off
        drops Cp by 91 % for Sharp-inspired CPPC (0.067 -> 0.006) and 75 %
        for the optimised passive machine (0.272 -> 0.068).  A passive
        pitch mechanism runs near static stall, so the DS model is load
        bearing for every passive result in this archive.  The bands are
        deliberately tight: these are deterministic runs, and a large move
        means the DS model or the anchors changed.

        The old bound (0.001 < delta < 0.95) was effectively vacuous and is
        replaced here.
        """
        from scripts.uncertainty import ANCHORS

        cps = {}
        for name in ("sharp_cppc", "optimised_passive"):
            p = ANCHORS[name]
            r_ds = create_sim_from_params({**p, 'use_dynamic_stall': True}).run()
            r_nods = create_sim_from_params({**p, 'use_dynamic_stall': False}).run()
            assert r_ds['cp'] > r_nods['cp']
            cps[name] = abs(r_ds['cp'] - r_nods['cp']) / max(r_ds['cp'], 1e-9)

        assert cps["sharp_cppc"] == pytest.approx(0.91, abs=0.05), (
            f"Sharp passive DS sensitivity {cps['sharp_cppc']*100:.1f}% "
            "outside 0.91 +/- 0.05"
        )
        assert cps["optimised_passive"] == pytest.approx(0.75, abs=0.05), (
            f"Optimised passive DS sensitivity "
            f"{cps['optimised_passive']*100:.1f}% outside 0.75 +/- 0.05"
        )
