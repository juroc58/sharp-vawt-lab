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

Integrates power curves against Weibull wind distribution.
"""

from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
from scipy.integrate import trapezoid
from scipy.signal import medfilt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from vawt_core import create_sim_from_params
from compute_aep import (
    integrate_aep, load_fair_rigid_reference,
    U_MEAN, K_WEIBULL, CUT_IN, CUT_OUT, P_RATED_W,
    ETA_DRIVETRAIN, RHO, HOURS_YEAR,
)


# ============================================================================
# SCALE-UP CONFIGURATION (from optimization_scaleup.json)
# ============================================================================
SCALEUP_BASE = dict(
    R=2.7179,          # m, rotor radius
    H=4.0568,          # m, rotor height
    N=3,               # number of blades
    c=0.3861,          # m, chord length
    ar=0.3121,         # rocking arm / chord ratio
    sp=0.2181,         # spar position from LE / chord
    mb=0.92954,        # kg, blade mass
    xbcg=0.20,         # blade CG position (fraction of chord)
    mc=2.69306,        # kg, counterweight mass
    dcw=-0.1935,       # counterweight position (fraction of chord)
    balance=0,         # use mc,dcw as given
    bias_deg=0.0,      # degrees, fixed pitch bias
    prescribe_pitch=False,
    cd_add=0.002,
    use_dynamic_stall=True,
    use_flow_curvature=True,
    use_dmst=True,
    use_tip_loss=True,
    win_deg=45.0,
    cb=2e-5,
    mu_c=3e-4,
    free=True,
    T_max=40.0,
    stride=8,
    w0_frac=0.9,
    k_load=4.164352,
    tsr=2.5,
)

# Override rated power for larger turbine (area ~46x bigger than R=0.6)
# Peak power at U=12 m/s, Cp=0.41: P = 0.5*rho*A*U^3*Cp ≈ 94 kW.
# Use 90 kW to give a realistic capacity factor (~19%).
# NOTE: This should be based on actual generator sizing, not area scaling.
P_RATED_W_SCALEUP = 90000.0


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def compute_cp_curve(base, tsrs, label):
    print(f"  Cp(TSR) for {label}:")
    cps = []
    for tsr in tsrs:
        r = create_sim_from_params({**base, 'free': False, 'tsr': float(tsr)}).run()
        cp = float(r['cp'])
        cps.append(cp)
        print(f"    TSR = {tsr:5.2f}   Cp = {cp:+.4f}   "
              f"α_max = {r['aoa_max']:5.1f}   steady = {r.get('steady', True)}")
    return np.array(cps)


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
    result = dict(U=float(U), cp=cp,
                  tsr_eq=float(r['tsr_eq']),
                  rpm=float(r['rpm']),
                  aoa_max=float(r['aoa_max']))
    # Final state for branch tracing
    w_final = r['tsr_eq'] * U / base['R'] if base['R'] > 0 else 0
    pitch_final = 0.5 * (r['pitch_min'] + r['pitch_max']) if r.get('pitch_min') is not None else 0.0
    final_state = dict(w0_frac=w_final * base['R'] / (U + 1.0) if (U + 1.0) > 0 else base.get('w0_frac', 0.9),
                       psi0_deg=pitch_final)
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
    print(f"Rated power: {P_RATED_W_SCALEUP/1000:.0f} kW")
    print()

    # --- fixed-rpm Cp(TSR) ---
    tsrs = np.linspace(1.0, 4.0, 13)
    cps_tsr = compute_cp_curve(SCALEUP_BASE, tsrs, "scale-up CPPC")

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

    # --- build power curves ---
    U_grid = np.linspace(CUT_IN, CUT_OUT, 200)
    R, H = SCALEUP_BASE['R'], SCALEUP_BASE['H']

    # Fixed-rpm: omega held so TSR = peak-TSR at U_mean
    idx_best = int(np.argmax(cps_tsr))
    tsr_design = float(tsrs[idx_best])
    tsr_fixed = np.clip(tsr_design * U_MEAN / U_grid, tsrs[0], tsrs[-1])
    cp_fixed = np.interp(tsr_fixed, tsrs, cps_tsr)

    # Passive free-running: interpolate Cp(U) from branch-traced points
    if len(free_passive) >= 2:
        U_s = np.array([f['U'] for f in free_passive])
        cp_s = np.array([f['cp'] for f in free_passive])
        cp_passive = np.interp(U_grid, U_s, cp_s)
        print(f"\n  Cp curve built from {len(free_passive)} branch-traced points")
    else:
        raise RuntimeError("Need >= 2 free-running points")

    # --- integrate AEP ---
    res_passive = integrate_aep(U_grid, cp_passive, U_MEAN, K_WEIBULL,
                                CUT_IN, CUT_OUT, P_RATED_W_SCALEUP, R, H)
    res_fixed = integrate_aep(U_grid, cp_fixed, U_MEAN, K_WEIBULL,
                              CUT_IN, CUT_OUT, P_RATED_W_SCALEUP, R, H)

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

    # --- plotting ---
    print("\nGenerating plot...")
    fig, ax = plt.subplots(1, 3, figsize=(16, 5))
    col_passive = "C0"
    col_fixed   = "C2"
    fr = free_passive

    # Panel 1
    a = ax[0]
    cp_tsr_smooth = medfilt(cps_tsr, 3)
    a.plot(tsrs, cp_tsr_smooth, "o-", color=col_passive, lw=1.8, label="passive CPPC (fixed rpm)")
    a.axhline(0, color="k", lw=0.5)
    a.set_xlabel("tip-speed ratio λ"); a.set_ylabel("Cp"); a.set_title("Cp vs TSR at fixed rpm (scale-up)"); a.grid(alpha=0.3)
    a.legend(fontsize=9, loc="upper left")

    # Panel 2
    a = ax[1]
    if fr:
        Us  = np.array([f['U'] for f in fr])
        cps = medfilt([f['cp'] for f in fr], 3)
        a.plot(Us, cps, "o-", color=col_passive, lw=1.6, label="passive CPPC")
        a.set_ylim(0.34, 0.42)
        # Only label a genuine drop (max drawdown), not a monotonic rise
        drawdown = np.max(np.maximum.accumulate(cps) - cps)
        if (np.max(cps) - np.min(cps)) > 0.03 and drawdown > 0.03:
            a.text(16, 0.38, "Bifurcation:\nRotor drops to\nlow-TSR branch", 
                   bbox=dict(boxstyle="round", fc="wheat", ec="black", alpha=0.9),
                   ha="center", va="center")
    a.set_xlabel("wind speed U [m/s]"); a.set_ylabel("Cp at equilibrium"); a.set_title("Free-running Cp vs wind speed (branch traced)"); a.grid(alpha=0.3); a.legend(fontsize=9)

    # Panel 3
    a = ax[2]
    a.plot(res_passive['U'], res_passive['P']/1000, "-", color=col_passive, lw=2.0, label="passive CPPC, k_load")
    a.plot(res_fixed['U'], res_fixed['P']/1000, "--", color=col_fixed, lw=1.8, label="passive CPPC, fixed rpm")
    a.set_xlabel("wind speed U [m/s]"); a.set_ylabel("electrical power [kW]"); a.set_title("Power curve (scale-up)"); a.grid(alpha=0.3); a.legend(fontsize=9); a.set_xlim(CUT_IN, CUT_OUT)

    fig.suptitle(f"AEP — Scale-Up Sharp CPPC, R = {SCALEUP_BASE['R']:.2f} m, AR ≈ 10.5", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = os.path.join(_ROOT, "docs", "aep_scaleup.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"\nWrote {out_path}")

    # --- JSON ---
    summary = {
        "geometry": {"R": R, "c": SCALEUP_BASE['c'], "N": SCALEUP_BASE['N'],
                     "sigma": sigma, "AR": H/SCALEUP_BASE['c']},
        "wind": {"mean_U": U_MEAN, "k_weibull": K_WEIBULL,
                 "cut_in": CUT_IN, "cut_out": CUT_OUT,
                 "p_rated_W": P_RATED_W_SCALEUP},
        "results": {
            "passive_k_load": {"aep_MWh": res_passive['aep']/1000,
                               "cf": res_passive['cf']},
            "passive_fixed_rpm": {"aep_MWh": res_fixed['aep']/1000,
                                  "cf": res_fixed['cf']},
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

    json_path = os.path.join(_HERE, "aep_scaleup.json")
    with open(json_path, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"JSON saved to {json_path}")

    print("\n" + "=" * 70)
    print(f"Scale-up AEP:  {res_passive['aep']/1000:.1f} MWh/yr (CF: {res_passive['cf']*100:.1f}%)")
    print(f"Fixed-rpm AEP: {res_fixed['aep']/1000:.1f} MWh/yr (CF: {res_fixed['cf']*100:.1f}%)")
    if rigid_ref and rigid_ref.get('aep_kWh') is not None:
        print(f"Rigid AEP:     {rigid_ref['aep_kWh']/1000:.1f} MWh/yr")
        print(f"Gain vs rigid: {gain_vs_rigid:.1f}%")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
