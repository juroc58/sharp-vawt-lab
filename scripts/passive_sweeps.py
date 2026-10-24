"""Passive Sharp parameter sweeps: counterweight offset (dcw) and load (k_load).

Reproduces the runs documented in the README. Run this to regenerate the
Cp-vs-dcw and Cp-vs-k_load curves for the passive CPPC mechanism.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sharp_vawt import create_sim_from_params

BASE = {
    "R": 2.7179, "H": 4.0568, "N": 3, "c": 0.3861,
    "ar": 0.3121, "sp": 0.2181,
    "mb": 0.92954, "xbcg": 0.20,
    "mc": 2.69306,
    "balance": 0, "bias_deg": 0.0,
    "prescribe_pitch": False,
    "cd_add": 0.002,
    "use_dynamic_stall": True, "use_flow_curvature": True, "use_dmst": True,
    "use_tip_loss": True,
    "win_deg": 45.0, "cb": 2e-5, "mu_c": 3e-4,
    "free": True, "T_max": 40.0, "stride": 5,
    "w0_frac": 0.9, "k_load": 4.164352, "tsr": 2.5,
}


def main():
    print("dcw sweep (counterweight offset):")
    print(f"{'dcw':>8} {'Cp':>9} {'TSR_eq':>8} {'psi range':>18} {'alpha_max':>10}")
    for dcw in (-0.30, -0.10, 0.05, 0.15, 0.25, 0.35, 0.50, 0.70):
        r = create_sim_from_params({**BASE, 'dcw': dcw}).run()
        print(f"{dcw:>8.2f} {r['cp']:>9.4f} {r['tsr_eq']:>8.3f} "
              f"[{r['pitch_min']:>+6.1f},{r['pitch_max']:>+6.1f}] "
              f"{r['aoa_max']:>10.1f}")

    print()
    print("k_load sweep (load factor):")
    print(f"{'k_load':>8} {'Cp':>9} {'TSR_eq':>8} {'psi range':>18} {'alpha_max':>10}")
    for kl in (0.5, 1.0, 2.0, 4.0, 6.0, 8.0):
        r = create_sim_from_params({**BASE, 'k_load': kl}).run()
        print(f"{kl:>8.4f} {r['cp']:>9.4f} {r['tsr_eq']:>8.3f} "
              f"[{r['pitch_min']:>+6.1f},{r['pitch_max']:>+6.1f}] "
              f"{r['aoa_max']:>10.1f}")


if __name__ == "__main__":
    main()
