"""
Passive Sharp cycloturbine — peak Cp search.

Tunes physical hardware parameters in PASSIVE mode (no prescribed pitch):
    c        chord
    k_load   external load factor
    mc       counterweight mass
    dcw      counterweight offset ahead of LE
    ar       rocking arm ratio
    sp       pivot position from LE
    bias_deg fixed pitch bias

Two-stage: differential evolution (global) -> Nelder-Mead (local).

Reference point: earlier manual sweeps found Cp = 0.3606 at
    c=0.1176, k_load=0.0015, mc=0.004, dcw=-0.10, ar=0.50, sp=0.25, bias=0
The optimiser should at least match this.

Runtime on 4 cores: ~15-25 minutes.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import differential_evolution, minimize

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from vawt_core import create_sim_from_params


# ---------------------------------------------------------------------------
# Design space
# ---------------------------------------------------------------------------
PARAM_NAMES: Tuple[str, ...] = (
    "c", "k_load", "mc", "dcw", "ar", "sp", "bias_deg",
)

# In scripts/optimize_passive.py, temporarily change PARAM_BOUNDS to:
PARAM_BOUNDS = (
    (0.060, 0.180),    # c
    (0.0005, 0.0050),  # k_load
    (0.001, 0.040),    # mc
    (-0.30, 0.60),     # dcw
    (0.20, 0.80),      # ar
    (0.15, 0.35),      # sp
    (-5.0, 5.0),       # bias
)

PENALTY = 1000.0
BETZ_CEILING = 0.593
R_ROTOR = 0.60


DEFAULT_BASE: Dict[str, Any] = dict(
    R=R_ROTOR, H=0.40, N=3,
    mb=0.010, xbcg=0.20,
    balance=0,                 # use mc, dcw as given
    prescribe_pitch=False,     # KEY: passive mode
    cd_add=0.002,
    use_dynamic_stall=True,
    use_flow_curvature=True,
    use_dmst=True,
    win_deg=45.0,              # Sharp's physical stop limit
    cb=2e-5,
    mu_c=3e-4,
    free=True,
    T_max=25.0,
    stride=5,
    w0_frac=0.9,
    tsr=2.14,
)


# ---------------------------------------------------------------------------
# Objective (must be picklable for multiprocessing)
# ---------------------------------------------------------------------------
class PassiveObjective:
    """-Cp with feasibility penalties.  Runs one passive simulation per call."""

    def __init__(self, base_params: Dict[str, Any], R: float) -> None:
        self.base = dict(base_params)
        self.R = float(R)

    def __call__(self, x: np.ndarray) -> float:
        c, k_load, mc, dcw, ar, sp, bias = (float(v) for v in x)

        # Geometry feasibility: rocking arm must fit inside rotor radius
        if c * ar >= 0.95 * self.R:
            return PENALTY
        # Chord must be physically sensible for a blade span of H = 0.4
        if c < 0.03 or c > 0.20:
            return PENALTY

        params = dict(self.base)
        params.update(
            c=c, k_load=k_load, mc=mc, dcw=dcw,
            ar=ar, sp=sp, bias_deg=bias,
            prescribe_pitch=False,
        )

        try:
            sim = create_sim_from_params(params)
            res = sim.run()
        except Exception:
            return PENALTY

        cp = float(res.get("cp", -1.0))

        # Physical bounds
        if not np.isfinite(cp) or cp <= 0.0:
            return PENALTY
        if cp > BETZ_CEILING:
            return PENALTY + 1000.0

        # Steady state
        if not res.get("steady", True):
            return PENALTY + 100.0

        # Reject deep-stall artefacts: if the blade is way past stall,
        # the polar extrapolation is not trustworthy.
        aoa_max = float(res.get("aoa_max", 0.0))
        if aoa_max > 40.0:
            return PENALTY + 20.0 * (aoa_max - 40.0)

        # Energy ledger must close (this is a diagnostic in passive mode —
        # it should be small since no external actuator is assumed)
        eb = abs(float(res.get("energy_balance", 0.0)))
        if res.get("energy_balance_valid", True) and eb > 0.05:
            return PENALTY + 100.0 * (eb - 0.05)

        return -cp


# ---------------------------------------------------------------------------
# Optimiser
# ---------------------------------------------------------------------------
@dataclass
class OptReport:
    best_params: Dict[str, Any]
    best_cp: float
    de_time_s: float
    local_time_s: float
    history: List[Dict[str, Any]] = field(default_factory=list)


class PassiveOptimizer:
    def __init__(self,
                 base_params: Optional[Dict[str, Any]] = None,
                 de_popsize: int = 10,
                 de_maxiter: int = 15,
                 local_maxiter: int = 30,
                 workers: int = -1,
                 seed: int = 42) -> None:
        self.base = dict(base_params or DEFAULT_BASE)
        self.de_popsize = de_popsize
        self.de_maxiter = de_maxiter
        self.local_maxiter = local_maxiter
        self.workers = workers
        self.seed = seed
        self.history: List[Dict[str, Any]] = []
        self._best_cp: float = -math.inf
        self._best_x: Optional[np.ndarray] = None
        self._obj = PassiveObjective(self.base, self.base["R"])

    # ------------------------------------------------------------------
    def _warmup(self) -> None:
        print("[Opt] Warming up Numba JIT (one short run) ...")
        warm = dict(self.base)
        warm.update(T_max=1.0)
        try:
            t0 = time.perf_counter()
            create_sim_from_params(warm).run()
            print(f"[Opt]   complete in {time.perf_counter() - t0:.2f} s")
        except Exception as exc:
            warnings.warn(f"Warm-up failed: {exc!r}")

    # ------------------------------------------------------------------
    def run_global(self) -> Tuple[np.ndarray, float]:
        print()
        print("=" * 78)
        print("[Opt] STAGE 1 — Differential evolution (global search)")
        print("=" * 78)
        print(f"      variables : {PARAM_NAMES}")
        print(f"      popsize   : {self.de_popsize}  maxiter : {self.de_maxiter}")
        print(f"      workers   : {self.workers}")
        print("-" * 78)

        t0 = time.perf_counter()
        gen = {"n": 0}

        def _cb(xk: np.ndarray, conv: float) -> None:
            gen["n"] += 1
            obj = self._obj(xk)
            cp = -obj if obj < PENALTY else 0.0
            marker = ""
            if cp > self._best_cp:
                self._best_cp = cp
                self._best_x = np.asarray(xk, dtype=float).copy()
                marker = "  <- new best"
            print(f"  [DE] gen={gen['n']:02d}  obj={obj:+9.4f}  "
                  f"Cp={cp:+.4f}  conv={conv:.2e}{marker}")
            self.history.append({
                "stage": "DE", "gen": gen["n"],
                "x": [float(v) for v in xk],
                "cp": float(cp), "obj": float(obj),
            })

        de = differential_evolution(
            func=self._obj,
            bounds=PARAM_BOUNDS,
            strategy="best1bin",
            maxiter=self.de_maxiter,
            popsize=self.de_popsize,
            tol=1e-4,
            mutation=(0.5, 1.0),
            recombination=0.7,
            polish=False,
            init="sobol",
            seed=self.seed,
            workers=self.workers,
            updating="deferred",
            callback=_cb,
            disp=False,
        )

        elapsed = time.perf_counter() - t0
        x_de = np.asarray(de.x, dtype=float)
        obj_de = float(de.fun)
        cp_de = -obj_de if obj_de < PENALTY else 0.0
        if cp_de > self._best_cp:
            self._best_cp = cp_de
            self._best_x = x_de.copy()
        print("-" * 78)
        print(f"  [DE] done in {elapsed:.1f} s  best Cp = {self._best_cp:+.4f}")
        print(f"  [DE] x* = {np.array2string(x_de, precision=5, floatmode='fixed')}")
        return x_de, elapsed

    # ------------------------------------------------------------------
    def run_local(self, x0: np.ndarray) -> Tuple[np.ndarray, float]:
        print()
        print("=" * 78)
        print("[Opt] STAGE 2 — Nelder-Mead (local refinement)")
        print("=" * 78)

        t0 = time.perf_counter()
        lb = np.array([b[0] for b in PARAM_BOUNDS])
        ub = np.array([b[1] for b in PARAM_BOUNDS])

        def _bounded(x: np.ndarray) -> float:
            x = np.asarray(x)
            if np.any(x < lb) or np.any(x > ub):
                return PENALTY
            return self._obj(x)

        it = {"n": 0}

        def _cb(xk: np.ndarray) -> None:
            it["n"] += 1
            obj = self._obj(xk)
            cp = -obj if obj < PENALTY else 0.0
            marker = ""
            if cp > self._best_cp:
                self._best_cp = cp
                self._best_x = np.asarray(xk, dtype=float).copy()
                marker = "  <- new best"
            print(f"  [NM] it={it['n']:03d}  obj={obj:+9.4f}  "
                  f"Cp={cp:+.4f}{marker}")
            self.history.append({
                "stage": "NM", "it": it["n"],
                "x": [float(v) for v in xk],
                "cp": float(cp), "obj": float(obj),
            })

        res = minimize(
            _bounded, x0=np.asarray(x0, dtype=float),
            method="Nelder-Mead",
            options={
                "maxiter": self.local_maxiter,
                "xatol": 1e-3,
                "fatol": 1e-4,
                "disp": False,
            },
            callback=_cb,
        )

        elapsed = time.perf_counter() - t0
        x_nm = np.asarray(res.x, dtype=float)
        obj_nm = float(res.fun)
        cp_nm = -obj_nm if obj_nm < PENALTY else 0.0
        if cp_nm > self._best_cp:
            self._best_cp = cp_nm
            self._best_x = x_nm.copy()
        print("-" * 78)
        print(f"  [NM] done in {elapsed:.1f} s  best Cp = {self._best_cp:+.4f}")
        return x_nm, elapsed

    # ------------------------------------------------------------------
    def optimise(self) -> OptReport:
        print()
        print("#" * 78)
        print("# Passive Sharp cycloturbine — peak Cp search")
        print("#" * 78)
        print(f"# baseline reference Cp = 0.3606 (from manual sweeps)")
        print(f"# Betz ceiling = {BETZ_CEILING}")

        self._warmup()

        x_de, t_de = self.run_global()
        x_nm, t_nm = self.run_local(x_de)

        x_star = self._best_x if self._best_x is not None else x_nm

        best_dict = dict(self.base)
        for name, val in zip(PARAM_NAMES, x_star):
            best_dict[name] = float(val)

        print()
        print("#" * 78)
        print(f"# BEST passive Cp = {self._best_cp:+.4f}")
        print("#" * 78)
        for name, val in zip(PARAM_NAMES, x_star):
            print(f"    {name:<12s} = {val:+.6g}")
        print(f"    DE time = {t_de:.1f} s")
        print(f"    NM time = {t_nm:.1f} s")

        return OptReport(
            best_params=best_dict,
            best_cp=float(self._best_cp),
            de_time_s=float(t_de),
            local_time_s=float(t_nm),
            history=self.history,
        )

    # ------------------------------------------------------------------
    def save(self, path: str, report: OptReport) -> None:
        def _clean(v: Any) -> Any:
            if isinstance(v, (bool, np.bool_)):
                return bool(v)
            if isinstance(v, (int, np.integer)):
                return int(v)
            if isinstance(v, (float, np.floating)):
                return float(v)
            return v

        payload = {
            "param_names": list(PARAM_NAMES),
            "bounds": [list(b) for b in PARAM_BOUNDS],
            "best_params": {k: _clean(v) for k, v in report.best_params.items()},
            "best_cp": float(report.best_cp),
            "de_time_s": float(report.de_time_s),
            "local_time_s": float(report.local_time_s),
            "history": report.history,
        }
        Path(path).write_text(json.dumps(payload, indent=2))
        print(f"[Opt] report saved -> {Path(path).resolve()}")

    # ------------------------------------------------------------------
    def verify(self, report: OptReport, T_long: float = 40.0) -> Dict[str, Any]:
        print()
        print(f"[Opt] Verification run with T_max = {T_long:.0f} s ...")
        params = dict(report.best_params)
        params["T_max"] = T_long
        sim = create_sim_from_params(params)
        res = sim.run()
        print(f"  Cp        = {res['cp']:+.4f}")
        print(f"  TSR_eq    = {res['tsr_eq']:.3f}")
        print(f"  RPM       = {res['rpm']:.1f}")
        print(f"  pitch     = [{res['pitch_min']:+.1f}, "
              f"{res['pitch_max']:+.1f}] deg")
        print(f"  pitch_rms = {res['pitch_rms']:.2f} deg")
        print(f"  alpha_max = {res['aoa_max']:.1f} deg")
        print(f"  stop_pct  = {res['stop_pct']:.1f} %")
        print(f"  steady    = {res.get('steady', True)}")
        return res


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    print()
    print("Passive Sharp cycloturbine — peak Cp search")
    print("Parameters:", ", ".join(PARAM_NAMES))
    print()

    opt = PassiveOptimizer(
        de_popsize=10,
        de_maxiter=15,
        local_maxiter=30,
        workers=-1,
        seed=42,
    )
    report = opt.optimise()

    out_path = Path(__file__).with_name("optimization_passive.json")
    opt.save(str(out_path), report)
    opt.verify(report, T_long=40.0)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
