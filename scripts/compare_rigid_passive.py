"""Compare passive CPPC vs rigid fixed-pitch baseline at same geometry.

Compares:
1. Passive CPPC (prescribe_pitch=False) - free-running pitch control
2. Fixed-rpm rigid baseline (prescribe_pitch=True, pp0_deg=optimal constant pitch)

Sweeps TSR from 1.0 to 4.0 and plots Cp vs TSR for both strategies.

Usage:
    python3 scripts/compare_rigid_passive.py
    python3 scripts/compare_rigid_passive.py --out docs/cp_rigid_vs_passive.png
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# This block fixes the import path so it works from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from scripts.plot_style import (
    COL_PASSIVE_FIXED,
    COL_PASSIVE_KLOAD,
    FONT_SIZE,
    GRID_ALPHA,
    LS_DASHED,
    LS_SOLID,
    MK_FIXED,
    apply_style,
    create_figure_3panel,
    finalize_figure,
    save_figure,
)
from sharp_vawt import create_sim_from_params
from vawt_presets import PRESETS

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def _simulate_cp(params: dict) -> float:
    """Run one simulation and return Cp."""
    result = create_sim_from_params(params).run()
    return float(result["cp"])


def run_simulation(tsr: float, base: dict, prescribe_pitch: bool, pp0_deg: float = 0.0) -> float:
    """Run one simulation and return Cp."""
    params = {
        **base,
        "free": not prescribe_pitch,
        "tsr": tsr,
        "prescribe_pitch": prescribe_pitch,
        "pp0_deg": pp0_deg,
        "pp1_deg": 0.0,
        "pp2_deg": 0.0,
        "pp3_deg": 0.0,
        "pp_ph_deg": 0.0,
        "T_max": 15.0,
        "stride": 5,
    }
    result = create_sim_from_params(params).run()
    return float(result["cp"])


def run_sweep() -> tuple[list[float], list[float], list[float]]:
    """Run passive and fixed-rpm sweeps over TSR.

    Returns:
        (tsr_values, cp_passive, cp_rigid)
    """
    base = PRESETS["prototype_1_3"].copy()
    base["free"] = True
    base["T_max"] = 15.0
    base["stride"] = 5

    tsr_values = np.arange(1.0, 4.05, 0.25)  # 1.0 to 4.0 step 0.25

    cp_passive = []
    cp_rigid = []

    for tsr in tsr_values:
        # Passive CPPC at this TSR
        cp_passive.append(run_simulation(tsr, base, prescribe_pitch=False))

        # Fixed pitch: sweep pp0_deg to find best Cp at this TSR
        best_cp = -1.0
        for pp0 in np.arange(-30.0, 30.01, 5.0):
            cp = run_simulation(tsr, base, prescribe_pitch=True, pp0_deg=pp0)
            best_cp = max(best_cp, cp)
        cp_rigid.append(best_cp)

    return tsr_values.tolist(), cp_passive, cp_rigid


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Compare passive CPPC vs rigid fixed-pitch Cp at same geometry."
    )
    ap.add_argument(
        "--out",
        type=str,
        default=str(DOCS / "cp_rigid_vs_passive.png"),
        help="Output PNG path",
    )
    args = ap.parse_args()

    tsr_vals, cp_passive, cp_rigid = run_sweep()

    apply_style()
    fig, axes = create_figure_3panel()
    ax = axes[0]

    ax.plot(
        tsr_vals, cp_passive, LS_SOLID, color=COL_PASSIVE_KLOAD, lw=1.8,
        marker=MK_FIXED, label="Passive CPPC (free-running)",
    )
    ax.plot(
        tsr_vals, cp_rigid, LS_DASHED, color=COL_PASSIVE_FIXED, lw=1.8,
        marker=MK_FIXED, label="Fixed-pitch rigid (best pp0_deg)",
    )

    ax.set_xlabel(r"TSR $\omega R / U$")
    ax.set_ylabel(r"Power coefficient $C_p$")
    ax.set_title("Cp vs TSR: Passive CPPC vs Fixed-Pitch Rigid")
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=GRID_ALPHA, axis="y")
    ax.legend(fontsize=FONT_SIZE - 1, loc="best")

    finalize_figure(fig, suptitle="Passive CPPC vs Fixed-Pitch Rigid Baseline")
    save_figure(fig, args.out)

    print(f"Wrote {args.out}")
    print(f"  Best Cp passive:  {max(cp_passive):.4f} at TSR={tsr_vals[int(np.argmax(cp_passive))]:.2f}")
    print(f"  Best Cp fixed:   {max(cp_rigid):.4f} at TSR={tsr_vals[int(np.argmax(cp_rigid))]:.2f}")


if __name__ == "__main__":
    main()