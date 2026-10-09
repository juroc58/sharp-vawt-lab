"""
Spearman rank-correlation sensitivity on the UQ samples.

Reads scripts/uncertainty_results.json (produced by scripts/uncertainty.py)
and computes the rank correlation between each of the 8 uncertain model
constants and the resulting Cp for each anchor.

Unlike Pearson, Spearman detects any *monotonic* relationship, which is
what we expect from the physics.  Unlike Sobol, it needs no new sampling
— it's a post-processing step on existing data.

Produces docs/spearman.png and scripts/spearman_results.json.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)


# ---------------------------------------------------------------------------
# Load UQ results
# ---------------------------------------------------------------------------
def load_uq():
    path = os.path.join(_HERE, "uncertainty_results.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found — run scripts/uncertainty.py first"
        )
    with open(path) as fh:
        data = json.load(fh)
    return data


def extract_design_matrix(raw_rows, param_names):
    """Rebuild X (N_samples, N_params) and cp (N_samples) from raw rows."""
    # The JSON stores only the Cp per sample, not the parameter values.
    # We need to reconstruct them from the LHS scheme — which requires
    # re-generating the same LHS with the same seed.
    from scripts.uncertainty import latin_hypercube, sample_to_params, UQ_SPEC
    unit = latin_hypercube(len(raw_rows), seed=42)
    X = np.zeros((len(raw_rows), len(param_names)))
    cp = np.zeros(len(raw_rows))
    for i, row in enumerate(raw_rows):
        params = sample_to_params(unit[i])
        for j, name in enumerate(param_names):
            X[i, j] = params[name]
        cp[i] = row["cp"]
    return X, cp


# ---------------------------------------------------------------------------
# Spearman correlation
# ---------------------------------------------------------------------------
def compute_spearman(X, cp, param_names):
    """Return (rho, pval) for each parameter."""
    rhos = []
    pvals = []
    for j in range(X.shape[1]):
        rho, p = spearmanr(X[:, j], cp)
        rhos.append(rho)
        pvals.append(p)
    return np.array(rhos), np.array(pvals)


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
def make_plot(anchor_results, param_names, out_path):
    """
    anchor_results: dict {anchor_name: (rhos, pvals)}
    """
    anchors = list(anchor_results.keys())
    n_anchors = len(anchors)
    n_params = len(param_names)

    fig, axes = plt.subplots(
        1, n_anchors, figsize=(4.5 * n_anchors, 5.5),
        sharey=True,
    )
    if n_anchors == 1:
        axes = [axes]

    for ax, anchor in zip(axes, anchors):
        rhos, pvals = anchor_results[anchor]
        # sort by |rho|
        order = np.argsort(-np.abs(rhos))
        y_pos = np.arange(n_params)
        colors = [
            "C3" if abs(r) > 0.4 else
            "C0" if abs(r) > 0.2 else
            "0.6" for r in rhos[order]
        ]
        ax.barh(y_pos, rhos[order], color=colors, edgecolor="k", lw=0.5)
        ax.set_yticks(y_pos)
        ax.set_yticklabels([param_names[i] for i in order], fontsize=9)
        ax.axvline(0, color="k", lw=0.5)
        ax.set_xlim(-1.0, 1.0)
        ax.set_xlabel("Spearman ρ")
        ax.set_title(anchor, fontsize=11)
        ax.grid(axis="x", alpha=0.3)
        # annotate significance
        for i, idx in enumerate(order):
            if pvals[idx] < 0.01:
                ax.text(
                    rhos[idx] + 0.02 * np.sign(rhos[idx]), i,
                    "**", va="center",
                    fontsize=8, color="k",
                )
            elif pvals[idx] < 0.05:
                ax.text(
                    rhos[idx] + 0.02 * np.sign(rhos[idx]), i,
                    "*", va="center", fontsize=8,
                )

    fig.suptitle(
        "Spearman rank correlation — which uncertain parameter drives Cp",
        fontsize=13, fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=140)
    print(f"Wrote {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 74)
    print("Spearman rank-correlation sensitivity")
    print("=" * 74)

    data = load_uq()
    param_names = [p[0] for p in data["parameters"]]
    anchor_names = list(data["summary"].keys())

    # Group raw rows by anchor
    rows_by_anchor = {a: [] for a in anchor_names}
    for row in data["raw"]:
        rows_by_anchor[row["anchor"]].append(row)

    # Compute Spearman per anchor
    from scripts.uncertainty import latin_hypercube, sample_to_params
    unit = latin_hypercube(data["n_samples"], seed=data["seed"])

    anchor_results = {}
    print()
    print(f"{'anchor':<22} {'top parameter':<24} "
          f"{'rho':>8} {'p-value':>10}")
    print("-" * 74)

    summary_out = {}
    for anchor in anchor_names:
        rows = rows_by_anchor[anchor]
        if not rows:
            continue
        X = np.zeros((len(rows), len(param_names)))
        cp = np.zeros(len(rows))
        for i, row in enumerate(rows):
            params = sample_to_params(unit[i])
            for j, name in enumerate(param_names):
                X[i, j] = params[name]
            cp[i] = row["cp"]

        rhos, pvals = compute_spearman(X, cp, param_names)
        anchor_results[anchor] = (rhos, pvals)

        # Find strongest
        idx_max = int(np.argmax(np.abs(rhos)))
        print(f"{anchor:<22} {param_names[idx_max]:<24} "
              f"{rhos[idx_max]:+8.3f} {pvals[idx_max]:>10.2e}")

        summary_out[anchor] = {
            name: {"rho": float(rhos[j]), "p": float(pvals[j])}
            for j, name in enumerate(param_names)
        }

    # Full rankings
    print()
    print("=" * 74)
    print("Full rankings  (|rho| > 0.2 marked with *;  p < 0.01 with **)")
    print("=" * 74)
    for anchor in anchor_names:
        if anchor not in anchor_results:
            continue
        rhos, pvals = anchor_results[anchor]
        order = np.argsort(-np.abs(rhos))
        print(f"\n  {anchor}:")
        for j in order:
            mark = "**" if pvals[j] < 0.01 else "*" if pvals[j] < 0.05 else "  "
            print(f"    {param_names[j]:<26} "
                  f"rho = {rhos[j]:+7.3f}   "
                  f"p = {pvals[j]:.2e}  {mark}")

    # Plot
    out_png = os.path.join(_ROOT, "docs", "spearman.png")
    make_plot(anchor_results, param_names, out_png)

    # Save
    out_json = os.path.join(_HERE, "spearman_results.json")
    with open(out_json, "w") as fh:
        json.dump({
            "param_names": param_names,
            "anchor_results": summary_out,
        }, fh, indent=2)
    print(f"\nWrote {out_json}")


if __name__ == "__main__":
    main()