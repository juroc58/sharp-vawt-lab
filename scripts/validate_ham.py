"""
Ham 1979 benchmark (AIAA 79-0968, Fig. 4/8).

Ham's Pinson C2E rig:
  N = 3, R = 1.83 m, c = 0.305 m, H = 1.37 m
  Solidity, Ham's definition:       sigma_Ham = N*c / (2*R)   = 0.25
  Solidity, modern VAWT convention: sigma_std = N*c / (2*pi*R) = 0.080
  (Both are correct — they are different conventions. Modern papers use sigma_std.)

Pitch law: theta = theta_0 + theta_1c*cos(psi_Ham), theta_0 = 0, theta_1c = -10 deg

Runs three model configurations on Ham's own geometry:
  (a) static polars only              — matches Ham's model class
  (b) + dynamic stall                 — modern VAWT model
  (c) + dynamic stall + curvature     — full model
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vawt_core import create_sim_from_params

R_HAM, C_HAM, H_HAM, N_HAM = 1.83, 0.305, 1.37, 3
SIGMA_HAM = N_HAM * C_HAM / (2.0 * R_HAM)
SIGMA_STD = N_HAM * C_HAM / (2.0 * 3.14159265 * R_HAM)
print(f"Ham geometry: R={R_HAM} c={C_HAM} H={H_HAM} N={N_HAM}")
print(f"  sigma (Ham defn, Nc/2R)   = {SIGMA_HAM:.3f}")
print(f"  sigma (modern, Nc/2piR)   = {SIGMA_STD:.3f}")
print(f"  Re at tip, TSR=2.5, U=8   = {2.5*8*C_HAM/1.5e-5:.2e}")
print()

COMMON = dict(
    R=R_HAM, c=C_HAM, H=H_HAM, N=N_HAM,
    ar=0.0, sp=0.25,
    free=False, T_max=20.0, stride=5,
    prescribe_pitch=True,
    pp0_deg=0.0, pp2_deg=0.0, pp3_deg=0.0,
    use_dmst=True, cd_add=0.005,
)

configs = [
    ("static only   ", dict(use_dynamic_stall=False, use_flow_curvature=False)),
    ("+ DS          ", dict(use_dynamic_stall=True,  use_flow_curvature=False)),
    ("+ DS + curv   ", dict(use_dynamic_stall=True,  use_flow_curvature=True)),
]

TSRS = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5)

# Collect results so we can run a pass/fail check afterwards
results = {label: [] for label, _ in configs}

for label, flags in configs:
    print(f"--- {label} ---")
    print(f"{'TSR':>6} {'Cp(pp1=-10)':>14} {'Cp(pp1=+10)':>14}")
    for tsr in TSRS:
        cps = []
        for pp1 in (-10.0, +10.0):
            r = create_sim_from_params({**COMMON, **flags, 'tsr': tsr,
                                        'pp1_deg': pp1}).run()
            cps.append(r['cp'])
        results[label].append((tsr, cps[0], cps[1]))
        print(f"{tsr:>6.1f} {cps[0]:>14.4f} {cps[1]:>14.4f}")
    print()

# ------------------------------------------------------------------ verdict
# Ham's measured band is Cp = 0.42-0.45 at TSR 2.5-3.0.  Compare the
# model peak against the midpoint of the band, not the lower edge.
HAM_BAND_LO, HAM_BAND_HI = 0.42, 0.45
HAM_MID = 0.5 * (HAM_BAND_LO + HAM_BAND_HI)
TOL = 0.10

static_only = [cp for _, cp, _ in results["static only   "]]
static_peak = max(static_only)
err = abs(static_peak - HAM_MID) / HAM_MID
in_band = HAM_BAND_LO <= static_peak <= HAM_BAND_HI

print("=" * 60)
print("VERDICT")
print("=" * 60)
print(f"  static-only peak Cp  = {static_peak:.4f}")
print(f"  Ham 1979 band        = {HAM_BAND_LO:.2f} - {HAM_BAND_HI:.2f} "
      f"(mid {HAM_MID:.3f})")
print(f"  relative error       = {err * 100:.1f} % vs mid-band")
print(f"  inside Ham's band?   = {'yes' if in_band else 'no'}")
print()
if in_band:
    print("  PASS  (peak inside Ham's measured band)")
elif err < TOL:
    print(f"  PASS  (peak within {TOL * 100:.0f} % of Ham's mid-band)")
else:
    print(f"  FAIL  (off by {err * 100:.0f} % from mid-band)")
print()
print("  Note: only the peak is checked here.  See docs/ham_curve.png")
print("  and the README section for the full Cp(TSR) shape, which does")
print("  not match Ham across the range.")
