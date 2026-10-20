"""
Uncertainty quantification for the Sharp cycloturbine model.

Eight model constants are uncalibrated (they come from the literature but
are not fitted to this specific machine).  We sample them over their
plausible ranges with Latin hypercube sampling (default) or Saltelli
sampling (for Sobol indices) and propagate through the four anchor
cases documented in the README.

Outputs
-------
* Terminal table: Cp mean, median, 5 %, 95 % per anchor
* docs/uncertainty.png: histogram per anchor
* scripts/uncertainty_results.json: raw samples + Cp values (+ Sobol indices if Saltelli used)
* .uq_cache/: disk cache of completed runs (resume on interruption)

Runtime: ~5 min on 4 cores (LHS) or ~40 min on 4 cores (Saltelli, N=1024).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from SALib.sample import saltelli
    from SALib.analyze import sobol
    HAS_SALIB = True
except ImportError:
    HAS_SALIB = False

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
    ("cd_add",                   0.001, 0.005),   # parasitic drag (strut/interference)
    ("ds_Tf",                    1.5,   4.5),     # separation lag  (default 3)
    ("ds_Tv",                    3.0,   9.0),     # vortex lag      (default 6)
    ("ds_Ta",                    0.05,  0.15),    # attached lag    (default 0.10)
    ("ds_Kv",                    0.25,  0.75),    # vortex strength (default 0.50)
    ("tau_rev",                  0.05,  0.20),    # induction lag   (default 0.10)
    ("e_osw",                    0.85,  0.95),    # Oswald efficiency for finite-span
    ("c_scale_override",         0.30,  0.60),    # Adams shift strength
    ("tip_loss_floor_override",  0.59,  0.84),    # finite-span correction floor [0.59, 0.84] from Prandtl lifting-line theory across all anchor AR values (Sharp-inspired AR=2.86→0.59, scale-up AR=10.5→0.84)
    ("ds_Knc",                   0.5,   1.5),     # apparent-mass lift multiplier (k_nc)
    ("arm_cd",                   0.5,   1.5),     # arm drag coefficient multiplier (Geometry)
]
UQ_NAMES = [s[0] for s in UQ_SPEC]
UQ_LOW   = np.array([s[1] for s in UQ_SPEC])
UQ_HIGH  = np.array([s[2] for s in UQ_SPEC])

N_SAMPLES = 40
SEED = 42

# Disk cache for UQ runs (interrupt-safe resume)
CACHE_DIR = ".uq_cache"

# Version string that gets hashed into the cache key so that changes to
# the core physics, polars or parameter spec invalidate stale cache entries.
_UQ_VERSION = "v8-2026-10-19"


def _code_hash() -> str:
    """Hash of vawt_core.py, polars, UQ_SPEC and the script version."""
    h = hashlib.sha256()
    # Core physics
    for path in ["vawt_core.py", "scripts/uncertainty.py"]:
        try:
            with open(path, "rb") as f:
                h.update(f.read())
        except OSError:
            pass
    # UQ parameter spec (catches bound/name changes)
    h.update(json.dumps(UQ_SPEC, sort_keys=True).encode())
    # Polar files
    polars_dir = Path("polars")
    if polars_dir.is_dir():
        for f in sorted(polars_dir.glob("**/*.csv")):
            h.update(f.read_bytes())
    h.update(_UQ_VERSION.encode())
    return h.hexdigest()[:16]


def _cache_key(anchor_name: str, anchor_params: dict, uq_params: dict) -> str:
    """Stable SHA-256-based key for a (anchor, params) task.

    Includes a hash of vawt_core.py, the polar files, UQ_SPEC and a version
    string so that stale cache entries are invalidated when the code or data
    changes.
    """
    key = {
        "anchor": anchor_name,
        "anchor_params": {k: float(v) for k, v in anchor_params.items()},
        "uq_params": {k: float(v) for k, v in uq_params.items()},
        "code_hash": _code_hash(),
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def _load_from_cache(key: str) -> Optional[dict]:
    path = _cache_path(key)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _save_to_cache(key: str, result: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(key)
    with open(path, "w") as f:
        json.dump(result, f)


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
        arm_cd=1.0,
    ),
    # Sharp-inspired CPPC at R = 0.60 m
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
        arm_cd=1.0,
    ),
    # Optimised passive (mass-balanced) at R = 0.60 m — matches the
    # optimiser output in scripts/optimization_passive.json (Cp = 0.308)
    "optimised_passive": dict(
        R=0.60, c=0.070077, H=0.40, N=3,
        ar=0.260419, sp=0.209523,
        mb=0.010, xbcg=0.20, mc=0.025151, dcw=-0.190913,
        balance=0, bias_deg=4.676692,
        prescribe_pitch=False,
        free=True, tsr=2.0, T_max=30.0, stride=5,
        use_dynamic_stall=True,
        use_flow_curvature=True,
        use_tip_loss=True,
        use_dmst=True,
        win_deg=45.0, cb=2e-5, mu_c=3e-4,
        k_load=0.000535,
        arm_cd=1.0,
    ),
    # Scale-up R = 2.26 m with tip loss on
    "scaleup": dict(
        R=2.7179, c=0.3861, H=4.0568, N=3,
        ar=0.3121, sp=0.2181,
        mb=0.92954, xbcg=0.20, mc=2.69306, dcw=-0.1935,
        balance=0, bias_deg=0.0,
        prescribe_pitch=False,
        free=True, tsr=2.5, T_max=40.0, stride=8,
        use_dynamic_stall=True,
        use_flow_curvature=True,
        use_tip_loss=True,
        use_dmst=True,
        win_deg=45.0, cb=2e-5, mu_c=3e-4,
        k_load=4.164352,
        arm_cd=1.0,
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


def sample_to_params_saltelli(unit_row: np.ndarray) -> Dict[str, float]:
    """Map a Saltelli sample in [0,1]^d to physical parameter values.
    
    Saltelli samples can go slightly outside [0,1] due to the way
    Saltelli sampling extends the LHS. We clip to [0,1] before mapping.
    """
    unit_row = np.clip(unit_row, 0.0, 1.0)
    values = UQ_LOW + unit_row * (UQ_HIGH - UQ_LOW)
    return {name: float(v) for name, v in zip(UQ_NAMES, values)}


# ============================================================================
# 4. WORKER
# ============================================================================
def run_one_task(args):
    """Standalone top-level function for pickling."""
    anchor_name, anchor_params, uq_params = args
    key = _cache_key(anchor_name, anchor_params, uq_params)

    # Check disk cache first (interrupt-safe resume)
    cached = _load_from_cache(key)
    if cached is not None:
        return (anchor_name, cached, None, uq_params)

    try:
        params = {**anchor_params, **uq_params}
        r = create_sim_from_params(params).run()
        cp = float(r["cp"])
        if not np.isfinite(cp) or cp <= 0.0:
            return (anchor_name, None, "non-positive Cp", uq_params)
        result = dict(cp=cp,
                      tsr=float(r["tsr_eq"]),
                      aoa_max=float(r["aoa_max"]),
                      steady=bool(r.get("steady", True)))
        _save_to_cache(key, result)
        return (anchor_name, result, None, uq_params)
    except Exception as e:
        return (anchor_name, None, str(e)[:80], uq_params)


# ============================================================================
# 5. MAIN
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Uncertainty quantification for the Sharp cycloturbine model"
    )
    parser.add_argument(
        "--saltelli",
        action="store_true",
        help="Use Saltelli sampling for Sobol indices (requires SALib). "
             "N_SAMPLES becomes the base N; total runs = N * (D + 2).",
    )
    parser.add_argument(
        "--saltelli-n",
        type=int,
        default=None,
        help="Base N for Saltelli sampling (default: use N_SAMPLES). "
             "Total runs = N * (D + 2) per anchor (first-order) "
             "or N * (2D + 2) per anchor (second-order).",
    )
    parser.add_argument(
        "--saltelli-second-order",
        action="store_true",
        help="Compute second-order Sobol indices. Requires N * (2D + 2) "
             "samples per anchor instead of N * (D + 2).",
    )
    args = parser.parse_args()

    use_saltelli = args.saltelli
    saltelli_n = args.saltelli_n if args.saltelli_n is not None else N_SAMPLES
    calc_second_order = args.saltelli_second_order

    print("=" * 74)
    print("Uncertainty quantification — Sharp cycloturbine model")
    print("=" * 74)
    
    if use_saltelli:
        if not HAS_SALIB:
            print("ERROR: SALib not installed. Install with: pip install SALib")
            return 1
        D = len(UQ_SPEC)
        samples_per_anchor = saltelli_n * (2 * D + 2 if calc_second_order else D + 2)
        total_runs = samples_per_anchor
        print(f"  Saltelli sampling: N={saltelli_n}, D={D}, second_order={calc_second_order}")
        print(f"  Total runs per anchor: {total_runs}")
    else:
        print(f"  Samples per anchor : {N_SAMPLES}")
    print(f"  Anchors            : {len(ANCHORS)}")
    if use_saltelli:
        print(f"  Total runs         : {samples_per_anchor * len(ANCHORS)}")
    else:
        print(f"  Total runs         : {N_SAMPLES * len(ANCHORS)}")
    print()
    print("  Uncertain parameters and ranges:")
    for name, lo, hi in UQ_SPEC:
        print(f"    {name:<26s} {lo:>8.4g}  ->  {hi:<8.4g}")
    print()

    # Generate samples
    if use_saltelli:
        problem = {
            'num_vars': len(UQ_SPEC),
            'names': UQ_NAMES,
            'bounds': [[lo, hi] for lo, hi in zip(UQ_LOW, UQ_HIGH)],
        }
        # Saltelli sampling
        unit = saltelli.sample(problem, saltelli_n, calc_second_order=calc_second_order)
        samples = [sample_to_params_saltelli(row) for row in unit]
        print(f"  Generated {len(samples)} Saltelli samples")
    else:
        unit = latin_hypercube(N_SAMPLES, SEED)
        samples = [sample_to_params(unit[i]) for i in range(N_SAMPLES)]
        print(f"  Generated {len(samples)} LHS samples")

    # Build task list
    tasks = []
    for s_idx, uq in enumerate(samples):
        for anchor_name, anchor_params in ANCHORS.items():
            tasks.append((anchor_name, anchor_params, uq))

    # Run in parallel, preserving task order for Sobol compatibility
    print("  Running ...")
    results_by_anchor: Dict[str, List[float]] = {n: [] for n in ANCHOR_NAMES}
    failures: Dict[str, int] = {n: 0 for n in ANCHOR_NAMES}
    raw_rows: List[Dict[str, Any]] = []

    with ProcessPoolExecutor(max_workers=4) as ex:
        for i, (anchor_name, res, err, uq_params) in enumerate(ex.map(run_one_task, tasks)):
            if res is not None:
                results_by_anchor[anchor_name].append(res["cp"])
                raw_rows.append({
                    "anchor": anchor_name,
                    "cp": res["cp"],
                    "tsr": res["tsr"],
                    "aoa_max": res["aoa_max"],
                    "steady": res["steady"],
                    "params": {k: float(v) for k, v in uq_params.items()},
                })
            else:
                failures[anchor_name] += 1
            if (i + 1) % 40 == 0:
                print(f"    {i + 1}/{len(tasks)} runs complete")

    # Summary
    print()
    print("=" * 74)
    print(f"RESULTS  (N = {len(samples)} samples per anchor)")
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

    # Compute Sobol indices if using Saltelli
    sobol_results = {}
    if use_saltelli and HAS_SALIB:
        print("\nComputing Sobol indices...")
        # Group raw data by anchor for Sobol analysis
        for anchor_name in ANCHOR_NAMES:
            anchor_rows = [r for r in raw_rows if r["anchor"] == anchor_name]
            if len(anchor_rows) < 10:
                continue
            # Extract X matrix and Y vector
            X = np.zeros((len(anchor_rows), len(UQ_NAMES)))
            Y = np.zeros(len(anchor_rows))
            for i, row in enumerate(anchor_rows):
                for j, name in enumerate(UQ_NAMES):
                    X[i, j] = row["params"][name]
                Y[i] = row["cp"]
            # Compute Sobol indices
            problem = {
                'num_vars': len(UQ_SPEC),
                'names': UQ_NAMES,
                'bounds': [[lo, hi] for lo, hi in zip(UQ_LOW, UQ_HIGH)],
            }
            Si = sobol.analyze(problem, Y, calc_second_order=calc_second_order, print_to_console=False)
            sobol_entry = {
                'S1': {name: float(Si['S1'][i]) for i, name in enumerate(UQ_NAMES)},
                'ST': {name: float(Si['ST'][i]) for i, name in enumerate(UQ_NAMES)},
                'S1_conf': {name: float(Si['S1_conf'][i]) for i, name in enumerate(UQ_NAMES)},
                'ST_conf': {name: float(Si['ST_conf'][i]) for i, name in enumerate(UQ_NAMES)},
            }
            if calc_second_order and 'S2' in Si:
                sobol_entry['S2'] = {
                    f"{UQ_NAMES[i]}|{UQ_NAMES[j]}": float(Si['S2'][i, j])
                    for i in range(len(UQ_NAMES))
                    for j in range(i + 1, len(UQ_NAMES))
                }
                sobol_entry['S2_conf'] = {
                    f"{UQ_NAMES[i]}|{UQ_NAMES[j]}": float(Si['S2_conf'][i, j])
                    for i in range(len(UQ_NAMES))
                    for j in range(i + 1, len(UQ_NAMES))
                }
            sobol_results[anchor_name] = sobol_entry
            print(f"  {anchor_name}: S1 dominant = {max(Si['S1']):.4f}")

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
            "n_samples": len(samples),
            "seed": SEED,
            "method": "saltelli" if use_saltelli else "lhs",
            "parameters": UQ_SPEC,
            "summary": summary,
            "sobol": sobol_results,
            "raw": raw_rows,
        }, fh, indent=2)
    print(f"Wrote {out_json}")

    # Print Sobol summary if available
    if sobol_results:
        print("\nSobol indices (first-order S1 and total-order ST):")
        for anchor, res in sobol_results.items():
            print(f"\n  {anchor}:")
            for name in UQ_NAMES:
                s1 = res['S1'][name]
                st = res['ST'][name]
                print(f"    {name:>24s}: S1 = {s1:.4f}, ST = {st:.4f}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())