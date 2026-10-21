#!/usr/bin/env python3
"""Sanity-check the committed NACA 0012 polar tables.

This is a WARNING report, not a validation gate.  It flags three patterns
that are suspicious for an attached-flow polar:

1. ``|dCl/dalpha| > 1.15 * 2*pi`` for ``|alpha| <= 4 deg``.  A thin
   airfoil has a lift slope of 2*pi per rad; a table nearly 2x that at low
   Reynolds number is a surrogate artefact, not a physical measurement.
2. Non-monotone Cl before the tabulated stall angle.
3. Sign changes in Cm through the attached range (``|alpha| <= 20 deg``).

The script exits 0 even when it finds warnings so CI can publish them
without blocking on a known model-form limitation.  It exits non-zero only
if there are no polar files or a file cannot be parsed.

Usage:
    python3 scripts/check_polars.py
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
POLAR_GLOB = os.path.join(_ROOT, "airfoil_polars", "**", "*.csv")
SLOPE_LIMIT = 1.15 * 2.0 * np.pi
ATTACHED_DEG = 20.0
LOW_ALPHA_DEG = 4.0


def load_polar(path):
    d = np.genfromtxt(path, delimiter=",", comments="#")
    if d.ndim != 2 or d.shape[1] < 3:
        raise ValueError(f"{path}: expected at least 3 columns")
    d = d[~np.isnan(d).any(axis=1)]
    o = np.argsort(d[:, 0])
    a, cl, cd = d[o, 0], d[o, 1], d[o, 2]
    cm = d[o, 3] if d.shape[1] >= 4 else np.zeros_like(a)
    return a, cl, cd, cm


def check_one(path):
    """Return a list of warning strings for one polar file."""
    a, cl, cd, cm = load_polar(path)
    warnings = []
    low = np.abs(a) <= LOW_ALPHA_DEG
    if low.sum() >= 2:
        slope = float(np.polyfit(np.radians(a[low]), cl[low], 1)[0])
        if abs(slope) > SLOPE_LIMIT:
            warnings.append(
                f"attached lift slope {abs(slope):.2f}/rad exceeds "
                f"1.15*2*pi = {SLOPE_LIMIT:.2f}/rad for |alpha| <= 4 deg"
            )

    # Stall angle: first maximum of Cl on the positive side up to 20 deg.
    pos = (a >= 0.0) & (a <= ATTACHED_DEG)
    if pos.sum() >= 3:
        aa, cc = a[pos], cl[pos]
        istall = int(np.argmax(cc))
        pre = cc[:istall + 1]
        if len(pre) >= 3 and np.any(np.diff(pre) < -1e-5):
            warnings.append(
                f"Cl is non-monotone before the tabulated stall at "
                f"alpha = {aa[istall]:.1f} deg"
            )
        post = cc[istall:]
        if len(post) >= 3 and np.any(np.diff(post) < -1e-5):
            warnings.append(
                f"Cl drops after the first peak at alpha = {aa[istall]:.1f} "
                f"deg (laminar-bubble kink)"
            )

    attached = np.abs(a) <= ATTACHED_DEG
    cm_att = cm[attached]
    nz = np.abs(cm_att) > 1e-6
    signs = np.sign(cm_att[nz])
    if len(signs) >= 2 and np.any(np.diff(signs) != 0):
        warnings.append("Cm changes sign in the attached range |alpha| <= 20 deg")

    return warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--polar-glob", default=POLAR_GLOB,
                    help="glob for polar CSVs (default: airfoil_polars/**/*.csv)")
    args = ap.parse_args(argv)

    files = sorted(glob.glob(args.polar_glob, recursive=True))
    if not files:
        print(f"ERROR: no polar CSVs found for {args.polar_glob}", file=sys.stderr)
        return 1

    n_warn = 0
    print("Polar sanity report (warnings only; not a validation gate)")
    print(f"  files: {len(files)}")
    for path in files:
        rel = os.path.relpath(path, _ROOT)
        try:
            warns = check_one(path)
        except Exception as exc:
            print(f"ERROR: {rel}: {exc}", file=sys.stderr)
            return 1
        print(f"  {rel}: {'OK' if not warns else f'{len(warns)} warning(s)'}")
        for w in warns:
            print(f"    WARNING: {w}")
            n_warn += 1
    print(f"  total warnings: {n_warn}")
    print("  These are known surrogate/model-form limitations; see "
          "airfoil_polars/README.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
