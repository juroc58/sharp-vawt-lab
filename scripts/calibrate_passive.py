"""Calibrate passive-pitch VAWT parameters to measured power data.

Fits ``cd_add`` (strut/interference drag) and ``tip_loss_multiplier`` to
measured power-vs-wind-speed data from the 1/3 scale prototype
(:data:`PRESETS["prototype_1_3"]`).

The objective function runs the BEM simulator at each measured wind speed
with the candidate parameters, computes the predicted power
(``Cp * 0.5 * rho * A * U^3 * 0.9``), and returns the residual against the
measured power.  ``scipy.optimize.least_squares`` minimizes the sum of
squared residuals (equivalently, the RMSE).

This tool deliberately does *not* attempt to fit dynamic-stall constants
(``ds_Tf``, ``ds_Tv``, ``ds_Ta``) or the time-reversal parameter
``tau_rev``.  Those require time-resolved per-blade pitch and force data,
which this script does not have access to.  Only steady-state power-curve
fitting is supported.

Usage::

    python3 scripts/calibrate_passive.py --data data/measured.csv \
        --out scripts/calibration_results.json --provenance measured
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

# This block fixes the import path so it works from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy.optimize import least_squares

from scripts.stamp import write_json_with_stamp
from sharp_vawt import create_sim_from_params
from vawt_presets import PRESETS

RHO = 1.225  # kg/m^3, air density (matches AeroConfig default)
BASE_PRESET = PRESETS["prototype_1_3"]


def load_measured_data(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Load ``Wind_Speed_m_s`` and ``Power_W`` from a CSV file.

    Only rows with ``Wind_Speed_m_s > 3.0`` and ``Power_W > 0`` are kept.
    """
    wind_speeds: list[float] = []
    powers: list[float] = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                u = float(row["Wind_Speed_m_s"])
                p = float(row["Power_W"])
            except (KeyError, ValueError, TypeError):
                continue
            if u > 3.0 and p > 0:
                wind_speeds.append(u)
                powers.append(p)
    return np.array(wind_speeds), np.array(powers)


def load_or_generate_data(args: argparse.Namespace) -> tuple[np.ndarray, np.ndarray]:
    """Load measured data from CSV or generate synthetic data from PRESETS."""
    if args.generate_synthetic:
        return _generate_synthetic_data()
    return load_measured_data(args.data)


def _generate_synthetic_data() -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic data from PRESETS['prototype_1_3'].

    Runs the simulator at U in [4, 5, 6, 7, 8, 9, 10] using the preset
    parameters, computes power via P = Cp * 0.5 * rho * A * U^3 * 0.9,
    and adds 5% random noise.
    """
    import random

    random.seed(42)
    np.random.seed(42)

    wind_speeds = [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    powers = []
    for U in wind_speeds:
        params = {
            **BASE_PRESET,
            "free": True,
            "U": U,
            "w0_frac": 0.9,
        }
        result = create_sim_from_params(params).run()
        cp = float(result["cp"])
        power = cp * 0.5 * RHO * 2.0 * BASE_PRESET["R"] * BASE_PRESET["H"] * U**3 * 0.9
        # Add 5% random noise
        noise = 1.0 + np.random.uniform(-0.05, 0.05)
        powers.append(power * noise)
    return np.array(wind_speeds), np.array(powers)


def _simulate_cp(cd_add: float, tip_loss_multiplier: float, U: float) -> float:
    """Run the simulator and return Cp at wind speed U."""
    params = {
        **BASE_PRESET,
        "cd_add": cd_add,
        "tip_loss_multiplier": tip_loss_multiplier,
        "U": U,
        "free": True,
        "w0_frac": 0.9,
    }
    result = create_sim_from_params(params).run()
    return float(result["cp"])


def compute_predicted_power(cd_add: float, tip_loss_multiplier: float, U: float) -> float:
    """Compute predicted power at wind speed U with given parameters."""
    cp = _simulate_cp(cd_add, tip_loss_multiplier, U)
    R = BASE_PRESET["R"]
    H = BASE_PRESET["H"]
    A = 2.0 * R * H  # swept area of the VAWT
    return cp * 0.5 * RHO * A * U**3 * 0.9


def objective(
    x: np.ndarray, wind_speeds: np.ndarray, measured_powers: np.ndarray
) -> np.ndarray:
    """Return residuals (predicted - measured) for least_squares."""
    cd_add, tip_loss_multiplier = x
    predicted = np.array(
        [
            compute_predicted_power(cd_add, tip_loss_multiplier, U)
            for U in wind_speeds
        ]
    )
    return predicted - measured_powers


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Calibrate cd_add and tip_loss_multiplier to measured power data."
    )
    ap.add_argument("--data", type=str, required=False, help="Path to measured CSV")
    ap.add_argument(
        "--generate-synthetic",
        action="store_true",
        help="Generate synthetic data from PRESETS['prototype_1_3'] instead of reading --data",
    )
    ap.add_argument("--out", type=str, required=True, help="Path to output JSON")
    ap.add_argument(
        "--provenance",
        type=str,
        choices=["measured", "synthetic"],
        default="synthetic",
        help="Data provenance (default: synthetic)",
    )
    args = ap.parse_args()

    wind_speeds, measured_powers = load_or_generate_data(args)

    if len(wind_speeds) == 0:
        print("No valid data points found after filtering.")
        sys.exit(1)

    # Initial guess: use preset defaults
    cd_add_init = float(BASE_PRESET.get("cd_add", 0.002))
    tip_loss_init = float(BASE_PRESET.get("tip_loss_multiplier", 1.0))
    x0 = np.array([cd_add_init, tip_loss_init])

    # Initial RMSE
    initial_residuals = objective(x0, wind_speeds, measured_powers)
    rmse_initial = float(np.sqrt(np.mean(initial_residuals**2)))

    # Optimize
    bounds = ([0.001, 0.7], [0.010, 1.3])
    result = least_squares(
        objective, x0, bounds=bounds, args=(wind_speeds, measured_powers)
    )
    cd_add_opt, tip_loss_opt = result.x

    # Final RMSE
    final_residuals = objective(result.x, wind_speeds, measured_powers)
    rmse_final = float(np.sqrt(np.mean(final_residuals**2)))

    improvement_percent = (
        (rmse_initial - rmse_final) / rmse_initial * 100.0
        if rmse_initial > 0
        else 0.0
    )

    # Determine status
    if args.provenance == "synthetic":
        status = "not_calibrated"
        print(
            "WARNING: provenance is 'synthetic' — status set to 'not_calibrated'. "
            "Synthetic data proves tooling only."
        )
    else:
        status = "calibrated"

    output = {
        "status": status,
        "provenance": args.provenance,
        "fitted_parameters": {
            "cd_add": float(cd_add_opt),
            "tip_loss_multiplier": float(tip_loss_opt),
        },
        "rmse_initial": rmse_initial,
        "rmse_final": rmse_final,
        "improvement_percent": improvement_percent,
    }

    write_json_with_stamp(
        path=args.out,
        data=output,
        script="scripts/calibrate_passive.py",
        version="1.0.1",
        n=len(wind_speeds),
        seed=None,
        extra_files=["vawt_presets.py"],
        extra_data={
            "data_path": args.data,
            "provenance": args.provenance,
        },
        script_args=sys.argv[1:],
    )

    print(f"Status: {status}")
    print(f"Provenance: {args.provenance}")
    print(f"Fitted cd_add: {cd_add_opt:.6f}")
    print(f"Fitted tip_loss_multiplier: {tip_loss_opt:.6f}")
    print(f"RMSE initial: {rmse_initial:.4f} W")
    print(f"RMSE final: {rmse_final:.4f} W")
    print(f"Improvement: {improvement_percent:.2f}%")
    print(f"Written to {args.out}")


if __name__ == "__main__":
    main()