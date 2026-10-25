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

Tip-loss correction is ON (Helmbold finite-span),
matching the convention used in the README headline results.

Integrates each power curve against a Weibull wind distribution to give
kWh/year.  Produces scripts/aep_results.json.  Plotting is done by
scripts/plot_aep.py from the JSON output.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
from scipy.integrate import trapezoid

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from scripts.stamp import make_stamp
from sharp_vawt import create_sim_from_params
from vawt_presets import PRESETS

# ============================================================================
# CONFIGURATION
# ============================================================================
BASE = dict(PRESETS["scaleup"], free=False, T_max=25.0, stride=5)

U_MEAN         = 6.0
K_WEIBULL      = 2.0
CUT_IN         = 3.0
CUT_OUT        = 25.0
U_RATED        = 12.0
RHO            = 1.225
HOURS_YEAR     = 8760.0
ETA_DRIVETRAIN = 0.90


def rated_power_from_cp(R, H, cp_at_rated, U_rated=U_RATED):
    """Generator rating defined by power at a stated rated wind speed.

    This replaces the old arbitrary 90 kW number.  The rating is the
    mechanical power from the design Cp at U_rated times drivetrain
    efficiency; it is recorded in the JSON next to the Cp used.
    """
    area = 2.0 * R * H
    return float(0.5 * RHO * area * U_rated ** 3 * cp_at_rated
                 * ETA_DRIVETRAIN)


# Cp jump between adjacent 1 m/s free-running samples that flags a
# possible branch switch at the U ~ 8 m/s bifurcation.
BRANCH_JUMP_TOL = 0.05


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
    # New structure: stamp at top level, geometry data at top level
    # The scaleup data is at the top level (not under "geometries")
    if "geometries" in data:
        g = data.get("geometries", {}).get("scaleup")
    else:
        # New structure: stamp at top level, geometry data at top level
        # Check if this is the scaleup geometry (AR ~ 10.5)
        if data.get("AR", 0) > 5:  # scaleup has AR ~ 10.5
            g = data
        else:
            g = {}
    if not g:
        return None
    br = g.get("best_rigid") or {}
    return {
        "source":       "aep_rigid_fair.json",
        "geometry":     "scaleup",
        "psi0_deg":     br.get("psi0_deg"),
        "k_load":       br.get("k_load"),
        "cp_design":    br.get("cp_design"),
        "viable":       bool(br.get("viable", True)),
        "aep_kWh":      br.get("aep_kWh"),
        "cf":           br.get("cf"),
        "gain_percent": g.get("gain_percent"),
    }


# ============================================================================
# Cp(TSR) at fixed rpm — passive
# ============================================================================
def compute_cp_curve(base, tsrs, label, n_phase=3):
    """Phase-averaged fixed-rpm Cp(TSR).

    At a fixed rpm the passive pitch mechanism can settle into different
    limit cycles depending on the initial rotor phase.  A single psi0 = 0
    run produced a spurious narrow maximum at TSR = 3.25 (Cp 0.4122) that
    fell to 0.3479 for psi0 = 120 or 240 deg.  Average three equally spaced
    initial phases so the curve is not an initial-condition artefact.
    """
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
        cp = float(np.mean(vals))
        cps.append(cp)
        los.append(float(np.min(vals)))
        his.append(float(np.max(vals)))
        print(f"    TSR = {tsr:5.2f}   Cp = {cp:+.4f} "
              f"[{min(vals):+.4f}, {max(vals):+.4f}]")
    return np.array(cps), np.array(los), np.array(his)


# ============================================================================
# Free-running equilibrium at each U (with branch tracing)
# ============================================================================
def free_run(base, U, w0_frac=None, psi0_deg=None):
    """
    Run free-running simulation at wind speed U.
    
    If w0_frac and psi0_deg are provided, use them as initial conditions
    (branch tracing from previous wind speed). Otherwise use base defaults.
    """
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
    # Return result dict + final state for branch tracing
    result = {"U": float(U), "cp": cp,
                  "tsr_eq": float(r['tsr_eq']),
                  "rpm": float(r['rpm']),
                  "aoa_max": float(r['aoa_max'])}
    # Final state: use equilibrium omega and mean pitch as initial guess for next U
    # w0_frac for next U is computed so that:
    #   w0_frac * base['tsr'] * (U+1) / base['R'] = w_final = r['tsr_eq'] * U / base['R']
    #   => w0_frac = r['tsr_eq'] * U / (base['tsr'] * (U + 1))
    r['tsr_eq'] * U / base['R'] if base['R'] > 0 else 0
    pitch_final = 0.5 * (r['pitch_min'] + r['pitch_max']) if r.get('pitch_min') is not None else 0.0
    tsr_design = base.get('tsr', 2.5)
    final_state = {"w0_frac": r['tsr_eq'] * U / (tsr_design * (U + 1.0)) if (U + 1.0) > 0 else base.get('w0_frac', 0.9),
                       "psi0_deg": pitch_final}
    return result, final_state


def free_run_with_branch_check(base, U, w0_frac=None, psi0_deg=None, 
                                expected_cp=None, cp_tol=0.03):
    """
    Run free-run with branch switching detection and correction.
    
    If expected_cp is provided and the result differs by more than cp_tol,
    try alternative initial conditions to find the high-Cp branch.
    """
    # First attempt: use provided initial conditions (branch tracing)
    r, final_state = free_run(base, U, w0_frac, psi0_deg)
    
    if r is not None and expected_cp is not None:
        cp_diff = r['cp'] - expected_cp
        if cp_diff < -0.02:  # Significant drop suggests branch switch
            print(f"  U={U:.1f}: Cp drop detected ({cp_diff:+.4f}), trying alternative seeds...")
            # Try multiple alternative seeds to find high-Cp branch
            best_r = None
            best_cp = -1.0
            best_final = None
            
            # Try 1: Slightly higher initial omega (push toward high-TSR branch)
            for w0_mult in [1.05, 1.1, 1.2]:
                r_alt, fs_alt = free_run(base, U, 
                                         w0_frac=w0_frac * w0_mult if w0_frac else None,
                                         psi0_deg=psi0_deg)
                if r_alt and r_alt['cp'] > best_cp:
                    best_cp = r_alt['cp']
                    best_r = r_alt
                    best_final = fs_alt
            
            # Try 2: Slightly lower initial pitch (push toward high-TSR branch)
            for psi_mult in [0.8, 0.6, 0.4]:
                r_alt, fs_alt = free_run(base, U, w0_frac=w0_frac, psi0_deg=psi0_deg * psi_mult)
                if r_alt and r_alt['cp'] > best_cp:
                    best_cp = r_alt['cp']
                    best_r = r_alt
                    best_final = fs_alt
            
            # Try 3: Higher initial omega
            for w0_frac_mult in [1.05, 1.1, 1.15]:
                r_alt, fs_alt = free_run(base, U, 
                                         w0_frac=w0_frac * w0_frac_mult if w0_frac else None,
                                         psi0_deg=psi0_deg)
                if r_alt and r_alt['cp'] > best_cp:
                    best_cp = r_alt['cp']
                    best_r = r_alt
                    best_final = fs_alt
            
            if best_r and best_cp > r['cp'] + 0.01:
                print(f"  U={U:.1f}: Branch switch corrected! Cp {r['cp']:.4f} -> {best_cp:.4f}")
                return best_r, best_final
    
    return r, final_state


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
    return {"U": U_grid, "cp": cp_curve, "P": P, "pdf": pdf, "aep": aep, "cf": cf}


# Plotting is now done by scripts/plot_aep.py from the JSON output.
# The make_plot function has been moved to scripts/plot_aep.py.


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
    print(f"  Rated wind speed: {U_RATED} m/s (rating from the Cp curve)")
    print("  Tip loss : ON (Helmbold finite-span)")
    print(f"  Drivetrain efficiency: {ETA_DRIVETRAIN*100:.0f} %")
    print()

    # --- fixed-rpm Cp(TSR) ---
    tsrs = np.linspace(1.0, 4.5, 15)
    cps_passive_tsr, _cps_phase_lo, _cps_phase_hi = compute_cp_curve(
        BASE, tsrs, "passive CPPC")

    # --- free-running reference speeds (with branch tracing) ---
    # Sample every 1 m/s. The free-running equilibrium is bistable near
    # U ~ 8 m/s (a saddle-node bifurcation between a high-TSR and a low-TSR
    # branch). To stay on the high-Cp branch, we use branch tracing:
    # each point is seeded with the previous point's final (omega, pitch).
    print()
    U_ref = np.arange(CUT_IN, CUT_OUT + 1.0, 1.0).tolist()

    print("  Free-running passive CPPC (branch tracing):")
    free_passive = []
    w0_frac = BASE.get('w0_frac', 0.9)
    prev_cp = None  # Track previous Cp for branch switch detection
    psi0_deg = BASE.get('psi0_deg', 0.0)
    for U in U_ref:
        f, final_state = free_run_with_branch_check(BASE, U, w0_frac=w0_frac, psi0_deg=psi0_deg, expected_cp=prev_cp)
        if f:
            free_passive.append(f)
            # Use final state as initial condition for next wind speed
            if final_state:
                w0_frac = final_state['w0_frac']
                psi0_deg = final_state['psi0_deg']
            print(f"    U = {U:4.1f}   Cp = {f['cp']:+.4f}   "
                  f"TSR = {f['tsr_eq']:5.2f}   α_max = {f['aoa_max']:5.1f}"
                  f"   (seeded w0_frac={w0_frac:.3f}, psi0={psi0_deg:+.1f}°)")
        else:
            # If fails, reset to defaults and try next U
            w0_frac = BASE.get('w0_frac', 0.9)
            prev_cp = None  # Track previous Cp for branch switch detection
            psi0_deg = BASE.get('psi0_deg', 0.0)
            print(f"    U = {U:4.1f}   (no equilibrium, resetting seed)")

    # --- build power curves on a common U grid ---
    U_grid = np.linspace(CUT_IN, CUT_OUT, 200)
    R, H = BASE['R'], BASE['H']

    # fixed-rpm: omega held so that TSR = peak-TSR of passive at U_mean
    idx_best   = int(np.argmax(cps_passive_tsr))
    tsr_design = float(tsrs[idx_best])
    tsr_fixed  = np.clip(tsr_design * U_MEAN / U_grid, tsrs[0], tsrs[-1])
    cp_fixed   = np.interp(tsr_fixed, tsrs, cps_passive_tsr)

    # passive free-running: interpolate Cp(U) from reference runs.
    # If fewer than two points converged there is no curve to integrate;
    # falling back to a flat "max fixed-rpm Cp" would silently fabricate
    # an operating point, so that is an error, not a fallback.
    branch_jumps = []
    if len(free_passive) >= 2:
        U_s  = np.array([f['U'] for f in free_passive])
        cp_s = np.array([f['cp'] for f in free_passive])
        dcp = np.diff(cp_s)
        for i, j in enumerate(dcp):
            if abs(j) > BRANCH_JUMP_TOL:
                branch_jumps.append(
                    (float(U_s[i]), float(U_s[i + 1]),
                     float(cp_s[i]), float(cp_s[i + 1])))
                print(f"    NOTE: Cp jump of {j:+.3f} between U = "
                      f"{U_s[i]:.0f} and {U_s[i+1]:.0f} m/s "
                      f"(possible branch switch)")
        cp_passive = np.interp(U_grid, U_s, cp_s)
    else:
        raise RuntimeError(
            f"only {len(free_passive)} free-running equilibria converged; "
            f"need >= 2 to build the passive power curve. Check the "
            f"stability of the design point."
        )

    # --- rated power for this design, from the Cp curve at U_RATED ---
    cp_at_rated = float(np.interp(U_RATED, U_grid, cp_passive))
    p_rated = rated_power_from_cp(R, H, cp_at_rated)
    print(f"\n  Rated power from Cp(U={U_RATED:.0f} m/s) = {cp_at_rated:.4f}: "
          f"{p_rated/1000:.2f} kW")

    # --- integrate ---
    res_passive = integrate_aep(U_grid, cp_passive, U_MEAN, K_WEIBULL,
                                CUT_IN, CUT_OUT, p_rated, R, H)
    res_fixed   = integrate_aep(U_grid, cp_fixed, U_MEAN, K_WEIBULL,
                                CUT_IN, CUT_OUT, p_rated, R, H)


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
        if rigid_ref.get("viable", True) and rigid_ref.get("aep_kWh") is not None:
            print(f"  {'Rigid blade, best fixed pitch':<40} "
                  f"{rigid_ref['aep_kWh']:>14.1f} {rigid_ref['cf']*100:>11.2f}%"
                  f"   (from aep_rigid_fair.json)")
        else:
            print(f"  {'Rigid blade, best fixed pitch':<40} "
                  f"{'(no viable baseline)':>14}")
    else:
        print(f"  {'Rigid blade, best fixed pitch':<40} "
              f"{'(run compute_aep_rigid_fair.py)':>14}")
    print()
    gain_fixed = (res_passive['aep'] / max(res_fixed['aep'], 1e-9) - 1.0) * 100
    print(f"  Passive CPPC vs fixed-rpm, same physics : {gain_fixed:+6.1f} %")
    if rigid_ref and rigid_ref.get("gain_percent") is not None:
        print(f"  Passive CPPC vs fair rigid baseline    : "
              f"{rigid_ref['gain_percent']:+6.1f} %")
    elif rigid_ref is not None:
        print("  Passive CPPC vs fair rigid baseline    : "
              "n/a (no viable rigid configuration)")

    # --- plot ---
    # --- json dump ---
    summary = {
        "geometry": {"R": R, "c": BASE['c'], "H": H, "N": BASE['N'],
                     "sigma": BASE['N']*BASE['c']/(2*math.pi*R)},
        "wind": {"mean_U": U_MEAN, "k_weibull": K_WEIBULL,
                 "cut_in": CUT_IN, "cut_out": CUT_OUT,
                 "rated_wind_speed": U_RATED,
                 "cp_at_rated": cp_at_rated,
                 "p_rated_W": p_rated},
        "results": {
            "passive_k_load":    {"aep_kWh": res_passive['aep'],
                                  "cf": res_passive['cf'],
                                  "branch_jumps": branch_jumps,
                                  "cp_tsr": [float(v) for v in cps_passive_tsr],
                                  "tsr": [float(v) for v in tsrs],
                                  "free_results": free_passive},
            "passive_fixed_rpm": {"aep_kWh": res_fixed['aep'],
                                  "cf": res_fixed['cf'],
                                  "cp_tsr": [float(v) for v in cps_passive_tsr],
                                  "tsr": [float(v) for v in tsrs]},
        },
        "gains_percent": {
            "passive_vs_fixed_rpm": gain_fixed,
        },
    }
    if rigid_ref:
        summary["rigid_fair_ref"] = rigid_ref
        if rigid_ref.get("gain_percent") is not None:
            summary["gains_percent"]["passive_vs_rigid_fair"] = \
                rigid_ref["gain_percent"]

    json_path = os.path.join(_HERE, "aep_results.json")
    stamp = make_stamp(
        "scripts/compute_aep.py",
        script_version="2.0.0",
        n=len(tsrs) + len(free_passive),
        seed=0,
        extra_files=["vawt_presets.py"],
        extra_data={"U_MEAN": U_MEAN, "K_WEIBULL": K_WEIBULL, "CUT_IN": CUT_IN, "CUT_OUT": CUT_OUT, "U_RATED": U_RATED},
    )
    with open(json_path, "w") as fh:
        json.dump({"stamp": stamp, **summary}, fh, indent=2)
    print(f"JSON saved to {json_path}")


if __name__ == "__main__":
    main()
