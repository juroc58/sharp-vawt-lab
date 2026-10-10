"""
Annual Energy Production (AEP) for the Sharp cycloturbine.

Three operating strategies are compared at the same rotor geometry and
the same k_load external load:

  1. Passive CPPC, free-running    — Sharp's centrifugal-pendulum pitch
                                     mechanism, rotor speed adjusts to
                                     match the wind.
  2. Rigid blade, free-running     — same rotor, same k_load, but pitch
                                     locked at zero. This isolates the
                                     effect of the CPPC mechanism.
  3. Passive CPPC, fixed-rpm       — synchronous generator holds omega
                                     constant. Shows the penalty of not
                                     tracking the wind.

Tip-loss correction is ON (bounded finite-span, max 15 % lift reduction),
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
# Sharp-inspired CPPC design at R = 0.60 m
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
    use_tip_loss=True,                # <-- bounded finite-span correction ON
    win_deg=45.0, cb=2e-5, mu_c=3e-4,
    free=False, T_max=25.0, stride=5,
    w0_frac=0.9, k_load=0.0025, tsr=2.0,
)

# Wind resource
U_MEAN      = 6.0
K_WEIBULL   = 2.0
CUT_IN      = 3.0
CUT_OUT     = 25.0
RHO         = 1.225
HOURS_YEAR  = 8760.0
P_RATED_W   = 250.0
ETA_DRIVETRAIN = 0.90    # shaft -> electrical (generator + bearings + wiring)


# ============================================================================
# Helpers
# ============================================================================
def rigid_params(base):
    """Lock the pitch at zero by prescribing an all-zero Fourier law."""
    return {**base,
            'prescribe_pitch': True,
            'pp0_deg': 0.0,
            'pp1_deg': 0.0,
            'pp2_deg': 0.0,
            'pp3_deg': 0.0,
            'pp_ph_deg': 0.0}


def weibull_pdf(U, U_mean, k):
    lam = U_mean / math.gamma(1.0 + 1.0 / k)
    return (k / lam) * (U / lam) ** (k - 1.0) * np.exp(-(U / lam) ** k)


# ============================================================================
# 1. Cp(TSR) at fixed rpm — passive vs rigid
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
# 2. Free-running equilibrium at each U
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
# 3. AEP integration
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
    aep = float(np.trapezoid(P * pdf, U_grid) * HOURS_YEAR / 1000.0)
    cf = aep * 1000.0 / (p_rated * HOURS_YEAR) if p_rated else float('nan')
    return dict(U=U_grid, cp=cp_curve, P=P, pdf=pdf, aep=aep, cf=cf)


# ============================================================================
# 4. Plot
# ============================================================================
def make_plot(results, tsrs, out_path):
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))

    # --- colours used consistently across all panels ---
    col_passive = "C0"    # blue
    col_rigid   = "C1"    # orange
    col_fixed   = "C2"    # green

    # --- Panel 1: Cp vs TSR ---
    a = ax[0, 0]
    a.plot(tsrs, results['passive']['cp_tsr'], "o-", color=col_passive,
           lw=1.8, label="passive CPPC")
    a.plot(tsrs, results['rigid']['cp_tsr'], "s--", color=col_rigid,
           lw=1.8, label="rigid blade")
    a.axhline(0, color="k", lw=0.5)
    a.set_xlabel("tip-speed ratio λ")
    a.set_ylabel("Cp")
    a.set_title("Cp vs TSR at fixed rpm (tip loss on)")
    a.grid(alpha=0.3)
    a.legend(fontsize=9)

    # --- Panel 2: free-running Cp vs U ---
    a = ax[0, 1]
    for key, col, marker, label in [
        ('passive', col_passive, 'o', 'passive CPPC'),
        ('rigid',   col_rigid,   's', 'rigid blade'),
    ]:
        fr = results[key]['free_results']
        if fr:
            Us = np.array([f['U'] for f in fr])
            cps = np.array([f['cp'] for f in fr])
            a.plot(Us, cps, marker + "-", color=col, lw=1.6, label=label)
    a.set_xlabel("wind speed U [m/s]")
    a.set_ylabel("Cp at equilibrium")
    a.set_title("Free-running Cp vs wind speed")
    a.grid(alpha=0.3)
    a.legend(fontsize=9)

    # --- Panel 3: power curves ---
    a = ax[1, 0]
    a.plot(results['passive']['U'], results['passive']['P'], "-",
           color=col_passive, lw=2.0, label="passive CPPC, k_load")
    a.plot(results['rigid']['U'], results['rigid']['P'], "-",
           color=col_rigid, lw=2.0, label="rigid blade, k_load")
    a.plot(results['fixed']['U'], results['fixed']['P'], "--",
           color=col_fixed, lw=1.8, label="passive CPPC, fixed rpm")
    a.set_xlabel("wind speed U [m/s]")
    a.set_ylabel("electrical power [W]")
    a.set_title("Power curve")
    a.grid(alpha=0.3)
    a.legend(fontsize=9)
    a.set_xlim(CUT_IN, CUT_OUT)

    # --- Panel 4: AEP contribution per bin ---
    a = ax[1, 1]
    for key, col, style, label in [
        ('passive', col_passive, "-",  None),
        ('rigid',   col_rigid,   "-",  None),
    ]:
        r = results[key]
        dE = r['P'] * r['pdf'] * HOURS_YEAR / 1000.0
        a.plot(r['U'], dE, style, color=col, lw=1.7,
               label=f"{key}: {r['aep']:.0f} kWh/yr")
    a.set_xlabel("wind speed U [m/s]")
    a.set_ylabel("d(AEP)/dU  [kWh/yr per m/s]")
    a.set_title(f"AEP per wind bin  (η_drivetrain = {ETA_DRIVETRAIN:.2f})")
    a.grid(alpha=0.3)
    a.legend(fontsize=9)
    a.set_xlim(CUT_IN, CUT_OUT)

    fig.suptitle("Annual energy production — Sharp CPPC vs rigid blade, R = 0.60 m",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out_path, dpi=150)
    print(f"\nWrote {out_path}")


# ============================================================================
# 5. Main
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

    rigid = rigid_params(BASE)

    # --- fixed-rpm Cp curves ---
    tsrs = np.linspace(1.0, 3.5, 11)
    cps_passive_tsr = compute_cp_curve(BASE, tsrs, "passive CPPC")
    print()
    cps_rigid_tsr = compute_cp_curve(rigid, tsrs, "rigid blade")

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

    print()
    print("  Free-running rigid blade:")
    free_rigid = []
    for U in U_ref:
        f = free_run(rigid, U, "rigid")
        if f:
            free_rigid.append(f)
            print(f"    U = {U:4.1f}   Cp = {f['cp']:+.4f}   "
                  f"TSR = {f['tsr_eq']:5.2f}   α_max = {f['aoa_max']:5.1f}")
        else:
            print(f"    U = {U:4.1f}   (no equilibrium)")

    # --- build power curves on a common U grid ---
    U_grid = np.linspace(CUT_IN, CUT_OUT, 200)
    R, H = BASE['R'], BASE['H']

    # fixed-rpm: omega held so that TSR = peak-TSR of passive at U_mean
    idx_best = int(np.argmax(cps_passive_tsr))
    tsr_design = float(tsrs[idx_best])
    tsr_fixed = np.clip(tsr_design * U_MEAN / U_grid, tsrs[0], tsrs[-1])
    cp_fixed = np.interp(tsr_fixed, tsrs, cps_passive_tsr)

    # passive free-running: interpolate Cp(U) from reference runs
    if len(free_passive) >= 2:
        U_s = np.array([f['U'] for f in free_passive])
        cp_s = np.array([f['cp'] for f in free_passive])
        cp_passive = np.interp(U_grid, U_s, cp_s)
    else:
        cp_passive = np.full_like(U_grid, float(cps_passive_tsr.max()))

    # rigid free-running
    if len(free_rigid) >= 2:
        U_s = np.array([f['U'] for f in free_rigid])
        cp_s = np.array([f['cp'] for f in free_rigid])
        cp_rigid = np.interp(U_grid, U_s, cp_s)
    else:
        cp_rigid = np.full_like(U_grid, float(cps_rigid_tsr.max()))

    # --- integrate ---
    res_passive = integrate_aep(U_grid, cp_passive, U_MEAN, K_WEIBULL,
                                CUT_IN, CUT_OUT, P_RATED_W, R, H)
    res_rigid   = integrate_aep(U_grid, cp_rigid, U_MEAN, K_WEIBULL,
                                CUT_IN, CUT_OUT, P_RATED_W, R, H)
    res_fixed   = integrate_aep(U_grid, cp_fixed, U_MEAN, K_WEIBULL,
                                CUT_IN, CUT_OUT, P_RATED_W, R, H)

    results = {
        'passive':   {**res_passive,
                      'cp_tsr': cps_passive_tsr,
                      'free_results': free_passive},
        'rigid':     {**res_rigid,
                      'cp_tsr': cps_rigid_tsr,
                      'free_results': free_rigid},
        'fixed':     {**res_fixed,
                      'cp_tsr': cps_passive_tsr,   # same physics, fixed omega
                      'free_results': []},
    }

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
    print(f"  Peak Cp (rigid,   fixed-rpm) = {cps_rigid_tsr.max():.4f} "
          f"at TSR = {tsrs[cps_rigid_tsr.argmax()]:.2f}")
    print()
    print(f"  {'Strategy':<32} {'AEP [kWh/yr]':>14} {'Cap factor':>12}")
    print("  " + "-" * 60)
    print(f"  {'Passive CPPC, k_load (var speed)':<32} "
          f"{res_passive['aep']:>14.1f} {res_passive['cf']*100:>11.2f}%")
    print(f"  {'Rigid blade, k_load (var speed)':<32} "
          f"{res_rigid['aep']:>14.1f} {res_rigid['cf']*100:>11.2f}%")
    print(f"  {'Passive CPPC, fixed rpm':<32} "
          f"{res_fixed['aep']:>14.1f} {res_fixed['cf']*100:>11.2f}%")
    print()
    gain_rigid = (res_passive['aep'] / max(res_rigid['aep'], 1e-9) - 1.0) * 100
    gain_fixed = (res_passive['aep'] / max(res_fixed['aep'], 1e-9) - 1.0) * 100
    print(f"  Passive CPPC vs rigid blade, same load  : "
          f"{gain_rigid:+6.1f} %")
    print(f"  Passive CPPC vs fixed-rpm,  same physics : "
          f"{gain_fixed:+6.1f} %")

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
            "passive_k_load":  {"aep_kWh": res_passive['aep'],
                                "cf": res_passive['cf']},
            "rigid_k_load":    {"aep_kWh": res_rigid['aep'],
                                "cf": res_rigid['cf']},
            "passive_fixed_rpm": {"aep_kWh": res_fixed['aep'],
                                  "cf": res_fixed['cf']},
        },
        "gains_percent": {
            "passive_vs_rigid": gain_rigid,
            "passive_vs_fixed_rpm": gain_fixed,
        },
    }
    json_path = os.path.join(_HERE, "aep_results.json")
    with open(json_path, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"JSON saved to {json_path}")


if __name__ == "__main__":
    main()