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

from vawt_core import create_sim_from_params
from compute_aep import (
    BASE, integrate_aep,
    U_MEAN, K_WEIBULL, CUT_IN, CUT_OUT, P_RATED_W,
)

U_DESIGN = 6.0
U_REF    = [3.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]

GEOMETRIES = {
    "sharp_inspired": {
        "base": {**BASE},   # already the Sharp-inspired config
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
        "rated_power_override": 25000.0,   # 46x area -> 100x rating (keeps cap non-binding)
    },
}


def rigid_params(base, psi0):
    return {**base,
            'prescribe_pitch': True,
            'pp0_deg': float(psi0),
            'pp1_deg': 0.0, 'pp2_deg': 0.0, 'pp3_deg': 0.0, 'pp_ph_deg': 0.0}


def try_free_run(params, U):
    try:
        r = create_sim_from_params({**params, 'free': True, 'U': float(U)}).run()
    except Exception:
        return None
    if not r.get('steady', True):
        return None
    cp = float(r['cp'])
    if cp <= 0.0 or not np.isfinite(cp):
        return None
    return cp, float(r['tsr_eq'])


def sweep_rigid(base, psi_grid, kl_grid, label):
    print(f"  Sweep: rigid blade at {label}")
    print(f"    {'psi0':>6} {'k_load':>9}  {'Cp':>9}  {'TSR':>6}")
    results = []
    for psi0 in psi_grid:
        for kl in kl_grid:
            p = rigid_params(base, psi0); p['k_load'] = kl
            res = try_free_run(p, U_DESIGN)
            if res is None:
                continue
            cp, tsr = res
            results.append(dict(psi0=psi0, k_load=kl, cp=cp, tsr=tsr))
    if not results:
        raise RuntimeError(f"no steady rigid configs at {label}")
    best = max(results, key=lambda r: r['cp'])
    print(f"    best: psi0 = {best['psi0']:+.1f} deg, "
          f"k_load = {best['k_load']:.4f}, Cp = {best['cp']:.4f}, "
          f"TSR = {best['tsr']:.2f}")
    return best


def sweep_passive(base, kl_grid, label):
    print(f"  Sweep: passive CPPC at {label}")
    print(f"    {'k_load':>9}  {'Cp':>9}  {'TSR':>6}")
    results = []
    for kl in kl_grid:
        res = try_free_run({**base, 'k_load': kl}, U_DESIGN)
        if res is None:
            continue
        cp, tsr = res
        results.append(dict(k_load=kl, cp=cp, tsr=tsr))
    if not results:
        raise RuntimeError(f"no steady passive configs at {label}")
    best = max(results, key=lambda r: r['cp'])
    print(f"    best: k_load = {best['k_load']:.4f}, Cp = {best['cp']:.4f}, "
          f"TSR = {best['tsr']:.2f}")
    return best


def aep_for(base, overrides, label, rated_power=P_RATED_W):
    free = []
    for U in U_REF:
        res = try_free_run({**base, **overrides}, U)
        if res is None:
            print(f"      U = {U:5.1f}   (no equilibrium)")
            continue
        cp, tsr = res
        free.append((U, cp))
    if len(free) < 2:
        raise RuntimeError(f"not enough free-running points for {label}")
    U_s  = np.array([f[0] for f in free])
    cp_s = np.array([f[1] for f in free])
    U_grid = np.linspace(CUT_IN, CUT_OUT, 200)
    cp_curve = np.interp(U_grid, U_s, cp_s)
    return integrate_aep(U_grid, cp_curve, U_MEAN, K_WEIBULL,
                         CUT_IN, CUT_OUT, rated_power,
                         base['R'], base['H'])


def main():
    print("=" * 74)
    print("Fair rigid-blade baseline — two geometries")
    print("=" * 74)

    output = {"geometries": {}}

    for label, cfg in GEOMETRIES.items():
        base = cfg["base"]
        print()
        print(f"### {label}  (R = {base['R']:.3f}, "
              f"H = {base['H']:.3f}, c = {base['c']:.3f}, "
              f"AR = {base['H']/base['c']:.2f})")

        best_r = sweep_rigid(base, cfg["pitch_grid"], cfg["kload_grid"], label)
        best_p = sweep_passive(base, cfg["kload_grid"], label)

        print(f"    AEP for rigid at (psi0 = {best_r['psi0']:+.1f}, "
              f"k_load = {best_r['k_load']:.4f}):")
        rp = rigid_params(base, best_r['psi0']); rp['k_load'] = best_r['k_load']
        rated = cfg.get("rated_power_override", P_RATED_W)
        aep_r = aep_for(base, {k: rp[k] for k in
                               ['prescribe_pitch', 'pp0_deg', 'pp1_deg',
                                'pp2_deg', 'pp3_deg', 'pp_ph_deg',
                                'k_load']}, f"{label}/rigid",
                        rated_power=rated)
        print(f"      AEP = {aep_r['aep']:.1f} kWh/yr "
              f"(CF {aep_r['cf']*100:.2f} %)")

        print(f"    AEP for passive at k_load = {best_p['k_load']:.4f}:")
        aep_p = aep_for(base, {'k_load': best_p['k_load']},
                        f"{label}/passive",
                        rated_power=rated)
        print(f"      AEP = {aep_p['aep']:.1f} kWh/yr "
              f"(CF {aep_p['cf']*100:.2f} %)")

        gain = (aep_p['aep'] / max(aep_r['aep'], 1e-9) - 1.0) * 100
        print(f"    -> passive vs rigid at this geometry: {gain:+.1f} %")

        output["geometries"][label] = {
            "R": base['R'], "c": base['c'], "H": base['H'],
            "AR": base['H']/base['c'],
            "best_rigid": {
                "psi0_deg": best_r['psi0'],
                "k_load":   best_r['k_load'],
                "cp_design": best_r['cp'],
                "aep_kWh":  aep_r['aep'],
                "cf":       aep_r['cf'],
            },
            "best_passive": {
                "k_load":    best_p['k_load'],
                "cp_design": best_p['cp'],
                "aep_kWh":   aep_p['aep'],
                "cf":        aep_p['cf'],
            },
            "gain_percent": gain,
        }

    path = os.path.join(_HERE, "aep_rigid_fair.json")
    with open(path, "w") as fh:
        json.dump(output, fh, indent=2)
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
