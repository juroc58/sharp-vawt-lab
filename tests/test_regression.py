"""Golden-Cp regression tests.

These pin the solver's output at three canonical operating points so that
any change in the physics kernel (induction, dynamic stall, pitch
dynamics, integration) that moves Cp is caught immediately. The values
below were generated with the committed `vawt_core.py`; regenerate with:

    python3 -c "import tests.regenerate_golden as g; g.main()"

Tolerance is 1e-3 relative. Small perturbations to the time step and
initial conditions move Cp by < 3e-4, while a genuine physics change
(e.g. the alpha sign convention, an induction coefficient) moves it by
percent-level. The band therefore catches regressions without being
flaky across platforms.
"""
import pytest

from vawt_core import create_sim_from_params
from tests.conftest import BASE_QUICK


# name -> (params, expected_cp)
GOLDEN = {
    "ham_static_tsr2_5": (
        dict(
            R=1.83, c=0.305, H=1.37, N=3, ar=0.0, sp=0.25,
            mb=0.010, xbcg=0.20, mc=0.002, dcw=0.30,
            balance=0, bias_deg=0.0,
            prescribe_pitch=True, pp0_deg=0.0, pp1_deg=-10.0,
            pp2_deg=0.0, pp3_deg=0.0, pp_ph_deg=0.0,
            free=False, tsr=2.5, T_max=12.0, stride=5,
            use_dynamic_stall=False, use_flow_curvature=False,
            use_tip_loss=False, use_dmst=True,
            win_deg=89.0, cb=2e-5, mu_c=0.0, k_load=0.0004,
        ),
        0.4660262550,
    ),
    "passive_short_free": (
        dict(
            R=0.60, H=0.40, N=3, c=0.14, ar=0.50, sp=0.25,
            mb=0.010, xbcg=0.20, mc=0.002, dcw=0.30,
            balance=0, bias_deg=0.0, prescribe_pitch=False,
            cd_add=0.002, use_dynamic_stall=True, use_flow_curvature=True,
            use_dmst=True, use_tip_loss=True, win_deg=45.0, cb=2e-5,
            mu_c=3e-4, free=True, T_max=10.0, stride=10,
            w0_frac=0.9, k_load=0.0025, tsr=2.0,
        ),
        0.1756620284,
    ),
    "prescribed_fixed_rpm": (
        dict(
            R=0.60, H=0.40, N=3, c=0.117607, ar=0.50, sp=0.25,
            mb=0.010, xbcg=0.20, mc=0.008, dcw=0.50,
            balance=0, bias_deg=0.0,
            prescribe_pitch=True, pp0_deg=5.15612, pp1_deg=-6.32883,
            pp2_deg=2.75837, pp3_deg=-0.0845207, pp_ph_deg=0.0,
            cd_add=0.002, use_flow_curvature=True,
            free=False, tsr=2.14487, T_max=10.0, stride=5,
            use_dynamic_stall=True, use_dmst=True, use_tip_loss=False,
            cb=2e-5, mu_c=3e-4, k_load=0.00149992,
        ),
        0.4360266506,
    ),
}

TOL = 1e-3


@pytest.mark.slow
@pytest.mark.parametrize("name", list(GOLDEN))
class TestGoldenCp:

    def test_cp_matches_golden(self, name):
        params, expected = GOLDEN[name]
        r = create_sim_from_params(params).run()
        assert r["steady"] is True, f"{name}: run did not settle"
        rel = abs(r["cp"] - expected) / abs(expected)
        assert rel < TOL, (
            f"{name}: Cp = {r['cp']:.8f}, golden = {expected:.8f} "
            f"(rel {rel:.2e} > {TOL:.0e}). "
            f"A >0.1% move means the physics changed; if intentional, "
            f"regenerate tests/regenerate_golden.py."
        )

    def test_energy_ledger_closes(self, name):
        params, _ = GOLDEN[name]
        r = create_sim_from_params(params).run()
        if params.get("prescribe_pitch"):
            # Prescribed pitch: the actuator work is external, so the
            # residual is not a meaningful diagnostic (documented in
            # derivation.md §10).
            pytest.skip("prescribed-pitch run: ledger not meaningful")
        assert r["energy_balance_valid"] is True
        assert abs(r["energy_balance"]) < 0.02, \
            f"{name}: energy residual {r['energy_balance']*100:.2f}%"


class TestBaseQuickReproducibility:
    """The shared test fixture (BASE_QUICK) must be bit-reproducible and
    hit its documented operating point."""

    def test_base_quick_reproducible(self):
        r1 = create_sim_from_params({**BASE_QUICK}).run()
        r2 = create_sim_from_params({**BASE_QUICK}).run()
        assert r1["cp"] == pytest.approx(r2["cp"], abs=1e-9)

    def test_base_quick_cp_in_range(self):
        r = create_sim_from_params({**BASE_QUICK}).run()
        # BASE_QUICK is the Sharp-inspired CPPC fixture; its Cp is ~0.17.
        assert 0.10 < r["cp"] < 0.25, f"BASE_QUICK Cp drifted to {r['cp']:.4f}"

    def test_gust_reproducible_with_seed(self):
        p = {**BASE_QUICK, "turb_I": 0.12, "seed": 7, "T_max": 8.0}
        r1 = create_sim_from_params(p).run()
        r2 = create_sim_from_params(p).run()
        assert r1["cp"] == pytest.approx(r2["cp"], abs=1e-9)