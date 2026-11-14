"""Joint optimization for the 2.7m scaleup model with the new CW insights.

Finds the best (sp, ar, mc, dcw, k_load) to maximize Cp at 8 m/s.
"""
from __future__ import annotations

import multiprocessing
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy.optimize import differential_evolution

from scripts.stamp import write_json_with_stamp
from sharp_vawt import create_sim_from_params

# Fixed geometry for the scaleup machine
R = 2.7179
H = 4.0568
N = 3
MB = 0.92954
XBCG = 0.20

# We optimize: [chord, sp, ar, mc, dcw, k_load]
BOUNDS = [
    (0.30, 0.45),    # chord (was 0.3861)
    (0.12, 0.24),    # sp (push it further forward than 0.2181)
    (0.20, 0.60),    # ar (was 0.3121)
    (0.50, 5.00),    # mc (allow heavier flywheel, was 2.69)
    (-0.40, 0.40),   # dcw 
    (2.00, 8.00),    # k_load (was 4.16)
]

PARAM_NAMES = ["c", "sp", "ar", "mc", "dcw", "k_load"]

def objective(x: np.ndarray) -> float:
    c, sp, ar, mc, dcw, k_load = x
    
    if c * ar >= R * 0.95:
        return 1000.0

    params = {
        "R": R, "H": H, "N": N, "c": c, "sp": sp, "ar": ar,
        "mc": mc, "dcw": dcw, "mb": MB, "xbcg": XBCG,
        "balance": 0, "bias_deg": 0.0, "prescribe_pitch": False,
        "free": True, "k_load": k_load,
        "use_dynamic_stall": True, "use_flow_curvature": True,
        "use_dmst": True, "use_tip_loss": True,
        "win_deg": 45.0, "cb": 2e-5, "mu_c": 3e-4,
    }

    # Startup test at 4.5 m/s (large machines need a bit more wind to start)
    try:
        start_res = create_sim_from_params({**params, "U": 4.5, "w0_frac": 0.1, "T_max": 20, "stride": 10}).run()
        if start_res["tsr_eq"] < 1.8:
            return 1000.0
    except (ValueError, RuntimeError, KeyError, ZeroDivisionError):
        return 1000.0

    # Power test at 8.0 m/s
    try:
        power_res = create_sim_from_params({**params, "U": 8.0, "w0_frac": 0.9, "T_max": 20, "stride": 10}).run()
        cp = float(power_res["cp"])
        if cp <= 0:
            return 1000.0
    except (ValueError, RuntimeError, KeyError, ZeroDivisionError):
        return 1000.0

    return -cp

def main():
    print("Optimizing 2.7m Scaleup...")
    result = differential_evolution(
        objective, BOUNDS,
        strategy="best1bin", maxiter=8, popsize=10,
        workers=-1, seed=42, updating="deferred", polish=False,
    )

    best_x = result.x
    best_cp = -result.fun
    best_params = dict(zip(PARAM_NAMES, best_x))

    print("\nWinning parameters:")
    print(f"  Chord: {best_params['c']:.4f} m")
    print(f"  sp:    {best_params['sp']:.4f}")
    print(f"  ar:    {best_params['ar']:.4f}")
    print(f"  mc:    {best_params['mc']:.4f} kg")
    print(f"  dcw:   {best_params['dcw']:.4f}")
    print(f"  k_load:{best_params['k_load']:.4f}")
    print(f"  Cp @ 8 m/s: {best_cp:.4f}")

    output = {
        "schema": "optimization_scaleup_v2",
        "winning_params": best_params,
        "cp_at_8mps": best_cp,
    }
    write_json_with_stamp(
        path="scripts/optimization_scaleup_v2.json",
        data=output,
        script="scripts/optimize_scaleup_v2.py",
        version="1.0.0",
        n=1, seed=42,
        extra_files=["vawt_presets.py"],
        extra_data={"bounds": BOUNDS},
    )

if __name__ == "__main__":
    try:
        multiprocessing.set_start_method("fork", force=True)
    except RuntimeError:
        pass
    main()