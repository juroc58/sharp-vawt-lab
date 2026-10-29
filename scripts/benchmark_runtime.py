"""
Benchmark runtime for the Sharp cycloturbine engine.

Runs a small, bounded, fixed workload using an existing representative preset.
Reports startup effects separately from warm execution, and compares worker
counts 1, 2, and 4 using identical tasks and verifying output equivalence.

Outputs a concise summary. Optionally saves machine-readable results to an
ignored local directory (``.bench_cache/``). Does NOT write into canonical
simulation JSON paths.

Usage:
    python3 scripts/benchmark_runtime.py          # default workload
    python3 scripts/benchmark_runtime.py --workers 1 2 4
    python3 scripts/benchmark_runtime.py --repeat 3 --save
    python3 scripts/benchmark_runtime.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sharp_vawt import create_sim_from_params
from vawt_presets import PRESETS

# Representative workload.  T_max and stride are overridden from the preset
# to keep the benchmark bounded; these overrides are reported explicitly.
BENCHMARK_PARAMS = dict(PRESETS["sharp_cppc"])
BENCHMARK_PARAMS["T_max"] = 5.0   # overridden: short run for bounded time
BENCHMARK_PARAMS["stride"] = 5    # overridden from preset default


def run_one(params):
    """Run one simulation and return Cp. Top-level for pickling."""
    r = create_sim_from_params(params).run()
    return r["cp"]


def bench_serial(n_tasks, repeat=1):
    """Run n_tasks simulations serially, repeated `repeat` times.

    Returns per-rep wall times (end-to-end, no pool startup) and the Cp
    values produced.
    """
    wall_times = []
    cps = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        for _ in range(n_tasks):
            cps.append(run_one(BENCHMARK_PARAMS))
        t1 = time.perf_counter()
        wall_times.append(t1 - t0)
    return wall_times, cps


def bench_fresh_pool(n_workers, n_tasks, repeat=1):
    """Run n_tasks simulations with a fresh ProcessPoolExecutor each rep.

    Measures end-to-end pool startup + work (no pool reuse).
    """
    wall_times = []
    cps = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            futs = [ex.submit(run_one, BENCHMARK_PARAMS) for _ in range(n_tasks)]
            for f in futs:
                cps.append(f.result())
        t1 = time.perf_counter()
        wall_times.append(t1 - t0)
    return wall_times, cps


def bench_reused_pool(n_workers, n_tasks, repeat=1):
    """Run n_tasks simulations per rep with ONE reused ProcessPoolExecutor.

    Measures reused-pool throughput (pool startup amortized across reps).
    """
    wall_times = []
    cps = []
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        for _ in range(repeat):
            t0 = time.perf_counter()
            futs = [ex.submit(run_one, BENCHMARK_PARAMS) for _ in range(n_tasks)]
            for f in futs:
                cps.append(f.result())
            t1 = time.perf_counter()
            wall_times.append(t1 - t0)
    return wall_times, cps


def measure_first_call_fresh_process():
    """Measure the first call in a fresh Python process.

    This includes Python startup, module import, and Numba JIT compilation
    on first use.  It is NOT labelled "cold compilation" because the Numba
    disk-cache state is not inspected here; cache reuse may occur.
    """
    import subprocess
    code = (
        "import time, sys; "
        "sys.path.insert(0, '.'); "
        "from sharp_vawt import create_sim_from_params; "
        "from vawt_presets import PRESETS; "
        "p = dict(PRESETS['sharp_cppc']); p['T_max'] = 5.0; p['stride'] = 5; "
        "t0 = time.perf_counter(); "
        "r = create_sim_from_params(p).run(); "
        "t1 = time.perf_counter(); "
        "print(f'{t1-t0:.6f} {r[\"cp\"]:.8f}')"
    )
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=os.getcwd(), check=False,
    )
    t1 = time.perf_counter()
    if proc.returncode != 0:
        return None, proc.stderr
    wall = t1 - t0
    parts = proc.stdout.strip().split()
    sim_time = float(parts[0])
    cp = float(parts[1])
    return {
        "wall_including_startup": wall,
        "sim_time": sim_time,
        "cp": cp,
        "stderr": proc.stderr,
    }, None


def measure_warm_call(n_repeats=5):
    """Measure repeated calls in the same process (Numba already compiled).

    Returns per-call wall times and the Cp values produced.
    """
    # Ensure Numba is compiled before timing.
    run_one(BENCHMARK_PARAMS)
    times = []
    cps = []
    for _ in range(n_repeats):
        t0 = time.perf_counter()
        cp = run_one(BENCHMARK_PARAMS)
        t1 = time.perf_counter()
        times.append(t1 - t0)
        cps.append(cp)
    return {
        "times": times,
        "mean": sum(times) / len(times),
        "cp": cps[0],
        "all_cps_identical": len(set(cps)) == 1,
    }


def _cps_identical(cps_a, cps_b):
    return all(a == b for a, b in zip(cps_a, cps_b))


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark runtime for the Sharp cycloturbine engine."
    )
    parser.add_argument(
        "--workers",
        type=int,
        nargs="*",
        default=[1, 2, 4],
        help="Worker counts to compare (default: 1 2 4).",
    )
    parser.add_argument(
        "--tasks",
        type=int,
        default=8,
        help="Number of simulation tasks per worker comparison (default: 8).",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=2,
        help="Number of repetitions per timing measurement (default: 2).",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save machine-readable results to .bench_cache/benchmark.json.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved configuration and exit without running benchmarks.",
    )
    args = parser.parse_args()

    if args.tasks < 1:
        parser.error("--tasks must be a positive integer")
    if args.repeat < 1:
        parser.error("--repeat must be a positive integer")
    for w in args.workers:
        if w < 1:
            parser.error("--workers values must be positive integers")

    print("=" * 70)
    print("Sharp cycloturbine — runtime benchmark")
    print("=" * 70)
    print("  Preset        : sharp_cppc")
    print("  Overrides     : T_max=5.0 s (benchmark), stride=5 (benchmark)")
    print("  Tasks         :", args.tasks)
    print("  Repeats       :", args.repeat)
    print("  Worker counts :", args.workers)
    print("  Save results  :", args.save)
    print()

    if args.dry_run:
        print("  Dry run complete: no benchmarks executed.")
        return 0

    # 1. Fresh process (startup + import + possible Numba compilation)
    print("  [1/4] Fresh process (startup + import + possible Numba JIT compile)...")
    fresh, fresh_err = measure_first_call_fresh_process()
    if fresh is None:
        print(f"    ERROR: {fresh_err}")
        return 1
    print(f"    Wall including startup: {fresh['wall_including_startup']:.3f} s")
    print(f"    Simulation time only  : {fresh['sim_time']:.3f} s")
    print(f"    Cp                    : {fresh['cp']:.8f}")
    print()

    # 2. Warm serial execution (same process, Numba compiled)
    print("  [2/4] Warm serial execution (same process, Numba compiled)...")
    serial_wall, serial_cps = bench_serial(args.tasks, args.repeat)
    serial_mean = sum(serial_wall) / len(serial_wall)
    print(f"    Mean wall ({args.tasks} tasks x {args.repeat} reps): {serial_mean:.3f} s")
    print(f"    Cp                    : {serial_cps[0]:.8f}")
    print()

    # 3. Fresh-pool worker comparison (pool startup + work each rep)
    print("  [3/4] Fresh-pool worker comparison (startup + work each rep)...")
    pool_results = {}
    for nw in args.workers:
        wall_times, cps = bench_fresh_pool(n_workers=nw, n_tasks=args.tasks, repeat=args.repeat)
        mean = sum(wall_times) / len(wall_times)
        identical = _cps_identical(serial_cps, cps)
        pool_results[nw] = {
            "times": wall_times,
            "mean": mean,
            "speedup": serial_mean / mean if mean > 0 else float("nan"),
            "cps_identical_to_serial": identical,
        }
        print(
            f"    Workers={nw}: {mean:.3f} s mean  "
            f"speedup={pool_results[nw]['speedup']:.2f}x  "
            f"Cp identical to serial: {identical}"
        )
    print()

    # 4. Reused-pool throughput (pool startup amortized across reps)
    print("  [4/4] Reused-pool throughput (pool startup amortized)...")
    reused_results = {}
    for nw in args.workers:
        wall_times, cps = bench_reused_pool(n_workers=nw, n_tasks=args.tasks, repeat=args.repeat)
        mean = sum(wall_times) / len(wall_times)
        identical = _cps_identical(serial_cps, cps)
        reused_results[nw] = {
            "times": wall_times,
            "mean": mean,
            "speedup": serial_mean / mean if mean > 0 else float("nan"),
            "cps_identical_to_serial": identical,
        }
        print(
            f"    Workers={nw}: {mean:.3f} s mean  "
            f"speedup={reused_results[nw]['speedup']:.2f}x  "
            f"Cp identical to serial: {identical}"
        )
    print()

    # Summary
    print("=" * 70)
    print("Benchmark summary")
    print("=" * 70)
    print(f"  Fresh process wall (incl. startup): {fresh['wall_including_startup']:.3f} s")
    print(f"  Fresh process sim time only       : {fresh['sim_time']:.3f} s")
    print(f"  Warm serial mean                  : {serial_mean:.3f} s "
          f"({args.tasks} tasks x {args.repeat} reps)")
    print("  Fresh-pool worker comparison:")
    for nw in args.workers:
        r = pool_results[nw]
        print(f"    Workers={nw}: {r['mean']:.3f} s mean  "
              f"speedup={r['speedup']:.2f}x  "
              f"Cp identical={r['cps_identical_to_serial']}")
    print("  Reused-pool throughput:")
    for nw in args.workers:
        r = reused_results[nw]
        print(f"    Workers={nw}: {r['mean']:.3f} s mean  "
              f"speedup={r['speedup']:.2f}x  "
              f"Cp identical={r['cps_identical_to_serial']}")
    print()

    if args.save:
        bench_dir = Path(".bench_cache")
        bench_dir.mkdir(exist_ok=True)
        out = {
            "fresh_process": fresh,
            "warm_serial": {"mean": serial_mean, "times": serial_wall,
                            "cp": serial_cps[0]},
            "fresh_pool": pool_results,
            "reused_pool": reused_results,
            "tasks": args.tasks,
            "repeat": args.repeat,
            "preset": "sharp_cppc",
            "overrides": {"T_max": 5.0, "stride": 5},
        }
        out_path = bench_dir / "benchmark.json"
        with open(out_path, "w") as fh:
            json.dump(out, fh, indent=2)
        print(f"  Results saved to {out_path}")
        print("  (Note: .bench_cache/ is git-ignored)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
