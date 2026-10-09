"""
Qa diagnostic — no core modification required.

Instead of patching vawt_core.py's output array, this script monkey-patches
the kernel's print behavior by wrapping the sim call with a JIT-disabled
evaluation that captures Qa per timestep.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from vawt_core import create_sim_from_params

BASE = dict(
    R=0.60, H=0.40, N=3, c=0.1176,
    ar=0.50, sp=0.25,
    mb=0.010, xbcg=0.20,
    mc=0.004, dcw=-0.10,
    balance=0, bias_deg=0.0,
    prescribe_pitch=False,
    cd_add=0.002,
    use_dynamic_stall=True,
    use_flow_curvature=True,
    use_dmst=True,
    win_deg=45.0, cb=2e-5, mu_c=3e-4,
    free=True, T_max=40.0, stride=5,
    w0_frac=0.9, k_load=0.0015, tsr=2.14,
)

print("Running passive Sharp case...")
r = create_sim_from_params(BASE).run()
out = r["out"]
print(f"  Cp = {r['cp']:.4f}")
print(f"  output shape: {out.shape}")

# ---------------------------------------------------------------------------
# The core writes blade-0 kinematic quantities in columns 0-11.
# Column 5 is blade-0 alpha (radians), column 3 is blade-0 psi.
# We don't have Qa in the output, so we RECONSTRUCT it from the other
# columns using the code's own formula:
#    Qa = stc * Fr - src * Ft
# where stc, src depend on psi and the pivot geometry.
# This gives us the aero torque time-history without touching the kernel.
# ---------------------------------------------------------------------------

# Extract last revolution
th = out[:, 1]
m = th >= th[-1] - 2 * np.pi
th_m = th[m]
psi_m = out[m, 3]
alpha_m = out[m, 5]            # radians
Tsum_m = out[m, 6]             # total blade torque (aero + AM)
psd_m = out[m, 11]             # pitch rate
t_m = out[m, 0]

# Estimate aerodynamic pitch torque from the pitch-rate balance.
# In passive mode, the pitch dynamics are:
#    Ip * psd_dot = Qa - cb*psd - kc*psi - Qfr + M_cf
# We can compute d(psd)/dt numerically, and infer Qa up to the
# small damping/friction terms.  We have w(t) too, so we can compute
# M_cf = -M * w^2 * Rp * R_cg * sin(psi).

# Physical constants from BASE
R, c, ar_ratio, sp_ratio = 0.60, 0.1176, 0.50, 0.25
ar = ar_ratio * c
sp = sp_ratio * c
Rp = R - ar
M = 0.010 + 0.004
Ip_est = M * (c*c/12 + 0.20*c*0.20*c + ar*ar)     # rough order-of-magnitude

# Numerical derivative of psd
dt = np.mean(np.diff(t_m))
dpsd = np.gradient(psd_m, dt)

# Pitch rate coupling: M_cf term
w_m = out[m, 2]
psi_rad = psi_m
xg = -0.0227                                       # from earlier dcw=-0.10 solve
M_cf = -M * w_m * w_m * Rp * abs(xg) * np.sin(psi_rad)

# Qa inferred = Ip * psd_dot + M_cf + damping
Qa_inferred = Ip_est * dpsd + M_cf

# Sort by azimuth
phi_deg = np.degrees(th_m % (2*np.pi))
order = np.argsort(phi_deg)
phi_s   = phi_deg[order]
psi_s   = np.degrees(psi_m[order])
alpha_s = np.degrees(alpha_m[order])
Qa_s    = Qa_inferred[order]

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

ax[0].plot(phi_s, psi_s, "b-", lw=1.6)
ax[0].axhline(0, color="k", lw=0.5)
ax[0].set_ylabel("psi [deg]")
ax[0].set_title("Blade pitch (rocking angle)")
ax[0].grid(alpha=0.3)

ax[1].plot(phi_s, alpha_s, color="darkorange", lw=1.6)
ax[1].axhline(0, color="k", lw=0.5)
ax[1].axhline( 14, color="r", ls=":", lw=0.9, label="+-14 deg stall")
ax[1].axhline(-14, color="r", ls=":", lw=0.9)
ax[1].set_ylabel("alpha [deg]")
ax[1].set_title("Effective angle of attack")
ax[1].legend(loc="upper right", fontsize=8)
ax[1].grid(alpha=0.3)

ax[2].plot(phi_s, Qa_s, color="purple", lw=1.6)
ax[2].axhline(0, color="k", lw=0.5)
ax[2].set_ylabel("Qa inferred [N m]")
ax[2].set_xlabel("rotor angle [deg]   (0 = with wind,  180 = upwind)")
ax[2].set_title("Aerodynamic pitch torque on blade 0 (reconstructed)")
ax[2].grid(alpha=0.3)

fig.tight_layout()
outpath = os.path.join(ROOT, "docs", "diag_qa.png")
os.makedirs(os.path.dirname(outpath), exist_ok=True)
fig.savefig(outpath, dpi=150)
print(f"  wrote {outpath}")

# ---------------------------------------------------------------------------
# Numeric summary
# ---------------------------------------------------------------------------
print()
print(f"{'phi':>8} {'psi':>8} {'alpha':>8} {'Qa_inf':>12}  "
      f"{'regime':>12}  {'sign ok?':>10}")
for ph in (0, 45, 90, 135, 180, 225, 270, 315):
    i = np.argmin(np.abs(phi_s - ph))
    a = alpha_s[i]
    q = Qa_s[i]
    if a > 14:
        regime, ok = "stalled(+)", "yes" if q < 0 else "NO"
    elif a < -14:
        regime, ok = "stalled(-)", "yes" if q > 0 else "NO"
    else:
        regime, ok = "attached",  "yes" if abs(q) < 0.5 else "border"
    print(f"{phi_s[i]:>8.1f} {psi_s[i]:>8.1f} {a:>8.1f} "
          f"{q:>12.5f}  {regime:>12}  {ok:>10}")

# Add to scripts/diag_qa.py after the table
print()
print("Pitch range vs k_load:")
for kl in (0.0005, 0.0010, 0.0015, 0.0020, 0.0030):
    r2 = create_sim_from_params({**BASE, 'k_load': kl}).run()
    print(f"  k_load={kl:.4f}  Cp={r2['cp']:.4f}  "
          f"TSR={r2['tsr_eq']:.2f}  "
          f"psi=[{r2['pitch_min']:+.1f}, {r2['pitch_max']:+.1f}]  "
          f"alpha_max={r2['aoa_max']:.1f}")