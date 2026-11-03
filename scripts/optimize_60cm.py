"""Optimization for a fixed 60cm x 60cm physical prototype.

Fixed geometry: R=0.60m, H=0.60m (Swept area = 0.72 m^2).
Optimizes chord, pivot, arm, counterweight, and electrical load (k_load) 
to maximize Cp while ensuring it self-starts in low wind.
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

# FIXED GEOMETRY
R = 0.60
H = 0.60
N = 3
MB = 0.025  # lighter blades (e.g. 25g each) for a 60cm rotor
XBCG = 0.20

# BOUNDS: [chord, sp, ar, mc, dcw, k_load]
BOUNDS = [
    (0.08, 0.15),    # chord (keep it larger to keep Reynolds number up)
    (0.15, 0.24),    # sp (pivot position)
    (0.20, 0.60),    # ar (arm ratio)
    (0.02, 0.15),    # mc (counterweight mass)
    (-0.30, 0.30),   # dcw (counterweight offset)
    (0.0001, 0.0050), # k_load (FIXED: much lighter electrical load!)
]

PARAM_NAMES = ["c", "sp", "ar", "mc", "dcw", "k_load"]

def objective(x: np.ndarray) -> float:
    c, sp, ar, mc, dcw, k_load = x
    
    # Geometry constraint: rocking arm must fit inside radius
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

    # 1. Startup test 
    try:
        start_res = create_sim_from_params({**params, "U": 4.0, "w0_frac": 0.1, "T_max": 12, "stride": 10}).run()
        if start_res["tsr_eq"] < 1.8:
            return 1000.0
    except (ValueError, RuntimeError):
        return 1000.0

    # 2. Power test at 6.0 m/s (typical wind speed)
    try:
        power_res = create_sim_from_params({**params, "U": 6.0, "w0_frac": 0.9, "T_max": 12, "stride": 10}).run()
        cp = float(power_res["cp"])
        if cp <= 0:
            return 1000.0
    except Exception:  # noqa: BLE001 - simulator may fail for invalid params
        return 1000.0

    return -cp

def main():
    print("=" * 70)
    print("Optimization: 60cm x 60cm Physical Prototype")
    print("=" * 70)

    result = differential_evolution(
        objective, BOUNDS,
        strategy="best1bin", maxiter=10, popsize=12,
        workers=-1, seed=42, updating="deferred", polish=False,
    )

    best_x = result.x
    best_cp = -result.fun
    best_params = dict(zip(PARAM_NAMES, best_x))
    effective_cw = best_params["sp"] + best_params["dcw"]

    print("\n" + "=" * 70)
    print("OPTIMIZATION COMPLETE")
    print("=" * 70)
    print("Winning parameters:")
    print(f"  Chord (c):    {best_params['c']:.4f} m ({best_params['c']*100:.1f} cm)")
    print(f"  Pivot (sp):   {best_params['sp']:.4f}")
    print(f"  Arm (ar):     {best_params['ar']:.4f}")
    print(f"  CW mass:      {best_params['mc']:.4f} kg ({best_params['mc']*1000:.0f} g)")
    print(f"  CW offset:    {best_params['dcw']:.4f}")
    print(f"  k_load:       {best_params['k_load']:.4f}")
    print(f"\nEffective CW offset (sp + dcw): {effective_cw:.4f} m")
    print(f"Cp @ 6 m/s: {best_cp:.4f}")

    # Write to JSON
    output = {
        "schema": "optimization_60cm",
        "winning_params": best_params,
        "cp_at_6mps": best_cp,
        "effective_cw_offset": effective_cw,
    }
    write_json_with_stamp(
        path="scripts/optimization_60cm.json",
        data=output,
        script="scripts/optimize_60cm.py",
        version="1.0.0",
        n=1, seed=42,
        extra_files=["vawt_presets.py"],
        extra_data={"bounds": BOUNDS},
    )
    print("\nResults saved to scripts/optimization_60cm.json")

if __name__ == "__main__":
    try:
        multiprocessing.set_start_method("fork", force=True)
    except RuntimeError:
        pass
    main()