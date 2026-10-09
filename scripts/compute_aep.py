"""
Annual Energy Production (AEP) for the Sharp cycloturbine.

Two operating strategies are compared:

  1. Passive k_load   — rotor speed adjusts to balance aero torque against
                        the external load torque k_load*omega^2. This is the
                        natural mode for a passive Sharp machine.
  2. Fixed-rpm gen.   — rotor speed held constant by a synchronous
                        generator. TSR varies with wind speed.

Both are integrated against a Weibull wind distribution to give kWh/year.

Produces docs/aep.png with four panels: Cp(TSR), P(U), Weibull pdf,
and the AEP contribution per wind-speed bin.
"""
from __future__ import annotations

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
# Sharp-conforming CPPC design at R = 0.60 m  (Cp = 0.36)
BASE = dict(
    R=0.60, H=0.40, N=3, c=0.14,
    ar=0.50, sp=0.25,
    mb=0.010, xbcg=0.20,
    mc=0.002, dcw=0.30,
    balance=0, bias_deg=0.0,
    prescribe_pitch=False,
    cd_add=0.002,
    use_dynamic_stall=True, use_flow_curvature=True, use_dmst=True,
    win_deg=45.0, cb=2e-5, mu_c=3e-4,
    free=False, T_max=25.0, stride=5,
    w0_frac=0.9, k_load=0.0025, tsr=2.0,
)

# Wind resource
U_MEAN      = 6.0      # m/s
K_WEIBULL   = 2.0      # shape (2 = Rayleigh)
CUT_IN      = 3.0      # m/s
CUT_OUT     = 25.0     # m/s
RHO         = 1.225
HOURS_YEAR  = 8760.0

# Rated power cap (set to None for no cap).  For R = 0.6 m the peak power
# at the design point is ~200 W, so 250 W is a reasonable generator rating.
P_RATED_W   = 250.0


# ============================================================================
# 1. Cp vs TSR (fixed rpm)
# ============================================================================
def compute_cp_curve(base, tsrs):
    print("Computing Cp(TSR) at fixed rpm ...")
    out = []
    for tsr in tsrs:
        r = create_sim_from_params({**base, 'free': False, 'tsr': float(tsr)}).run()
        cp = float(r['cp'])
        out.append(cp)
        print(f"  TSR = {tsr:5.2f}   Cp = {cp:+.4f}   "
              f"alpha_max = {r['aoa_max']:5.1f}   steady = {r.get('steady', True)}")
    return np.array(out)


# ============================================================================
# 2. Passive free-running operating point
# ============================================================================
def free_run_cp(base, U):
    """Run in free mode at wind speed U and return the equilibrium Cp."""
    try:
        r = create_sim_from_params({**base, 'free': True, 'U': U}).run()
    except Exception:
        return None
    if not r.get('steady', True):
        return None
    cp = float(r['cp'])
    if cp <= 0.0 or not np.isfinite(cp):
        return None
    return dict(U=U, cp=cp, tsr_eq=float(r['tsr_eq']),
                rpm=float(r['rpm']), aoa_max=float(r['aoa_max']))


# ============================================================================
# 3. Weibull
# ============================================================================
def weibull_pdf(U, U_mean, k):
    lam = U_mean / math.gamma(1.0 + 1.0 / k)
    return (k / lam) * (U / lam) ** (k - 1.0) * np.exp(-(U / lam) ** k)


# ============================================================================
# 4. AEP integration
# ============================================================================
def compute_aep(base, tsrs, cps_fixed, U_mean, k_weibull,
                cut_in, cut_out, p_rated):
    R = base['R']
    H = base['H']
    A_swept = 2.0 * R * H

    # Peak of the Cp curve (used as the fixed-rpm design TSR)
    idx_best = int(np.argmax(cps_fixed))
    tsr_best = float(tsrs[idx_best])
    cp_best = float(cps_fixed[idx_best])
    print(f"\n  Cp curve: peak Cp = {cp_best:.4f} at TSR = {tsr_best:.2f}")

    # --- strategy 2: fixed-rpm generator ---
    # Design speed: omega set so that TSR = tsr_best at U = U_mean
    # omega_design = tsr_best * U_mean / R
    # At another wind speed: TSR = omega_design * R / U = tsr_best * U_mean / U
    U_grid = np.linspace(cut_in, cut_out, 200)
    tsr_fixed = np.clip(tsr_best * U_mean / U_grid, tsrs[0], tsrs[-1])
    cp_fixed = np.interp(tsr_fixed, tsrs, cps_fixed)
    P_fixed = 0.5 * RHO * A_swept * U_grid ** 3 * cp_fixed
    if p_rated is not None:
        P_fixed = np.minimum(P_fixed, p_rated)

    # --- strategy 1: passive k_load (variable speed) ---
    # Run free at several reference wind speeds, get Cp(U)
    print("\n  Free-running k_load strategy — running at reference U:")
    U_ref = [3.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]
    free_results = []
    for U in U_ref:
        f = free_run_cp(base, U)
        if f is not None:
            free_results.append(f)
            print(f"    U = {U:4.1f} m/s   Cp = {f['cp']:+.4f}   "
                  f"TSR_eq = {f['tsr_eq']:5.2f}   α_max = {f['aoa_max']:5.1f}")
        else:
            print(f"    U = {U:4.1f} m/s   (did not converge)")

    # Interpolate Cp(U); hold the last valid value beyond the sample range
    if len(free_results) >= 2:
        U_samp = np.array([f['U'] for f in free_results])
        cp_samp = np.array([f['cp'] for f in free_results])
        cp_kload = np.interp(U_grid, U_samp, cp_samp)
    else:
        # fallback: use the fixed-rpm peak
        cp_kload = np.full_like(U_grid, cp_best)

    P_kload = 0.5 * RHO * A_swept * U_grid ** 3 * cp_kload
    if p_rated is not None:
        P_kload = np.minimum(P_kload, p_rated)

    # --- integrate against Weibull ---
    pdf = weibull_pdf(U_grid, U_mean, k_weibull)
    aep_kload = float(np.trapezoid(P_kload * pdf, U_grid) * HOURS_YEAR / 1000.0)   # kWh/yr
    aep_fixed = float(np.trapezoid(P_fixed * pdf, U_grid) * HOURS_YEAR / 1000.0)

    # capacity factor
    cf_kload = aep_kload * 1000.0 / (p_rated * HOURS_YEAR) if p_rated else float('nan')
    cf_fixed = aep_fixed * 1000.0 / (p_rated * HOURS_YEAR) if p_rated else float('nan')

    return dict(
        U_grid=U_grid, pdf=pdf,
        P_kload=P_kload, P_fixed=P_fixed,
        cp_kload=cp_kload, cp_fixed=cp_fixed,
        tsr_fixed=tsr_fixed,
        cp_best=cp_best, tsr_best=tsr_best,
        aep_kload_kWh=aep_kload, aep_fixed_kWh=aep_fixed,
        cf_kload=cf_kload, cf_fixed=cf_fixed,
        free_results=free_results,
    )


# ============================================================================
# 5. Plot
# ============================================================================
def make_plot(res, tsrs, cps_fixed, U_mean, k_weibull, cut_in, cut_out, out_path):
    fig, ax = plt.subplots(2, 2, figsize=(12, 9))

    # Panel 1: Cp vs TSR
    a = ax[0, 0]
    a.plot(tsrs, cps_fixed, "o-", color="C3", lw=1.8)
    a.axhline(0, color="k", lw=0.5)
    a.axvline(res['tsr_best'], color="k", ls=":", lw=0.8,
              label=f"design TSR = {res['tsr_best']:.2f}")
    a.axhline(res['cp_best'], color="k", ls=":", lw=0.8,
              label=f"peak Cp = {res['cp_best']:.3f}")
    a.set_xlabel("tip-speed ratio λ")
    a.set_ylabel("power coefficient Cp")
    a.set_title("Cp vs TSR at fixed rpm")
    a.grid(alpha=0.3)
    a.legend(fontsize=8)

    # Panel 2: Power curves
    a = ax[0, 1]
    a.plot(res['U_grid'], res['P_kload'], "-", color="C0", lw=1.8,
           label="passive k_load (variable speed)")
    a.plot(res['U_grid'], res['P_fixed'], "--", color="C1", lw=1.8,
           label="fixed-rpm generator")
    a.set_xlabel("wind speed U [m/s]")
    a.set_ylabel("electrical/mechanical power [W]")
    a.set_title("Power curve")
    a.grid(alpha=0.3)
    a.legend(fontsize=8)
    a.set_xlim(cut_in, cut_out)

    # Panel 3: Weibull PDF
    a = ax[1, 0]
    a.fill_between(res['U_grid'], res['pdf'], alpha=0.35, color="C2")
    a.plot(res['U_grid'], res['pdf'], color="C2", lw=1.5)
    a.axvline(U_mean, color="k", ls="--", lw=0.8,
              label=f"mean U = {U_mean:.1f} m/s")
    a.set_xlabel("wind speed U [m/s]")
    a.set_ylabel("Weibull pdf")
    a.set_title(f"Wind distribution  (Weibull k = {k_weibull})")
    a.grid(alpha=0.3)
    a.legend(fontsize=8)
    a.set_xlim(cut_in, cut_out)

    # Panel 4: AEP per bin
    a = ax[1, 1]
    dE_kload = res['P_kload'] * res['pdf'] * HOURS_YEAR / 1000.0
    dE_fixed = res['P_fixed'] * res['pdf'] * HOURS_YEAR / 1000.0
    a.plot(res['U_grid'], dE_kload, "-", color="C0", lw=1.6,
           label=f"k_load: {res['aep_kload_kWh']:.0f} kWh/yr")
    a.plot(res['U_grid'], dE_fixed, "--", color="C1", lw=1.6,
           label=f"fixed-rpm: {res['aep_fixed_kWh']:.0f} kWh/yr")
    a.set_xlabel("wind speed U [m/s]")
    a.set_ylabel("d(AEP)/dU  [kWh/yr per m/s]")
    a.set_title("AEP contribution per wind-speed bin")
    a.grid(alpha=0.3)
    a.legend(fontsize=8)
    a.set_xlim(cut_in, cut_out)

    fig.suptitle(f"Annual energy production — Sharp CPPC at R = 0.60 m",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out_path, dpi=150)
    print(f"\nWrote {out_path}")


# ============================================================================
# 6. Main
# ============================================================================
def main():
    print("=" * 74)
    print("Sharp cycloturbine — Annual Energy Production")
    print("=" * 74)
    print(f"  Design   : R = {BASE['R']} m, c = {BASE['c']} m, N = {BASE['N']}")
    print(f"  Wind     : Weibull k = {K_WEIBULL}, mean U = {U_MEAN} m/s")
    print(f"  Cut-in   : {CUT_IN} m/s   cut-out: {CUT_OUT} m/s")
    print(f"  Rated P  : {P_RATED_W} W")
    print()

    # Cp curve over the TSR range we care about
    tsrs = np.linspace(1.0, 3.5, 11)
    cps = compute_cp_curve(BASE, tsrs)

    res = compute_aep(BASE, tsrs, cps, U_MEAN, K_WEIBULL,
                      CUT_IN, CUT_OUT, P_RATED_W)

    print()
    print("=" * 74)
    print("RESULTS")
    print("=" * 74)
    print(f"  Peak Cp                     = {res['cp_best']:.4f} "
          f"(at TSR = {res['tsr_best']:.2f})")
    print(f"  Passive k_load  AEP         = {res['aep_kload_kWh']:8.1f} kWh/yr")
    print(f"      capacity factor         = {res['cf_kload']*100:6.2f} %")
    print(f"  Fixed-rpm       AEP         = {res['aep_fixed_kWh']:8.1f} kWh/yr")
    print(f"      capacity factor         = {res['cf_fixed']*100:6.2f} %")
    print()
    print(f"  Annual load match (k_load/fixed) = "
          f"{res['aep_kload_kWh'] / max(res['aep_fixed_kWh'], 1e-9):.3f}")

    out_path = os.path.join(_ROOT, "docs", "aep.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    make_plot(res, tsrs, cps, U_MEAN, K_WEIBULL, CUT_IN, CUT_OUT, out_path)


if __name__ == "__main__":
    main()