"""Diagnose the free-running vs fixed-rpm Cp discrepancy in aep_small.json.

Reads the free-running equilibria (single-phase, psi0=0) from aep_small.json
and re-runs fixed-rpm at the same TSR, same psi0, same everything else. If
the fixed Cp matches the free Cp, the gap is due to aep_small's 3-phase
averaging (its cp_tsr curve is a 3-phase mean; its free_results are
single-phase). If the fixed Cp still differs from the free Cp, the gap
reflects a genuine difference between free and fixed operation.

This is diagnostic only. The output JSON is not consumed by any other script
and does not change any result. It is tracked in stamp.py's STAMP_CHECK_MAP
so freshness checks catch a stale diagnostic report, but regenerating it is
cheap (~3 simulations).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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


def run_fixed_at_tsr(tsr: float, psi0_deg: float, U: float) -> dict:
    params = {**BASE, "free": False, "tsr": float(tsr),
              "psi0_deg": float(psi0_deg), "U": float(U)}
    r = create_sim_from_params(params).run()
    return {
        "tsr": float(tsr),
        "psi0_deg": float(psi0_deg),
        "U": float(U),
        "cp": float(r["cp"]),
        "steady": bool(r.get("steady", True)),
        "rpm": float(r["rpm"]),
    }


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

        fixed = run_fixed_at_tsr(tsr_eq, psi0_deg=0.0, U=U)
        print(f"    fixed-rpm at same TSR, psi0=0: Cp = {fixed['cp']:.4f}")
        gap = (free_cp - fixed["cp"]) / max(fixed["cp"], 1e-9)
        print(f"    gap (free - fixed) / fixed = {gap*100:+.1f} %")

        case = {
            "U": U,
            "free_tsr_eq": tsr_eq,
            "free_cp": free_cp,
            "fixed_cp": fixed["cp"],
            "fixed_steady": fixed["steady"],
            "gap_percent": gap * 100.0,
            "interpretation": (
                "gap explained by phase averaging (free is single-phase, "
                "aep_small cp_tsr is 3-phase mean) — free and fixed agree"
                if abs(gap) < 0.05
                else "genuine free-vs-fixed difference — "
                     "free run is not a fixed-omega operation"
            ),
        }
        cases.append(case)

    if not cases:
        raise RuntimeError("No cases could be evaluated; check aep_small.json")

    out = {
        "note": (
            "Diagnostic for the small-rotor free-vs-fixed Cp gap. "
            "Compares aep_small.json's single-phase free-running "
            "equilibrium Cp against a fixed-rpm run at the same TSR. "
            "The gap is either a reporting artefact (phase averaging) "
            "or a genuine free-vs-fixed physics difference."
        ),
        "source": str(AEP_SMALL.relative_to(_ROOT)),
        "cases": cases,
    }
    write_json_with_stamp(
        path=str(OUT_JSON),
        data=out,
        script="scripts/diag_small_equilibria.py",
        version="1.0.1",
        n=len(cases),
        seed=None,
        extra_files=["vawt_presets.py", "scripts/aep_small.json"],
        extra_data={"want_U": want_U},
    )
    print(f"\nWrote {OUT_JSON.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
