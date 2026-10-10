"""
Ham 1979 Cp(TSR) curve comparison.

Runs the three model configurations on Ham's Pinson C2E geometry across
TSR = 1.5 to 4.5 and plots them against his measured points.  Saves
docs/ham_curve.png.

Why this exists: the peak Cp of the static-polar run (Ham's own model
class) matches his published band, but the shape of the curve does not.
The peak-only comparison in validate_ham.py hides that; this figure
shows it.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from vawt_core import create_sim_from_params

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ham's Pinson C2E rig
R_HAM, C_HAM, H_HAM, N_HAM = 1.83, 0.305, 1.37, 3

COMMON = dict(
    R=R_HAM, c=C_HAM, H=H_HAM, N=N_HAM,
    ar=0.0, sp=0.25,
    free=False, T_max=20.0, stride=5,
    prescribe_pitch=True,
    pp0_deg=0.0, pp1_deg=-10.0, pp2_deg=0.0, pp3_deg=0.0,
    use_dmst=True, cd_add=0.005,
)

CONFIGS = [
    ("static polars only",     dict(use_dynamic_stall=False, use_flow_curvature=False), "C0", "--"),
    ("+ dynamic stall",        dict(use_dynamic_stall=True,  use_flow_curvature=False), "C1", "-"),
    ("+ DS + curvature",       dict(use_dynamic_stall=True,  use_flow_curvature=True),  "C2", "-"),
]

TSRS = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5)

# Ham 1979 experimental points (approximate, digitised from Fig. 8)
HAM_TSR = np.array([1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
HAM_CP  = np.array([0.22, 0.35, 0.43, 0.44, 0.38, 0.12])
HAM_ERR = np.array([0.02, 0.03, 0.03, 0.03, 0.04, 0.03])

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
ax.set_title("Ham 1979 reproduction: peak matches, shape does not")
fig.tight_layout()

out = os.path.join(ROOT, "docs", "ham_curve.png")
fig.savefig(out, dpi=200)
plt.close(fig)
print(f"Wrote {out}")
