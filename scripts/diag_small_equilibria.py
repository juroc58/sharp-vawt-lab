"""Diagnose the free-running vs fixed-rpm Cp discrepancy in aep_small.json.

Reads the free-running equilibria (single-phase, psi0=0) from aep_small.json
and re-runs fixed-rpm at the same TSR, same psi0, same everything else.

The diagnostic runs four checks at each wind speed to discriminate the cause
of the free-vs-fixed Cp gap:

CHECK A — Ripple vs Q-mean correlation (free run only)
  Compares mean(Q*omega)/A against mean(Q)*mean(omega)/A. If the Q-omega
  correlation contributes little to Cp, velocity ripple is not the dominant
  driver of the gap.

CHECK B — Per-revolution energy ledger (free vs fixed)
  Compares per-channel energy ratios (free / fixed) across aero, shaft, arm,
  piv_vis, piv_cou, stop, d_stored. A stop-energy ratio far from 1 means
  pitch limit cycles differ between free and fixed operation.

CHECK C — Waveform comparison (free vs fixed)
  Compares psi_rad statistics over the steady window: RMS, min, max, and
  fraction of samples on the stops. Large differences indicate different
  limit cycles.

CHECK D — Bistability check (multiple attractors)
  Runs 3 free runs at w0_frac in {0.5, 0.9, 1.5} and 5 fixed runs at
  psi0_deg in {-40, -20, 0, 20, 40}. Clusters Cp values within 2% to count
  distinct attractors. If both free and fixed show a single attractor but
  Cp differs, the gap is an accounting difference.

This is diagnostic only. The output JSON is not consumed by any other script
and does not change any result. It is tracked in stamp.py's STAMP_CHECK_MAP
so freshness checks catch a stale diagnostic report.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_HERE))

from scripts.stamp import write_json_with_stamp
from sharp_vawt import create_sim_from_params

AEP_SMALL = _HERE / "aep_small.json"
OUT_JSON = _HERE / "diag_small_equilibria.json"

# Match aep_small's BASE exactly (R=0.6, c=0.14, H=0.40, etc.).
BASE = {
    "R": 0.60,
    "H": 0.40,
    "N": 3,
    "c": 0.14,
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
    "free": False,
    "T_max": 30.0,
    "stride": 5,
    "w0_frac": 0.9,
}

RHO = 1.225  # air density, matches AeroConfig default


def _steady_mask(theta: np.ndarray) -> np.ndarray:
    """Boolean mask for the last 4 revolutions of the time series."""
    return theta > theta[-1] - 4.0 * 2.0 * 3.141592653589793


def _cluster_count(values: list[float], tol: float = 0.02) -> int:
    """Count distinct clusters within a relative tolerance.

    Values are sorted; a new cluster starts when a value differs from the
    cluster's first representative by more than ``tol`` (relative).
    """
    if not values:
        return 0
    sorted_vals = sorted(values)
    clusters = 1
    rep = sorted_vals[0]
    for v in sorted_vals[1:]:
        if abs(v - rep) / max(abs(rep), 1e-9) > tol:
            clusters += 1
            rep = v
    return clusters


def run_free_with_history(U: float) -> dict:
    """Run a free simulation storing the full time history."""
    params = {**BASE, "free": True, "U": float(U), "T_max": 30.0, "stride": 5}
    r = create_sim_from_params(params).run(store_history=True)
    return r


def run_fixed_at_tsr(tsr: float, psi0_deg: float, U: float) -> dict:
    """Run a fixed-rpm simulation at the given TSR, psi0, U."""
    params = {
        **BASE,
        "free": False,
        "tsr": float(tsr),
        "psi0_deg": float(psi0_deg),
        "U": float(U),
        "T_max": 30.0,
        "stride": 5,
    }
    r = create_sim_from_params(params).run(store_history=True)
    return r


def _area(U: float, R: float, H: float) -> float:
    """Swept area factor A = 0.5 * rho * U^3 * 2*R*H (used as Cp divisor)."""
    return 0.5 * RHO * U**3 * 2.0 * R * H


def _ripple_check(r: dict, U: float) -> dict:
    """CHECK A: Q-omega correlation decomposition for the free run."""
    hist = r["history"]
    omega = hist["omega"]
    q_shaft = hist["Q_shaft"]
    theta = hist["theta"]
    m = _steady_mask(theta)

    omega_s = omega[m]
    q_s = q_shaft[m]
    A = _area(U, BASE["R"], BASE["H"])

    cp_free = float(np.mean(q_s * omega_s) / A)
    cp_q_mean_omega_mean = float(np.mean(q_s) * np.mean(omega_s) / A)
    diff = cp_free - cp_q_mean_omega_mean
    corr_pct = abs(diff) / max(abs(cp_free), 1e-9) * 100.0
    cube_ratio = float(np.mean(omega_s**3) / max(np.mean(omega_s) ** 3, 1e-12))

    return {
        "cp_free": cp_free,
        "cp_q_mean_omega_mean": cp_q_mean_omega_mean,
        "correlation_contribution_percent": corr_pct,
        "cube_ratio": cube_ratio,
    }


def _ledger_check(r_free: dict, r_fixed: dict) -> dict:
    """CHECK B: per-revolution energy ledger comparison (free / fixed)."""
    e_free = r_free["energies"]
    e_fixed = r_fixed["energies"]
    ratios = {}
    for key in ("aero", "shaft", "arm", "piv_vis", "piv_cou", "stop", "d_stored"):
        ratios[key] = float(e_free[key] / max(e_fixed[key], 1e-12))
    return ratios


def _waveform_check(r_free: dict, r_fixed: dict, win_deg: float) -> dict:
    """CHECK C: psi_rad waveform comparison over the steady window."""

    def extract(r: dict) -> dict:
        hist = r["history"]
        psi = hist["psi_rad"]
        theta = hist["theta"]
        m = _steady_mask(theta)
        psi_s = psi[m]
        stop_frac = float(
            np.mean(np.abs(psi_s) > 0.98 * math.radians(win_deg))
        )
        return {
            "rms": float(np.std(psi_s)),
            "min": float(np.min(psi_s)),
            "max": float(np.max(psi_s)),
            "stop_fraction": stop_frac,
        }

    return {"free": extract(r_free), "fixed": extract(r_fixed)}


def _bistability_check(U: float, tsr_eq: float) -> dict:
    """CHECK D: multiple-attractor check via free and fixed runs."""
    cps_free = []
    for w0_frac in (0.5, 0.9, 1.5):
        params = {
            **BASE,
            "free": True,
            "U": float(U),
            "w0_frac": float(w0_frac),
            "psi0_deg": 0.0,
            "T_max": 30.0,
            "stride": 5,
        }
        r = create_sim_from_params(params).run()
        cps_free.append(float(r["cp"]))

    cps_fixed = []
    for psi0_deg in (-40.0, -20.0, 0.0, 20.0, 40.0):
        params = {
            **BASE,
            "free": False,
            "tsr": float(tsr_eq),
            "psi0_deg": float(psi0_deg),
            "U": float(U),
            "T_max": 30.0,
            "stride": 5,
        }
        r = create_sim_from_params(params).run()
        cps_fixed.append(float(r["cp"]))

    n_distinct_free = _cluster_count(cps_free, 0.02)
    n_distinct_fixed = _cluster_count(cps_fixed, 0.02)

    return {
        "cp_w0_0p5": cps_free[0],
        "cp_w0_0p9": cps_free[1],
        "cp_w0_1p5": cps_free[2],
        "cp_psi0_n40": cps_fixed[0],
        "cp_psi0_n20": cps_fixed[1],
        "cp_psi0_0": cps_fixed[2],
        "cp_psi0_p20": cps_fixed[3],
        "cp_psi0_p40": cps_fixed[4],
        "n_distinct_free": n_distinct_free,
        "n_distinct_fixed": n_distinct_fixed,
    }


def _interpretation(
    n_distinct_free: int, n_distinct_fixed: int, gap: float
) -> str:
    if n_distinct_fixed >= 2 and n_distinct_free >= 1:
        return "pitch bistability: fixed-rpm has multiple attractors"
    if n_distinct_fixed == 1 and n_distinct_free >= 2:
        return "free dynamics bistable but fixed single-attractor"
    if n_distinct_fixed == 1 and n_distinct_free == 1 and abs(gap) > 0.10:
        return "single attractor on both; gap is accounting"
    if n_distinct_fixed == 1 and n_distinct_free == 1:
        return "single attractor both, gap < 10%; consistent"
    return "mixed; see checks"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true",
                    help="Only run U = 6 m/s (one case).")
    args = ap.parse_args(argv)

    with open(AEP_SMALL) as fh:
        aep = json.load(fh)

    free_results = aep["results"]["passive_k_load"]["free_results"]
    want_U = [6.0] if args.quick else [6.0, 8.0, 12.0]
    free_by_U = {round(f["U"], 1): f for f in free_results}

    cases = []
    for U in want_U:
        key = round(U, 1)
        if key not in free_by_U:
            print(f"  U = {U}: no free-running result in aep_small.json; skipping")
            continue
        free = free_by_U[key]
        tsr_eq = float(free["tsr_eq"])
        free_cp = float(free["cp"])
        print(f"  U = {U:.1f}  free Cp = {free_cp:.4f}  TSR_eq = {tsr_eq:.3f}")

        # CHECK A + CHECK C + CHECK D need the free run with history
        r_free_hist = run_free_with_history(U)
        ripple = _ripple_check(r_free_hist, U)

        # Fixed run at same TSR, psi0=0
        fixed = run_fixed_at_tsr(tsr_eq, psi0_deg=0.0, U=U)
        fixed_cp = fixed["cp"]
        gap = (free_cp - fixed_cp) / max(abs(fixed_cp), 1e-9)
        print(f"    fixed-rpm at same TSR, psi0=0: Cp = {fixed_cp:.4f}")
        print(f"    gap (free - fixed) / fixed = {gap*100:+.1f} %")

        # CHECK B: ledger
        ledger = _ledger_check(r_free_hist, fixed)

        # CHECK C: waveform
        waveform = _waveform_check(r_free_hist, fixed, BASE["win_deg"])

        # CHECK D: bistability
        bi = _bistability_check(U, tsr_eq)
        print(f"    bistability: free distinct={bi['n_distinct_free']}, "
              f"fixed distinct={bi['n_distinct_fixed']}")

        interp = _interpretation(
            bi["n_distinct_free"], bi["n_distinct_fixed"], gap
        )
        print(f"    interpretation: {interp}")

        case = {
            "U": U,
            "free_tsr_eq": tsr_eq,
            "cp_free": free_cp,
            "cp_fixed_psi0_0": fixed_cp,
            "gap_percent": gap * 100.0,
            "ripple_check": ripple,
            "ledger_ratio_free_over_fixed": ledger,
            "waveform": waveform,
            "bistability": bi,
            "interpretation": interp,
        }
        cases.append(case)

    if not cases:
        raise RuntimeError("No cases could be evaluated; check aep_small.json")

    out = {
        "note": (
            "Diagnostic for the small-rotor free-vs-fixed Cp gap. "
            "Four checks discriminate the cause: (a) Q-omega correlation "
            "from velocity ripple (ripple_check), (b) per-revolution energy "
            "ledger comparison (ledger_ratio_free_over_fixed), "
            "(c) psi(azimuth) waveform comparison including fraction of time "
            "on the stops (waveform), (d) bistability check via free runs "
            "from w0_frac in {0.5, 0.9, 1.5} and fixed runs from psi0_deg "
            "in {-40, -20, 0, 20, 40} (bistability). Numbers and "
            "interpretation are recorded per U."
        ),
        "source": str(AEP_SMALL.relative_to(_ROOT)),
        "cases": cases,
    }
    write_json_with_stamp(
        path=str(OUT_JSON),
        data=out,
        script="scripts/diag_small_equilibria.py",
        version="2.0.0",
        n=len(cases),
        seed=None,
        extra_files=["vawt_presets.py", "scripts/aep_small.json"],
        extra_data={"want_U": want_U},
    )
    print(f"\nWrote {OUT_JSON.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
