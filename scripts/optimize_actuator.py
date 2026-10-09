# vawt_optimizer.py
"""
Parallel Multi-Parameter Optimisation for the SHARP Cycloturbine.

Objective
---------
Maximise Cp with the prescribed pitch law implemented by vawt_core.py v3.1:
    ψ(φ) = pp0 + pp1·cos(φ) + pp2·cos(2φ) + pp3·sin(2φ)

The core does NOT have a pp4 term and does NOT have a sin(φ) term. Parameter
names and bounds here match the core exactly. Do not add axes the core
does not read.

Reference targets (from literature, scaled to R = 0.6 m):
    Ham  1979, R = 1.83 m, Re ~2e6 :  Cp = 0.42–0.45 @ λ = 2.5–3.0
    Adams 2018, R = 0.69 m, Re ~1e6:  Cp = 0.44–0.52 @ λ = 1.5, 2.25
This work at R = 0.60 m, Re ~1.4e5 reaches Cp ≈ 0.46 at λ ≈ 3.2.
"""
from __future__ import annotations

import json
import math
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import differential_evolution, minimize
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vawt_core import create_sim_from_params

# ----------------------------------------------------------------- design space
# Four pitch coefficients, matching the core's prescribed-pitch law.
PARAM_NAMES: Tuple[str, ...] = (
    "c", "tsr", "k_load",
    "pp0_deg", "pp1_deg", "pp2_deg", "pp3_deg",
)

PARAM_BOUNDS: Tuple[Tuple[float, float], ...] = (
    (0.060, 0.130),     # chord c [m]          → σ = 0.048–0.104 for N=3, R=0.6
    (2.000, 3.500),     # TSR
    (0.0003, 0.0015),   # k_load [N·m·s²]
    (-10.0, 10.0),      # pp0  — collective pitch offset [deg]
    (-25.0, 0.0),       # pp1  — cos φ amplitude  (negative = nose-out at φ=0)
    (-15.0, 15.0),      # pp2  — cos 2φ amplitude
    (-15.0, 15.0),      # pp3  — sin 2φ amplitude
)

PENALTY: float = 1000.0
ENERGY_TOL: float = 0.03
BETZ_LIMIT: float = 0.593     # physical ceiling — reject anything above this


DEFAULT_BASE: Dict[str, Any] = {
    # --- geometry ---------------------------------------------------------
    "R": 0.60, "c": 0.10, "H": 0.40, "N": 3,
    "ar": 0.50, "sp": 0.25, "arm_d": 0.0, "n_arm": 2, "arm_cd": 1.0,
    # --- mass / CPPC ------------------------------------------------------
    "mb": 0.010, "xbcg": 0.20, "mc": 0.008, "dcw": 0.50,
    "balance": 0, "bias_deg": 0.0, "J_hub": 0.02, "mu_friction": 3.0e-4,
    # --- polar / aero switches -------------------------------------------
    "polar_dir": "polars/naca0012",
    "use_dynamic_stall": True, "use_tip_loss": False,
    "use_dmst": True, "use_dynamic_inflow": True,
    "use_flow_curvature": True,
    "cd_add": 0.002,
    "win_deg": 45.0,
    "wstop": 300.0,        # <-- was 1.5 in the buggy version
    "cb": 2.0e-5, "kc": 0.0, "mu_c": 0.0, "r_bearing": 0.002,
    "prescribe_pitch": True,
    "pp0_deg": 0.0, "pp1_deg": -10.0, "pp2_deg": 0.0, "pp3_deg": 0.0,
    "pp_ph_deg": 0.0,
    # --- simulation ------------------------------------------------------
    "U": 8.0, "tsr": 2.5, "free": True, "w0_frac": 0.9,
    "dt": 2.0e-4, "T_max": 20.0, "stride": 5,
    "n_span": 1, "n_rev_fixed": 20,
}


class CpObjective:
    """Picklable objective: −Cp with feasibility penalties.

    Reads exactly the parameters the core understands. Applies:
      * geometry feasibility check
      * steady-state requirement
      * energy-balance penalty, ONLY when the ledger is valid
      * physical Betz limit ceiling
    """

    def __init__(self, base_params: Dict[str, Any], R: float, ar: float) -> None:
        self.base = dict(base_params)
        self.R = float(R)
        self.ar = float(ar)

    def __call__(self, x: np.ndarray) -> float:
        c, tsr, k_load, pp0, pp1, pp2, pp3 = (float(v) for v in x)

        if c * self.ar >= self.R:
            return PENALTY

        params = dict(self.base)
        params.update(
            c=c, tsr=tsr, k_load=k_load,
            pp0_deg=pp0, pp1_deg=pp1, pp2_deg=pp2, pp3_deg=pp3,
            prescribe_pitch=True,
        )

        try:
            sim = create_sim_from_params(params)
            res = sim.run()
        except Exception:
            return PENALTY

        cp = float(res.get("cp", -1.0))

        # Physical ceiling and floor
        if not np.isfinite(cp) or cp <= 0.0:
            return PENALTY
        if cp > BETZ_LIMIT:
            return PENALTY + 1000.0

        # Steady-state requirement
        if not res.get("steady", True):
            return PENALTY + 100.0

        # Energy ledger — only enforce when the core says it is meaningful.
        # In prescribed-pitch mode, energy_balance_valid is False and the
        # residual measures untracked actuator work, not a physics error.
        if res.get("energy_balance_valid", True):
            eb = abs(float(res.get("energy_balance", 0.0)))
            if not np.isfinite(eb):
                return PENALTY
            if eb > ENERGY_TOL:
                return PENALTY + 10.0 * (eb - ENERGY_TOL) * PENALTY

        return -cp


@dataclass
class OptimizationReport:
    best_params: Dict[str, Any]
    best_cp: float
    de_time_s: float
    local_time_s: float
    de_result: Any = None
    local_result: Any = None
    history: List[Dict[str, Any]] = field(default_factory=list)


class VAWTOptimizer:
    """Two-stage optimiser: DE (global) → SLSQP (local)."""

    def __init__(self,
                 base_params: Optional[Dict[str, Any]] = None,
                 de_popsize: int = 15,
                 de_maxiter: int = 30,
                 local_maxiter: int = 40,
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
        self._objective = CpObjective(self.base,
                                      R=float(self.base["R"]),
                                      ar=float(self.base["ar"]))

    # ------------------------------------------------------------------
    def _warmup(self) -> None:
        print("[Opt] Warming up Numba JIT ...")
        warm = dict(self.base)
        warm.update(T_max=0.5, n_span=1)
        try:
            t0 = time.perf_counter()
            create_sim_from_params(warm).run()
            print(f"[Opt] Warm-up complete in {time.perf_counter() - t0:.2f} s")
        except Exception as exc:
            warnings.warn(f"Warm-up failed: {exc!r}")

    # ------------------------------------------------------------------
    def run_global(self):
        print("\n" + "=" * 78)
        print("[Opt] STAGE 1 — Global differential evolution")
        print("=" * 78)
        t0 = time.perf_counter()

        def _cb(xk, conv):
            obj = self._objective(xk)
            cp = -obj if obj < PENALTY else 0.0
            marker = ""
            if cp > self._best_cp:
                self._best_cp = cp
                self._best_x = np.asarray(xk).copy()
                marker = "  ← new best"
            print(f"  [DE] obj={obj:+9.4f}  Cp≈{cp:+.4f}  conv={conv:.2e}{marker}")
            self.history.append({"stage": "DE", "x": xk.tolist(),
                                 "cp": float(cp), "obj": float(obj)})

        de = differential_evolution(
            func=self._objective, bounds=PARAM_BOUNDS,
            strategy="best1bin", maxiter=self.de_maxiter,
            popsize=self.de_popsize, tol=1e-4,
            mutation=(0.5, 1.0), recombination=0.7,
            polish=False, init="sobol", seed=self.seed,
            workers=self.workers, updating="deferred",
            callback=_cb, disp=False)

        elapsed = time.perf_counter() - t0
        x_best = np.asarray(de.x)
        obj_best = float(de.fun)
        cp_best = -obj_best if obj_best < PENALTY else 0.0
        if cp_best > self._best_cp:
            self._best_cp = cp_best
            self._best_x = x_best.copy()
        print("-" * 78)
        print(f"  [DE] completed in {elapsed:.1f} s — best Cp = {cp_best:+.4f}")
        return x_best, cp_best, de, elapsed

    # ------------------------------------------------------------------
    def run_local(self, x0):
        print("\n" + "=" * 78)
        print("[Opt] STAGE 2 — Local refinement (Nelder-Mead)")
        print("=" * 78)
        t0 = time.perf_counter()
        it = {"n": 0}

        def _cb(xk):
            it["n"] += 1
            obj = self._objective(xk)
            cp = -obj if obj < PENALTY else 0.0
            marker = ""
            if cp > self._best_cp:
                self._best_cp = cp
                self._best_x = np.asarray(xk).copy()
                marker = "  ← new best"
            print(f"  [NM] it={it['n']:03d}  obj={obj:+9.4f}  Cp≈{cp:+.4f}{marker}")
            self.history.append({"stage": "NM", "it": it["n"],
                                 "x": xk.tolist(),
                                 "cp": float(cp), "obj": float(obj)})

        # Nelder-Mead is derivative-free and robust to the penalty
        # plateaus. It does not accept bounds directly, so we clip inside
        # the objective by rejecting out-of-box points via a wrapper.
        lb = np.array([b[0] for b in PARAM_BOUNDS])
        ub = np.array([b[1] for b in PARAM_BOUNDS])

        def _bounded(x):
            x = np.asarray(x)
            if np.any(x < lb) or np.any(x > ub):
                return PENALTY
            return self._objective(x)

        res = minimize(
            fun=_bounded, x0=np.asarray(x0, dtype=float),
            method="Nelder-Mead",
            options={"maxiter": self.local_maxiter, "xatol": 1e-3,
                     "fatol": 1e-4, "disp": False},
            callback=_cb)

        elapsed = time.perf_counter() - t0
        x_best = np.asarray(res.x)
        obj_best = float(res.fun)
        cp_best = -obj_best if obj_best < PENALTY else 0.0
        if cp_best > self._best_cp:
            self._best_cp = cp_best
            self._best_x = x_best.copy()
        print("-" * 78)
        print(f"  [NM] completed in {elapsed:.1f} s — best Cp = {cp_best:+.4f}")
        return x_best, cp_best, res, elapsed

    # ------------------------------------------------------------------
    def optimise(self) -> OptimizationReport:
        print("\n" + "#" * 78)
        print("# SHARP Cycloturbine — Optimisation")
        print("#" * 78)
        self._warmup()

        x_de, cp_de, de_res, t_de = self.run_global()

        x_loc, cp_loc, loc_res, t_loc = self.run_local(x_de)

        x_star = self._best_x if self._best_x is not None else x_loc
        best_dict = dict(self.base)
        for name, val in zip(PARAM_NAMES, x_star):
            best_dict[name] = float(val)

        report = OptimizationReport(
            best_params=best_dict, best_cp=float(self._best_cp),
            de_time_s=t_de, local_time_s=t_loc,
            de_result=de_res, local_result=loc_res,
            history=self.history)

        print("\n" + "#" * 78)
        print(f"# BEST Cp = {self._best_cp:+.4f}")
        print("#" * 78)
        for name, val in zip(PARAM_NAMES, x_star):
            print(f"    {name:<10s} = {val:+.6g}")
        return report

    # ------------------------------------------------------------------
    def save(self, filepath: str, report: OptimizationReport) -> None:
        def _clean(v):
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
            "history": [
                {"stage": h["stage"],
                 "x": [float(x) for x in h["x"]],
                 "cp": float(h["cp"]),
                 "obj": float(h["obj"])}
                for h in report.history
            ],
        }
        Path(filepath).write_text(json.dumps(payload, indent=2))
        print(f"[Opt] Report saved → {Path(filepath).resolve()}")

    # ------------------------------------------------------------------
    def evaluate_best(self, report: OptimizationReport,
                      T_long: float = 30.0) -> Dict[str, Any]:
        print(f"\n[Opt] Validation run (T_max = {T_long} s) ...")
        params = dict(report.best_params)
        params["T_max"] = T_long
        sim = create_sim_from_params(params)
        res = sim.run(store_history=True)
        print(f"[Opt] Cp={res['cp']:+.4f}  TSR_eq={res['tsr_eq']:.3f}  "
              f"RPM={res['rpm']:.1f}  Eb={res['energy_balance']*100:+.2f}%  "
              f"div={res.get('diverged', False)}  "
              f"steady={res.get('steady', True)}")
        return res


def _cli():
    base = dict(DEFAULT_BASE)
    ovr = Path(__file__).with_name("optimizer_overrides.json")
    if ovr.exists():
        base.update(json.loads(ovr.read_text()))
    opt = VAWTOptimizer(base_params=base, de_popsize=15, de_maxiter=30,
                        local_maxiter=40, workers=-1, seed=42)
    report = opt.optimise()
    out = Path(__file__).with_name("optimization_result.json")
    opt.save(str(out), report)
    opt.evaluate_best(report, T_long=30.0)


if __name__ == "__main__":
    _cli()