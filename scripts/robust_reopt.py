#!/usr/bin/env python3
"""Robust local re-optimisation of the passive and scale-up designs.

The original optimisers maximise the *nominal* Cp at one parameter set.  That
rewards designs that sit on a bifurcation edge and collapse when the Cm table
or finite-span multiplier moves.  This script adds a robust objective:

    maximise  mean(Cp)  (or the 10th percentile) over a small scenario set
    sampled from the UQ input ranges, including cm_scale and
    tip_loss_multiplier.

It starts from the stored optimiser solutions and runs a bounded
Nelder-Mead refinement, so it is a genuine re-optimisation but much cheaper
than repeating the global DE.  The output records nominal Cp, scenario mean,
scenario p10 and every parameter that sits on a bound.

Writes ``scripts/robust_optimization.json``.

Usage:
    python3 scripts/robust_reopt.py
    python3 scripts/robust_reopt.py --mode p10 --maxiter 10
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import numpy as np
from scipy.optimize import minimize

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from scripts.stamp import write_json_with_stamp
from sharp_vawt import create_sim_from_params
from vawt_presets import PRESETS

BETZ = 16.0 / 27.0
PENALTY = 1000.0

# Scenario set: a small, explicitly enumerated subset of the UQ ranges.
# Grabbing the full 13-D Saltelli design inside an optimiser is prohibitive;
# these four directions are the ones that have caused collapse.
SCENARIOS: list[dict[str, Any]] = [
    {},
    {"cm_scale": 0.0},
    {"tip_loss_multiplier": 0.96},
    {"cm_scale": 0.0, "tip_loss_multiplier": 0.96},
    {"cd_add": 0.005},
]

PASSIVE_NAMES = ("c", "k_load", "mc", "dcw", "ar", "sp", "bias_deg")
SCALEUP_NAMES = ("R", "c_over_R", "H_over_R", "k_load_ref", "mc_ref",
                 "ar", "sp", "dcw")


def _cp(params: dict[str, Any], extra: dict[str, Any]) -> float | None:
    try:
        r = create_sim_from_params({**params, **extra}).run()
    except Exception:
        return None
    cp = float(r.get("cp", -1.0))
    if (not np.isfinite(cp) or cp <= 0.0 or cp > BETZ
            or not r.get("steady", True)
            or float(r.get("aoa_max", 0.0)) > 40.0):
        return None
    return cp


def _metrics(params, scenarios, mode):
    cps = [_cp(params, s) for s in scenarios]
    if any(c is None for c in cps):
        return PENALTY, {"valid": False, "cps": cps}
    arr = np.asarray(cps, dtype=float)
    obj = float(np.mean(arr) if mode == "mean" else np.percentile(arr, 10))
    return -obj, {"valid": True, "nominal_cp": float(arr[0]),
                  "mean_cp": float(arr.mean()),
                  "p10_cp": float(np.percentile(arr, 10)),
                  "min_cp": float(arr.min()), "max_cp": float(arr.max()),
                  "scenario_cps": [float(c) for c in arr]}


def _active_bounds(x, lb, ub, names, rel=0.01):
    active = []
    for v, lo, hi, name in zip(x, lb, ub, names):
        span = max(hi - lo, 1e-12)
        if v <= lo + rel * span:
            active.append({"name": name, "value": float(v), "bound": "lower",
                           "limit": float(lo)})
        elif v >= hi - rel * span:
            active.append({"name": name, "value": float(v), "bound": "upper",
                           "limit": float(hi)})
    return active


def _scaleup_params(x):
    R, cR, HR, kl, mcr, ar, sp, dcw = (float(v) for v in x)
    scale = R / 0.60
    return {
        **PRESETS["scaleup"],
        "R": R, "c": cR * R, "H": HR * R,
        "k_load": kl * scale ** 5,
        "mc": mcr * scale ** 3,
        "mb": 0.010 * scale ** 3,
        "ar": ar, "sp": sp, "dcw": dcw,
        "free": True, "prescribe_pitch": False,
    }


def _passive_params(x):
    p = dict(PRESETS["optimised_passive"])
    for name, val in zip(PASSIVE_NAMES, x):
        p[name] = float(val)
    return p


def optimise_design(label, x0, lb, ub, names, build, args):
    calls = {"n": 0}

    def objective(x):
        calls["n"] += 1
        obj, _ = _metrics(build(x), SCENARIOS, args.mode)
        return obj

    print(f"\n[{label}] start Cp = {_cp(build(x0), {}):.4f}")
    print(f"[{label}] robust {args.mode} over {len(SCENARIOS)} scenarios, "
          f"maxiter = {args.maxiter}")
    res = minimize(objective, x0, method="Nelder-Mead",
                   bounds=list(zip(lb, ub)),
                   options={"maxiter": args.maxiter, "xatol": 1e-4,
                            "fatol": 1e-4, "disp": False})
    x = np.asarray(res.x, dtype=float)
    params = build(x)
    _, m = _metrics(params, SCENARIOS, args.mode)
    active = _active_bounds(x, lb, ub, names)
    print(f"[{label}] nominal Cp = {m['nominal_cp']:.4f}  "
          f"mean = {m['mean_cp']:.4f}  p10 = {m['p10_cp']:.4f}  "
          f"({calls['n']} objective calls)")
    print(f"[{label}] bound-active: "
          f"{', '.join(a['name'] for a in active) if active else 'none'}")
    return {
        "design": label,
        "param_names": list(names),
        "x0": [float(v) for v in x0],
        "x": [float(v) for v in x],
        "bounds": [[float(a), float(b)] for a, b in zip(lb, ub)],
        "best_params": params,
        "objective_mode": args.mode,
        "scenarios": SCENARIOS,
        "metrics": m,
        "bound_active": active,
        "success": bool(res.success),
        "message": str(res.message),
        "objective_calls": calls["n"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=("mean", "p10"), default="mean")
    ap.add_argument("--maxiter", type=int, default=12)
    ap.add_argument("--quick", action="store_true",
                    help="run only the passive design")
    args = ap.parse_args(argv)

    out = {
        "note": (
            "Robust local refinement from the stored optimiser solutions. "
            "The scenario set is a small explicit subset of the UQ input "
            "ranges, not the full Saltelli design. These are model results."
        ),
        "objective": f"maximise scenario {args.mode} Cp",
        "designs": {},
    }

    # Passive R = 0.6 m
    old = json.load(open(os.path.join(_HERE, "optimization_passive.json")))
    p = old["best_params"]
    x0 = np.array([p[k] for k in PASSIVE_NAMES], dtype=float)
    b = old["bounds"]
    lb = np.array([v[0] for v in b], dtype=float)
    ub = np.array([v[1] for v in b], dtype=float)
    out["designs"]["passive"] = optimise_design(
        "passive R=0.60 m", x0, lb, ub, PASSIVE_NAMES, _passive_params, args)

    if not args.quick:
        old_s = json.load(open(os.path.join(_HERE, "optimization_scaleup.json")))
        x0s = np.array(old_s["best_x"], dtype=float)
        b = old_s["bounds"]
        lb = np.array([v[0] for v in b], dtype=float)
        ub = np.array([v[1] for v in b], dtype=float)
        out["designs"]["scaleup"] = optimise_design(
            "scaleup R=2.72 m", x0s, lb, ub, SCALEUP_NAMES,
            _scaleup_params, args)

    path = os.path.join(_HERE, "robust_optimization.json")
    write_json_with_stamp(
        path=path,
        data=out,
        script="scripts/robust_reopt.py",
        version="2.0.0",
        n=1,
        seed=0,
        extra_files=["vawt_presets.py", "scripts/compute_aep.py"],
        extra_data={},
    )
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
