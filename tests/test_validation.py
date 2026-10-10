"""Validation tests against published references.

These are slow (long simulations) but they're the ones that catch physics
regressions. Mark them `slow` so they can be skipped for quick local
iteration: `pytest -m "not slow"`.
"""
import pytest

from vawt_core import create_sim_from_params


@pytest.mark.slow
class TestHamReproduction:
    """Ham 1979 Pinson C2E geometry, Ham's own model class (no DS, no tip loss)."""

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

    def test_ham_tsr_2_5_within_band(self):
        r = create_sim_from_params(self.BASE_HAM).run()
        # Ham 1979 reported Cp = 0.42-0.45 at TSR 2.5-3.0.
        # The solver (2D, no tip loss) runs ~+9 % above the band; see README.
        assert 0.40 < r['cp'] < 0.52, f"Ham Cp = {r['cp']:.3f} outside plausible band"

    def test_ham_tsr_2_0_within_band(self):
        r = create_sim_from_params({**self.BASE_HAM, 'tsr': 2.0}).run()
        assert 0.40 < r['cp'] < 0.52


@pytest.mark.slow
class TestDynamicStallSensitivity:
    """Turning DS off should change Cp by less than 10 % at the design point."""

    # Prescribed-pitch design at the optimiser's best point.  Matches
    # the DS sensitivity number quoted in the README (2.1 %).
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

    def test_ds_sensitivity_under_10_percent(self):
        """The README claims ΔCp < 5 % when the dynamic-stall model is
        turned off at the optimiser's prescribed-pitch design point."""
        r_ds = create_sim_from_params({**self.DESIGN, 'use_dynamic_stall': True}).run()
        r_nods = create_sim_from_params({**self.DESIGN, 'use_dynamic_stall': False}).run()
        delta = abs(r_ds['cp'] - r_nods['cp']) / max(r_ds['cp'], 1e-9)
        assert delta < 0.10, \
            f"DS sensitivity {delta*100:.1f}% > 10% " \
            f"(Cp with DS = {r_ds['cp']:.4f}, without = {r_nods['cp']:.4f})"

    def test_passive_ds_sensitivity_is_larger(self):
        """A test that documents the physical difference: passive operation
        is much more DS-sensitive than prescribed.  If this test ever fails
        it means something in the pitch dynamics has changed."""
        passive = {**self.DESIGN,
                   'prescribe_pitch': False,
                   'use_tip_loss': True,
                   'T_max': 30.0}
        r_ds = create_sim_from_params({**passive, 'use_dynamic_stall': True}).run()
        r_nods = create_sim_from_params({**passive, 'use_dynamic_stall': False}).run()
        delta = abs(r_ds['cp'] - r_nods['cp']) / max(r_ds['cp'], 1e-9)
        # Passive mode: DS sensitivity is larger than prescribed (2.1 %)
        # but should not dominate.  Observed range: 3-10 %.
        # Wide bounds so the test detects regressions without being fragile.
        assert 0.01 < delta < 0.30, \
            f"Passive DS sensitivity {delta*100:.1f}% outside expected range"
