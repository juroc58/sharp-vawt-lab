"""Generate docs/validation.png - Ham 1979 band + this model's Cp(TSR) curve.

The comparison is run at the SAME radius as Ham's rig (R = 1.83 m) so that
the two curves can be compared directly. The optimiser's design point is
R = 0.60 m; it is scaled up rigidly, keeping the dimensionless ratios
(c/R, H/R) and the TSR-invariant scaling of masses and load:
    c, H ~ R ;  mb, mc ~ R^3 ;  k_load ~ R^5.

The curve is swept at FIXED rpm (free=False) so that the prescribed TSR is
actually enforced; a free-running sweep would collapse to a single
equilibrium point set by k_load.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from vawt_core import create_sim_from_params

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
cps = []
for tsr in tsrs:
    r = create_sim_from_params({
        'R': R_MODEL, 'c': _C, 'H': _H,
        'mb': _MB, 'mc': _MC, 'k_load': _K_LOAD,
        'tsr': tsr,
        'free': False, 'T_max': 25.0, 'stride': 5, 'n_rev_fixed': 16,
        'prescribe_pitch': True, 'w0_frac': 0.9,
        'pp0_deg': +5.156, 'pp1_deg': -6.329,
        'pp2_deg': +2.758, 'pp3_deg': -0.085,
        'cd_add': 0.002,
    }).run()
    cps.append(r['cp'])
cps = np.array(cps)

# --- Ham 1979 experimental band (approximate, from his Fig. 8) ---
ham_tsr = np.array([1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
ham_cp  = np.array([0.22, 0.35, 0.43, 0.44, 0.38, 0.12])
ham_err = np.array([0.02, 0.03, 0.03, 0.03, 0.04, 0.03])

fig, ax = plt.subplots(figsize=(7, 5))
ax.errorbar(ham_tsr, ham_cp, yerr=ham_err, fmt='o', capsize=4,
            label='Ham 1979 (R = 1.83 m)', color='C0')
ax.plot(tsrs, cps, '-o', lw=2,
        label=f'this work (R = {R_MODEL:.2f} m, scaled, fixed rpm)', color='C3')
ax.set_xlabel('tip-speed ratio')
ax.set_ylabel('power coefficient Cp')
ax.set_ylim(0, 0.62)
ax.grid(alpha=0.3)
ax.legend(loc='lower right')
fig.tight_layout()

out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "docs", "validation.png")
fig.savefig(out, dpi=200)
print(f"Wrote {out}")
peak = int(np.argmax(cps))
print(f"Model peak Cp = {cps[peak]:.4f} at TSR = {tsrs[peak]:.1f}")
print(f"Ham measured peak ~0.42-0.45 at TSR 2.5-3.0")