#!/usr/bin/env python3
"""Check two suspicious AEP points with longer runs and several ICs.

1. The fixed-rpm Cp(TSR) curve has a narrow maximum at TSR = 3.25
   (Cp ~= 0.4122) between neighbours near 0.36.  Is it a converged
   operating point or a finite-time transient?
2. The free-running U = 4 m/s point sits near a branch edge.  Does a
   longer run or a different initial condition move it?

The script writes ``scripts/branch_point_checks.json``.  It does not change
the production curves; the result decides whether a point is reported as a
real branch feature or a transient to be replaced.

Usage:
    python3 scripts/check_branch_points.py
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from vawt_core import create_sim_from_params  # noqa: E402
from compute_aep import BASE  # noqa: E402

OUT = os.path.join(_HERE, "branch_point_checks.json")


def summarize(r):
    return dict(cp=float(r["cp"]), tsr_eq=float(r["tsr_eq"]),
                aoa_max=float(r["aoa_max"]),
                steady=bool(r.get("steady", True)),
                stop_pct=float(r.get("stop_pct", 0.0)))


def main():
    out = {
        "note": (
            "Suspicious AEP points re-run with longer T_max and several "
            "initial conditions. 'baseline' matches the production setup. "
            "This is a convergence check, not new measured data."
        ),
        "fixed_tsr_3.25": [],
        "free_U4": [],
    }

    print("Fixed-rpm TSR = 3.25, T_max = 25 vs 60 s, three initial psi:")
    for tm in (25.0, 60.0):
        for psi in (0.0, 120.0, 240.0):
            r = create_sim_from_params({
                **BASE, "free": False, "tsr": 3.25,
                "T_max": tm, "stride": 5, "psi0_deg": psi,
            }).run()
            row = dict(T_max=tm, psi0_deg=psi, **summarize(r))
            out["fixed_tsr_3.25"].append(row)
            print(f"  T_max={tm:4.0f} psi0={psi:5.1f}  Cp={row['cp']:.4f}  "
                  f"TSR={row['tsr_eq']:.3f}  steady={row['steady']}")

    print("\nFree-running U = 4 m/s, T_max = 25 vs 60 s, three seeds:")
    seeds = [(0.90, 0.0), (1.20, 120.0), (0.60, 240.0)]
    for tm in (25.0, 60.0):
        for w0, psi in seeds:
            r = create_sim_from_params({
                **BASE, "free": True, "U": 4.0,
                "T_max": tm, "stride": 5,
                "w0_frac": w0, "psi0_deg": psi,
            }).run()
            row = dict(T_max=tm, w0_frac=w0, psi0_deg=psi, **summarize(r))
            out["free_U4"].append(row)
            print(f"  T_max={tm:4.0f} w0={w0:.2f} psi0={psi:5.1f}  "
                  f"Cp={row['cp']:.4f}  TSR={row['tsr_eq']:.3f}  "
                  f"steady={row['steady']}")

    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
