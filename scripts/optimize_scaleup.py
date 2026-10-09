"""
Absolute peak Cp of the physics core — scale-up study.

Scales R from 0.6 m (current machine) to 3.0 m (Sharp's larger experimental
machines) and optimises the design jointly with R.

Physical scaling rules (all extensive quantities):
    chord               c      ∝ R     (via c_over_R)
    span                H      ∝ R     (via H_over_R)
    blade mass          mb     ∝ R³    (volumetric)
    counterweight mass  mc     ∝ R³    (volumetric)
    load factor         k_load ∝ R⁵    (so free-running TSR is scale-invariant)

Dimensionless design variables: c/R, H/R, ar, sp, dcw
Dimensional reference values at R=0.6 m: mb_ref, mc_ref, k_load_ref

Reynolds number at fixed TSR·U scales as Re ∝ R, so the tip Re grows from
~1.4e5 at R=0.6 to ~7e5 at R=3.

Runtime: 20-40 min on 4 cores.
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
# Reference design point (current machine at R = 0.6 m)
# ---------------------------------------------------------------------------
R_REF   = 0.60      # m
MB_REF  = 0.010     # kg blade mass at R_ref
U_INF   = 8.0       # m/s freestanding reference wind speed

# ---------------------------------------------------------------------------
# Design space
# ---------------------------------------------------------------------------
PARAM_NAMES: Tuple[str, ...] = (
    "R", "c_over_R", "H_over_R", "k_load_ref", "mc_ref", "ar", "sp", "dcw",
)

PARAM_BOUNDS: Tuple[Tuple[float, float], ...] = (
    (0.60, 3.00),       # R            [m]
    (0.10, 0.30),       # c/R          [-]
    (0.50, 1.50),       # H/R          [-]
    (0.0005, 0.0050),   # k_load_ref   [N·m·s²]   at R = R_REF
    (0.002, 0.030),     # mc_ref       [kg]       at R = R_REF
    (0.30, 0.70),       # ar           [-]
    (0.15, 0.30),       # sp           [-]
    (-0.30, 0.60),      # dcw          [-]
)

PENALTY = 1000.0
BETZ_CEILING = 0.593


# ---------------------------------------------------------------------------
# Objective (picklable for multiprocessing)
# ---------------------------------------------------------------------------
class ScaledObjective:
    def __init__(self, R_ref: float = R_REF, mb_ref: float = MB_REF) -> None:
        self.R_ref = float(R_ref)
        self.mb_ref = float(mb_ref)

    def __call__(self, x: np.ndarray) -> float:
        R, c_over_R, H_over_R, kl_ref, mc_ref, ar, sp, dcw = (float(v) for v in x)

        # ---- geometry feasibility ----
        c = c_over_R * R
        H = H_over_R * R
        if c * ar >= 0.95 * R:
            return PENALTY
        if c < 0.03 or c > 0.40:
            return PENALTY
        if H < 0.05 or H > 4.5:
            return PENALTY

        # ---- physical scaling ----
        scale = R / self.R_ref
        mb = self.mb_ref * scale ** 3
        mc = mc_ref * scale ** 3
        k_load = kl_ref * scale ** 5

        params = dict(
            R=R, c=c, H=H, N=3,
            ar=ar, sp=sp,
            mb=mb, xbcg=0.20,
            mc=mc, dcw=dcw,
            balance=0, bias_deg=0.0,
            prescribe_pitch=False,
            cd_add=0.002,
            use_dynamic_stall=True,
            use_flow_curvature=True,
            use_dmst=True,
            use_tip_loss=False,
            win_deg=45.0,
            cb=2e-5, mu_c=3e-4,
            free=True,
            T_max=30.0, stride=8,
            w0_frac=0.9,
            k_load=k_load,
            tsr=2.5,
        )

        try:
            sim = create_sim_from_params(params)
            res = sim.run()
        except Exception:
            return PENALTY

        cp = float(res.get("cp", -1.0))
        if not np.isfinite(cp) or cp <= 0.0:
            return PENALTY
        if cp > BETZ_CEILING:
            return PENALTY + 1000.0
        if not res.get("steady", True):
            return PENALTY + 100.0

        aoa_max = float(res.get("aoa_max", 0.0))
        if aoa_max > 40.0:
            return PENALTY + 20.0 * (aoa_max - 40.0)

        return -cp


@dataclass
class Report:
    best_x: np.ndarray
    best_cp: float
    best_Re: float
    history: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def _warmup() -> None:
    print("[Opt] Warming up Numba JIT ...")
    try:
        create_sim_from_params({
            'R': 0.6, 'c': 0.12, 'H': 0.4, 'N': 3,
            'mb': 0.010, 'mc': 0.008,
            'prescribe_pitch': False,
            'free': True, 'T_max': 1.0, 'k_load': 0.0015, 'tsr': 2.5,
        }).run()
        print("[Opt] done")
    except Exception as exc:
        warnings.warn(f"Warm-up failed: {exc!r}")


def optimise() -> Report:
    obj = ScaledObjective()
    history: List[Dict[str, Any]] = []
    state = {"best_cp": -math.inf, "best_x": None, "gen": 0}

    def _cb(xk: np.ndarray, conv: float) -> None:
        state["gen"] += 1
        o = obj(xk)
        cp = -o if o < PENALTY else 0.0
        marker = ""
        if cp > state["best_cp"]:
            state["best_cp"] = cp
            state["best_x"] = np.asarray(xk, dtype=float).copy()
            marker = "  <- best"
        print(f"  [DE] gen={state['gen']:02d}  obj={o:+9.4f}  "
              f"Cp={cp:+.4f}  conv={conv:.2e}{marker}")
        history.append({
            "stage": "DE", "gen": state["gen"],
            "x": [float(v) for v in xk],
            "cp": float(cp), "obj": float(o),
        })

    print()
    print("=" * 78)
    print("[Opt] STAGE 1 — Differential evolution")
    print("=" * 78)
    print(f"      vars: {PARAM_NAMES}")
    print(f"      popsize: 6  maxiter: 8  workers: -1")
    print("-" * 78)
    t0 = time.perf_counter()

    de = differential_evolution(
        obj, PARAM_BOUNDS,
        strategy="best1bin",
        maxiter=8,
        popsize=6,
        tol=1e-4,
        mutation=(0.5, 1.0),
        recombination=0.7,
        polish=False,
        init="sobol",
        seed=1,
        workers=-1,
        updating="deferred",
        callback=_cb,
        disp=False,
    )
    print("-" * 78)
    print(f"  [DE] done in {time.perf_counter() - t0:.0f} s  "
          f"best Cp = {state['best_cp']:+.4f}")

    # ------------------------------------------------------------------
    print()
    print("=" * 78)
    print("[Opt] STAGE 2 — Nelder-Mead local refinement")
    print("=" * 78)
    t0 = time.perf_counter()

    lb = np.array([b[0] for b in PARAM_BOUNDS])
    ub = np.array([b[1] for b in PARAM_BOUNDS])

    def _bounded(x: np.ndarray) -> float:
        x = np.asarray(x)
        if np.any(x < lb) or np.any(x > ub):
            return PENALTY
        return obj(x)

    res = minimize(
        _bounded, x0=np.asarray(de.x, dtype=float),
        method="Nelder-Mead",
        options={"maxiter": 40, "xatol": 1e-3, "fatol": 1e-4, "disp": False},
    )
    print(f"  [NM] done in {time.perf_counter() - t0:.0f} s")

    x_nm = np.asarray(res.x, dtype=float)
    o_nm = float(res.fun)
    cp_nm = -o_nm if o_nm < PENALTY else 0.0
    if cp_nm > state["best_cp"]:
        state["best_cp"] = cp_nm
        state["best_x"] = x_nm
        print(f"  [NM] improved: Cp = {cp_nm:+.4f}")

    # ---- Reynolds number at winning design ----
    x = state["best_x"]
    R, c_over_R = float(x[0]), float(x[1])
    c = c_over_R * R
    # For a rotor at TSR ≈ 2.5, tip W ≈ U·sqrt(1 + 2.5²) ≈ 2.7·U
    Re_tip = 2.7 * U_INF * c / 1.5e-5

    return Report(
        best_x=np.asarray(x, dtype=float),
        best_cp=float(state["best_cp"]),
        best_Re=float(Re_tip),
        history=history,
    )


def main() -> None:
    print()
    print("#" * 78)
    print("# Absolute peak Cp of the physics core — scale-up study")
    print("#" * 78)
    print(f"# R range      : {PARAM_BOUNDS[0][0]:.2f} - {PARAM_BOUNDS[0][1]:.2f} m")
    print(f"# Reference    : R={R_REF} m, mb={MB_REF} kg, U={U_INF} m/s")

    _warmup()
    rep = optimise()

    # Decode winning design
    R, c_over_R, H_over_R, kl_ref, mc_ref, ar, sp, dcw = (
        float(v) for v in rep.best_x
    )
    scale = R / R_REF
    c = c_over_R * R
    H = H_over_R * R
    mb = MB_REF * scale ** 3
    mc = mc_ref * scale ** 3
    k_load = kl_ref * scale ** 5
    sigma = 3 * c / (2 * math.pi * R)

    print()
    print("#" * 78)
    print(f"# BEST Cp = {rep.best_cp:.4f}  at  R = {R:.3f} m  "
          f"(Re_tip ~ {rep.best_Re:.2e})")
    print("#" * 78)
    print(f"    R          = {R:.4f} m")
    print(f"    c          = {c:.4f} m   (c/R = {c_over_R:.3f})")
    print(f"    H          = {H:.4f} m   (H/R = {H_over_R:.3f},  H/c = {H/c:.2f})")
    print(f"    sigma      = {sigma:.4f}")
    print(f"    mb         = {mb*1000:8.3f} g")
    print(f"    mc         = {mc*1000:8.3f} g")
    print(f"    k_load     = {k_load:.6f} N·m·s²")
    print(f"    ar         = {ar:.4f}")
    print(f"    sp         = {sp:.4f}")
    print(f"    dcw        = {dcw:.4f}")
    print()

    # Save
    out_path = Path(__file__).with_name("optimization_scaleup.json")
    payload = {
        "param_names": list(PARAM_NAMES),
        "bounds": [list(b) for b in PARAM_BOUNDS],
        "best_x": [float(v) for v in rep.best_x],
        "best_cp": float(rep.best_cp),
        "best_Re": float(rep.best_Re),
        "derived": {
            "R": R, "c": c, "H": H, "H_over_c": H / c,
            "sigma": sigma, "mb": mb, "mc": mc, "k_load": k_load,
            "ar": ar, "sp": sp, "dcw": dcw,
        },
        "history": rep.history,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"[Opt] report saved -> {out_path.resolve()}")

    # ---- verification run with a longer window ----
    print()
    print(f"[Opt] Verification run (T_max = 60 s) ...")
    params = dict(
        R=R, c=c, H=H, N=3,
        ar=ar, sp=sp,
        mb=mb, xbcg=0.20,
        mc=mc, dcw=dcw,
        balance=0, bias_deg=0.0,
        prescribe_pitch=False,
        cd_add=0.002,
        use_dynamic_stall=True, use_flow_curvature=True, use_dmst=True,
        use_tip_loss=False,
        win_deg=45.0, cb=2e-5, mu_c=3e-4,
        free=True, T_max=60.0, stride=8,
        w0_frac=0.9, k_load=k_load, tsr=2.5,
    )
    r = create_sim_from_params(params).run()
    print(f"  Cp        = {r['cp']:+.4f}")
    print(f"  TSR_eq    = {r['tsr_eq']:.3f}")
    print(f"  RPM       = {r['rpm']:.1f}")
    print(f"  pitch     = [{r['pitch_min']:+.1f}, {r['pitch_max']:+.1f}] deg")
    print(f"  alpha_max = {r['aoa_max']:.1f} deg")
    print(f"  stop_pct  = {r['stop_pct']:.1f} %")
    print(f"  steady    = {r.get('steady', True)}")


if __name__ == "__main__":
    main()