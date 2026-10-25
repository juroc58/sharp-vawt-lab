"""Generate docs/validation.png - this model's Cp(TSR) curve at the
prescribed-pitch upper bound.

The model's optimiser design point is R = 0.60 m; it is scaled up to
Ham's radius (R = 1.83 m) rigidly, keeping *the model's own* dimensionless
ratios (c/R, H/R) and the TSR-invariant scaling of masses and load:
    c, H ~ R ;  mb, mc ~ R^3 ;  k_load ~ R^5.

CAVEAT: This preserves the model's aspect ratio (H/R = 0.667), which is
*not* Ham's rig aspect ratio (H/R = 0.749).  The figure is therefore a
scaled comparison of this work against Ham, not a like-for-like geometry
match.  For the exact-geometry comparison (Ham's R=1.83, H=1.37, c=0.305)
see scripts/plot_ham_curve.py.

Ham's experimental points are NOT plotted here because the geometries
differ.  This figure shows the model's prescribed-pitch upper bound only.

The curve is swept at FIXED rpm (free=False) so that the prescribed TSR is
actually enforced; a free-running sweep would collapse to a single
equilibrium point set by k_load.

Unlike the headline results this model curve runs WITHOUT tip loss (the
prescribed-pitch upper bound is defined that way; see optimize_actuator.py).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sharp_vawt import create_sim_from_params

# --- this model's curve, scaled to Ham's radius for a fair comparison ---
R_MODEL = 1.83
R_DESIGN = 0.60
SCALE = R_MODEL / R_DESIGN
_C = 0.117607 * SCALE
_H = 0.40 * SCALE
_MB = 0.010 * SCALE ** 3
_MC = 0.004 * SCALE ** 3
_K_LOAD = 0.0015 * SCALE ** 5

tsrs = np.array([1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5])


def main():
    cps = []
    for tsr in tsrs:
        try:
            r = create_sim_from_params({
                'R': R_MODEL, 'c': _C, 'H': _H,
                'mb': _MB, 'mc': _MC, 'k_load': _K_LOAD,
                'tsr': tsr,
                'free': False, 'T_max': 25.0, 'stride': 5,
                'n_rev_fixed': 16,
                'prescribe_pitch': True, 'w0_frac': 0.9,
                'pp0_deg': +5.156, 'pp1_deg': -6.329,
                'pp2_deg': +2.758, 'pp3_deg': -0.085,
                'cd_add': 0.002,
            }).run()
        except Exception as exc:
            print(f"  TSR = {tsr:.1f}: run failed ({exc!r}); skipping")
            cps.append(np.nan)
            continue
        cps.append(r['cp'])
    cps = np.array(cps)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(tsrs, cps, '-o', lw=2,
            label=f'this work (R = {R_MODEL:.2f} m, scaled, fixed rpm)',
            color='C3')
    ax.set_xlabel('tip-speed ratio')
    ax.set_ylabel('power coefficient Cp')
    ax.set_ylim(0, 0.62)
    ax.grid(alpha=0.3)
    ax.legend(loc='lower right')

    # Add caveat text
    ax.text(0.02, 0.98,
            'CAVEAT: Model H/R = 0.667 ≠ Ham H/R = 0.749.\n'
            'Not a like-for-like geometry match.\n'
            'See plot_ham_curve.py for exact-geometry comparison.',
            transform=ax.transAxes, va='top', ha='left',
            fontsize=9, color='red',
            bbox={"boxstyle": 'round', "facecolor": 'wheat', "alpha": 0.8})

    fig.tight_layout()

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "docs", "validation.png")
    fig.savefig(out, dpi=200)
    print(f"Wrote {out}")
    if np.all(np.isnan(cps)):
        raise RuntimeError("every sweep point failed; validation figure is empty")
    peak = int(np.nanargmax(cps))
    print(f"Model peak Cp = {cps[peak]:.4f} at TSR = {tsrs[peak]:.1f}")


if __name__ == "__main__":
    main()