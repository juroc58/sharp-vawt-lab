"""Targeted optimization for shifted chord / forward counterweight geometry.

This forces the optimizer to explore the regime where:
- The pivot is far back (sp up to 0.28)
- The counterweight is far forward (dcw down to -0.60)
- The counterweight is heavy (mc up to 500g)

We want to see if a heavy pendulum effect can stabilize a highly aft pivot point.
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

# Fixed geometry
R = 0.906
H = 1.353
N = 3
MB = 0.045
XBCG = 0.20
K_LOAD = 0.0193  # Hoverboard motor

# AGGRESSIVE BOUNDS
BOUNDS = [
    (0.13, 0.17),    # c - Chord (keep it reasonable)
    (0.20, 0.28),    # sp - Pivot heavily aft
    (0.20, 0.50),    # ar - Arm length
    (0.02, 0.50),    # mc - Allow up to 500g counterweight!
    (-0.60, -0.10),  # dcw - Force CW far forward (negative = ahead of LE)
]

PARAM_NAMES = ["c", "sp", "ar", "mc", "dcw"]

def objective(x: np.ndarray) -> float:
    c, sp, ar, mc, dcw = x
    
    # Check physical constraint: blade must not overlap the shaft
    if c * ar >= R * 0.95:
        return 1000.0

    params = {
        "R": R, "H": H, "N": N, "c": c, "sp": sp, "ar": ar,
        "mc": mc, "dcw": dcw, "mb": MB, "xbcg": XBCG,
        "balance": 0, "bias_deg": 0.0, "prescribe_pitch": False,
        "free": True, "k_load": K_LOAD,
        "use_dynamic_stall": True, "use_flow_curvature": True,
        "use_dmst": True, "use_tip_loss": True,
        "win_deg": 45.0, "cb": 2e-5, "mu_c": 3e-4,
    }

    # 1. Startup test
    try:
        start_res = create_sim_from_params({**params, "U": 4.0, "w0_frac": 0.1, "T_max": 12, "stride": 10}).run()
        if start_res["tsr_eq"] < 1.8:
            return 1000.0
    except Exception:  # noqa: BLE001 - simulator may fail for invalid params
        return 1000.0

    # 2. Power test
    try:
        power_res = create_sim_from_params({**params, "U": 7.0, "w0_frac": 0.9, "T_max": 12, "stride": 10}).run()
        cp = float(power_res["cp"])
        if cp <= 0:
            return 1000.0
    except Exception:  # noqa: BLE001 - simulator may fail for invalid params
        return 1000.0

    return -cp

def main():
    print("=" * 70)
    print("Optimization: Shifted Chord + Forward Heavy Counterweight")
    print("=" * 70)
    print("Bounds:")
    for name, (lo, hi) in zip(PARAM_NAMES, BOUNDS):
        print(f"  {name:6s} ∈ [{lo}, {hi}]")
    print()

    result = differential_evolution(
        objective, BOUNDS,
        strategy="best1bin",
        maxiter=10,
        popsize=12,
        workers=-1,
        seed=42,
        updating="deferred",
        polish=False,
    )

    best_x = result.x
    best_cp = -result.fun
    best_params = dict(zip(PARAM_NAMES, best_x))
    effective_cw = best_params["sp"] + best_params["dcw"]

    print("\n" + "=" * 70)
    print("OPTIMIZATION COMPLETE")
    print("=" * 70)
    print("Winning parameters:")
    print(f"  Chord (c):  {best_params['c']:.4f} m ({best_params['c']*100:.1f} cm)")
    print(f"  Pivot (sp): {best_params['sp']:.4f}")
    print(f"  Arm (ar):   {best_params['ar']:.4f}")
    print(f"  CW mass:    {best_params['mc']:.4f} kg ({best_params['mc']*1000:.0f} g)")
    print(f"  CW offset:  {best_params['dcw']:.4f}")
    print(f"\nEffective CW offset from pivot (sp + dcw): {effective_cw:.4f} m")
    print(f"Cp @ 7 m/s: {best_cp:.4f}")

    # Write to JSON
    output = {
        "schema": "optimization_cw_forward",
        "winning_params": best_params,
        "cp_at_7mps": best_cp,
        "effective_cw_offset": effective_cw,
    }
    write_json_with_stamp(
        path="scripts/optimization_cw_forward.json",
        data=output,
        script="scripts/optimize_cw_forward.py",
        version="1.0.0",
        n=1, seed=42,
        extra_files=["vawt_presets.py"],
        extra_data={"bounds": BOUNDS},
    )
    print("\nResults saved to scripts/optimization_cw_forward.json")

if __name__ == "__main__":
    try:
        multiprocessing.set_start_method("fork", force=True)
    except RuntimeError:
        pass
    main()