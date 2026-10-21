"""
Uncertainty quantification for the Sharp cycloturbine model.

Thirteen inputs are sampled: nine uncalibrated model constants, the
finite-span multiplier, the attached-flow Cm scale, the polar model-form
variant, and the arm-drag multiplier (13 dimensions); the arm-drag
multiplier is inert because every anchor sets arm_d = 0, so 12 of the 13
enter the calculation.
They are propagated with Latin hypercube sampling (default) or Saltelli
sampling (for Sobol indices) through the four anchor cases documented in
the README.

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
from vawt_presets import PRESETS


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
    ("tip_loss_multiplier",       0.85,  1.15),    # residual multiplier on the Helmbold finite-span f_ar (<1 = stronger tip loss, >1 = weaker)
    ("cm_scale",                  0.0,   1.0),     # scale on attached-flow Cm from the surrogate (0 = none, 1 = full NeuralFoil value)
    ("ds_Knc",                   0.5,   1.5),     # apparent-mass lift multiplier (k_nc)
    ("polar_variant",            0.0,   1.0),     # model form: 0 = neuralfoil table, 1 = smoothed_lowRe variant
    ("arm_cd",                   0.5,   1.5),     # arm drag coefficient multiplier (Geometry)
]
UQ_NAMES = [s[0] for s in UQ_SPEC]
UQ_LOW   = np.array([s[1] for s in UQ_SPEC])
UQ_HIGH  = np.array([s[2] for s in UQ_SPEC])

N_SAMPLES = 40
SEED = 42
# Cp below which a sample is counted as collapsed.  The Sharp-inspired
# working branch is ~0.04-0.07 and the collapsed branch ~0.003-0.005, so the
# exact threshold is not sensitive.
COLLAPSE_CP = 0.02

# Disk cache for UQ runs (interrupt-safe resume)
CACHE_DIR = ".uq_cache"

# Version string that gets hashed into the cache key so that changes to
# the core physics, polars or parameter spec invalidate stale cache entries.
_UQ_VERSION = "v13-2026-10-20"


def _code_hash() -> str:
    """Hash of vawt_core.py, airfoil polars, UQ_SPEC and the script version.

    Paths are resolved relative to the repository root (``__file__``), never
    the process working directory, so the hash is identical however the
    script is launched. Missing inputs raise instead of being silently
    skipped: a stale cache that cannot see the polars is worse than no cache.
    """
    root = Path(__file__).resolve().parent.parent
    h = hashlib.sha256()
    # Core physics (hard requirement)
    for rel in ("vawt_core.py", "scripts/uncertainty.py"):
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"UQ cache hash: missing source file {path}")
        h.update(path.read_bytes())
    # UQ parameter spec (catches bound/name changes)
    h.update(json.dumps(UQ_SPEC, sort_keys=True).encode())
    # Polar files (hard requirement: a cache key that ignores them is unsafe)
    polar_dir = root / "airfoil_polars"
    polar_files = sorted(polar_dir.glob("**/*.csv"))
    if not polar_files:
        raise FileNotFoundError(
            f"UQ cache hash: no polar CSVs found under {polar_dir}"
        )
    for f in polar_files:
        h.update(f.read_bytes())
    provenance = polar_dir / "provenance.json"
    if not provenance.is_file():
        raise FileNotFoundError(
            f"UQ cache hash: missing polar provenance {provenance}"
        )
    h.update(provenance.read_bytes())
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
        "anchor_params": {k: str(v) for k, v in anchor_params.items()},
        "uq_params": {k: str(v) for k, v in uq_params.items()},
        "code_hash": _code_hash(),
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def _base_cm0(anchor_params: Dict[str, Any]) -> Dict[str, float]:
    """Deterministic base case with physically plausible Cm = 0.

    For a symmetric NACA 0012 the attached-flow Cm should be near zero; the
    NeuralFoil table is noisy.  This run is the "physical Cm" scenario and is
    reported alongside the UQ distribution, not used to condition it.
    """
    try:
        r = create_sim_from_params({**anchor_params, "cm_scale": 0.0}).run()
        return dict(cp=float(r["cp"]), tsr=float(r["tsr_eq"]),
                    steady=bool(r.get("steady", True)))
    except Exception as exc:  # pragma: no cover - diagnostic path
        return dict(cp=float("nan"), tsr=float("nan"), steady=False,
                    error=str(exc)[:120])


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
# Named machines live in vawt_presets.py so the core dataclass defaults never
# encode a particular scale-up design.  Keep this as a copy: the UQ code
# sometimes adds model-form overrides without changing the stored preset.
ANCHORS: Dict[str, Dict[str, Any]] = {
    name: dict(PRESETS[name])
    for name in ("ham_1979", "sharp_cppc", "optimised_passive", "scaleup")
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
        # Categorical model-form input: 0 = raw NeuralFoil table, 1 = the
        # smoothed low-Re variant.  Keep the raw UQ row numeric so Sobol
        # analysis can treat it as a 0/1 indicator.
        if "polar_variant" in params:
            params["polar_variant"] = ("smoothed_lowRe"
                                       if float(params["polar_variant"]) >= 0.5
                                       else "neuralfoil")
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
        # SALib returns samples scaled to the problem bounds. Give it the unit
        # hypercube here and map to physical values exactly once below.
        # (Passing physical bounds and then re-scaling was a double-mapping bug
        # that compressed every parameter into a narrow band near its low
        # bound.)
        problem = {
            'num_vars': len(UQ_SPEC),
            'names': UQ_NAMES,
            'bounds': [[0.0, 1.0] for _ in UQ_SPEC],
        }
        # Saltelli sampling
        unit = saltelli.sample(problem, saltelli_n, calc_second_order=calc_second_order)
        samples = [sample_to_params_saltelli(row) for row in unit]
        print(f"  Generated {len(samples)} Saltelli samples")
    else:
        unit = latin_hypercube(N_SAMPLES, SEED)
        samples = [sample_to_params(unit[i]) for i in range(N_SAMPLES)]
        print(f"  Generated {len(samples)} LHS samples")

    # Deterministic physical-Cm base case per anchor (Cm = 0).
    print("  Base case with physical attached-flow Cm (cm_scale = 0):")
    base_cm0 = {}
    for name, p in ANCHORS.items():
        base_cm0[name] = _base_cm0(p)
        b = base_cm0[name]
        print(f"    {name:<22s} Cp = {b['cp']:.4f}  TSR = {b['tsr']:.3f}")
    print()

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
        working = cps[cps >= COLLAPSE_CP]
        summary[name] = dict(
            mean=m,
            all_mean=m,
            working_mean=float(np.mean(working)) if len(working) else float("nan"),
            median=med, p5=p5, p95=p95,
            std=float(np.std(cps)), n_ok=len(cps),
            n_fail=failures[name],
            n_working=int(len(working)),
            collapse_fraction=float(np.mean(cps < COLLAPSE_CP)),
            collapse_cp_threshold=float(COLLAPSE_CP),
            base_cm0_cp=float(base_cm0[name]["cp"]),
            base_cm0_tsr=float(base_cm0[name]["tsr"]),
        )
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
    fig.suptitle("Uncertainty propagation — 13 sampled inputs (12 active)",
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
            "base_cm0": base_cm0,
            "collapse_cp_threshold": COLLAPSE_CP,
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