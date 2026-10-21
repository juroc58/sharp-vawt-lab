#!/usr/bin/env python3
"""Scan the two model-form knobs that control the small-rotor collapse.

* ``cm_scale``: 0 = physical symmetric-section Cm (~0), 1 = raw NeuralFoil
  table.  This is a uniform scale, not a calibrated uncertainty.
* ``tip_loss_multiplier``: residual multiplier on the Helmbold finite-span
  factor (<1 = stronger tip loss).

The scan is deterministic at each anchor's nominal parameters.  It is
stored next to the UQ results and quoted in the README; it is not a
validation against measured data.

Writes ``scripts/cm_scale_scan.json``.

Usage:
    python3 scripts/scan_cm_scale.py
    python3 scripts/scan_cm_scale.py --quick   # cm_scale only
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from vawt_core import create_sim_from_params  # noqa: E402
import uncertainty as U  # noqa: E402

CM_VALUES = [0.0, 0.25, 0.5, 0.75, 1.0]
TIP_VALUES = [0.90, 0.94, 0.95, 0.955, 0.96, 0.98, 1.00]
ANCHORS = ["sharp_cppc", "optimised_passive"]


def run_case(anchor, **overrides):
    p = {**U.ANCHORS[anchor], **overrides}
    r = create_sim_from_params(p).run()
    return {
        "cp": float(r["cp"]),
        "tsr": float(r["tsr_eq"]),
        "aoa_max": float(r["aoa_max"]),
        "steady": bool(r.get("steady", True)),
        "stop_pct": float(r["stop_pct"]),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true",
                    help="scan cm_scale only (skip tip-loss scan)")
    args = ap.parse_args(argv)

    out = {
        "note": (
            "Deterministic scans at the nominal anchor parameters. cm_scale "
            "is a uniform model-form scale: 0 = physical symmetric-section "
            "Cm (~0), 1 = raw NeuralFoil table. tip_loss_multiplier < 1 "
            "means stronger finite-span loss than Helmbold. These are "
            "scenario probes, not measured values."
        ),
        "cm_scale_values": CM_VALUES,
        "tip_loss_multiplier_values": [] if args.quick else TIP_VALUES,
        "anchors": {},
    }

    for anchor in ANCHORS:
        print(f"\n{anchor}")
        cm_rows = []
        for cm in CM_VALUES:
            row = run_case(anchor, cm_scale=cm)
            row["cm_scale"] = cm
            cm_rows.append(row)
            print(f"  cm_scale={cm:.2f}  Cp={row['cp']:.4f}  "
                  f"TSR={row['tsr']:.3f}  steady={row['steady']}")
        entry = {"cm_scale": cm_rows}

        if not args.quick:
            tip_rows = []
            for m in TIP_VALUES:
                row = run_case(anchor, tip_loss_multiplier=m)
                row["tip_loss_multiplier"] = m
                tip_rows.append(row)
                print(f"  tip_mult={m:.3f}  Cp={row['cp']:.4f}  "
                      f"TSR={row['tsr']:.3f}  steady={row['steady']}")
            entry["tip_loss_multiplier"] = tip_rows

        out["anchors"][anchor] = entry

    path = os.path.join(_HERE, "cm_scale_scan.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
