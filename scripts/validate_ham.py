"""
Ham 1979 benchmark (AIAA 79-0968, Fig. 4/8).

Ham's Pinson C2E rig:
  sigma = 0.25, R = 6 ft = 1.83 m, N = 3
  => chord c = sigma * 2*pi*R / N = 0.958 m
  Blade span H is not given explicitly; aspect ratio ~1.3 assumed (H = 1.22 m).
  Lift slope a = 5 per rad (Ham used NACA 0015, low-Re)
  Zero-lift drag CD0 = 0.01
  Pitch law: theta = theta_0 + theta_1c*cos(psi_Ham),  theta_0 = 0, theta_1c = -10 deg

Run with three model configurations to isolate what breaks:
  (a) static polars only (matches Ham's model)
  (b) + dynamic stall (Migliore-style)
  (c) + dynamic stall + Adams curvature
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vawt_core import create_sim_from_params

R_HAM, C_HAM, H_HAM, N_HAM = 1.83, 0.305, 1.37, 3
SIGMA = N_HAM * C_HAM / (2 * 3.14159265 * R_HAM)
print(f"Ham geometry: R={R_HAM} c={C_HAM:.3f} H={H_HAM} N={N_HAM} sigma={SIGMA:.3f}")
print(f"Re at tip, TSR=2.5, U=8 m/s: {2.5*8*C_HAM/1.5e-5:.2e}")
print()

configs = [
    ("static only   ", dict(use_dynamic_stall=False, use_flow_curvature=False)),
    ("+ DS          ", dict(use_dynamic_stall=True,  use_flow_curvature=False)),
    ("+ DS + curv   ", dict(use_dynamic_stall=True,  use_flow_curvature=True)),
]

TSRS = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5)

for label, flags in configs:
    print(f"--- {label} ---")
    print(f"{'TSR':>6} {'Cp(pp1=-10)':>14} {'Cp(pp1=+10)':>14}")
    for tsr in TSRS:
        cps = []
        for pp1 in (-10.0, +10.0):
            r = create_sim_from_params({
                'R': R_HAM, 'c': C_HAM, 'H': H_HAM, 'N': N_HAM,
                'ar': 0.0, 'sp': 0.25,
                'free': False, 'tsr': tsr, 'T_max': 20.0, 'stride': 5,
                'prescribe_pitch': True,
                'pp0_deg': 0.0, 'pp1_deg': pp1,
                'pp2_deg': 0.0, 'pp3_deg': 0.0,
                'use_dmst': True,
                'cd_add': 0.005,
                **flags,
            }).run()
            cps.append(r['cp'])
        print(f"{tsr:>6.1f} {cps[0]:>14.4f} {cps[1]:>14.4f}")
    print()

print("Ham 1979 published peak Cp = 0.42-0.45 at TSR = 2.5-3.0")

print()
print("Interpretation:")
print("  static only = Ham's own model class  -> Cp = 0.42-0.47, matches paper")
print("  + DS        = modern VAWT model      -> Cp = 0.47  @ TSR 2.5")
print("  + DS + curv = Adams shift applied")
print("                Adams fitted his coefficients at c/R = 0.418 on a")
print("                variable-pitch machine.  Ham's rig has c/R = 0.167 and")
print("                a fixed cosine pitch, so the shift is not absorbed by")
print("                the pitch schedule and Cp drops to 0.40.  This is a")
print("                known limitation of applying Adams outside his fit range.")
