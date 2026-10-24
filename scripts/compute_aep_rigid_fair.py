"""
Fair rigid-blade baseline for the AEP comparison.

The old 'rigid_k_load' case in compute_aep.py inherited the passive
machine's k_load, so it barely turned.  This script finds the best
operating point for the rigid blade at each geometry:

  1. Sweep (psi0, k_load); pick the pair maximising steady Cp at U = 6.
  2. Compare against passive CPPC at the same geometry.
  3. Integrate AEP against the same Weibull distribution.

Two geometries:
  sharp_inspired : R=0.60, H=0.40, AR 2.86 (Sharp-inspired CPPC optimum)
  scaleup        : R=2.72, H=4.06, AR 10.5 (scaleup CPPC optimum)

The point of the two-geometry comparison is that the fixed-pitch
threshold is geometry-dependent.  At AR 2.86, induced drag kills
fixed-pitch operation; at AR 10.5, a rigid blade works fine.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from compute_aep import (
    BASE,
    integrate_aep,
    rated_power_from_cp,
)

from scripts.stamp import make_stamp
from sharp_vawt import create_sim_from_params

U_DESIGN = 6.0
U_REF    = [3.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]

# A rigid configuration only counts as a *fair* baseline if it actually
# extracts power and spins.  Below these floors the rotor is effectively
# dead: at low aspect ratio the uncapped induced drag (Cd_i ~ 1/(pi e AR))
# kills fixed-pitch operation entirely, and quoting a percentage gain
# against a barely-turning blade is meaningless.  The floors are reported
# explicitly rather than hidden inside a max().
MIN_RIGID_CP  = 0.05
MIN_RIGID_TSR = 1.0

GEOMETRIES = {
    "sharp_inspired": {
        # Sharp-inspired CPPC anchor (R = 0.60 m, AR 2.86).  Do not inherit
        # BASE from compute_aep.py: that dict is the scale-up machine.
        "base": {**BASE,
                 "R": 0.60, "H": 0.40, "c": 0.14,
                 "ar": 0.50, "sp": 0.25,
                 "mb": 0.010, "xbcg": 0.20,
                 "mc": 0.002, "dcw": 0.30,
                 "k_load": 0.0025, "tsr": 2.0, "T_max": 30.0},
        "pitch_grid": [-10.0, -5.0, 0.0, 5.0, 10.0, 15.0],
        "kload_grid": [0.0005, 0.0010, 0.0015, 0.0020, 0.0030, 0.0040,
                       0.0050, 0.0080, 0.0120],
    },
    "scaleup": {
        "base": {**BASE,
                 "R": 2.7179, "c": 0.3861, "H": 4.0568,
                 "ar": 0.3121, "sp": 0.2181,
                 "mc": 2.6929, "dcw": -0.1935,
                 "mb": 0.9295, "xbcg": 0.20},
        "pitch_grid": [-5.0, 0.0, 5.0, 10.0, 15.0],
        "kload_grid": [0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0],
    },
}


def rigid_params(base, psi0):
    return {**base,
            'prescribe_pitch': True,
            'pp0_deg': float(psi0),
            'pp1_deg': 0.0, 'pp2_deg': 0.0, 'pp3_deg': 0.0, 'pp_ph_deg': 0.0}


def try_free_run(params, U):
    """Run free simulation, return (cp, tsr) or (None, None) if no equilibrium."""
    try:
        res = create_sim_from_params({**params, 'free': True, 'U': float(U)}).run()
    except Exception:
        return None, None
    if not res.get('steady', True) or res['cp'] <= 0.0:
        return None, None
    return float(res['cp']), float(res['tsr_eq'])


def find_best_passive(base, label):
    """Find best k_load for passive CPPC at this geometry."""

    results = []
    for kl in base['kload_grid']:
        res = try_free_run({**base['base'], 'k_load': kl}, U_DESIGN)
        if res[0] is None:
            continue
        cp, tsr = res
        results.append({"k_load": kl, "cp": cp, "tsr": tsr})
    if not results:
        raise RuntimeError(f"no steady passive configs at {label}")
    best = max(results, key=lambda r: r['cp'])
    print(f"    best: k_load = {best['k_load']:.4f}, Cp = {best['cp']:.4f}, "
          f"TSR = {best['tsr']:.2f}")
    return best


def find_best_rigid(base, label):
    """Find best (psi0, k_load) for rigid blade at this geometry."""
    results = []
    for psi in base['pitch_grid']:
        for kl in base['kload_grid']:
            r = try_free_run({**base['base'], 'prescribe_pitch': True,
                              'pp0_deg': psi, 'k_load': kl}, U_DESIGN)
            if r[0] is None:
                continue
            cp, tsr = r
            if cp >= MIN_RIGID_CP and tsr >= MIN_RIGID_TSR:
                results.append({"psi0": psi, "k_load": kl, "cp": cp, "tsr": tsr})
    if not results:
        return {"viable": False}
    best = max(results, key=lambda r: r['cp'])
    print(f"    best: psi0 = {best['psi0']:+.1f}, k_load = {best['k_load']:.4f}, "
          f"Cp = {best['cp']:.4f}, TSR = {best['tsr']:.2f}")
    return dict(best, viable=True)


def aep_for(base, overrides, label):
    """Compute AEP for a given configuration."""
    R = base['base']['R']
    H = base['base']['H']
    free = []
    for U in U_REF:
        res = try_free_run({**base['base'], **overrides}, U)
        if res[0] is None:
            print(f"      U = {U:5.1f}   (no equilibrium)")
            continue
        cp, tsr = res
        free.append((U, cp))
        print(f"      U = {U:5.1f}   Cp = {cp:+.4f}   TSR = {tsr:.2f}")
    if len(free) < 2:
        raise RuntimeError(f"not enough free-running points for {label}")
    U_s  = np.array([f[0] for f in free])
    cp_s = np.array([f[1] for f in free])
    U_grid = np.linspace(3.0, 25.0, 200)
    cp_curve = np.interp(U_grid, U_s, cp_s)

    # Rated power from Cp at U_RATED
    cp_at_rated = float(np.interp(12.0, U_grid, cp_curve))
    rated_power = rated_power_from_cp(R, H, cp_at_rated)

    res = integrate_aep(U_grid, cp_curve, 6.0, 2.0,
                        3.0, 25.0, rated_power,
                        R, H)
    return res


def main():
    print("=" * 74)
    print("Fair rigid-blade baseline — two geometries")
    print("=" * 74)

    output = {"geometries": {}}

    for label, cfg in GEOMETRIES.items():
        base = cfg["base"]
        print(f"\n### {label}  (R = {base['R']:.3f}, H = {base['H']:.3f}, c = {base['c']:.3f}, AR = {base['H']/base['c']:.2f})")

        # Sweep rigid blade
        print(f"  Sweep: rigid blade at {label}")
        best_r = find_best_rigid(cfg, label)
        # Sweep passive CPPC
        print(f"  Sweep: passive CPPC at {label}")
        best_p = find_best_passive(cfg, label)

        if best_r.get('viable', False):
            aep_r = aep_for(cfg, {
                'prescribe_pitch': True, 'pp0_deg': best_r['psi0'],
                'pp1_deg': 0, 'pp2_deg': 0, 'pp3_deg': 0, 'pp_ph_deg': 0,
                'k_load': best_r['k_load']
            }, f"{label}/rigid")
        else:
            aep_r = None
            print(f"  No viable rigid configuration at {label}")

        aep_p = aep_for(cfg, {'k_load': best_p['k_load']}, f"{label}/passive")

        if aep_r and aep_p:
            gain = (aep_p['aep'] / aep_r['aep'] - 1.0) * 100
        else:
            gain = None

        output["geometries"][label] = {
            "R": base['R'],
            "c": base['c'],
            "H": base['H'],
            "AR": base['H'] / base['c'],
            "best_rigid": {
                "psi0_deg": best_r.get('psi0'),
                "k_load": best_r.get('k_load'),
                "cp_design": best_r.get('cp'),
                "tsr": best_r.get('tsr'),
                "viable": best_r.get('viable', False),
                "aep_kWh": aep_r['aep'] if aep_r else None,
                "cf": aep_r['cf'] if aep_r else None,
            },
            "best_passive": {
                "k_load": best_p['k_load'],
                "cp_design": best_p['cp'],
                "aep_kWh": aep_p['aep'],
                "cf": aep_p['cf'],
            },
            "gain_percent": gain,
        }

    # Add stamp
    stamp = make_stamp(
        "scripts/compute_aep_rigid_fair.py",
        script_version="2.0.0",
        n=100,
        seed=0,
        extra_files=["scripts/compute_aep.py"],
        extra_data={"U_MEAN": 6.0, "K_WEIBULL": 2.0, "CUT_IN": 3.0, "CUT_OUT": 25.0, "U_RATED": 12.0, "U_DESIGN": 6.0},
    )

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aep_rigid_fair.json")
    with open(path, "w") as fh:
        json.dump({"stamp": stamp, "geometries": output["geometries"]}, fh, indent=2)
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()