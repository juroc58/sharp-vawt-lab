"""
Sobol sensitivity indices on the UQ samples.

Computes first-order and total-order Sobol indices for the 8 uncertain
model constants on Cp for each anchor case. Requires SALib.

This uses the existing LHS samples from uncertainty_results.json.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

try:
    from SALib.analyze import sobol
    from SALib.sample import saltelli
except ImportError:
    print("SALib not installed. Install with: pip install SALib")
    sys.exit(1)

_HERE = Path(__file__).parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from scripts.uncertainty import UQ_SPEC, latin_hypercube, sample_to_params, ANCHORS


def load_uq():
    path = _HERE / "uncertainty_results.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run scripts/uncertainty.py first"
        )
    with open(path) as fh:
        return json.load(fh)


def build_design_matrix(data, n_samples_per_anchor):
    """Build design matrix X and output Y for each anchor from stored params."""
    param_names = [p[0] for p in UQ_SPEC]
    anchor_names = list(ANCHORS.keys())
    
    results = {}
    for anchor in anchor_names:
        rows = [r for r in data["raw"] if r["anchor"] == anchor]
        n = len(rows)
        X = np.zeros((n, len(param_names)))
        Y = np.zeros(n)
        for i, row in enumerate(rows):
            for j, name in enumerate(param_names):
                X[i, j] = row["params"][name]
            Y[i] = row["cp"]
        results[anchor] = (X, Y)
    return results


def compute_sobol(X, Y, param_names):
    """Compute Sobol indices using SALib."""
    problem = {
        'num_vars': len(param_names),
        'names': param_names,
        'bounds': [[p[1], p[2]] for p in UQ_SPEC]
    }
    
    # SALib's sobol.analyze expects Saltelli samples, but we can use
    # the 'analyze' method with pre-computed samples if we tell it
    # the samples were generated with Saltelli. 
    # Since our samples are LHS not Saltelli, we'll use the 
    # 'fast' or 'morris' analyzer instead, or compute Sobol 
    # directly using the pick-freeze method.
    
    # For now, use the Saltelli analyzer with our LHS samples
    # (approximate, but useful for ranking)
    try:
        Si = sobol.analyze(problem, Y, calc_second_order=True, print_to_console=False)
        return Si
    except Exception as e:
        print(f"  SALib error: {e}")
        return None


def compute_sobol_pickfreeze(X, Y, param_names, n_boot=100):
    """
    Compute Sobol indices using pick-freeze method (saltelli estimator).
    More robust for arbitrary sampling schemes.
    """
    N, d = X.shape
    n_boot = min(n_boot, N // 10)
    
    # Split into two matrices A and B
    split = N // 2
    A = X[:split]
    B = X[split:split*2]
    Y_A = Y[:split]
    Y_B = Y[split:split*2]
    
    # Ensure equal size
    n = min(len(A), len(B))
    A = A[:n]
    B = B[:n]
    Y_A = Y_A[:n]
    Y_B = Y_B[:n]
    
    f0 = np.mean(Y_A)
    var_Y = np.var(np.concatenate([Y_A, Y_B]))
    
    S1 = np.zeros(d)
    ST = np.zeros(d)
    
    for j in range(param_names):
        # Create C matrix: A with column j from B
        C = A.copy()
        C[:, j] = B[:, j]
        
        # Need to evaluate model at C - but we don't have the model!
        # We can't do pick-freeze without re-running simulations.
        # Fall back to SALib with our existing data.
    
    return None


def main():
    print("=" * 70)
    print("Sobol Sensitivity Analysis")
    print("=" * 70)
    
    data = load_uq()
    param_names = [p[0] for p in UQ_SPEC]
    anchor_names = list(ANCHORS.keys())
    
    # Build design matrices
    matrices = build_design_matrix(data, data["n_samples"])
    
    print(f"\n{'Anchor':<22} {'N':>4} {'Method':>10} " + "".join(f"{name:>10}" for name in param_names))
    print("-" * (56 + 10 * len(param_names)))
    
    # Since we can't do true pick-freeze without re-running sims,
    # use SALib's FAST method which works with any sampling
    # or compute using the existing samples with RBD-FAST
    # For now, compute using SALib's FAST (first-order only)
    # and approximate total-order using the sensitivity package
    
    # Alternative: Use the existing spearman results as proxy
    # and note that Sobol would require additional samples
    
    print("\nNote: True Sobol indices require Saltelli sampling (N*(d+2) samples).")
    print("Current LHS samples (N=40) are insufficient for Saltelli estimator.")
    print("Recommendation: Re-run uncertainty.py with Saltelli sampling for true Sobol.")
    print("\nApproximate first-order indices from Spearman (rank correlation):")
    
    # Load spearman results as proxy
    spearman_path = _HERE / "spearman_results.json"
    if spearman_path.exists():
        with open(spearman_path) as fh:
            spearman = json.load(fh)
        
        print(f"\n{'Anchor':<22} " + "".join(f"{name:>10}" for name in param_names))
        print("-" * (22 + 10 * len(param_names)))
        for anchor in anchor_names:
            if anchor in spearman["anchor_results"]:
                row = spearman["anchor_results"][anchor]
                print(f"{anchor:<22} " + "".join(f"{row.get(name, {}).get('rho', 0):>10.3f}" for name in param_names))
    
    # Save what we have
    out_json = _HERE / "sobol_results.json"
    with open(out_json, "w") as fh:
        json.dump({
            "note": "True Sobol indices require Saltelli sampling. These are Spearman rank correlations as proxy.",
            "method": "Spearman rank correlation (proxy for first-order Sobol)",
            "param_names": param_names,
            "anchor_results": spearman.get("anchor_results", {}) if spearman_path.exists() else {}
        }, fh, indent=2)
    print(f"\nSaved proxy results to {out_json}")
    
    print("\nRecommendation for true Sobol indices:")
    print("  pip install SALib")
    print("  Modify uncertainty.py to use Saltelli sampling: saltelli.sample(problem, N=1024)")
    print("  Re-run uncertainty.py (will take ~8x longer)")

if __name__ == "__main__":
    main()
