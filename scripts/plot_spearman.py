#!/usr/bin/env python3
"""Plot Spearman sensitivity from ``scripts/spearman_results.json`` (plot only)."""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.spearman_sensitivity import make_plot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=os.path.join(_ROOT, "scripts", "spearman_results.json"))
    ap.add_argument("--out", default=os.path.join(_ROOT, "docs", "spearman.png"))
    args = ap.parse_args(argv)

    with open(args.json, encoding="utf-8") as fh:
        data = json.load(fh)
    names = data["param_names"]
    anchor_results = {}
    for anchor, rows in data["anchor_results"].items():
        rhos = np.array([rows[n]["rho"] for n in names], dtype=float)
        pvals = np.array([rows[n]["p"] for n in names], dtype=float)
        anchor_results[anchor] = (rhos, pvals)
    make_plot(anchor_results, names, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
