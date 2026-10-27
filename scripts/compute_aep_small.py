"""Compute AEP for the small-rotor Sharp CPPC design (R=0.60 m).

This is a standalone script that computes the AEP for the small-rotor
passive CPPC machine and saves results to aep_small.json.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
from scipy.integrate import trapezoid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.stamp import make_stamp
from sharp_vawt import create_sim_from_params

# Small-rotor passive CPPC design (sharp_cppc preset)
SMALL_BASE = {
    "R": 0.6,
    "H": 0.4,
    "N": 3,
    "c": 0.14,
    "ar": 0.5,
    "sp": 0.25,
    "mb": 0.01,
    "mc": 0.002,
    "xbcg": 0.2,
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
    "free": True,
    "T_max": 25.0,
    "stride": 5,
    "w0_frac": 0.9,
    "k_load": 0.0015,
    "tsr": 2.5,
}

# Wind resource parameters (Weibull distribution)
U_MEAN = 6.0
K_WEIBULL = 2.0
CUT_IN = 3.0
CUT_OUT = 25.0
RHO = 1.225
ETA_DRIVETRAIN = 0.90
HOURS_YEAR = 8760.0
U_RATED = 12.0

def weibull_pdf(U, U_mean, k):
    lam = U_mean / math.gamma(1.0 + 1.0 / k)
    return (k / lam) * (U / lam) ** (k - 1.0) * np.exp(-(U / lam) ** k)

def power_from_cp(cp, U, R, H):
    A = 2.0 * R * H
    return 0.5 * RHO * A * U**3 * cp

def run_free(params, U):
    try:
        sim = create_sim_from_params({**params, 'U': float(U)})
        result = sim.run()
        if result.get('steady', True) and result['cp'] > 0:
            return {'cp': float(result['cp']), 'tsr_eq': float(result['tsr_eq']),
                    'steady': True, 'rpm': float(result['rpm'])}
    except (RuntimeError, ValueError, KeyError) as e:
        print(f"  Error at U={U} m/s: {e}")
    return None

def compute_cp_curve(base, tsrs, label, n_phase=3):
    """Phase-averaged fixed-rpm Cp(TSR) with full diagnostics.

    Returns signed Cp values for all phases, including negative and non-steady results.
    Missing or failed runs are marked explicitly rather than substituted with zero.
    """
    print(f"  Cp(TSR) for {label} (mean of {n_phase} initial phases):")
    cps = []          # phase-mean Cp (signed, NaN if no valid phases)
    los = []          # min Cp across phases (signed)
    his = []          # max Cp across phases (signed)
    phase_data = []   # detailed per-phase data for each TSR

    for tsr in tsrs:
        phase_results = []
        for psi0 in [0.0, 120.0, 240.0]:
            params = {**base, 'tsr': float(tsr), 'psi0_deg': float(psi0), 'free': False}
            phase_info = {
                'tsr': float(tsr),
                'psi0_deg': float(psi0),
                'cp': None,
                'tsr_eq': None,
                'steady': None,
                'rpm': None,
                'success': False,
                'error': None,
            }
            try:
                sim = create_sim_from_params(params)
                res = sim.run()
                cp_val = float(res['cp'])
                steady = res.get('steady', True)
                tsr_eq = float(res['tsr_eq'])
                rpm = float(res['rpm'])
                phase_info.update({
                    'cp': cp_val,
                    'tsr_eq': tsr_eq,
                    'steady': bool(steady),
                    'rpm': float(rpm),
                    'success': True,
                })
                # We record ALL Cp values, including negative and non-steady
                # The caller decides how to handle them
            except (RuntimeError, ValueError, KeyError) as e:
                phase_info['error'] = str(e)
            phase_results.append(phase_info)

        # Collect all Cp values (including negative and non-steady)
        valid_cps = [p['cp'] for p in phase_results if p['success'] and p['cp'] is not None]
        steady_cps = [p['cp'] for p in phase_results if p['success'] and p['steady']]
        positive_steady_cps = [p['cp'] for p in phase_results if p['success'] and p['steady'] and p['cp'] > 0]

        # Compute statistics
        if valid_cps:
            cps.append(float(np.mean(valid_cps)))
            los.append(float(np.min(valid_cps)))
            his.append(float(np.max(valid_cps)))
            mean_cp = float(np.mean(valid_cps))
            spread = float(np.max(valid_cps) - np.min(valid_cps))
            n_valid = len(valid_cps)
            n_steady = len(steady_cps)
            n_pos = len(positive_steady_cps)
            print(f"    TSR = {tsr:.2f}: Cp = {mean_cp:.4f} (spread {spread:.4f}) "
                  f"[{n_valid} valid, {n_steady} steady, {n_pos} pos steady]")
        else:
            # No valid results at all
            cps.append(float('nan'))
            los.append(float('nan'))
            his.append(float('nan'))
            print(f"    TSR = {tsr:.2f}: NO VALID RESULTS")

        phase_data.append(phase_results)

    # Also return detailed phase data for transparency
    return np.array(cps), np.array(los), np.array(his), phase_data

def integrate_aep(U_grid, cp_curve, U_mean, k_weibull,
                  cut_in, cut_out, p_rated, R, H):
    A = 2.0 * R * H
    cp_clipped = np.clip(cp_curve, 0.0, 0.593)
    P_mech = 0.5 * RHO * A * U_grid**3 * cp_clipped
    P = P_mech * ETA_DRIVETRAIN
    if p_rated is not None:
        P = np.minimum(P, p_rated)
    pdf = (k_weibull / (U_mean / math.gamma(1.0 + 1.0 / k_weibull))) * \
          (U_grid / (U_mean / math.gamma(1.0 + 1.0 / k_weibull))) ** (k_weibull - 1.0) * \
          np.exp(-(U_grid / (U_mean / math.gamma(1.0 + 1.0 / k_weibull))) ** k_weibull)
    aep = float(trapezoid(P * pdf, U_grid) * HOURS_YEAR / 1000.0)
    cf = aep * 1000.0 / (p_rated * HOURS_YEAR) if p_rated else float('nan')
    return {"aep": aep, "cf": cf, "U": U_grid, "cp": cp_curve, "P": P, "pdf": pdf}

def main():
    print("=" * 70)
    print("Small-Rotor AEP — Passive CPPC (R = 0.60 m)")
    print("=" * 70)

    R = SMALL_BASE['R']
    H = SMALL_BASE['H']
    area = 2.0 * R * H

    # Fixed-rpm Cp(TSR)
    tsrs = np.linspace(1.0, 4.5, 15)
    cps_tsr, cps_lo, cps_hi, cps_phase_data = compute_cp_curve(SMALL_BASE, tsrs, "small-rotor passive CPPC")

    # Free-running reference speeds (branch tracing)
    U_grid = np.linspace(3.0, 25.0, 200)
    free_results = []
    print("\n  Free-running equilibria (branch-traced):")
    for U in np.linspace(3.0, 15.0, 13):
        res = run_free(SMALL_BASE, U)
        if res:
            free_results.append({'U': float(U), **res})
            print(f"    U = {U:5.1f}   Cp = {res['cp']:+.4f}   TSR = {res['tsr_eq']:.2f}")

    # Rated power from Cp at U_RATED
    if free_results:
        cp_at_rated = float(np.interp(U_RATED, [f['U'] for f in free_results],
                                      [f['cp'] for f in free_results]))
    else:
        cp_at_rated = float(np.interp(U_RATED, tsrs, cps_tsr))
    p_rated = 0.5 * RHO * area * U_RATED**3 * cp_at_rated * ETA_DRIVETRAIN
    print(f"\n  Rated power: {p_rated/1000:.2f} kW (Cp@12m/s = {cp_at_rated:.4f})")

    # AEP integration
    if free_results:
        U_free = np.array([f['U'] for f in free_results])
        cp_free = np.array([f['cp'] for f in free_results])
        cp_passive = np.interp(U_grid, U_free, cp_free)
    else:
        cp_passive = np.zeros_like(U_grid)

    # Fixed-rpm Cp
    idx_best = int(np.argmax(cps_tsr))
    tsr_design = float(tsrs[idx_best])
    tsr_fixed = np.clip(tsr_design * U_MEAN / U_grid, tsrs[0], tsrs[-1])
    cp_fixed = np.interp(tsr_fixed, tsrs, cps_tsr)

    res_passive = integrate_aep(U_grid, cp_passive, U_MEAN, K_WEIBULL,
                                CUT_IN, CUT_OUT, p_rated, R, H)
    res_fixed = integrate_aep(U_grid, cp_fixed, U_MEAN, K_WEIBULL,
                              CUT_IN, CUT_OUT, p_rated, R, H)

    print()
    print("=" * 70)
    print("RESULTS — SMALL ROTOR (R = 0.60 m)")
    print("=" * 70)
    print(f"  Passive CPPC, k_load (var speed): {res_passive['aep']/1000:.2f} MWh/yr (CF: {res_passive['cf']*100:.1f}%)")
    print(f"  Passive CPPC, fixed rpm:          {res_fixed['aep']/1000:.2f} MWh/yr (CF: {res_fixed['cf']*100:.1f}%)")
    print(f"  Rated power: {p_rated/1000:.2f} kW")
    print("=" * 70)

    # JSON output
    summary = {
        "geometry": {"R": R, "c": SMALL_BASE['c'], "H": H, "N": SMALL_BASE['N'],
                     "sigma": SMALL_BASE['N']*SMALL_BASE['c']/(2*math.pi*SMALL_BASE['R']),
                     "AR": H/SMALL_BASE['c']},
        "wind": {"mean_U": U_MEAN, "k_weibull": K_WEIBULL,
                 "cut_in": CUT_IN, "cut_out": CUT_OUT,
                 "rated_wind_speed": U_RATED,
                 "cp_at_rated": cp_at_rated,
                 "p_rated_W": p_rated},
        "results": {
            "passive_k_load": {"aep_MWh": res_passive['aep']/1000,
                               "cf": res_passive['cf'],
                               "cp_tsr": [float(v) for v in cps_tsr],
                               "cp_tsr_lo": [float(v) for v in cps_lo],
                               "cp_tsr_hi": [float(v) for v in cps_hi],
                               "tsr": [float(v) for v in tsrs],
                               "free_results": free_results,
                               "cp_phase_data": cps_phase_data},
            "passive_fixed_rpm": {"aep_MWh": res_fixed['aep']/1000,
                                  "cf": res_fixed['cf']},
        },
        "gains_percent": {
            "passive_vs_fixed_rpm": (res_passive['aep'] / max(res_fixed['aep'], 1e-9) - 1.0) * 100,
        },
    }

    stamp = make_stamp(
        "scripts/compute_aep_small.py",
        script_version="1.0.0",
        n=len(tsrs) + len(free_results),
        seed=0,
        extra_files=["vawt_presets.py"],
        extra_data={"U_MEAN": U_MEAN, "K_WEIBULL": K_WEIBULL, "CUT_IN": CUT_IN, "CUT_OUT": CUT_OUT, "U_RATED": U_RATED},
    )

    out_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aep_small.json")
    with open(out_json, "w") as fh:
        json.dump({"stamp": stamp, **summary}, fh, indent=2)
    print(f"\nSaved results to {out_json}")

    return 0

if __name__ == "__main__":
    sys.exit(main())