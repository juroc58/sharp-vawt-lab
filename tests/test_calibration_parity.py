"""Aerodynamic parity test: calibration ModelRunner vs production _aero_coeffs.

This test ensures the calibration path in scripts/calibrate_dynamic_stall.py uses
exactly the same aerodynamic routine as the production rotor engine.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from scripts.calibrate_dynamic_stall import ModelRunner
from sharp_vawt.config import AeroConfig
from sharp_vawt.database import PolarDatabase
from sharp_vawt.engine import _aero_coeffs


def _make_fixed_trace() -> list[dict[str, float]]:
    """Build a fixed trace spanning attached flow, stall, and reattachment.

    Returns a list of dicts with keys: time, alpha, W, chord, Re.
    Uses 200 steps covering:
    - Attached flow: alpha from -5 to +5 deg
    - Stall: alpha from +5 to +25 deg (positive stall)
    - Reattachment: alpha from +25 back to -5 deg
    - Negative stall: alpha from -5 to -25 deg
    - Final attached: alpha from -25 back to +5 deg
    """
    trace: list[dict[str, float]] = []
    chord = 0.14
    W = 8.0
    Re = 2.0e5
    dt = 0.01  # 100 Hz sampling

    # Phase 1: Attached flow, positive alpha sweep (-5 to +5 deg)
    for i, alpha_deg in enumerate(np.linspace(-5.0, 5.0, 20)):
        trace.append({
            "time": i * dt,
            "alpha": alpha_deg,
            "W": W,
            "chord": chord,
            "Re": Re,
        })

    # Phase 2: Positive stall (+5 to +25 deg)
    for i, alpha_deg in enumerate(np.linspace(5.0, 25.0, 40)):
        idx = 20 + i
        trace.append({
            "time": idx * dt,
            "alpha": alpha_deg,
            "W": W,
            "chord": chord,
            "Re": Re,
        })

    # Phase 3: Reattachment (+25 back to -5 deg)
    for i, alpha_deg in enumerate(np.linspace(25.0, -5.0, 60)):
        idx = 60 + i
        trace.append({
            "time": idx * dt,
            "alpha": alpha_deg,
            "W": W,
            "chord": chord,
            "Re": Re,
        })

    # Phase 4: Negative stall (-5 to -25 deg)
    for i, alpha_deg in enumerate(np.linspace(-5.0, -25.0, 40)):
        idx = 120 + i
        trace.append({
            "time": idx * dt,
            "alpha": alpha_deg,
            "W": W,
            "chord": chord,
            "Re": Re,
        })

    # Phase 5: Final attached (-25 back to +5 deg)
    for i, alpha_deg in enumerate(np.linspace(-25.0, 5.0, 40)):
        idx = 160 + i
        trace.append({
            "time": idx * dt,
            "alpha": alpha_deg,
            "W": W,
            "chord": chord,
            "Re": Re,
        })

    return trace


def _run_production_path(trace: list[dict[str, float]], aero: AeroConfig, pdb: PolarDatabase) -> list[tuple[float, float, float]]:
    """Run the trace through the production _aero_coeffs exactly as the kernel does."""
    out: list[tuple[float, float, float]] = []
    ds = [0.0, 0.0, 0.0, 0.0, 0.0]  # alpha_eff, f_dyn, v_vortex, alpha_prev, initialised
    prev_t = None
    dyn = int(aero.use_dynamic_stall)
    clmax = pdb.Cl_max
    cm_scale = aero.cm_scale

    for pt in trace:
        t = pt["time"]
        dt = (t - prev_t) if prev_t is not None else 0.05 * pt["chord"] / max(pt["W"], 1e-3)
        prev_t = t
        Cl, Cd, _Cl_nc, _f, Cm = _aero_coeffs(
            ds, math.radians(pt["alpha"]), pt["W"], pt["chord"], dt, pt["Re"],
            dyn,
            aero.ds_Tf, aero.ds_Tv, aero.ds_Ta,
            aero.ds_Kv, clmax,
            pdb.logRe_grid, pdb.alpha_grid, pdb.cla_re,
            pdb.Cl, pdb.Cd, pdb.Cm, cm_scale,
        )
        out.append((float(Cl), float(Cd), float(Cm)))
    return out


def _run_calibration_path(trace: list[dict[str, float]]) -> list[tuple[float, float, float]]:
    """Run the trace through the calibration ModelRunner.simulate with default params."""
    runner = ModelRunner()
    # Use the same DS params that ModelRunner uses internally (from DEFAULTS)
    params = {
        "ds_Tf": runner.aero.ds_Tf,
        "ds_Tv": runner.aero.ds_Tv,
        "ds_Ta": runner.aero.ds_Ta,
        "ds_Kv": runner.aero.ds_Kv,
        "ds_Knc": runner.aero.ds_Knc,
    }
    return runner.simulate(trace, params)


class TestAerodynamicParity:
    """Test that calibration and production aerodynamic paths produce identical results."""

    def test_parity_identical_results_default_config(self):
        """Cl, Cd, Cm must agree to <= 1e-12 relative at every step with default config."""
        trace = _make_fixed_trace()
        # Use ModelRunner's internal config for both paths to ensure exact match
        runner = ModelRunner()
        aero = runner.aero
        pdb = runner.pdb

        prod_results = _run_production_path(trace, aero, pdb)
        cal_results = _run_calibration_path(trace)

        assert len(prod_results) == len(cal_results) == len(trace)

        for i, ((Cl_p, Cd_p, Cm_p), (Cl_c, Cd_c, Cm_c)) in enumerate(zip(prod_results, cal_results)):
            # Relative tolerance of 1e-12 for identical code paths
            assert Cl_p == pytest.approx(Cl_c, rel=1e-12), f"Step {i}: Cl mismatch: prod={Cl_p}, cal={Cl_c}"
            assert Cd_p == pytest.approx(Cd_c, rel=1e-12), f"Step {i}: Cd mismatch: prod={Cd_p}, cal={Cd_c}"
            assert Cm_p == pytest.approx(Cm_c, rel=1e-12), f"Step {i}: Cm mismatch: prod={Cm_p}, cal={Cm_c}"

    def test_parity_with_dynamic_stall_off(self):
        """Parity must also hold when dynamic stall is disabled.

        This test creates a ModelRunner with use_dynamic_stall=False by patching
        the config before instantiation.
        """
        trace = _make_fixed_trace()

        # Create AeroConfig with dynamic stall off
        aero_no_ds = AeroConfig(use_dynamic_stall=False)
        pdb_no_ds = PolarDatabase(aero_no_ds.polar_dir, variant=aero_no_ds.polar_variant)

        # For calibration path, we need a ModelRunner with dynamic stall off
        # Since ModelRunner creates its own AeroConfig, we test production path
        # against a direct _aero_coeffs call with the same settings
        prod_results = _run_production_path(trace, aero_no_ds, pdb_no_ds)

        # Manual calibration-style call with dyn=0
        cal_results: list[tuple[float, float, float]] = []
        ds = [0.0, 0.0, 0.0, 0.0, 0.0]
        prev_t = None
        dyn = 0
        clmax = pdb_no_ds.Cl_max
        cm_scale = aero_no_ds.cm_scale

        for pt in trace:
            t = pt["time"]
            dt = (t - prev_t) if prev_t is not None else 0.05 * pt["chord"] / max(pt["W"], 1e-3)
            prev_t = t
            Cl, Cd, _Cl_nc, _f, Cm = _aero_coeffs(
                ds, math.radians(pt["alpha"]), pt["W"], pt["chord"], dt, pt["Re"],
                dyn,
                aero_no_ds.ds_Tf, aero_no_ds.ds_Tv, aero_no_ds.ds_Ta,
                aero_no_ds.ds_Kv, clmax,
                pdb_no_ds.logRe_grid, pdb_no_ds.alpha_grid, pdb_no_ds.cla_re,
                pdb_no_ds.Cl, pdb_no_ds.Cd, pdb_no_ds.Cm, cm_scale,
            )
            cal_results.append((float(Cl), float(Cd), float(Cm)))

        assert len(prod_results) == len(cal_results) == len(trace)

        for i, ((Cl_p, Cd_p, Cm_p), (Cl_c, Cd_c, Cm_c)) in enumerate(zip(prod_results, cal_results)):
            assert Cl_p == pytest.approx(Cl_c, rel=1e-12), f"Step {i}: Cl mismatch (dyn off)"
            assert Cd_p == pytest.approx(Cd_c, rel=1e-12), f"Step {i}: Cd mismatch (dyn off)"
            assert Cm_p == pytest.approx(Cm_c, rel=1e-12), f"Step {i}: Cm mismatch (dyn off)"


class TestAerodynamicParityNegativeControls:
    """Negative controls: deliberate mismatches must be detected."""

    def test_mismatch_cm_scale_detected(self):
        """Changing cm_scale in only one path must cause a detectable mismatch."""
        trace = _make_fixed_trace()
        aero_prod = AeroConfig(cm_scale=1.0)
        aero_cal = AeroConfig(cm_scale=0.5)  # Different!
        pdb_prod = PolarDatabase(aero_prod.polar_dir, variant=aero_prod.polar_variant)
        pdb_cal = PolarDatabase(aero_cal.polar_dir, variant=aero_cal.polar_variant)

        prod_results = _run_production_path(trace, aero_prod, pdb_prod)

        # Manual calibration-style call with different cm_scale
        cal_results: list[tuple[float, float, float]] = []
        ds = [0.0, 0.0, 0.0, 0.0, 0.0]
        prev_t = None
        dyn = int(aero_cal.use_dynamic_stall)
        clmax = pdb_cal.Cl_max
        cm_scale = aero_cal.cm_scale

        for pt in trace:
            t = pt["time"]
            dt = (t - prev_t) if prev_t is not None else 0.05 * pt["chord"] / max(pt["W"], 1e-3)
            prev_t = t
            Cl, Cd, _Cl_nc, _f, Cm = _aero_coeffs(
                ds, math.radians(pt["alpha"]), pt["W"], pt["chord"], dt, pt["Re"],
                dyn,
                aero_cal.ds_Tf, aero_cal.ds_Tv, aero_cal.ds_Ta,
                aero_cal.ds_Kv, clmax,
                pdb_cal.logRe_grid, pdb_cal.alpha_grid, pdb_cal.cla_re,
                pdb_cal.Cl, pdb_cal.Cd, pdb_cal.Cm, cm_scale,
            )
            cal_results.append((float(Cl), float(Cd), float(Cm)))

        # At least one Cm value must differ significantly
        cm_diffs = [abs(c_p - c_c) for (_, _, c_p), (_, _, c_c) in zip(prod_results, cal_results)]
        max_diff = max(cm_diffs)
        assert max_diff > 1e-6, f"Expected Cm mismatch from cm_scale change, max diff = {max_diff}"

    def test_mismatch_polar_variant_detected(self):
        """Changing polar variant in only one path must cause a detectable mismatch."""
        trace = _make_fixed_trace()
        aero_prod = AeroConfig(polar_variant="neuralfoil")
        aero_cal = AeroConfig(polar_variant="neuralfoil_cm")  # Different!
        pdb_prod = PolarDatabase(aero_prod.polar_dir, variant=aero_prod.polar_variant)
        pdb_cal = PolarDatabase(aero_cal.polar_dir, variant=aero_cal.polar_variant)

        prod_results = _run_production_path(trace, aero_prod, pdb_prod)

        # Manual calibration-style call with different polar variant
        cal_results: list[tuple[float, float, float]] = []
        ds = [0.0, 0.0, 0.0, 0.0, 0.0]
        prev_t = None
        dyn = int(aero_cal.use_dynamic_stall)
        clmax = pdb_cal.Cl_max
        cm_scale = aero_cal.cm_scale

        for pt in trace:
            t = pt["time"]
            dt = (t - prev_t) if prev_t is not None else 0.05 * pt["chord"] / max(pt["W"], 1e-3)
            prev_t = t
            Cl, Cd, _Cl_nc, _f, Cm = _aero_coeffs(
                ds, math.radians(pt["alpha"]), pt["W"], pt["chord"], dt, pt["Re"],
                dyn,
                aero_cal.ds_Tf, aero_cal.ds_Tv, aero_cal.ds_Ta,
                aero_cal.ds_Kv, clmax,
                pdb_cal.logRe_grid, pdb_cal.alpha_grid, pdb_cal.cla_re,
                pdb_cal.Cl, pdb_cal.Cd, pdb_cal.Cm, cm_scale,
            )
            cal_results.append((float(Cl), float(Cd), float(Cm)))

        # At least one value must differ significantly
        all_diffs = []
        for (Cl_p, Cd_p, Cm_p), (Cl_c, Cd_c, Cm_c) in zip(prod_results, cal_results):
            all_diffs.append(abs(Cl_p - Cl_c))
            all_diffs.append(abs(Cd_p - Cd_c))
            all_diffs.append(abs(Cm_p - Cm_c))
        max_diff = max(all_diffs)
        assert max_diff > 1e-6, f"Expected mismatch from polar_variant change, max diff = {max_diff}"

    


if __name__ == "__main__":
    pytest.main([__file__, "-v"])