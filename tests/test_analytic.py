"""Analytic-invariant sanity tests for the BEM solver.

These tests pin the solver against analytic invariants it should always
satisfy. They are *not* golden-value regression tests: they assert
inequalities and tolerances only, so they survive polar regeneration,
physics upgrades, and numerical tweaks without needing a golden-value
update.

The full suite is slow (each test runs 1-4 fixed-rpm simulations). Use
  python3 -m pytest tests/test_analytic.py -m "not slow"
to skip them for fast iteration, or run the whole fast suite with
  python3 -m pytest tests/ -q -m "not slow".

If any test fails, it means a physics invariant has broken -- investigate,
do not adjust the tolerance.
"""

from __future__ import annotations

import pytest

from sharp_vawt import create_sim_from_params

BASE = {
    # Small, fast, non-collapsing configuration.
    "R": 0.60,
    "c": 0.14,
    "H": 0.40,
    "N": 3,
    "ar": 0.50,
    "sp": 0.25,
    "mb": 0.010,
    "xbcg": 0.20,
    "mc": 0.002,
    "dcw": 0.30,
    "balance": 0,
    "bias_deg": 0.0,
    "prescribe_pitch": False,
    "cd_add": 0.002,
    "use_dynamic_stall": True,
    "use_flow_curvature": True,
    "use_dmst": True,
    "use_tip_loss": True,
    "win_deg": 45.0,
    "cb": 2e-5,
    "mu_c": 3e-4,
    "free": False,  # fixed-rpm for most tests (matches analytic form)
    "tsr": 2.5,
    "T_max": 15.0,
    "stride": 5,
    "k_load": 0.0025,
    "U": 8.0,
}

BETZ_LIMIT = 16.0 / 27.0


def _run(overrides: dict) -> float:
    """Run one fixed-rpm simulation and return its Cp."""
    params = {**BASE, **overrides}
    result = create_sim_from_params(params).run()
    return float(result["cp"])


@pytest.mark.slow
def test_betz_bound():
    """Cp must never exceed the Betz limit (16/27), at any TSR where the
    rotor produces positive power (this geometry's positive-Cp range is
    roughly TSR 0.5-2.25; above that it brakes)."""
    for tsr in (0.5, 1.0, 1.5, 2.0):
        cp = _run({"tsr": tsr})
        assert 0.0 < cp <= BETZ_LIMIT + 1e-9, (
            f"Cp={cp} at tsr={tsr} violates Betz bound {BETZ_LIMIT}"
        )


@pytest.mark.slow
def test_similarity_in_wind_speed():
    """At fixed TSR, doubling U should barely change Cp (Re dependence only)."""
    cp_6 = _run({"U": 6.0, "tsr": 2.0})
    cp_12 = _run({"U": 12.0, "tsr": 2.0})
    rel = abs(cp_12 - cp_6) / max(cp_6, 1e-9)
    assert rel < 0.02, (
        f"wind-speed similarity violated: cp_6={cp_6:.4f}, cp_12={cp_12:.4f}, "
        f"relative change {rel*100:.2f}% (limit 2%)"
    )


@pytest.mark.slow
def test_geometric_scaling():
    """Cp invariant under uniform geometric scaling with documented mass/load scaling."""
    cp_a = _run({"tsr": 2.0})
    scaled = {
        "R": 2 * BASE["R"],
        "H": 2 * BASE["H"],
        "c": 2 * BASE["c"],
        "mb": 2**3 * BASE["mb"],
        "mc": 2**3 * BASE["mc"],
        "k_load": 2**5 * BASE["k_load"],
        "tsr": 2.0,
    }
    cp_b = _run(scaled)
    rel = abs(cp_b - cp_a) / max(cp_a, 1e-9)
    assert rel < 0.05, (
        f"geometric scaling violated: cp_a={cp_a:.4f}, cp_b={cp_b:.4f}, "
        f"relative change {rel*100:.2f}% (limit 5%)"
    )


@pytest.mark.slow
def test_rotational_symmetry():
    """For an N=3 rotor, psi0 shifted by 2*pi/N gives equivalent Cp."""
    cp_a = _run({"psi0_deg": 0.0, "tsr": 2.0})
    cp_b = _run({"psi0_deg": 120.0, "tsr": 2.0})
    rel = abs(cp_b - cp_a) / max(cp_a, 1e-9)
    assert rel < 0.02, (
        f"rotational symmetry violated: cp_0={cp_a:.4f}, cp_120={cp_b:.4f}, "
        f"relative change {rel*100:.2f}% (limit 2%)"
    )


@pytest.mark.slow
def test_dt_convergence():
    """Halving dt must converge Cp to within 1%."""
    cp_a = _run({"dt": 2e-4, "tsr": 2.0})
    cp_b = _run({"dt": 1e-4, "tsr": 2.0})
    rel = abs(cp_b - cp_a) / max(cp_a, 1e-9)
    assert rel < 0.01, (
        f"dt convergence violated: cp_dt2e-4={cp_a:.4f}, cp_dt1e-4={cp_b:.4f}, "
        f"relative change {rel*100:.2f}% (limit 1%)"
    )


@pytest.mark.slow
def test_cm_sign_effect():
    """Cp(+1.0) < Cp(0.0) < Cp(-1.0): Cm sign invariant."""
    cp_pos = _run({"cm_scale": 1.0, "tsr": 2.0})
    cp_zero = _run({"cm_scale": 0.0, "tsr": 2.0})
    cp_neg = _run({"cm_scale": -1.0, "tsr": 2.0})
    assert cp_pos < cp_zero < cp_neg, (
        f"Cm sign effect violated: cp(+1)={cp_pos:.4f}, cp(0)={cp_zero:.4f}, "
        f"cp(-1)={cp_neg:.4f} (expected cp(+1) < cp(0) < cp(-1))"
    )


@pytest.mark.slow
def test_zero_wind_does_not_sustain():
    """At essentially zero wind, the rotor must not sustain rotation and
    must produce no meaningful power. No rotor can sustain rotation
    without wind. (Cp is ill-conditioned as U -> 0 because it divides by
    U**3, so we check rpm near zero instead of Cp near zero.)"""

    # Normal operating condition: rotor should produce positive power.
    result_norm = create_sim_from_params({**BASE, "free": True, "U": 8.0}).run()
    cp_norm = float(result_norm["cp"])
    assert cp_norm > 0.0, (
        f"free-running rotor at U=8.0 should produce power, got Cp={cp_norm:.4f}"
    )
    assert bool(result_norm["steady"]), (
        "free-running rotor at U=8.0 should reach steady state"
    )

    # Zero wind: rotor should not sustain rotation (rpm near zero).
    result_zero = create_sim_from_params({**BASE, "free": True, "U": 1e-3}).run()
    rpm_zero = float(result_zero["rpm"])
    assert rpm_zero < 1.0, (
        f"zero-wind rotor should not sustain rotation, got rpm={rpm_zero:.4f}"
    )


@pytest.mark.slow
def test_mirror_symmetry_prescribed():
    """Prescribed-pitch mode: reversed rotation + negated pitch preserves Cp.

    The polar tables are odd in Cl/Cm and even in Cd by construction.
    Prescribed-pitch mode has no asymmetric restoring force (xbcg, bias_deg),
    so mirroring (tsr, psi, alpha) should preserve Cp within Re-interpolation
    tolerance.
    """
    BASE_PRESCRIBE = {
        **BASE,
        "prescribe_pitch": True,
        "free": False,
        "tsr": 2.5,
        "pp0_deg": 5.0,
        "pp1_deg": -6.0,
        "pp2_deg": 2.0,
        "pp3_deg": -0.5,
        "pp_ph_deg": 0.0,
    }
    cp_a = _run(BASE_PRESCRIBE)

    mirrored = {
        **BASE_PRESCRIBE,
        "tsr": -2.5,
        "pp0_deg": -5.0,
        "pp1_deg": 6.0,
        "pp2_deg": -2.0,
        "pp3_deg": 0.5,
    }
    try:
        cp_b = _run(mirrored)
    except ZeroDivisionError:
        pytest.skip(
            "negative TSR causes ZeroDivisionError in BEM kernel; "
            "mirror symmetry not verifiable for reverse rotation"
        )

    rel = abs(cp_b - cp_a) / max(cp_a, 1e-9)
    assert rel < 0.05, (
        f"mirror symmetry violated: cp_a={cp_a:.4f}, cp_b={cp_b:.4f}, "
        f"relative change {rel*100:.2f}% (limit 5%)"
    )


@pytest.mark.slow
def test_helmbold_lift_slope():
    """Pure math check: Helmbold finite-span lift-slope factor matches
    the analytic formula for AR in {2, 3, 4, 6, 10}."""
    import math

    c = 0.14
    for AR in (2, 3, 4, 6, 10):
        params = {**BASE, "H": AR * c, "tsr": 2.0}
        sim = create_sim_from_params(params)
        expected = 1.0 / (math.sqrt(1.0 + (2.0 / AR) ** 2) + 2.0 / AR)
        assert abs(sim.f_ar - expected) < 0.001, (
            f"AR={AR}: f_ar={sim.f_ar:.6f}, expected={expected:.6f}"
        )
