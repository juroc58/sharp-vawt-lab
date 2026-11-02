"""Parametric sweep tool for VAWT mechanical parameters.

Sweeps a single parameter (e.g. pivot position ``sp``, aspect ratio ``ar``,
chord ``c``) across a range of values while automatically solving the
counterweight offset ``dcw`` via ``balance=1``.  For each value it runs:

1. A normal fixed-rpm simulation at the test wind speed ``--U``.
2. A fixed-rpm startup simulation at ``--startup-U`` with low initial
   speed ratio (``w0_frac=0.1``) to check self-starting behaviour.

Results are printed as a table and written to a CSV file.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

# This block fixes the import path so it works from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sharp_vawt import create_sim_from_params
from vawt_presets import PRESETS

DEFAULT_VALUES = "0.15,0.18,0.20,0.22,0.25"


def parse_values(values_str: str) -> list[float]:
    """Parse a comma-separated string of floats."""
    return [float(v.strip()) for v in values_str.split(",") if v.strip()]


def run_sweep(
    param: str,
    values: list[float],
    U: float,
    startup_U: float,
    out_path: str,
) -> None:
    """Sweep ``param`` across ``values`` and write results to ``out_path``."""
    base = PRESETS["prototype_1_3"].copy()

    # Use balance=1 so the engine solves for dcw automatically.
    base["balance"] = 1
    base["mc"] = 0.1243  # Keep the 124 g weight

    rows: list[dict] = []

    print(
        f"{'Param value':<12} | {'Solved dcw':<12} | {'Cp @ U':<10} | {'RPM @ U':<10} | {'Startup @ U':<14} | {'Self-start'}"
    )
    print("-" * 80)

    for val in values:
        params = {**base, param: val, "U": U, "w0_frac": 0.9}

        try:
            # Normal-speed run
            sim = create_sim_from_params(params)
            solved_dcw = sim.dcw
            res = sim.run()

            # Startup test
            start_params = {**params, "U": startup_U, "w0_frac": 0.1}
            start_sim = create_sim_from_params(start_params)
            start_res = start_sim.run()
            startup_tsr = start_res["tsr_eq"]
            startup_success = startup_tsr > 1.8

            rows.append(
                {
                    "param_value": val,
                    "solved_dcw": solved_dcw,
                    "cp": res["cp"],
                    "rpm": res["rpm"],
                    "startup_tsr": startup_tsr,
                    "startup_success": startup_success,
                }
            )

            print(
                f"{val:<12.4f} | {solved_dcw:<12.4f} | {res['cp']:<10.4f} | "
                f"{res['rpm']:<10.1f} | {startup_tsr:<14.3f} | {'YES' if startup_success else 'NO'}"
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "param_value": val,
                    "solved_dcw": None,
                    "cp": None,
                    "rpm": None,
                    "startup_tsr": None,
                    "startup_success": False,
                }
            )
            print(f"{val:<12.4f} | ERROR: {exc}")

    # Write CSV
    fieldnames = [
        "param_value",
        "solved_dcw",
        "cp",
        "rpm",
        "startup_tsr",
        "startup_success",
    ]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nResults written to {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Parametric sweep tool for VAWT mechanical parameters."
    )
    ap.add_argument(
        "--param",
        type=str,
        default="sp",
        help="Parameter to sweep (e.g. 'sp', 'ar', 'c').",
    )
    ap.add_argument(
        "--values",
        type=str,
        default=DEFAULT_VALUES,
        help="Comma-separated parameter values.",
    )
    ap.add_argument(
        "--U",
        type=float,
        default=6.0,
        help="Wind speed for the Cp test (m/s).",
    )
    ap.add_argument(
        "--startup-U",
        type=float,
        default=4.0,
        help="Wind speed for the startup test (m/s).",
    )
    ap.add_argument(
        "--out",
        type=str,
        default="data/experiment_pivot_results.csv",
        help="Output CSV path.",
    )
    args = ap.parse_args()

    values = parse_values(args.values)
    run_sweep(args.param, values, args.U, args.startup_U, args.out)


if __name__ == "__main__":
    main()