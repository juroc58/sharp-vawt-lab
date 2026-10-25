"""
Dynamic-stall sensitivity test.

The most important robustness check: is the optimised Cp real, or is the
model exploiting the (uncalibrated) dynamic-stall increment?

Runs the optimiser's prescribed-pitch design point with the DS model on
and off. The README claim is ΔCp < 3 % at this point; this script prints
the delta and exits non-zero if it exceeds the tolerance, so it can be
wired into CI.

Also computes DS sensitivity for the two passive headline anchors.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.stamp import write_json_with_stamp
from sharp_vawt import create_sim_from_params
from vawt_presets import PRESETS

# Prescribed-pitch optimiser design point (from optimization_actuator.json)
DESIGN = {
    "R": 0.60, "H": 0.40, "N": 3, "c": 0.117607,
    "ar": 0.31, "sp": 0.18,
    "mb": 0.010, "xbcg": 0.20, "mc": 0.040, "dcw": -0.132,
    "balance": 0, "bias_deg": -1.1,
    "tsr": 2.14487, "k_load": 0.00149992,
    "pp0_deg": +5.15612, "pp1_deg": -6.32883,
    "pp2_deg": +2.75837, "pp3_deg": -0.0845207,
    "cd_add": 0.002,
    "use_flow_curvature": True,
    "use_dmst": True, "use_tip_loss": False,
    "win_deg": 45.0, "cb": 2e-5, "mu_c": 3e-4,
    "free": True, "T_max": 30.0, "stride": 5,
    "prescribe_pitch": True, "w0_frac": 0.9,
}

# Passive headline anchors from vawt_presets.py
PASSIVE_ANCHORS = {
    "sharp_cppc": PRESETS["sharp_cppc"],
    "optimised_passive": PRESETS["optimised_passive"],
}

CASES = [
    ("full model",           {}),
    ("no dynamic stall",     {"use_dynamic_stall": False}),
    ("no DS, no curvature",  {"use_dynamic_stall": False,
                                  "use_flow_curvature": False}),
]

TOL = 0.03   # README claim: ΔCp < 3 % at prescribed-pitch design point


def run_cases(base_params: dict[str, Any], overrides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run multiple cases with different overrides on the same base params."""
    out = []
    for label, override in overrides:
        r = create_sim_from_params({**base_params, **override}).run()
        out.append({
            "label": label,
            "cp": r['cp'],
            "aoa_max": r['aoa_max'],
            "tsr_eq": r['tsr_eq'],
            "rpm": r['rpm'],
        })
    return out


def compute_ds_sensitivity(base_params: dict[str, Any]) -> dict[str, float]:
    """Compute DS sensitivity for a given base parameter set."""
    r_ds = create_sim_from_params({**base_params, 'use_dynamic_stall': True}).run()
    r_nods = create_sim_from_params({**base_params, 'use_dynamic_stall': False}).run()
    cp_ds = r_ds['cp']
    cp_nods = r_nods['cp']
    delta_abs = cp_ds - cp_nods
    delta_rel = abs(delta_abs) / max(abs(cp_ds), 1e-9)
    return {
        "cp_ds_on": cp_ds,
        "cp_ds_off": cp_nods,
        "delta_abs": delta_abs,
        "delta_rel": delta_rel,
    }


def main():
    # 1. Prescribed-pitch design point (optimiser result)
    rows = run_cases(DESIGN, CASES)

    print("Dynamic-stall sensitivity - optimiser design point")
    print("=" * 60)
    print(f"{'case':<25} {'Cp':>9} {'alpha_max':>12}")
    print("-" * 60)
    for row in rows:
        print(f"{row['label']:<25} {row['cp']:>9.4f} {row['aoa_max']:>12.2f}")

    full = rows[0]['cp']
    no_ds = rows[1]['cp']
    delta = abs(full - no_ds) / max(abs(full), 1e-9)

    print()
    print(f"  delta Cp (DS on vs off) = {delta * 100:.2f} %  "
          f"(tolerance {TOL * 100:.0f} %)")
    print()

    # 2. Passive anchors
    passive_results = {}
    print("Dynamic-stall sensitivity - passive headline anchors")
    print("=" * 60)
    for name, params in PASSIVE_ANCHORS.items():
        sens = compute_ds_sensitivity(params)
        passive_results[name] = sens
        print(f"  {name}:")
        print(f"    DS on:  Cp = {sens['cp_ds_on']:.6f}")
        print(f"    DS off: Cp = {sens['cp_ds_off']:.6f}")
        print(f"    drop:   {sens['delta_rel'] * 100:.1f} %  "
              f"({sens['cp_ds_on']:.4f} -> {sens['cp_ds_off']:.4f})")

    sharp_drop_pct = passive_results['sharp_cppc']['delta_rel'] * 100
    opt_drop_pct = passive_results['optimised_passive']['delta_rel'] * 100

    print()
    print(
        f"Note: this check runs at a prescribed-pitch design point where "
        f"alpha_max stays below stall. A small delta Cp here does NOT "
        f"imply the passive case is DS-insensitive: switching DS off drops "
        f"Cp by {sharp_drop_pct:.0f} % at the Sharp-inspired anchor "
        f"({passive_results['sharp_cppc']['cp_ds_on']:.3f} -> "
        f"{passive_results['sharp_cppc']['cp_ds_off']:.3f}) and "
        f"{opt_drop_pct:.0f} % at the optimised-passive anchor "
        f"({passive_results['optimised_passive']['cp_ds_on']:.3f} -> "
        f"{passive_results['optimised_passive']['cp_ds_off']:.3f})."
    )

    if delta < TOL:
        print("\nPASS: DS model is not driving the result at this point.")
    else:
        print(f"\nFAIL: DS sensitivity {delta*100:.1f}% exceeds {TOL*100:.0f}%.")

    # 3. Write JSON output with stamp
    output = {
        "prescribed_pitch": {
            "cases": rows,
            "delta_rel": delta,
            "tolerance": TOL,
            "pass": delta < TOL,
        },
        "passive_anchors": passive_results,
    }

    write_json_with_stamp(
        path="scripts/validate_ds_off.json",
        data=output,
        script="scripts/validate_ds_off.py",
        version="1.1.0",
        n=1,
        extra_files=["vawt_presets.py"],
    )
    print("\nWrote scripts/validate_ds_off.json")

    return 0 if delta < TOL else 1


if __name__ == "__main__":
    raise SystemExit(main())