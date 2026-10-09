"""
Run the Sharp cycloturbine in PASSIVE mode.

No prescribed pitch.  The blade rocks because:
  - the aerodynamic pitching moment pushes it
  - the centrifugal pendulum pulls it back
  - pivot friction damps it

The steady-state cycle is whatever emerges from those forces.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from vawt_core import create_sim_from_params

# ----------------------------------------------------------------- baseline
# Sharp's original proportions:
#   - solidity ~ 0.167 to 0.20 (his models used 1/6)
#   - rocking arm ≈ 1/2 chord
#   - pivot near 25% chord
#   - counterweight roughly 1 chord-length ahead of LE
#   - mechanical stops at ±45°
#
# We take the optimiser's geometry (c = 0.118 m) and scale the CPPC hardware
# to Sharp's design rules.
BASE = dict(
    R=0.60, H=0.40, N=3,
    c=0.1176,               # from the optimiser
    ar=0.50,                # rocking arm = half chord (Sharp)
    sp=0.25,                # pivot at 25% chord (Sharp)
    # Sharp balance: counterweight roughly compensates blade pitching moment
    mb=0.010, xbcg=0.20,    # blade CG at 20% chord
    mc=0.008, dcw=0.50,     # counterweight mass, offset 0.5c ahead of LE
    balance=0,              # use mc, dcw directly
    bias_deg=0.0,
    # passive mode — NO prescribed schedule
    prescribe_pitch=False,
    # aerodynamics (same as optimiser)
    cd_add=0.002,
    use_dynamic_stall=True,
    use_flow_curvature=True,
    use_dmst=True,
    # mechanical
    win_deg=45.0,
    cb=2e-5,
    mu_c=3e-4,              # pitch bearing Coulomb friction
    # simulation
    free=True, T_max=40.0, stride=5,
    w0_frac=0.9,
    k_load=0.0015,
    tsr=2.14,
)

print("=" * 74)
print("Sharp cycloturbine — PASSIVE mode (no prescribed pitch)")
print("=" * 74)

r = create_sim_from_params(BASE).run()
print(f"  Cp        = {r['cp']:+.4f}")
print(f"  TSR_eq    = {r['tsr_eq']:.3f}")
print(f"  RPM       = {r['rpm']:.1f}")
print(f"  pitch_min = {r['pitch_min']:+.1f}°")
print(f"  pitch_max = {r['pitch_max']:+.1f}°")
print(f"  pitch_rms = {r['pitch_rms']:.2f}°")
print(f"  α_max     = {r['aoa_max']:.1f}°")
print(f"  stop_pct  = {r['stop_pct']:.1f}%  (fraction of time against hard stops)")
print(f"  steady    = {r.get('steady', True)}")
print()

# ----------------------------------------------------------------- parameter sweeps
def sweep(name, values):
    print(f"--- sweeping {name} ---")
    print(f"{name:>14} {'Cp':>9} {'TSR_eq':>8} {'pitch RMS':>11} {'stop%':>7}")
    best = (None, -1)
    for v in values:
        p = {**BASE, name: v}
        r = create_sim_from_params(p).run()
        mark = ""
        if r['cp'] > best[1]:
            best = (v, r['cp'])
            mark = "  ←"
        print(f"{v:>14.4g} {r['cp']:>9.4f} {r['tsr_eq']:>8.2f} "
              f"{r['pitch_rms']:>11.2f} {r['stop_pct']:>7.1f}{mark}")
    print(f"  best {name} = {best[0]}, Cp = {best[1]:.4f}")
    print()

# Sweep the Sharp hardware parameters
sweep("mc",   [0.004, 0.006, 0.008, 0.012, 0.016])   # counterweight mass
sweep("dcw",  [0.3,   0.4,   0.5,   0.6,   0.8])     # counterweight offset
sweep("ar",   [0.3,   0.4,   0.5,   0.6,   0.7])     # rocking arm length
sweep("bias_deg", [-4, -2, 0, 2, 4])                 # static pitch bias
sweep("k_load",   [0.0004, 0.0008, 0.0012, 0.0018, 0.0025])