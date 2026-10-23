#!/usr/bin/env python3
"""
Finite-span ablation study for the Ham 1979 geometry.

Runs the Ham geometry with different combinations of finite-span corrections:
(a) Lift loss only (Helmbold f_ar applied to Cl, no induced drag)
(b) Induced drag only (Cd += Cl^2/(pi*e*AR), no lift loss)
(c) Both (current default: Helmbold lift loss + induced drag)
(d) Neither (pure 2D, no finite-span correction)

Runs over TSR 2-4 and writes JSON with Cp(TSR) for each case.
Plots Cp(TSR) against the Ham measured band.

Usage:
    python3 scripts/finite_span_ablation.py
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from vawt_core import create_sim_from_params
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
    print("Finite-Span Ablation Study — Ham 1979 Geometry")
    print("=" * 70)
    print(f"Geometry: R={HAM_BASE['R']}, H={HAM_BASE['H']}, c={HAM_BASE['c']}, AR={HAM_BASE['H']/HAM_BASE['c']:.2f}")
    print(f"Prescribed pitch: pp1 = {HAM_BASE.get('pp1_deg', 0)} deg")
    print(f"cd_add = {HAM_BASE.get('cd_add')}")
    print()

    tsrs = np.linspace(2.0, 4.0, 21)

    # Case (d): Neither - pure 2D, no finite-span correction
    print("Case (d): Neither (pure 2D, no tip loss, no induced drag)")
    res_neither = run_tsr_sweep(tsrs, {
        'use_tip_loss': False,
        'use_dmst': True,
    })

    # Case (a): Lift loss only (Helmbold f_ar on Cl, no induced drag)
    print("\nCase (a): Lift loss only (Helmbold f_ar, no induced drag)")
    res_lift_only = run_tsr_sweep(tsrs, {
        'use_tip_loss': True,
        'tip_loss_floor_override': 0.0,
        'e_osw': 1.0,  # Disable induced drag by setting e=1 (infinite)
    })

    # Case (b): Induced drag only (no lift loss, but induced drag from DMST)
    print("\nCase (b): Induced drag only (no lift loss, DMST induced drag)")
    res_drag_only = run_tsr_sweep(tsrs, {
        'use_tip_loss': True,
        'tip_loss_floor_override': 1.0,  # Disable lift loss by flooring f_ar at 1.0
    })

    # Case (c): Both (current default: Helmbold + induced drag)
    print("\nCase (c): Both (Helmbold f_ar + induced drag, current default)")
    res_both = run_tsr_sweep(tsrs, {
        'use_tip_loss': True,
        'tip_loss_floor_override': 0.0,
        'e_osw': 0.9,  # Default Oswald efficiency
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
            "lift_only": [{"tsr": t, "cp": c, "steady": s} for t, c, s in res_lift_only],
            "drag_only": [{"tsr": t, "cp": c, "steady": s} for t, c, s in res_drag_only],
            "both": [{"tsr": t, "cp": c, "steady": s} for t, c, s in res_both],
        },
        "ham_band": {
            "tsr_range": HAM_TSR_RANGE,
            "cp_min": min(HAM_MEASURED_CP.values()),
            "cp_max": max(HAM_MEASURED_CP.values()),
        }
    }

    # Save JSON
    out_json = os.path.join(os.path.dirname(_HERE), "scripts", "finite_span_ablation.json")
    with open(out_json, "w") as fh:
        json.dump(results, fh, indent=2)
    print(f"\nWrote {out_json}")

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot each case
    for case_name, label, color, style in [
        ("neither", "Neither (2D)", "gray", ":"),
        ("lift_only", "Lift loss only", "blue", "--"),
        ("drag_only", "Induced drag only", "green", "-."),
        ("both", "Both (default)", "red", "-"),
    ]:
        data = results["cases"][case_name]
        if data:
            tsrs = [d["tsr"] for d in data]
            cps = [d["cp"] for d in data]
            ax.plot(tsrs, cps, style, color=color, lw=2, label=label)

    # Ham measured band
    ham_tsr_min, ham_tsr_max = HAM_TSR_RANGE
    cp_min, cp_max = HAM_MEASURED_CP[min(HAM_MEASURED_CP.keys())], HAM_MEASURED_CP[max(HAM_MEASURED_CP.keys())]
    # Actually use the actual measured values
    for tsr in [2.0, 2.5, 3.0, 3.5, 4.0]:
        if tsr in HAM_MEASURED_CP:
            pass  # We'll plot the band

    # Plot measured band as shaded region
    # Ham's band is 0.42-0.45 at TSR 2.5-3.0
    ax.axhspan(0.42, 0.45, xmin=0.25, xmax=0.5, alpha=0.2, color='black', label='Ham 1979 measured band (0.42-0.45)')
    # Plot individual points
    for tsr, cp in HAM_MEASURED_CP.items():
        ax.plot(tsr, cp, 'ko', markersize=8, markerfacecolor='white', markeredgewidth=2)

    ax.set_xlabel("Tip-speed ratio (TSR)")
    ax.set_ylabel("Power coefficient Cp")
    ax.set_title("Finite-Span Ablation: Ham 1979 Geometry (R=1.83m, AR=4.49)")
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
    print(f"{'Case':<20} {'Cp':>10} {'vs Ham band':<20}")
    print("-" * 50)
    for case_name, label, _, _ in [
        ("neither", "Neither (2D)", "", ""),
        ("lift_only", "Lift loss only", "", ""),
        ("drag_only", "Induced drag only", "", ""),
        ("both", "Both (default)", "", ""),
    ]:
        data = results["cases"][case_name]
        # Find Cp at TSR closest to 2.5
        cp_at_25 = None
        for d in results["cases"][case_name]:
            if abs(d["tsr"] - 2.5) < 0.06:
                cp_at_25 = d["cp"]
                break
        if cp_at_25 is None:
            # Interpolate
            tsrs = [d["tsr"] for d in results["cases"][case_name]]
            cps = [d["cp"] for d in results["cases"][case_name]]
            cp_at_25 = float(np.interp(2.5, tsrs, cps))
        
        # Compare to Ham band midpoint (0.435)
        diff = cp_at_25 - 0.435
        pct = diff / 0.435 * 100
        status = ""
        if 0.42 <= cp_at_25 <= 0.45:
            status = "INSIDE band"
        elif cp_at_25 > 0.45:
            status = f"ABOVE band (+{pct:.1f}%)"
        else:
            status = f"BELOW band ({pct:.1f}%)"
        print(f"{label:<20} {cp_at_25:>10.4f} {status:<20}")

    return 0


if __name__ == "__main__":
    sys.exit(main())