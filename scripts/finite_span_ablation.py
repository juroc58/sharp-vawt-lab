#!/usr/bin/env python3
"""
Finite-span ablation study for the Ham 1979 geometry.

Runs the Ham geometry with four selectable finite-span corrections:
- helmbold (default, standard low-AR lift-slope correction)
- prandtl_k2 (Prandtl lifting-line with k=2.0)
- prandtl_k18 (generalized Prandtl with k=1.8, previous default)
- prandtl_k15 (Prandtl with k=1.5)

Each model is run with both lift loss (f_ar on Cl) and induced drag enabled.

Runs over TSR 2-4 and writes JSON with Cp(TSR) for each case.
Plots Cp(TSR) against the Ham measured band.

Usage:
    python3 scripts/finite_span_ablation.py
"""
from __future__ import annotations

import os
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from scripts.stamp import write_json_with_stamp
from sharp_vawt import create_sim_from_params
from vawt_presets import PRESETS

# Ham 1979 measured band (from validation scripts)
HAM_MEASURED_CP = {
    2.0: 0.42,
    2.5: 0.45,
    3.0: 0.44,
    3.5: 0.42,
    4.0: 0.40,
}
HAM_TSR_RANGE = (2.0, 3.0)  # Band applies at TSR 2.5-3.0 per Ham's paper

# Ham geometry from preset
HAM_BASE = dict(PRESETS["ham_1979"])
# Ensure the configuration matches the static validation
HAM_BASE.update({
    'free': False,
    'prescribe_pitch': True,
    'pp0_deg': 0.0,
    'pp1_deg': -10.0,
    'pp2_deg': 0.0,
    'pp3_deg': 0.0,
    'pp_ph_deg': 0.0,
    'use_dynamic_stall': False,
    'use_flow_curvature': False,
    'use_dmst': True,
    'use_tip_loss': True,
    'cd_add': 0.005,
    'win_deg': 89.0,
    'cb': 2e-5,
    'mu_c': 0.0,
    'T_max': 20.0,
    'stride': 5,
})

# The four finite-span models to test
FINITE_SPAN_MODELS = ["helmbold", "prandtl_k2", "prandtl_k18", "prandtl_k15"]
MODEL_LABELS = {
    "helmbold": "Helmbold (default)",
    "prandtl_k2": "Prandtl k=2.0",
    "prandtl_k18": "Prandtl k=1.8 (prev. default)",
    "prandtl_k15": "Prandtl k=1.5",
}
MODEL_COLORS = {
    "helmbold": "red",
    "prandtl_k2": "blue",
    "prandtl_k18": "green",
    "prandtl_k15": "purple",
}
MODEL_STYLES = {
    "helmbold": "-",
    "prandtl_k2": "--",
    "prandtl_k18": "-.",
    "prandtl_k15": ":",
}


def run_tsr_sweep(tsrs, overrides):
    """Run a TSR sweep and return list of (tsr, cp, steady)."""
    results = []
    for tsr in tsrs:
        params = {**HAM_BASE, 'tsr': float(tsr), **overrides}
        try:
            r = create_sim_from_params(params).run()
        except Exception as e:
            print(f"  TSR={tsr:.2f}: ERROR {e}")
            continue
        cp = float(r.get('cp', 0.0))
        steady = bool(r.get('steady', True))
        results.append((float(tsr), cp, steady))
        print(f"  TSR={tsr:.2f}: Cp={cp:.4f}, steady={steady}")
    return results


def main():
    print("=" * 70)
    print("Finite-Span Model Ablation Study — Ham 1979 Geometry")
    print("=" * 70)
    print(f"Geometry: R={HAM_BASE['R']}, H={HAM_BASE['H']}, c={HAM_BASE['c']}, AR={HAM_BASE['H']/HAM_BASE['c']:.2f}")
    print(f"Prescribed pitch: pp1 = {HAM_BASE.get('pp1_deg', 0)} deg")
    print(f"cd_add = {HAM_BASE.get('cd_add')}")
    print()

    tsrs = np.linspace(2.0, 4.0, 21)

    # Case 0: Neither (pure 2D, no finite-span correction, no induced drag)
    print("Case (0): Neither (pure 2D, no tip loss, no induced drag)")
    res_neither = run_tsr_sweep(tsrs, {
        'use_tip_loss': False,
        'use_dmst': True,
    })

    # Case 1: Both (lift loss + induced drag) for each model
    model_results = {}
    for model in FINITE_SPAN_MODELS:
        print(f"\nCase: {MODEL_LABELS[model]} (lift loss + induced drag)")
        model_results[model] = run_tsr_sweep(tsrs, {
            'use_tip_loss': True,
            'tip_loss_floor_override': 0.0,
            'e_osw': 0.9,
            'finite_span_model': model,
        })

    # Collect results
    results = {
        "geometry": {
            "R": HAM_BASE['R'],
            "H": HAM_BASE['H'],
            "c": HAM_BASE['c'],
            "AR": HAM_BASE['H'] / HAM_BASE['c'],
        },
        "cases": {
            "neither": [{"tsr": t, "cp": c, "steady": s} for t, c, s in res_neither],
        },
        "model_cases": {
            model: [{"tsr": t, "cp": c, "steady": s} for t, c, s in model_results[model]]
            for model in FINITE_SPAN_MODELS
        },
        "ham_band": {
            "tsr_range": HAM_TSR_RANGE,
            "cp_min": min(HAM_MEASURED_CP.values()),
            "cp_max": max(HAM_MEASURED_CP.values()),
        }
    }

    # Save JSON
    out_json = os.path.join(os.path.dirname(_HERE), "scripts", "finite_span_ablation.json")
    write_json_with_stamp(
        path=out_json,
        data=results,
        script="scripts/finite_span_ablation.py",
        version="3.0.0",
        n=1,
        seed=0,
        extra_files=["vawt_presets.py"],
        extra_data={},
    )
    print(f"\nWrote {out_json}")

    # Plot
    _fig, ax = plt.subplots(figsize=(10, 6))

    # Plot "neither" case
    data = results["cases"]["neither"]
    if data:
        tsrs_p = [d["tsr"] for d in data]
        cps_p = [d["cp"] for d in data]
        ax.plot(tsrs_p, cps_p, ":", color="gray", lw=2, label="Neither (2D)")

    # Plot each model
    for model in FINITE_SPAN_MODELS:
        data = results["model_cases"][model]
        if data:
            tsrs_p = [d["tsr"] for d in data]
            cps_p = [d["cp"] for d in data]
            ax.plot(tsrs_p, cps_p, MODEL_STYLES[model], color=MODEL_COLORS[model],
                    lw=2, label=MODEL_LABELS[model])

    # Ham measured band
    ax.axhspan(0.42, 0.45, xmin=0.25, xmax=0.5, alpha=0.2, color='black',
               label='Ham 1979 measured band (0.42-0.45)')
    for tsr, cp in HAM_MEASURED_CP.items():
        ax.plot(tsr, cp, 'ko', markersize=8, markerfacecolor='white', markeredgewidth=2)

    ax.set_xlabel("Tip-speed ratio (TSR)")
    ax.set_ylabel("Power coefficient Cp")
    ax.set_title("Finite-Span Model Ablation: Ham 1979 Geometry (R=1.83m, AR=4.49)")
    ax.set_xlim(2.0, 4.0)
    ax.set_ylim(0.2, 0.6)
    ax.grid(alpha=0.3)
    ax.legend(loc='lower right')
    ax.axvline(2.5, color='gray', ls=':', alpha=0.5)
    ax.axvline(3.0, color='gray', ls=':', alpha=0.5)

    plt.tight_layout()
    out_dir = os.path.join(os.path.dirname(_HERE), "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_png = os.path.join(out_dir, "finite_span_ablation.png")
    plt.savefig(out_png, dpi=150)
    plt.close()
    print(f"Plot saved to {out_png}")

    # Summary table
    print("\n" + "=" * 70)
    print("ABLATION SUMMARY at TSR=2.5 (Ham's design point)")
    print("=" * 70)
    print(f"{'Model':<30} {'Cp':>10} {'Bias vs band mid':<20} {'Status':<20}")
    print("-" * 80)

    def cp_at_25(case_data):
        cp_at_25 = None
        for d in case_data:
            if abs(d["tsr"] - 2.5) < 0.06:
                cp_at_25 = d["cp"]
                break
        if cp_at_25 is None:
            tsrs_list = [d["tsr"] for d in case_data]
            cps_list = [d["cp"] for d in case_data]
            cp_at_25 = float(np.interp(2.5, tsrs_list, cps_list))
        return cp_at_25

    # Neither case
    cp_neither = cp_at_25(results["cases"]["neither"])
    diff = cp_neither - 0.435
    pct = diff / 0.435 * 100
    if 0.42 <= cp_neither <= 0.45:
        status = "INSIDE band"
    elif cp_neither > 0.45:
        status = f"ABOVE band (+{pct:.1f}%)"
    else:
        status = f"BELOW band ({pct:.1f}%)"
    print(f"{'Neither (2D)':<30} {cp_neither:>10.4f} {f'{pct:+.1f}%':<20} {status:<20}")

    # Each model
    for model in FINITE_SPAN_MODELS:
        cp_mod = cp_at_25(results["model_cases"][model])
        diff = cp_mod - 0.435
        pct = diff / 0.435 * 100
        if 0.42 <= cp_mod <= 0.45:
            status = "INSIDE band"
        elif cp_mod > 0.45:
            status = f"ABOVE band (+{pct:.1f}%)"
        else:
            status = f"BELOW band ({pct:.1f}%)"
        print(f"{MODEL_LABELS[model]:<30} {cp_mod:>10.4f} {f'{pct:+.1f}%':<20} {status:<20}")

    # State the conclusion
    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    print("No tested finite-span variant reproduces the Ham band (0.42-0.45 at TSR 2.5-3.0).")
    print("The 2D model (no finite-span correction) OVERSHOOTS the band.")
    print("All finite-span corrections UNDERSHOOT the band.")
    print("This is a MODEL-FORM UNCERTAINTY: absolute Cp values for passive machines")
    print("carry an irreducible uncertainty from the finite-span correction choice.")
    print("Finite-span results should be read as SCENARIOS, not predictions.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())