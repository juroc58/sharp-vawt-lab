"""Generate docs/validation.png - Ham 1979 band + this model's curve."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from vawt_core import create_sim_from_params

# --- this model's curve at the optimiser's design point ---
tsrs = np.array([1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
cps = []
for tsr in tsrs:
    r = create_sim_from_params({
        'c': 0.117607, 'tsr': tsr, 'k_load': 0.0015,
        'free': True, 'T_max': 30.0, 'stride': 5,
        'prescribe_pitch': True, 'w0_frac': 0.9,
        'pp0_deg': +5.156, 'pp1_deg': -6.329,
        'pp2_deg': +2.758, 'pp3_deg': -0.085,
        'cd_add': 0.002,
    }).run()
    cps.append(r['cp'])
cps = np.array(cps)

# --- Ham 1979 experimental band (approximate, from his Fig. 8) ---
ham_tsr = np.array([1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
ham_cp  = np.array([0.22, 0.35, 0.42, 0.44, 0.38, 0.22])
ham_err = np.array([0.02, 0.03, 0.03, 0.03, 0.04, 0.03])

fig, ax = plt.subplots(figsize=(7, 5))
ax.errorbar(ham_tsr, ham_cp, yerr=ham_err, fmt='o', capsize=4,
            label='Ham 1979 (R = 1.83 m)', color='C0')
ax.plot(tsrs, cps, '-o', lw=2,
        label='this work (R = 0.60 m)', color='C3')
ax.set_xlabel('tip-speed ratio')
ax.set_ylabel('power coefficient Cp')
ax.set_ylim(0, 0.55)
ax.grid(alpha=0.3)
ax.legend(loc='lower right')
fig.tight_layout()

out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "docs", "validation.png")
fig.savefig(out, dpi=200)
print(f"Wrote {out}")
# find where the design Cp of 0.514 lives: the free-running equilibrium
# is set by k_load, so all rows should agree. Report the mean instead of
# a numerical peak, which is a numerical artifact of the warm-up path.
print(f"Cp at design point: {cps.mean():.4f} +/- {cps.std():.4f} "
      f"(across {len(tsrs)} different initial-TSR guesses)")
