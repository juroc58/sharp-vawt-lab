"""
Annual Energy Production (AEP) for the Sharp cycloturbine.

Compares two operating strategies at the same rotor geometry:

  1. Passive CPPC, free-running    — Sharp's centrifugal-pendulum pitch
                                     mechanism, rotor speed adjusts to
                                     match the wind.
  2. Passive CPPC, fixed-rpm       — synchronous generator holds omega
                                     constant. Shows the penalty of not
                                     tracking the wind.

A third reference — a rigid blade at its own best pitch and load — is
computed by scripts/compute_aep_rigid_fair.py, which sweeps (psi0, k_load)
and picks the optimum at U = 6 m/s. That is the fair baseline.

This script reads the fair rigid result from scripts/aep_rigid_fair.json
(if present) and echoes it into the JSON output under 'rigid_fair_ref'
so the AEP record is self-contained. If the file is missing, the run
still succeeds; the rigid row is reported as '(run compute_aep_rigid_fair.py)'.

Tip-loss correction is ON (bounded finite-span, max 15% lift reduction),
matching the convention used in the README headline results.

Integrates each power curve against a Weibull wind distribution to give
kWh/year.  Produces docs/aep.png.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
from scipy.integrate import trapezoid
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from vawt_core import create_sim_from_params


# ============================================================================
# CONFIGURATION
# ============================================================================
BASE = dict(
    R=0.60, H=0.40, N=3, c=0.14,
    ar=0.50, sp=0.25,
    mb=0.010, xbcg=0.20,
    mc=0.002, dcw=0.30,
    balance=0, bias_deg=0.0,
    prescribe_pitch=False,
    cd_add=0.002,
    use_dynamic_stall=True,
    use_flow_curvature=True,
    use_dmst=True,
    use_tip_loss=True,
    win_deg=45.0, cb=2e-5, mu_c=3e-4,
    free=False, T_max=25.0, stride=5,
    w0_frac=0.9, k_load=0.0025, tsr=2.0,
)

U_MEAN         = 6.0
K_WEIBULL      = 2.0
CUT_IN         = 3.0
CUT_OUT        = 25.0
RHO            = 1.225
HOURS_YEAR     = 8760.0
P_RATED_W      = 250.0
ETA_DRIVETRAIN = 0.90


# ============================================================================
# Helpers
# ============================================================================
def weibull_pdf(U, U_mean, k):
    lam = U_mean / math.gamma(1.0 + 1.0 / k)
    return (k / lam) * (U / lam) ** (k - 1.0) * np.exp(-(U / lam) ** k)


def load_fair_rigid_reference():
    """Read the fair rigid baseline from aep_rigid_fair.json (if present)."""
    path = os.path.join(_HERE, "aep_rigid_fair.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        data = json.load(fh)
    g = data.get("geometries", {}).get("sharp_inspired")
    if not g:
        return None
    return {
        "source":       "aep_rigid_fair.json",
        "geometry":     "sharp_inspired",
        "psi0_deg":     g["best_rigid"]["psi0_deg"],
        "k_load":       g["best_rigid"]["k_load"],
        "cp_design":    g["best_rigid"]["cp_design"],
        "aep_kWh":      g["best_rigid"]["aep_kWh"],
        "cf":           g["best_rigid"]["cf"],
        "gain_percent": g["gain_percent"],
    }


# ============================================================================
# Cp(TSR) at fixed rpm — passive
# ============================================================================
def compute_cp_curve(base, tsrs, label):
    print(f"  Cp(TSR) for {label}:")
    cps = []
    for tsr in tsrs:
        r = create_sim_from_params({**base, 'free': False, 'tsr': float(tsr)}).run()
        cp = float(r['cp'])
        cps.append(cp)
        print(f"    TSR = {tsr:5.2f}   Cp = {cp:+.4f}   "
              f"α_max = {r['aoa_max']:5.1f}   "
              f"steady = {r.get('steady', True)}")
    return np.array(cps)


# ============================================================================
# Free-running equilibrium at each U
# ============================================================================
def free_run(base, U, label):
    try:
        r = create_sim_from_params({**base, 'free': True, 'U': U}).run()
    except Exception:
        return None
    cp = float(r['cp'])
    if not r.get('steady', True) or cp <= 0.0 or not np.isfinite(cp):
        return None
    return dict(U=float(U), cp=cp,
                tsr_eq=float(r['tsr_eq']),
                rpm=float(r['rpm']),
                aoa_max=float(r['aoa_max']))


# ============================================================================
# AEP integration
# ============================================================================
def integrate_aep(U_grid, cp_curve, U_mean, k_weibull,
                  cut_in, cut_out, p_rated, R, H):
    A = 2.0 * R * H
    cp_clipped = np.clip(cp_curve, 0.0, 0.593)
    P_mech = 0.5 * RHO * A * U_grid ** 3 * cp_clipped
    P = P_mech * ETA_DRIVETRAIN
    if p_rated is not None:
        P = np.minimum(P, p_rated)
    pdf = weibull_pdf(U_grid, U_mean, k_weibull)
    aep = float(trapezoid(P * pdf, U_grid) * HOURS_YEAR / 1000.0)
    cf = aep * 1000.0 / (p_rated * HOURS_YEAR) if p_rated else float('nan')
    return dict(U=U_grid, cp=cp_curve, P=P, pdf=pdf, aep=aep, cf=cf)


# ============================================================================
# Plot
# ============================================================================
def make_plot(results, tsrs, out_path):
    fig, ax = plt.subplots(1, 3, figsize=(16, 5))

    col_passive = "C0"
    col_fixed   = "C2"

    # Panel 1: Cp vs TSR
    a = ax[0]
    a.plot(tsrs, results['passive']['cp_tsr'], "o-", color=col_passive,
           lw=1.8, label="passive CPPC")
    a.axhline(0, color="k", lw=0.5)
    a.set_xlabel("tip-speed ratio λ")
    a.set_ylabel("Cp")
    a.set_title("Cp vs TSR at fixed rpm")
    a.grid(alpha=0.3)
    a.legend(fontsize=9)

    # Panel 2: free-running Cp vs U
    a = ax[1]
    fr = results['passive']['free_results']
    if fr:
        Us  = np.array([f['U'] for f in fr])
        cps = np.array([f['cp'] for f in fr])
        a.plot(Us, cps, "o-", color=col_passive, lw=1.6, label="passive CPPC")
    a.set_xlabel("wind speed U [m/s]")
    a.set_ylabel("Cp at equilibrium")
    a.set_title("Free-running Cp vs wind speed")
    a.grid(alpha=0.3)
    a.legend(fontsize=9)

    # Panel 3: power curves
    a = ax[2]
    a.plot(results['passive']['U'], results['passive']['P'], "-",
           color=col_passive, lw=2.0, label="passive CPPC, k_load")
    a.plot(results['fixed']['U'], results['fixed']['P'], "--",
           color=col_fixed, lw=1.8, label="passive CPPC, fixed rpm")
    a.set_xlabel("wind speed U [m/s]")
    a.set_ylabel("electrical power [W]")
    a.set_title("Power curve")
    a.grid(alpha=0.3)
    a.legend(fontsize=9)
    a.set_xlim(CUT_IN, CUT_OUT)

    fig.suptitle("AEP — Sharp-inspired CPPC, R = 0.60 m",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=150)
    print(f"\nWrote {out_path}")


# ============================================================================
# Main
# ============================================================================
def main():
    print("=" * 74)
    print("Sharp cycloturbine — Annual Energy Production")
    print("=" * 74)
    print(f"  Geometry : R = {BASE['R']} m, c = {BASE['c']} m, N = {BASE['N']}, "
          f"σ = {BASE['N']*BASE['c']/(2*math.pi*BASE['R']):.3f}")
    print(f"  Wind     : Weibull k = {K_WEIBULL}, mean U = {U_MEAN} m/s")
    print(f"  Cut-in   : {CUT_IN} m/s   cut-out: {CUT_OUT} m/s")
    print(f"  Rated P  : {P_RATED_W} W")
    print(f"  Tip loss : ON (bounded finite-span)")
    print(f"  Drivetrain efficiency: {ETA_DRIVETRAIN*100:.0f} %")
    print()

    # --- fixed-rpm Cp(TSR) ---
    tsrs = np.linspace(1.0, 3.5, 11)
    cps_passive_tsr = compute_cp_curve(BASE, tsrs, "passive CPPC")

    # --- free-running reference speeds ---
    print()
    U_ref = [3.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]

    print("  Free-running passive CPPC:")
    free_passive = []
    for U in U_ref:
        f = free_run(BASE, U, "passive")
        if f:
            free_passive.append(f)
            print(f"    U = {U:4.1f}   Cp = {f['cp']:+.4f}   "
                  f"TSR = {f['tsr_eq']:5.2f}   α_max = {f['aoa_max']:5.1f}")

    # --- build power curves on a common U grid ---
    U_grid = np.linspace(CUT_IN, CUT_OUT, 200)
    R, H = BASE['R'], BASE['H']

    # fixed-rpm: omega held so that TSR = peak-TSR of passive at U_mean
    idx_best   = int(np.argmax(cps_passive_tsr))
    tsr_design = float(tsrs[idx_best])
    tsr_fixed  = np.clip(tsr_design * U_MEAN / U_grid, tsrs[0], tsrs[-1])
    cp_fixed   = np.interp(tsr_fixed, tsrs, cps_passive_tsr)

    # passive free-running: interpolate Cp(U) from reference runs
    if len(free_passive) >= 2:
        U_s  = np.array([f['U'] for f in free_passive])
        cp_s = np.array([f['cp'] for f in free_passive])
        cp_passive = np.interp(U_grid, U_s, cp_s)
    else:
        cp_passive = np.full_like(U_grid, float(cps_passive_tsr.max()))

    # --- integrate ---
    res_passive = integrate_aep(U_grid, cp_passive, U_MEAN, K_WEIBULL,
                                CUT_IN, CUT_OUT, P_RATED_W, R, H)
    res_fixed   = integrate_aep(U_grid, cp_fixed, U_MEAN, K_WEIBULL,
                                CUT_IN, CUT_OUT, P_RATED_W, R, H)

    results = {
        'passive': {**res_passive,
                    'cp_tsr': cps_passive_tsr,
                    'free_results': free_passive},
        'fixed':   {**res_fixed,
                    'cp_tsr': cps_passive_tsr,
                    'free_results': []},
    }

    # --- fair rigid reference ---
    rigid_ref = load_fair_rigid_reference()

    # --- report ---
    print()
    print("=" * 74)
    print("RESULTS")
    print("=" * 74)
    print(f"  Geometry    : R = {R} m, c = {BASE['c']} m, σ = "
          f"{BASE['N']*BASE['c']/(2*math.pi*R):.3f}")
    print(f"  Wind        : Weibull k = {K_WEIBULL}, mean U = {U_MEAN} m/s")
    print()
    print(f"  Peak Cp (passive, fixed-rpm) = {cps_passive_tsr.max():.4f} "
          f"at TSR = {tsrs[cps_passive_tsr.argmax()]:.2f}")
    print()
    print(f"  {'Strategy':<40} {'AEP [kWh/yr]':>14} {'Cap factor':>12}")
    print("  " + "-" * 68)
    print(f"  {'Passive CPPC, k_load (var speed)':<40} "
          f"{res_passive['aep']:>14.1f} {res_passive['cf']*100:>11.2f}%")
    print(f"  {'Passive CPPC, fixed rpm':<40} "
          f"{res_fixed['aep']:>14.1f} {res_fixed['cf']*100:>11.2f}%")
    if rigid_ref:
        print(f"  {'Rigid blade, best fixed pitch':<40} "
              f"{rigid_ref['aep_kWh']:>14.1f} {rigid_ref['cf']*100:>11.2f}%"
              f"   (from aep_rigid_fair.json)")
    else:
        print(f"  {'Rigid blade, best fixed pitch':<40} "
              f"{'(run compute_aep_rigid_fair.py)':>14}")
    print()
    gain_fixed = (res_passive['aep'] / max(res_fixed['aep'], 1e-9) - 1.0) * 100
    print(f"  Passive CPPC vs fixed-rpm, same physics : {gain_fixed:+6.1f} %")
    if rigid_ref:
        print(f"  Passive CPPC vs fair rigid baseline    : "
              f"{rigid_ref['gain_percent']:+6.1f} %")

    # --- plot ---
    out_path = os.path.join(_ROOT, "docs", "aep.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    make_plot(results, tsrs, out_path)

    # --- json dump ---
    summary = {
        "geometry": {"R": R, "c": BASE['c'], "N": BASE['N'],
                     "sigma": BASE['N']*BASE['c']/(2*math.pi*R)},
        "wind": {"mean_U": U_MEAN, "k_weibull": K_WEIBULL,
                 "cut_in": CUT_IN, "cut_out": CUT_OUT,
                 "p_rated_W": P_RATED_W},
        "results": {
            "passive_k_load":    {"aep_kWh": res_passive['aep'],
                                  "cf": res_passive['cf']},
            "passive_fixed_rpm": {"aep_kWh": res_fixed['aep'],
                                  "cf": res_fixed['cf']},
        },
        "gains_percent": {
            "passive_vs_fixed_rpm": gain_fixed,
        },
    }
    if rigid_ref:
        summary["rigid_fair_ref"] = rigid_ref
        summary["gains_percent"]["passive_vs_rigid_fair"] = rigid_ref["gain_percent"]

    json_path = os.path.join(_HERE, "aep_results.json")
    with open(json_path, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"JSON saved to {json_path}")


if __name__ == "__main__":
    main()
