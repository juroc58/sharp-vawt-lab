"""Joint optimization of sp, ar, mc, dcw for the 1/3 scale prototype.

This optimizer explores the joint (sp, ar, mc, dcw) space to find designs
where the counterweight contributes meaningful restoring torque via a
larger effective CW offset from the pivot. The previous optimizer fixed
mc and let balance=1 solve dcw, which always converged to dcw ≈ -sp
(CW at pivot, no restoring contribution). This optimizer avoids that
degeneracy by treating dcw as a free parameter.

The prototype geometry is fixed at R=0.906 m, H=1.353 m, N=3 blades,
mb=0.045 kg, xbcg=0.20 m. k_load is held fixed at 0.0193 (the hoverboard
motor resistance is a hardware constraint). balance=0 is used so mc and
dcw are explicit parameters rather than auto-solved.

The optimization maximizes Cp at U=7 m/s subject to self-starting at
U=4 m/s (tsr_eq >= 1.8 required).
"""
from __future__ import annotations

import multiprocessing
import os
import sys

# This block fixes the import path so it works from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy.optimize import differential_evolution

from scripts.stamp import write_json_with_stamp
from sharp_vawt import create_sim_from_params

# Fixed geometry parameters (from prototype_1_3 preset)
R = 0.906
H = 1.353
N = 3
MB = 0.045
XBCG = 0.20
BALANCE = 0  # explicit mc/dcw, not auto-solved
K_LOAD = 0.0193  # hoverboard motor resistance - hardware constraint

# Bounds for the 5 optimized parameters: c, sp, ar, mc, dcw
BOUNDS = [
    (0.11, 0.19),  # c - chord
    (0.15, 0.24),  # sp - pivot position
    (0.20, 0.55),  # ar - aspect ratio
    (0.02, 0.25),  # mc - counterweight mass
    (-0.40, 0.40),  # dcw - counterweight offset from pivot
]

# Parameter names for mapping results back
PARAM_NAMES = ["c", "sp", "ar", "mc", "dcw"]

TSR_STARTUP_THRESHOLD = 1.8


def simulate_cp_and_startup(params: dict) -> tuple[float, float, bool]:
    """Run startup test then power test.

    Returns (cp, startup_tsr, startup_success) or (1000.0, 0.0, False)
    if startup fails.
    """
    # Startup test at U=4.0, w0_frac=0.1
    startup_params = {**params, "U": 4.0, "w0_frac": 0.1, "T_max": 12, "stride": 10}
    try:
        start_res = create_sim_from_params(startup_params).run()
        startup_tsr = float(start_res["tsr_eq"])
        startup_success = startup_tsr >= TSR_STARTUP_THRESHOLD
    except Exception:  # noqa: BLE001 - simulator may fail for invalid params
        return 1000.0, 0.0, False

    if not startup_success:
        return 1000.0, startup_tsr, False

    # Power test at U=7.0, w0_frac=0.9
    power_params = {**params, "U": 7.0, "w0_frac": 0.9, "T_max": 12, "stride": 10}
    try:
        power_res = create_sim_from_params(power_params).run()
        cp = float(power_res["cp"])
    except Exception:  # noqa: BLE001 - simulator may fail for invalid params
        return 1000.0, startup_tsr, False

    if cp <= 0:
        return 1000.0, startup_tsr, False

    return cp, startup_tsr, True


def objective(x: np.ndarray) -> float:
    """Objective function for differential_evolution.

    Returns -cp to minimize (i.e., maximize Cp).
    Returns 1000.0 if startup fails or cp <= 0.
    """
    param_dict = {
        "R": R,
        "H": H,
        "N": N,
        "c": x[0],
        "sp": x[1],
        "ar": x[2],
        "mc": x[3],
        "dcw": x[4],
        "mb": MB,
        "xbcg": XBCG,
        "balance": BALANCE,
        "bias_deg": 0.0,
        "prescribe_pitch": False,
        "free": True,
        "k_load": K_LOAD,
        "use_dynamic_stall": True,
        "use_flow_curvature": True,
        "use_dmst": True,
        "use_tip_loss": True,
        "win_deg": 45.0,
        "cb": 2e-5,
        "mu_c": 3e-4,
    }

    cp, _startup_tsr, success = simulate_cp_and_startup(param_dict)

    if not success or cp <= 0:
        return 1000.0

    return -cp


def power_curve(cd_add: float, tip_loss_multiplier: float) -> list[dict]:
    """Compute power curve at U in [4, 5, 6, 7, 8, 10]."""
    base = {
        "R": R,
        "H": H,
        "N": N,
        "c": best_params["c"],
        "sp": best_params["sp"],
        "ar": best_params["ar"],
        "mc": best_params["mc"],
        "dcw": best_params["dcw"],
        "mb": MB,
        "xbcg": XBCG,
        "balance": BALANCE,
        "bias_deg": 0.0,
        "prescribe_pitch": False,
        "free": True,
        "k_load": K_LOAD,
        "use_dynamic_stall": True,
        "use_flow_curvature": True,
        "use_dmst": True,
        "use_tip_loss": True,
        "win_deg": 45.0,
        "cb": 2e-5,
        "mu_c": 3e-4,
    }

    curve = []
    for U in [4.0, 5.0, 6.0, 7.0, 8.0, 10.0]:
        params = {**base, "U": U, "w0_frac": 0.9, "T_max": 12, "stride": 10}
        try:
            res = create_sim_from_params(params).run()
            curve.append(
                {
                    "U": U,
                    "cp": float(res["cp"]),
                    "tsr_eq": float(res["tsr_eq"]),
                    "rpm": float(res["rpm"]),
                }
            )
        except Exception:  # noqa: BLE001 - simulator may fail for invalid params
            curve.append({"U": U, "cp": None, "tsr_eq": None, "rpm": None})

    return curve


def main() -> None:
    global best_params

    print("=" * 70)
    print("Prototype V2 Optimization - Joint (sp, ar, mc, dcw) search")
    print("=" * 70)
    print(f"Fixed geometry: R={R} m, H={H} m, N={N}")
    print(f"Fixed mass: mb={MB} kg, xbcg={XBCG} m")
    print(f"Fixed k_load={K_LOAD} (hoverboard motor resistance)")
    print(f"balance={BALANCE} (explicit mc/dcw, not auto-solved)")
    print()
    print("Parameter bounds:")
    for name, (lo, hi) in zip(PARAM_NAMES, BOUNDS):
        print(f"  {name:8s} ∈ [{lo}, {hi}]")
    print()

    # Run differential evolution
    result = differential_evolution(
        objective,
        BOUNDS,
        strategy="best1bin",
        maxiter=8,
        popsize=10,
        workers=-1,
        seed=42,
        updating="deferred",
        polish=False,
    )

    best_x = result.x
    best_cp = -result.fun
    best_params = dict(zip(PARAM_NAMES, best_x))

    print("\n" + "=" * 70)
    print("OPTIMIZATION COMPLETE")
    print("=" * 70)
    print()
    print("Winning parameters:")
    print(f"  c     = {best_params['c']:.6f} m")
    print(f"  sp    = {best_params['sp']:.6f} (pivot position)")
    print(f"  ar    = {best_params['ar']:.6f} (aspect ratio)")
    print(f"  mc    = {best_params['mc']:.6f} kg")
    print(f"  dcw   = {best_params['dcw']:.6f} m")
    print(f"  Cp @ 7 m/s = {best_cp:.6f}")
    print()

    effective_cw_offset = best_params["sp"] + best_params["dcw"]
    print(f"Effective CW offset from pivot (sp + dcw) = {effective_cw_offset:.6f} m")
    print()

    # Re-verify startup
    verify_params = {
        **best_params,
        "R": R,
        "H": H,
        "N": N,
        "mb": MB,
        "xbcg": XBCG,
        "balance": BALANCE,
        "bias_deg": 0.0,
        "prescribe_pitch": False,
        "free": True,
        "k_load": K_LOAD,
        "use_dynamic_stall": True,
        "use_flow_curvature": True,
        "use_dmst": True,
        "use_tip_loss": True,
        "win_deg": 45.0,
        "cb": 2e-5,
        "mu_c": 3e-4,
    }
    _cp_verify, startup_tsr, startup_ok = simulate_cp_and_startup(verify_params)
    print("Startup verification at U=4 m/s:")
    print(f"  tsr_eq = {startup_tsr:.4f}")
    print(f"  Self-start: {'PASS' if startup_ok else 'FAIL'}")
    print()

    # Power curve
    curve = power_curve(cd_add=0.002, tip_loss_multiplier=1.0)
    print("Power curve (U ∈ [4, 5, 6, 7, 8, 10]):")
    for point in curve:
        print(f"  U={point['U']:4.1f} m/s: Cp={point['cp']:.4f}, "
              f"TSR={point['tsr_eq']:.3f}, RPM={point['rpm']:.1f}")
    print()

    # Build output JSON
    output = {
        "schema": "prototype_v2_optimization",
        "winning_params": {
            "c": float(best_params["c"]),
            "sp": float(best_params["sp"]),
            "ar": float(best_params["ar"]),
            "mc": float(best_params["mc"]),
            "dcw": float(best_params["dcw"]),
        },
        "cp_at_7mps": float(best_cp),
        "effective_cw_offset": float(effective_cw_offset),
        "startup_tsr": float(startup_tsr),
        "startup_success": bool(startup_ok),
        "power_curve": curve,
    }

    write_json_with_stamp(
        path="scripts/optimization_prototype_v2.json",
        data=output,
        script="scripts/optimize_prototype_v2.py",
        version="1.0.1",
        n=1,
        seed=42,
        extra_files=["vawt_presets.py"],
        extra_data={"bounds": BOUNDS, "param_names": PARAM_NAMES},
        script_args=None,
    )
    print("\nResults written to scripts/optimization_prototype_v2.json")


if __name__ == "__main__":
    try:
        multiprocessing.set_start_method("fork", force=True)
    except RuntimeError:
        pass
    main()