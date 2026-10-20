#!/usr/bin/env python3
"""Scan the finite-span multiplier and record where the small rotor collapses.

The Sharp-inspired anchor has two solution branches: a rotation-sustaining
branch (Cp ~ 0.10) and a collapsed branch (Cp ~ 0.003). The transition is
sharp because the pitch mechanism cannot hold a steady angle of attack once
the lift is reduced below a threshold. A UQ mean/CI that samples only the
upper branch would hide this, so the scan is stored next to the UQ results
and quoted in the README.

Run from anywhere:

    python3 scripts/scan_tip_loss.py

Writes ``scripts/tip_loss_scan.json``.
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
import uncertainty as U  # noqa: E402

MULTIPLIERS = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00, 1.10, 1.20, 1.30]
ANCHORS = ["sharp_cppc", "optimised_passive", "scaleup"]


def main():
    out = {
        "note": (
            "Deterministic scan at each anchor's nominal parameters. "
            "tip_loss_multiplier < 1 means stronger finite-span loss than "
            "the raw generalized Prandtl value. The Sharp-inspired rotor "
            "switches from a rotation-sustaining branch to a collapsed "
            "branch at multiplier ~0.75."
        ),
        "multipliers": MULTIPLIERS,
        "anchors": {},
    }
    for name in ANCHORS:
        rows = []
        for m in MULTIPLIERS:
            params = {**U.ANCHORS[name], "tip_loss_multiplier": m}
            r = create_sim_from_params(params).run()
            rows.append({
                "multiplier": m,
                "cp": float(r["cp"]),
                "tsr": float(r["tsr_eq"]),
                "aoa_max": float(r["aoa_max"]),
                "steady": bool(r.get("steady", True)),
            })
            print(f"{name:18s} m={m:.2f}  Cp={r['cp']:.4f}  "
                  f"TSR={r['tsr_eq']:.3f}")
        out["anchors"][name] = rows
        print()

    path = os.path.join(_HERE, "tip_loss_scan.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
