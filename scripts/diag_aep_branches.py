#!/usr/bin/env python3
"""Diagnose AEP branch structure for the scale-up design.

Runs each fixed-TSR point and each free-running wind speed from multiple
starting conditions (psi0 in {0,120,240} deg and w0_frac in {0.2, 0.9, 1.2})
and records Cp, TSR_eq and which branch each run ends on.

Explains why free-running Cp at TSR ~3 (0.41) differs from the fixed-rpm
Cp(TSR) at the same TSR (0.33-0.37), and why the branch-traced run drops
at U=12-13 while the seeded runs do not.

Usage:
    python3 scripts/diag_aep_branches.py
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from vawt_core import create_sim_from_params
from vawt_presets import PRESETS

SCALEUP_BASE = dict(PRESETS["scaleup"])

# Test configurations
PSI0_DEGS = [0.0, 120.0, 240.0]
W0_FRACS = [0.2, 0.9, 1.2]

# TSR range for fixed-rpm sweep
TSRS = np.linspace(1.0, 4.0, 13)

# Wind speeds for free-running
U_REF = np.arange(3.0, 26.0, 1.0).tolist()


def run_fixed_tsr(tsr, psi0_deg):
    """Run fixed-rpm at given TSR with initial psi0."""
    params = {**SCALEUP_BASE, 'free': False, 'tsr': float(tsr), 'psi0_deg': psi0_deg}
    r = create_sim_from_params(params).run()
    return {
        'tsr': tsr,
        'psi0_deg': psi0_deg,
        'cp': float(r['cp']),
        'tsr_eq': float(r['tsr_eq']),
        'steady': bool(r.get('steady', True)),
        'aoa_max': float(r['aoa_max']),
        'pitch_min': float(r['pitch_min']) if r.get('pitch_min') is not None else None,
        'pitch_max': float(r['pitch_max']) if r.get('pitch_max') is not None else None,
    }


def run_free(U, w0_frac, psi0_deg):
    """Run free-running at given U with initial conditions."""
    params = {**SCALEUP_BASE, 'free': True, 'U': float(U),
              'w0_frac': w0_frac, 'psi0_deg': psi0_deg}
    try:
        r = create_sim_from_params(params).run()
    except Exception as e:
        return {'U': U, 'w0_frac': w0_frac, 'psi0_deg': psi0_deg, 'error': str(e)}
    cp = float(r['cp'])
    if not r.get('steady', True) or cp <= 0.0 or not np.isfinite(cp):
        return {'U': U, 'w0_frac': w0_frac, 'psi0_deg': psi0_deg, 'cp': None, 'steady': False}
    return {
        'U': U,
        'w0_frac': w0_frac,
        'psi0_deg': psi0_deg,
        'cp': cp,
        'tsr_eq': float(r['tsr_eq']),
        'rpm': float(r['rpm']),
        'aoa_max': float(r['aoa_max']),
        'steady': bool(r.get('steady', True)),
    }


def classify_branch(cp, tsr_eq):
    """Classify which branch based on Cp and TSR."""
    if cp is None:
        return 'none'
    if cp > 0.35 and tsr_eq > 2.8:
        return 'high'
    elif cp < 0.35 and tsr_eq < 2.9:
        return 'low'
    else:
        return 'ambiguous'


def main():
    print("=" * 80)
    print("AEP Branch Diagnosis — Scale-Up Sharp Cycloturbine (R=2.72 m)")
    print("=" * 80)
    
    results = {
        'fixed_tsr': [],
        'free_running': [],
    }
    
    # 1. Fixed-rpm Cp(TSR) with multiple psi0
    print("\n1. FIXED-RPM Cp(TSR) WITH MULTIPLE PSI0")
    print("-" * 80)
    print(f"{'TSR':>6} {'psi0':>8} {'Cp':>10} {'TSR_eq':>10} {'Branch':>10} {'pitch_range':>20}")
    for tsr in TSRS:
        vals = []
        for psi in PSI0_DEGS:
            res = run_fixed_tsr(tsr, psi)
            results['fixed_tsr'].append(res)
            branch = classify_branch(res['cp'], res['tsr_eq'])
            pitch_range = f"[{res['pitch_min']:+.1f},{res['pitch_max']:+.1f}]" if res['pitch_min'] is not None else "N/A"
            print(f"{tsr:6.2f} {psi:8.1f} {res['cp']:10.4f} {res['tsr_eq']:10.3f} {branch:>10} {pitch_range:>20}")
            vals.append(res['cp'])
        cp_spread = max(vals) - min(vals)
        if cp_spread > 0.03:
            print(f"  *** BISTABLE at TSR={tsr:.2f}: Cp spread = {cp_spread:.4f} ***")
    
    # 2. Free-running at each U with multiple seeds
    print("\n2. FREE-RUNNING AT EACH WIND SPEED WITH MULTIPLE SEEDS")
    print("-" * 80)
    for U in U_REF:
        print(f"\n  U = {U:.1f} m/s:")
        branches_found = set()
        for w0 in W0_FRACS:
            for psi in PSI0_DEGS:
                res = run_free(U, w0, psi)
                results['free_running'].append(res)
                if 'error' in res:
                    branch = 'error'
                else:
                    branch = classify_branch(res['cp'], res['tsr_eq'])
                branches_found.add(branch)
                status = f"  w0={w0:.2f}, psi={psi:6.1f}: "
                if 'error' in res:
                    status += f"ERROR: {res['error']}"
                elif res['cp'] is None:
                    status += f"no equilibrium"
                else:
                    status += f"Cp={res['cp']:.4f}, TSR={res['tsr_eq']:.3f}, branch={branch}"
                print(status)
        if len(branches_found) > 1:
            print(f"  *** MULTIPLE BRANCHES at U={U:.1f}: {branches_found} ***")
    
    # 3. Branch-traced (continuation) vs fixed seeds
    print("\n3. BRANCH-TRACED CONTINUATION vs FIXED SEEDS")
    print("-" * 80)
    
    # Branch-traced (continuation)
    print("  Branch-traced (continuation from U=3):")
    w0_frac = 0.9
    psi0_deg = 0.0
    traced_cps = []
    for U in U_REF:
        res = run_free(U, w0_frac, psi0_deg)
        if res['cp'] is not None:
            traced_cps.append(res['cp'])
            # Update for next U (simple continuation)
            w0_frac = res['tsr_eq'] * U / (SCALEUP_BASE['tsr'] * (U + 1.0)) if (U + 1.0) > 0 else 0.9
            psi0_deg = 0.0  # Use 0 for continuation
        else:
            traced_cps.append(None)
        branch = classify_branch(res['cp'], res['tsr_eq']) if res['cp'] else 'none'
        print(f"  U={U:4.1f}: Cp={res['cp']:.4f} TSR={res['tsr_eq']:.3f} branch={branch}")
    
    # Fixed high seed
    print("\n  Fixed high seed (w0=1.20, psi=0):")
    high_cps = []
    for U in U_REF:
        res = run_free(U, 1.20, 0.0)
        high_cps.append(res['cp'])
        branch = classify_branch(res['cp'], res['tsr_eq']) if res['cp'] else 'none'
        print(f"  U={U:4.1f}: Cp={res['cp']:.4f} TSR={res['tsr_eq']:.3f} branch={branch}")
    
    # Fixed low seed
    print("\n  Fixed low seed (w0=0.20, psi=0):")
    low_cps = []
    for U in U_REF:
        res = run_free(U, 0.20, 0.0)
        low_cps.append(res['cp'])
        branch = classify_branch(res['cp'], res['tsr_eq']) if res['cp'] else 'none'
        print(f"  U={U:4.1f}: Cp={res['cp']:.4f} TSR={res['tsr_eq']:.3f} branch={branch}")
    
    # Summary
    print("\n4. SUMMARY")
    print("-" * 80)
    print("Fixed-rpm Cp(TSR):")
    for i, tsr in enumerate(TSRS):
        cps_at_tsr = [r['cp'] for r in results['fixed_tsr'] if abs(r['tsr'] - tsr) < 1e-6]
        if cps_at_tsr:
            spread = max(cps_at_tsr) - min(cps_at_tsr)
            mean_cp = np.mean(cps_at_tsr)
            print(f"  TSR={tsr:.2f}: mean Cp={mean_cp:.4f}, spread={spread:.4f}, "
                  f"bistable={'YES' if spread > 0.03 else 'NO'}")
    
    print("\nFree-running Cp(U):")
    print(f"{'U':>6} {'traced':>10} {'high seed':>10} {'low seed':>10}")
    for i, U in enumerate(U_REF):
        print(f"{U:6.1f} {traced_cps[i] if traced_cps[i] else 'fail':>10} "
              f"{high_cps[i] if high_cps[i] else 'fail':>10} {low_cps[i] if low_cps[i] else 'fail':>10}")
    
    # Save results
    out_path = os.path.join(_HERE, "diag_aep_branches.json")
    with open(out_path, 'w') as fh:
        json.dump(results, fh, indent=2)
    print(f"\nSaved detailed results to {out_path}")


if __name__ == "__main__":
    main()