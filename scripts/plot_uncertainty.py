#!/usr/bin/env python3
"""Plot the uncertainty histograms from ``scripts/uncertainty_results.json``.

This is a plot-only step: it never re-runs the simulator and never smooths or
filters the stored Cp values.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=os.path.join(_ROOT, "scripts", "uncertainty_results.json"))
    ap.add_argument("--out", default=os.path.join(_ROOT, "docs", "uncertainty.png"))
    args = ap.parse_args(argv)

    with open(args.json, encoding="utf-8") as fh:
        data = json.load(fh)

    summary = data["summary"]
    anchors = list(summary)
    raw = data["raw"]
    by_anchor = {a: [r["cp"] for r in raw if r["anchor"] == a] for a in anchors}

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes = axes.flatten()
    for ax, name in zip(axes, anchors):
        cps = np.asarray(by_anchor[name], dtype=float)
        if cps.size == 0:
            ax.text(0.5, 0.5, "all failed", ha="center", va="center",
                    transform=ax.transAxes)
            ax.set_title(name)
            continue
        ax.hist(cps, bins=15, color="C0", alpha=0.7, edgecolor="k", lw=0.6)
        s = summary[name]
        ax.axvline(s["median"], color="C3", lw=2.0,
                   label=f"median = {s['median']:.3f}")
        ax.axvline(s["p5"], color="C3", ls=":", lw=1.2,
                   label=f"5% = {s['p5']:.3f}")
        ax.axvline(s["p95"], color="C3", ls=":", lw=1.2,
                   label=f"95% = {s['p95']:.3f}")
        ax.set_xlabel("Cp")
        ax.set_ylabel("count")
        ax.set_title(f"{name}  (N = {s['n_ok']})")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="upper left")
    fig.suptitle(
        f"Uncertainty propagation — method={data['method']}, "
        f"{data['runs_per_anchor']} runs/anchor",
        fontsize=13, fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=140)
    plt.close(fig)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
