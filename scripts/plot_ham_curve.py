"""
Ham 1979 Cp(TSR) curve comparison — 2D static-only upper bound vs measured.

Runs the three model configurations on Ham's Pinson C2E geometry across
TSR = 1.5 to 4.5 and plots them against his measured points.  Saves
docs/ham_curve.png.

Why this exists: the static-polar run (Ham's own model class, 2D with no
finite-span loss) over-predicts Ham's 3D measured peak — the expected
bias for a 2D solver without tip loss — and the shape of the curve also
differs. The peak-only comparison in validate_ham.py quantifies the
bias; this figure shows both.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sharp_vawt import create_sim_from_params

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ham's Pinson C2E rig
R_HAM, C_HAM, H_HAM, N_HAM = 1.83, 0.305, 1.37, 3

COMMON = {
    "R": R_HAM, "c": C_HAM, "H": H_HAM, "N": N_HAM,
    "ar": 0.0, "sp": 0.25,
    "free": False, "T_max": 20.0, "stride": 5,
    "prescribe_pitch": True,
    "pp0_deg": 0.0, "pp1_deg": -10.0, "pp2_deg": 0.0, "pp3_deg": 0.0,
    "use_dmst": True, "cd_add": 0.005,
    "use_tip_loss": False,  # Ham's model class has no finite-span correction
}

CONFIGS = [
    ("static polars only",     {"use_dynamic_stall": False, "use_flow_curvature": False}, "C0", "--"),
    ("+ dynamic stall",        {"use_dynamic_stall": True,  "use_flow_curvature": False}, "C1", "-"),
    ("+ DS + curvature",       {"use_dynamic_stall": True,  "use_flow_curvature": True},  "C2", "-"),
]

TSRS = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5)

# Ham 1979 experimental points (approximate, digitised from Fig. 8).
# Exposed at module level so plot_validation.py reuses the same data
# instead of keeping a second, drift-prone copy.
HAM_TSR = np.array([1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
HAM_CP  = np.array([0.22, 0.35, 0.43, 0.44, 0.38, 0.12])
HAM_ERR = np.array([0.02, 0.03, 0.03, 0.03, 0.04, 0.03])


def main():
    fig, ax = plt.subplots(figsize=(7.5, 5))

    # Ham's measured points
    ax.errorbar(HAM_TSR, HAM_CP, yerr=HAM_ERR, fmt='s', capsize=4,
                color='black', label="Ham 1979 (measured, R = 1.83 m)", zorder=5)

    # Model curves at Ham's geometry
    for label, flags, color, ls in CONFIGS:
        cps = []
        for tsr in TSRS:
            r = create_sim_from_params({**COMMON, **flags, 'tsr': tsr}).run()
            cps.append(r['cp'])
        cps = np.array(cps)
        ax.plot(TSRS, cps, marker='o', lw=2, ls=ls, color=color, label=label)
        print(f"{label:20s} peak Cp = {cps.max():.4f} "
              f"at TSR = {TSRS[int(cps.argmax())]:.1f}")

    ax.axhline(0, color='grey', lw=0.5)
    ax.set_xlabel('tip-speed ratio')
    ax.set_ylabel('power coefficient Cp')
    ax.set_xlim(1.2, 4.7)
    ax.set_ylim(-0.05, 0.55)
    ax.grid(alpha=0.3)
    ax.legend(loc='upper right', fontsize=9)
    ax.set_title("Ham 1979 comparison: 2D static-only upper bound vs measured Cp(TSR)")
    fig.tight_layout()

    out = os.path.join(ROOT, "docs", "ham_curve.png")
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
