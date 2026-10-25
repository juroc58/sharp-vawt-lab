"""
Annual Energy Production (AEP) for the SCALE-UP Sharp cycloturbine.

Uses the optimized scale-up geometry from optimize_scaleup.py:
- R = 2.72 m, H = 4.06 m (AR ≈ 10.5)
- Higher Reynolds numbers (Re ~ 5×10⁵ at design point)
- Should show much better Cp due to Reynolds effects and high AR

Compares:
1. Passive CPPC, free-running
2. Passive CPPC, fixed-rpm (shows penalty of not tracking wind)
3. Fair rigid baseline (from compute_aep_rigid_fair.py)

Integrates power curves against Weibull wind distribution.  Produces scripts/aep_scaleup.json.  Plotting is done by
scripts/plot_aep.py from the JSON output.
"""

from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from scripts.compute_aep import (
    CUT_IN,
    CUT_OUT,
    K_WEIBULL,
    U_MEAN,
    U_RATED,
    integrate_aep,
    load_fair_rigid_reference,
    rated_power_from_cp,
)
from scripts.stamp import make_stamp
from sharp_vawt import create_sim_from_params
from vawt_presets import PRESETS

# ============================================================================
# SCALE-UP CONFIGURATION (from optimization_scaleup.json)
# ============================================================================
SCALEUP_BASE = dict(PRESETS["scaleup"])


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def compute_cp_curve(base, tsrs, label, n_phase=3):
    """Phase-averaged fixed-rpm Cp(TSR); see compute_aep.compute_cp_curve."""
    print(f"  Cp(TSR) for {label} (mean of {n_phase} initial phases):")
    cps, los, his = [], [], []
    for tsr in tsrs:
        vals = []
        for k in range(n_phase):
            psi = 360.0 * k / n_phase
            r = create_sim_from_params({
                **base, 'free': False, 'tsr': float(tsr),
                'psi0_deg': psi,
            }).run()
            vals.append(float(r['cp']))
        cps.append(float(np.mean(vals)))
        los.append(float(np.min(vals)))
        his.append(float(np.max(vals)))
        print(f"    TSR = {tsr:5.2f}   Cp = {np.mean(vals):+.4f} "
              f"[{min(vals):+.4f}, {max(vals):+.4f}]")
    return np.array(cps), np.array(los), np.array(his)


def free_run(base, U, w0_frac=None, psi0_deg=None):
    """Run free-running simulation with optional branch-tracing initial conditions."""
    params = {**base, 'free': True, 'U': U}
    if w0_frac is not None:
        params['w0_frac'] = w0_frac
    if psi0_deg is not None:
        params['psi0_deg'] = psi0_deg
    try:
        r = create_sim_from_params(params).run()
    except Exception:
        return None, None
    cp = float(r['cp'])
    if not r.get('steady', True) or cp <= 0.0 or not np.isfinite(cp):
        return None, None
    result = {"U": float(U), "cp": cp,
                  "tsr_eq": float(r['tsr_eq']),
                  "rpm": float(r['rpm']),
                  "aoa_max": float(r['aoa_max'])}
    # Final state for branch tracing
    w_final = r['tsr_eq'] * U / base['R'] if base['R'] > 0 else 0
    pitch_final = 0.5 * (r['pitch_min'] + r['pitch_max']) if r.get('pitch_min') is not None else 0.0
    final_state = {"w0_frac": w_final * base['R'] / (U + 1.0) if (U + 1.0) > 0 else base.get('w0_frac', 0.9),
                       "psi0_deg": pitch_final}
    return result, final_state


def main():
    print("=" * 70)
    print("Annual Energy Production - SCALE-UP Sharp Cycloturbine (R=2.72 m)")
    print("=" * 70)
    print(f"Geometry: R={SCALEUP_BASE['R']:.2f}m, H={SCALEUP_BASE['H']:.2f}m, "
          f"c={SCALEUP_BASE['c']:.3f}m, AR={SCALEUP_BASE['H']/SCALEUP_BASE['c']:.1f}")
    print(f"Blades: {SCALEUP_BASE['N']}, Chord: {SCALEUP_BASE['c']}m")
    print(f"Design TSR: {SCALEUP_BASE['tsr']}, k_load: {SCALEUP_BASE['k_load']:.3f}")
    print(f"Reynolds at tip (TSR=2.5, U=8): ~{2.5*8*SCALEUP_BASE['c']/1.5e-5:.0f}")
    print(f"Wind: Weibull k={K_WEIBULL}, mean U={U_MEAN} m/s, {CUT_IN}-{CUT_OUT} m/s")
    print(f"Rated wind speed: {U_RATED} m/s (rating from the Cp curve)")
    print()

    # --- fixed-rpm Cp(TSR) ---
    tsrs = np.linspace(1.0, 4.0, 13)
    cps_tsr, _cps_phase_lo, _cps_phase_hi = compute_cp_curve(
        SCALEUP_BASE, tsrs, "scale-up CPPC")

    # --- free-running with branch tracing ---
    print()
    U_ref = np.arange(CUT_IN, CUT_OUT + 1.0, 1.0).tolist()
    print("  Free-running passive CPPC (branch tracing):")
    free_passive = []
    w0_frac = SCALEUP_BASE.get('w0_frac', 0.9)
    psi0_deg = SCALEUP_BASE.get('psi0_deg', 0.0)
    for U in U_ref:
        f, final_state = free_run(SCALEUP_BASE, U, w0_frac=w0_frac, psi0_deg=psi0_deg)
        if f:
            free_passive.append(f)
            if final_state:
                w0_frac = final_state['w0_frac']
                psi0_deg = final_state['psi0_deg']
            print(f"    U = {U:4.1f}   Cp = {f['cp']:+.4f}   TSR = {f['tsr_eq']:5.2f}   "
                  f"α_max = {f['aoa_max']:5.1f}   (w0_frac={w0_frac:.3f}, psi0={psi0_deg:+.1f}°)")
        else:
            w0_frac = SCALEUP_BASE.get('w0_frac', 0.9)
            psi0_deg = SCALEUP_BASE.get('psi0_deg', 0.0)
            print(f"    U = {U:4.1f}   (no equilibrium)")

    # --- fixed-seed branches: high and low initial speed -----------------
    # These are not "the" operating curve; they bracket the bistable region.
    # The branch-traced run above follows the high branch by continuation.
    def fixed_seed_branch(w0_seed, label):
        rows = []
        print(f"\n  {label} (fixed initial w0_frac={w0_seed:.2f}, psi0=0):")
        for U in U_ref:
            f, _ = free_run(SCALEUP_BASE, U, w0_frac=w0_seed, psi0_deg=0.0)
            if f:
                rows.append(f)
                print(f"    U = {U:4.1f}   Cp = {f['cp']:+.4f}   "
                      f"TSR = {f['tsr_eq']:5.2f}")
            else:
                print(f"    U = {U:4.1f}   (no equilibrium)")
        return rows

    free_high = fixed_seed_branch(1.20, "High-speed seed")
    free_low = fixed_seed_branch(0.20, "Low-speed seed")

    # --- build power curves ---
    U_grid = np.linspace(CUT_IN, CUT_OUT, 200)
    R, H = SCALEUP_BASE['R'], SCALEUP_BASE['H']

    # Fixed-rpm: omega held so TSR = peak-TSR at U_mean
    idx_best = int(np.argmax(cps_tsr))
    tsr_design = float(tsrs[idx_best])
    tsr_fixed = np.clip(tsr_design * U_MEAN / U_grid, tsrs[0], tsrs[-1])
    cp_fixed = np.interp(tsr_fixed, tsrs, cps_tsr)

    def curve_from_points(points, label):
        if len(points) < 2:
            raise RuntimeError(f"{label}: need >= 2 free-running points, "
                               f"got {len(points)}")
        U_s = np.array([f['U'] for f in points])
        cp_s = np.array([f['cp'] for f in points])
        return np.interp(U_grid, U_s, cp_s)

    # Passive free-running: interpolate Cp(U) from branch-traced points
    cp_passive = curve_from_points(free_passive, "branch-traced")
    print(f"\n  Cp curve built from {len(free_passive)} branch-traced points")
    cp_high = curve_from_points(free_high, "high-seed")
    cp_low = curve_from_points(free_low, "low-seed")

    # --- rated power for this design, from the branch-traced Cp curve ---
    cp_at_rated = float(np.interp(U_RATED, U_grid, cp_passive))
    p_rated = rated_power_from_cp(R, H, cp_at_rated)
    print(f"\n  Rated power from Cp(U={U_RATED:.0f} m/s) = {cp_at_rated:.4f}: "
          f"{p_rated/1000:.2f} kW")

    # --- integrate AEP: branch-traced, fixed high seed, fixed low seed ---
    res_passive = integrate_aep(U_grid, cp_passive, U_MEAN, K_WEIBULL,
                                CUT_IN, CUT_OUT, p_rated, R, H)
    res_fixed = integrate_aep(U_grid, cp_fixed, U_MEAN, K_WEIBULL,
                              CUT_IN, CUT_OUT, p_rated, R, H)
    res_high = integrate_aep(U_grid, cp_high, U_MEAN, K_WEIBULL,
                             CUT_IN, CUT_OUT, p_rated, R, H)
    res_low = integrate_aep(U_grid, cp_low, U_MEAN, K_WEIBULL,
                            CUT_IN, CUT_OUT, p_rated, R, H)
    aep_min = min(res_high['aep'], res_low['aep'], res_passive['aep'])
    aep_max = max(res_high['aep'], res_low['aep'], res_passive['aep'])

    # --- fair rigid reference ---
    rigid_ref = load_fair_rigid_reference()

    # --- report ---
    print()
    print("=" * 70)
    print("RESULTS — SCALE-UP (R = 2.72 m)")
    print("=" * 70)
    sigma = SCALEUP_BASE['N']*SCALEUP_BASE['c']/(2*math.pi*SCALEUP_BASE['R'])
    print(f"  Geometry: R = {R:.2f} m, c = {SCALEUP_BASE['c']:.3f} m, σ = {sigma:.3f}, AR = {H/SCALEUP_BASE['c']:.1f}")
    print(f"  Wind: Weibull k = {K_WEIBULL}, mean U = {U_MEAN} m/s")
    print()
    print(f"  Peak Cp (passive, fixed-rpm) = {cps_tsr.max():.4f} at TSR = {tsrs[cps_tsr.argmax()]:.2f}")
    print()
    print(f"  {'Strategy':<45} {'AEP [MWh/yr]':>14} {'Cap factor':>12}")
    print("  " + "-" * 73)
    print(f"  {'Passive CPPC, k_load (var speed)':<45} {res_passive['aep']/1000:>14.2f} {res_passive['cf']*100:>11.2f}%")
    print(f"  {'Passive CPPC, fixed rpm':<45} {res_fixed['aep']/1000:>14.2f} {res_fixed['cf']*100:>11.2f}%")
    print(f"  {'High-speed seed (w0=1.20)':<45} {res_high['aep']/1000:>14.2f} {res_high['cf']*100:>11.2f}%")
    print(f"  {'Low-speed seed (w0=0.20)':<45} {res_low['aep']/1000:>14.2f} {res_low['cf']*100:>11.2f}%")
    print(f"  {'Branch-traced (continuation)':<45} {res_passive['aep']/1000:>14.2f} {res_passive['cf']*100:>11.2f}%")
    print(f"  Branch AEP range: {aep_min/1000:.2f} - {aep_max/1000:.2f} MWh/yr")
    
    if rigid_ref and rigid_ref.get('aep_kWh') is not None:
        aep_rigid = rigid_ref['aep_kWh']
        cf_rigid = rigid_ref['cf']
        print(f"  {'Rigid blade, best fixed pitch':<45} {aep_rigid/1000:>14.2f} {cf_rigid*100:>11.2f}%")
        gain_vs_rigid = (res_passive['aep'] / max(aep_rigid, 1e-9) - 1.0) * 100
        print(f"  {'Passive CPPC vs rigid baseline':<45} {gain_vs_rigid:+.1f}%")
    else:
        print(f"  {'Rigid blade, best fixed pitch':<45} {'(run compute_aep_rigid_fair.py)':>14}")
    print()
    gain_fixed = (res_passive['aep'] / max(res_fixed['aep'], 1e-9) - 1.0) * 100
    print(f"  Passive CPPC vs fixed-rpm, same physics : {gain_fixed:+.1f}%")

    # --- JSON dump with stamp ---
    summary = {
        "geometry": {"R": R, "c": SCALEUP_BASE['c'], "H": H, "N": SCALEUP_BASE['N'],
                     "sigma": sigma, "AR": H/SCALEUP_BASE['c']},
        "wind": {"mean_U": U_MEAN, "k_weibull": K_WEIBULL,
                 "cut_in": CUT_IN, "cut_out": CUT_OUT,
                 "rated_wind_speed": U_RATED,
                 "cp_at_rated": cp_at_rated,
                 "p_rated_W": p_rated},
        "results": {
            "passive_k_load": {"aep_MWh": res_passive['aep']/1000,
                               "cf": res_passive['cf'],
                               "cp_tsr": [float(v) for v in cps_tsr],
                               "tsr": [float(v) for v in tsrs],
                               "free_results": free_passive},
            "passive_fixed_rpm": {"aep_MWh": res_fixed['aep']/1000,
                                   "cf": res_fixed['cf']},
        },
        "branches": {
            "high_seed": {"initial_w0_frac": 1.20, "initial_psi0_deg": 0.0,
                          "aep_MWh": res_high['aep']/1000,
                          "cf": res_high['cf'],
                          "free_results": free_high},
            "low_seed": {"initial_w0_frac": 0.20, "initial_psi0_deg": 0.0,
                         "aep_MWh": res_low['aep']/1000,
                         "cf": res_low['cf'],
                         "free_results": free_low},
            "branch_traced": {"initial_w0_frac": 0.9,
                              "initial_psi0_deg": 0.0,
                              "aep_MWh": res_passive['aep']/1000,
                              "cf": res_passive['cf'],
                              "free_results": free_passive},
            "aep_range_MWh": [aep_min/1000, aep_max/1000],
        },
        "gains_percent": {
            "passive_vs_fixed_rpm": gain_fixed,
        },
    }
    if rigid_ref and rigid_ref.get('aep_kWh') is not None:
        summary["rigid_fair_ref"] = {
            "aep_MWh": rigid_ref['aep_kWh']/1000,
            "cf": rigid_ref['cf']
        }
        summary["gains_percent"]["passive_vs_rigid_fair"] = gain_vs_rigid

    stamp = make_stamp(
        "scripts/compute_aep_scaleup.py",
        script_version="2.0.0",
        n=len(tsrs) + len(free_passive) + len(free_high) + len(free_low),
        seed=0,
        extra_files=["vawt_presets.py", "scripts/compute_aep.py"],
        extra_data={"U_MEAN": U_MEAN, "K_WEIBULL": K_WEIBULL, "CUT_IN": CUT_IN, "CUT_OUT": CUT_OUT, "U_RATED": U_RATED},
    )

    json_path = os.path.join(_HERE, "aep_scaleup.json")
    with open(json_path, "w") as fh:
        json.dump({"stamp": stamp, **summary}, fh, indent=2)
    print(f"JSON saved to {json_path}")

    print("\n" + "=" * 70)
    print(f"Scale-up AEP:  {res_passive['aep']/1000:.1f} MWh/yr (CF: {res_passive['cf']*100:.1f}%)")
    print(f"Fixed-rpm AEP: {res_fixed['aep']/1000:.1f} MWh/yr (CF: {res_fixed['cf']*100:.1f}%)")
    if rigid_ref and rigid_ref.get('aep_kWh') is not None:
        print(f"Rigid AEP:     {rigid_ref['aep_kWh']/1000:.1f} MWh/yr")
        print(f"Gain vs rigid: {gain_vs_rigid:.1f}%")


if __name__ == "__main__":
    sys.exit(main())