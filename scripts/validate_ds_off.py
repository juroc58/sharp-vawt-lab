"""
Dynamic-stall sensitivity test.

The most important robustness check: is the optimised Cp real, or is the
model exploiting the (uncalibrated) dynamic-stall increment?

Runs the optimiser's prescribed-pitch design point with the DS model on
and off. The README claim is ΔCp < 3 % at this point; this script prints
the delta and exits non-zero if it exceeds the tolerance, so it can be
wired into CI.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vawt_core import create_sim_from_params

DESIGN = dict(
    c=0.117607, tsr=2.14487, k_load=0.00149992,
    pp0_deg=+5.15612, pp1_deg=-6.32883,
    pp2_deg=+2.75837, pp3_deg=-0.0845207,
    cd_add=0.002,
    use_flow_curvature=True,
    free=True, T_max=30.0, stride=5,
    prescribe_pitch=True, w0_frac=0.9,
)

CASES = [
    ("full model",           dict()),
    ("no dynamic stall",     dict(use_dynamic_stall=False)),
    ("no DS, no curvature",  dict(use_dynamic_stall=False,
                                  use_flow_curvature=False)),
]

TOL = 0.03   # README claim: ΔCp < 3 %


def run_cases():
    """Return list of (label, cp, aoa_max)."""
    out = []
    for label, override in CASES:
        r = create_sim_from_params({**DESIGN, **override}).run()
        out.append((label, r['cp'], r['aoa_max']))
    return out


def main():
    rows = run_cases()

    print("Dynamic-stall sensitivity - optimiser design point")
    print("=" * 60)
    print(f"{'case':<25} {'Cp':>9} {'alpha_max':>12}")
    print("-" * 60)
    for label, cp, aoa in rows:
        print(f"{label:<25} {cp:>9.4f} {aoa:>12.2f}")

    full = rows[0][1]
    no_ds = rows[1][1]
    delta = abs(full - no_ds) / max(abs(full), 1e-9)

    print()
    print(f"  delta Cp (DS on vs off) = {delta * 100:.2f} %  "
          f"(tolerance {TOL * 100:.0f} %)")
    print()
    print(
        "Note: this check runs at a prescribed-pitch design point where "
        "alpha_max stays below stall. A small delta Cp here does NOT "
        "imply the passive case is DS-insensitive -- see the "
        "Uncertainty section for the passive-anchor spread."
    )
    if delta < TOL:
        print("\nPASS: DS model is not driving the result at this point.")
        return 0
    print(f"\nFAIL: DS sensitivity {delta*100:.1f}% exceeds {TOL*100:.0f}%.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())