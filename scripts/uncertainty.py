"""
Uncertainty quantification for the Sharp cycloturbine model.

Eight model constants are uncalibrated (they come from the literature but
are not fitted to this specific machine).  We sample them over their
plausible ranges with Latin hypercube sampling and propagate through the
four anchor cases documented in the README.

Outputs
-------
* Terminal table: Cp mean, median, 5 %, 95 % per anchor
* docs/uncertainty.png: histogram per anchor
* scripts/uncertainty_results.json: raw samples + Cp values

Runtime: ~5 min on 4 cores.
"""
from __future__ import annotations

import json
import math
import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from vawt_core import create_sim_from_params


# ============================================================================
# 1. UNCERTAIN PARAMETERS
# ============================================================================
# Each entry is (name, low, high).  Names must match AeroConfig fields
# (after the two overrides added in Step 1).
UQ_SPEC = [
    ("cd_add",                   0.001, 0.005),   # parasitic drag
    ("ds_Tf",                    1.5,   4.5),     # separation lag  (default 3)
    ("ds_Tv",                    3.0,   9.0),     # vortex lag      (default 6)
    ("ds_Ta",                    0.05,  0.15),    # attached lag    (default 0.10)
    ("ds_Kv",                    0.25,  0.75),    # vortex strength (default 0.50)
    ("tau_rev",                  0.05,  0.20),    # induction lag   (default 0.10)
    ("c_scale_override",         0.30,  0.60),    # Adams shift strength
    ("tip_loss_floor_override",  0.80,  1.00),    # finite-span floor
]
UQ_NAMES = [s[0] for s in UQ_SPEC]
UQ_LOW   = np.array([s[1] for s in UQ_SPEC])
UQ_HIGH  = np.array([s[2] for s in UQ_SPEC])

N_SAMPLES = 40
SEED = 42


# ============================================================================
# 2. ANCHOR CASES
# ============================================================================
ANCHORS: Dict[str, Dict[str, Any]] = {
    # Ham 1979 reproduction — his model class
    "ham_1979": dict(
        R=1.83, c=0.305, H=1.37, N=3,
        ar=0.0, sp=0.25,
        mb=0.010, xbcg=0.20, mc=0.002, dcw=0.30,
        balance=0, bias_deg=0.0,
        prescribe_pitch=True, pp0_deg=0.0, pp1_deg=-10.0,
        pp2_deg=0.0, pp3_deg=0.0, pp_ph_deg=0.0,
        free=False, tsr=2.5, T_max=20.0, stride=5,
        use_dynamic_stall=True,
        use_flow_curvature=False,
        use_tip_loss=False,
        use_dmst=True,
        win_deg=89.0, cb=2e-5, mu_c=0.0,
        k_load=0.0004,
    ),
    # Sharp-conforming CPPC at R = 0.60 m
    "sharp_cppc": dict(
        R=0.60, c=0.14, H=0.40, N=3,
        ar=0.50, sp=0.25,
        mb=0.010, xbcg=0.20, mc=0.002, dcw=0.30,
        balance=0, bias_deg=0.0,
        prescribe_pitch=False,
        free=True, tsr=2.0, T_max=30.0, stride=5,
        use_dynamic_stall=True,
        use_flow_curvature=True,
        use_tip_loss=True,
        use_dmst=True,
        win_deg=45.0, cb=2e-5, mu_c=3e-4,
        k_load=0.0025,
    ),
    # Optimised passive (mass-balanced) at R = 0.60 m
    "optimised_passive": dict(
        R=0.60, c=0.177, H=0.40, N=3,
        ar=0.312, sp=0.178,
        mb=0.010, xbcg=0.20, mc=0.040, dcw=-0.132,
        balance=0, bias_deg=-1.1,
        prescribe_pitch=False,
        free=True, tsr=2.14, T_max=30.0, stride=5,
        use_dynamic_stall=True,
        use_flow_curvature=True,
        use_tip_loss=True,
        use_dmst=True,
        win_deg=45.0, cb=2e-5, mu_c=3e-4,
        k_load=0.00355,
    ),
    # Scale-up R = 2.26 m with tip loss on
    "scaleup": dict(
        R=2.2602, c=0.3552, H=1.1328, N=3,
        ar=0.3542, sp=0.2001,
        mb=0.53457, xbcg=0.20, mc=0.52077, dcw=-0.1464,
        balance=0, bias_deg=0.0,
        prescribe_pitch=False,
        free=True, tsr=2.5, T_max=40.0, stride=8,
        use_dynamic_stall=True,
        use_flow_curvature=True,
        use_tip_loss=True,
        use_dmst=True,
        win_deg=45.0, cb=2e-5, mu_c=3e-4,
        k_load=0.970696,
    ),
}
ANCHOR_NAMES = list(ANCHORS.keys())


# ============================================================================
# 3. LHS SAMPLING
# ============================================================================
def latin_hypercube(n: int, seed: int) -> np.ndarray:
    """Simple LHS in [0,1]^d with the standard stratified shuffle."""
    rng = np.random.default_rng(seed)
    d = len(UQ_SPEC)
    # Stratify each dimension into n equal bins, one sample per bin
    strata = (np.arange(n)[:, None] + rng.random((n, d))) / n
    # Independently shuffle each column
    for j in range(d):
        strata[:, j] = rng.permutation(strata[:, j])
    return strata


def sample_to_params(unit_row: np.ndarray) -> Dict[str, float]:
    """Map a sample in [0,1]^d to physical parameter values."""
    values = UQ_LOW + unit_row * (UQ_HIGH - UQ_LOW)
    return {name: float(v) for name, v in zip(UQ_NAMES, values)}


# ============================================================================
# 4. WORKER
# ============================================================================
def run_one_task(args):
    """Standalone top-level function for pickling."""
    anchor_name, anchor_params, uq_params = args
    try:
        params = {**anchor_params, **uq_params}
        r = create_sim_from_params(params).run()
        cp = float(r["cp"])
        if not np.isfinite(cp) or cp <= 0.0:
            return (anchor_name, None, "non-positive Cp")
        return (anchor_name,
                dict(cp=cp,
                     tsr=float(r["tsr_eq"]),
                     aoa_max=float(r["aoa_max"]),
                     steady=bool(r.get("steady", True))),
                None)
    except Exception as e:
        return (anchor_name, None, str(e)[:80])


# ============================================================================
# 5. MAIN
# ============================================================================
def main():
    print("=" * 74)
    print("Uncertainty quantification — Sharp cycloturbine model")
    print("=" * 74)
    print(f"  Samples per anchor : {N_SAMPLES}")
    print(f"  Anchors            : {len(ANCHORS)}")
    print(f"  Total runs         : {N_SAMPLES * len(ANCHORS)}")
    print()
    print("  Uncertain parameters and ranges:")
    for name, lo, hi in UQ_SPEC:
        print(f"    {name:<26s} {lo:>8.4g}  ->  {hi:<8.4g}")
    print()

    # Generate samples
    unit = latin_hypercube(N_SAMPLES, SEED)
    samples = [sample_to_params(unit[i]) for i in range(N_SAMPLES)]

    # Build task list
    tasks = []
    for s_idx, uq in enumerate(samples):
        for anchor_name, anchor_params in ANCHORS.items():
            tasks.append((anchor_name, anchor_params, uq))

    # Run in parallel
    print("  Running ...")
    results_by_anchor: Dict[str, List[float]] = {n: [] for n in ANCHOR_NAMES}
    failures: Dict[str, int] = {n: 0 for n in ANCHOR_NAMES}
    raw_rows: List[Dict[str, Any]] = []

    with ProcessPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(run_one_task, t) for t in tasks]
        done = 0
        for fut in as_completed(futures):
            anchor_name, res, err = fut.result()
            done += 1
            if res is not None:
                results_by_anchor[anchor_name].append(res["cp"])
                raw_rows.append({
                    "anchor": anchor_name,
                    "cp": res["cp"],
                    "tsr": res["tsr"],
                    "aoa_max": res["aoa_max"],
                    "steady": res["steady"],
                })
            else:
                failures[anchor_name] += 1
            if done % 40 == 0:
                print(f"    {done}/{len(tasks)} runs complete")

    # Summary
    print()
    print("=" * 74)
    print(f"RESULTS  (N = {N_SAMPLES} samples per anchor)")
    print("=" * 74)
    print(f"{'anchor':<22} {'N_ok':>5} {'fail':>5} "
          f"{'mean':>8} {'median':>8} {'5%':>8} {'95%':>8} {'95%-5%':>8}")
    print("-" * 74)

    summary: Dict[str, Dict[str, float]] = {}
    for name in ANCHOR_NAMES:
        cps = np.array(results_by_anchor[name])
        if len(cps) == 0:
            print(f"{name:<22} {0:>5} {failures[name]:>5}   all failed")
            continue
        m   = float(np.mean(cps))
        med = float(np.median(cps))
        p5  = float(np.percentile(cps, 5))
        p95 = float(np.percentile(cps, 95))
        width = p95 - p5
        summary[name] = dict(mean=m, median=med, p5=p5, p95=p95,
                             std=float(np.std(cps)), n_ok=len(cps),
                             n_fail=failures[name])
        print(f"{name:<22} {len(cps):>5} {failures[name]:>5} "
              f"{m:>8.4f} {med:>8.4f} {p5:>8.4f} {p95:>8.4f} {width:>8.4f}")

    # -------- figure --------
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes = axes.flatten()
    for ax, name in zip(axes, ANCHOR_NAMES):
        cps = np.array(results_by_anchor[name])
        if len(cps) == 0:
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
    fig.suptitle("Uncertainty propagation — 8 uncalibrated model constants",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_png = os.path.join(_ROOT, "docs", "uncertainty.png")
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=140)
    print(f"\nWrote {out_png}")

    # -------- JSON --------
    out_json = os.path.join(_HERE, "uncertainty_results.json")
    with open(out_json, "w") as fh:
        json.dump({
            "n_samples": N_SAMPLES,
            "seed": SEED,
            "parameters": UQ_SPEC,
            "summary": summary,
            "raw": raw_rows,
        }, fh, indent=2)
    print(f"Wrote {out_json}")


if __name__ == "__main__":
    main()