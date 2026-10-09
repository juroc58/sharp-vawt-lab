"""
Turbulent-wind AEP for the Sharp cycloturbine.

Uses the AR(1) turbulence generator in vawt_core.  For turbulent runs
we do NOT use the internal steady-state check (a turbulent rotor is by
definition not stationary); instead we require that the run finished
without divergence and average the last 40 % of the time series.
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


# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
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
    free=True, T_max=60.0, stride=8,
    w0_frac=1.0, k_load=0.0025, tsr=2.0,
)

U_MEAN         = 6.0
K_WEIBULL      = 2.0
CUT_IN         = 3.0
CUT_OUT        = 25.0
RHO            = 1.225
HOURS_YEAR     = 8760.0
P_RATED_W      = 250.0
ETA_DRIVETRAIN = 0.90

TURB_I  = 0.12
TURB_L  = 30.0
N_SEEDS = 10

U_REF = [3.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def weibull_pdf(U, U_mean, k):
    lam = U_mean / math.gamma(1.0 + 1.0 / k)
    return (k / lam) * (U / lam) ** (k - 1.0) * np.exp(-(U / lam) ** k)



def cp_from_power(P_mech, U, R, H, rho=RHO):
    """Cp = P / (0.5 * rho * U^3 * 2*R*H). Consistent with the P we plot."""
    A = 0.5 * rho * (2 * R) * H * (U ** 3)
    return P_mech / A if A > 0 else 0.0

def mean_power_last40(r, T_used):
    """Mean mechanical power over the last 40 % of the run, in W."""
    out = r['out']
    if len(out) < 10:
        return float('nan'), float('nan')
    t = out[:, 0]
    t0 = t[0] + 0.6 * (t[-1] - t[0])
    m = t >= t0
    if m.sum() < 5:
        m = np.ones(len(t), dtype=bool)
    P = out[m, 7] * out[m, 2]     # Q_shaft * omega
    w = out[m, 2]
    return float(np.mean(P)), float(np.mean(w))


def run_one(U, seed, turbulent):
    params = {**BASE, 'U': float(U)}
    if turbulent:
        params.update(turb_I=TURB_I, turb_L=TURB_L, seed=int(seed))
    try:
        r = create_sim_from_params(params).run()
    except Exception as e:
        return None
    # never use r['steady'] here — turbulent runs are never stationary
    P, w = mean_power_last40(r, BASE['T_max'])
    if not np.isfinite(P) or w <= 1.0:
        return None
    return dict(P=P, w=w, cp=float(r['cp']),
                tsr=float(r['tsr_eq']),
                rpm=float(r['rpm']),
                aoa_max=float(r['aoa_max']))


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    print("=" * 74)
    print("Turbulent-wind AEP — Sharp cycloturbine")
    print("=" * 74)
    print(f"  Turbulence     : I = {TURB_I*100:.0f} %, L = {TURB_L:.0f} m")
    print(f"  Realisations   : {N_SEEDS} per wind speed")
    print(f"  Wind resource  : Weibull k = {K_WEIBULL}, mean U = {U_MEAN} m/s")
    print(f"  Rated P        : {P_RATED_W} W, drivetrain eta = {ETA_DRIVETRAIN:.2f}")
    print()

    steady_rows = []      # (U, P, cp, tsr)
    turb_rows   = []      # (U, P_mean, P_std, cp_mean, cp_std, n_ok)

    print("  Steady-wind:")
    for U in U_REF:
        r = run_one(U, 0, turbulent=False)
        if r:
            cp_ws = cp_from_power(r['P'], U, BASE['R'], BASE['H'])
            steady_rows.append((U, r['P'], cp_ws, r['tsr']))
            print(f"    U = {U:4.1f}   P = {r['P']:7.2f} W   "
                  f"Cp = {cp_ws:+.4f}   TSR = {r['tsr']:5.2f}")

    print()
    print(f"  Turbulent (I = {TURB_I*100:.0f} %, {N_SEEDS} seeds):")
    for U in U_REF:
        Ps, cps = [], []
        for s in range(N_SEEDS):
            r = run_one(U, s + 1, turbulent=True)
            if r:
                Ps.append(r['P'])
                cps.append(r['cp'])
        if not Ps:
            print(f"    U = {U:4.1f}   (all seeds failed)")
            continue
        Pm, Psd = float(np.mean(Ps)), float(np.std(Ps))
        cp_ws = cp_from_power(Pm, U, BASE['R'], BASE['H'])
        Cm, Csd = cp_ws, float(np.std(cps))
        turb_rows.append((U, Pm, Psd, Cm, Csd, len(Ps)))
        print(f"    U = {U:4.1f}   P = {Pm:7.2f} +/- {Psd:5.2f} W   "
              f"Cp = {Cm:+.4f} +/- {Csd:.4f}   (n = {len(Ps)})")

    # ------------------------------------------------------------------
    # AEP
    # ------------------------------------------------------------------
    U_s = np.array([r[0] for r in steady_rows])
    P_s = np.array([r[1] for r in steady_rows])

    U_t = np.array([r[0] for r in turb_rows])
    P_t = np.array([r[1] for r in turb_rows])

    U_grid = np.linspace(CUT_IN, CUT_OUT, 200)
    P_s_g = np.minimum(np.interp(U_grid, U_s, P_s) * ETA_DRIVETRAIN, P_RATED_W)
    P_t_g = np.minimum(np.interp(U_grid, U_t, P_t) * ETA_DRIVETRAIN, P_RATED_W)

    pdf = weibull_pdf(U_grid, U_MEAN, K_WEIBULL)
    aep_s = float(np.trapezoid(P_s_g * pdf, U_grid) * HOURS_YEAR / 1000.0)
    aep_t = float(np.trapezoid(P_t_g * pdf, U_grid) * HOURS_YEAR / 1000.0)

    cf_s = aep_s * 1000.0 / (P_RATED_W * HOURS_YEAR)
    cf_t = aep_t * 1000.0 / (P_RATED_W * HOURS_YEAR)
    loss = (aep_s - aep_t) / aep_s * 100.0 if aep_s > 0 else 0.0

    print()
    print("=" * 74)
    print("RESULTS")
    print("=" * 74)
    print(f"  Steady-wind AEP    : {aep_s:7.1f} kWh/yr   CF = {cf_s*100:5.2f} %")
    print(f"  Turbulent-wind AEP : {aep_t:7.1f} kWh/yr   CF = {cf_t*100:5.2f} %")
    delta = (aep_t - aep_s) / aep_s * 100.0 if aep_s > 0 else 0.0
    label = "gain" if delta >= 0 else "loss"
    print(f"  Turbulence effect  : {delta:+5.1f} % ({label})")

    # ------------------------------------------------------------------
    # Plot
    # ------------------------------------------------------------------
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.5))

    # Panel 1: Cp vs U
    a = ax[0]
    U_cp_s = np.array([r[0] for r in steady_rows])
    cp_s   = np.array([r[2] for r in steady_rows])
    U_cp_t = np.array([r[0] for r in turb_rows])
    cp_t   = np.array([r[3] for r in turb_rows])
    cp_te  = np.array([r[4] for r in turb_rows])
    a.plot(U_cp_s, cp_s, "o-", color="C0", lw=1.8, label="steady")
    a.errorbar(U_cp_t, cp_t, yerr=cp_te, fmt="s-", color="C3",
               lw=1.8, capsize=4, label=f"turbulent (I = {TURB_I*100:.0f} %)")
    a.set_xlabel("mean U [m/s]")
    a.set_ylabel("Cp")
    a.set_title("Cp vs wind speed")
    a.grid(alpha=0.3)
    a.legend(fontsize=9)

    # Panel 2: power curve
    a = ax[1]
    a.plot(U_grid, P_s_g, "-", color="C0", lw=2.0,
           label=f"steady: {aep_s:.0f} kWh/yr")
    a.plot(U_grid, P_t_g, "-", color="C3", lw=2.0,
           label=f"turbulent: {aep_t:.0f} kWh/yr")
    a.set_xlabel("mean U [m/s]")
    a.set_ylabel("electrical power [W]")
    a.set_title("Mean power curve")
    a.grid(alpha=0.3)
    a.legend(fontsize=9)
    a.set_xlim(CUT_IN, CUT_OUT)

    # Panel 3: AEP per bin
    a = ax[2]
    dE_s = P_s_g * pdf * HOURS_YEAR / 1000.0
    dE_t = P_t_g * pdf * HOURS_YEAR / 1000.0
    a.plot(U_grid, dE_s, "-", color="C0", lw=1.8, label="steady")
    a.plot(U_grid, dE_t, "-", color="C3", lw=1.8, label="turbulent")
    a.fill_between(U_grid, dE_s, dE_t, color="C3", alpha=0.2,
                   label=f"loss = {loss:.1f} %")
    a.set_xlabel("U [m/s]")
    a.set_ylabel("d(AEP)/dU  [kWh/yr per m/s]")
    a.set_title("AEP per wind bin")
    a.grid(alpha=0.3)
    a.legend(fontsize=9)
    a.set_xlim(CUT_IN, CUT_OUT)

    fig.suptitle(f"Turbulent-wind AEP — Sharp CPPC at R = 0.60 m, I = {TURB_I*100:.0f} %",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out_png = os.path.join(_ROOT, "docs", "aep_turbulent.png")
    fig.savefig(out_png, dpi=140)
    print(f"\n  Wrote {out_png}")

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------
    out_json = os.path.join(_HERE, "aep_turbulent.json")
    with open(out_json, "w") as fh:
        json.dump({
            "turbulence": {"I": TURB_I, "L_m": TURB_L, "n_seeds": N_SEEDS},
            "wind": {"mean_U": U_MEAN, "k_weibull": K_WEIBULL,
                     "cut_in": CUT_IN, "cut_out": CUT_OUT,
                     "p_rated_W": P_RATED_W, "eta_drivetrain": ETA_DRIVETRAIN},
            "steady":    {"aep_kWh": aep_s, "cf": cf_s},
            "turbulent": {"aep_kWh": aep_t, "cf": cf_t},
            "turbulence_loss_pct": loss,
            "per_wind_speed": [
                {
                    "U":              float(su),
                    "P_steady_W":     float(sp),
                    "P_turb_mean_W":  float(tp),
                    "P_turb_std_W":   float(tps),
                }
                for (su, sp, _, _), (tu, tp, tps, _, _, _) in
                    zip(steady_rows, turb_rows)
            ],
        }, fh, indent=2)
    print(f"  Wrote {out_json}")


if __name__ == "__main__":
    main()