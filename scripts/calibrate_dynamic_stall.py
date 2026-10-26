#!/usr/bin/env python3
"""
Bound-constrained calibration of the dynamic-stall (DS) constants.

This tool does NOT change the default DS constants in ``sharp_vawt/config.py``.
It writes a candidate parameter file.  A candidate may only be described as
"calibrated" if independent measured data are used and every held-out
acceptance criterion in docs/dynamic_stall_calibration_plan.md is met.

The script refuses to mark the model calibrated unless the held-out criteria
are satisfied.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import sharp_vawt.config as cfg
from scripts.stamp import make_stamp
from sharp_vawt.config import AeroConfig
from sharp_vawt.database import PolarDatabase
from sharp_vawt.engine import _aero_coeffs

# Canonical defaults (documented in docs/dynamic_stall_calibration_plan.md).
# These are read from sharp_vawt.config so the fit baseline cannot drift from
# the production defaults; this process never changes them.
_CALIBRATABLE = ("ds_Tf", "ds_Tv", "ds_Ta", "ds_Kv", "ds_Knc")

BOUNDS: dict[str, tuple[float, float]] = {
    "ds_Tf": (0.5, 10.0),
    "ds_Tv": (1.0, 20.0),
    "ds_Ta": (0.02, 1.0),
    "ds_Kv": (0.0, 2.0),
    "ds_Knc": (0.0, 2.0),
}

_DEFAULT_AERO = cfg.AeroConfig()
DEFAULTS: dict[str, float] = {
    p: float(getattr(_DEFAULT_AERO, p)) for p in _CALIBRATABLE
}


def _identifiability(jac) -> tuple[float, bool]:
    """Approximate Jacobian condition number and finite-identifiability flag."""
    import numpy as np
    try:
        sv = np.linalg.svd(np.asarray(jac, dtype=float), compute_uv=False)
        cond = float(sv[0] / max(sv[-1], 1e-300)) if sv.size else float("nan")
    except Exception:  # noqa: BLE001 - SVD may fail on a degenerate Jacobian
        return float("nan"), False
    return cond, bool(math.isfinite(cond) and cond < 1e10)

class CalibrationError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _num(row: dict[str, str], key: str) -> float:
    raw = (row.get(key) or "").strip()
    if raw == "":
        raise CalibrationError(f"case {row.get('case_id','?')}: missing {key!r}")
    try:
        return float(raw)
    except ValueError as exc:
        raise CalibrationError(
            f"case {row.get('case_id','?')}: {key!r} not numeric: {raw!r}"
        ) from exc


def load_dataset(path: str) -> tuple[dict[str, list[dict[str, float]]], list[str]]:
    """Load and validate the CSV.  Returns (cases keyed by case_id, column order)."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = list(reader.fieldnames or [])
        rows = list(reader)

    required = ["case_id", "time_s", "alpha_deg", "cl", "cd", "Re", "chord_m", "W_mps"]
    missing = [c for c in required if c not in cols]
    if missing:
        raise CalibrationError(f"dataset missing required column(s): {missing}")
    if not rows:
        raise CalibrationError("dataset has no rows")

    cases: dict[str, list[dict[str, float]]] = {}
    for row in rows:
        cid = (row.get("case_id") or "").strip()
        if not cid:
            raise CalibrationError("row with empty case_id")
        t = _num(row, "time_s")
        a = _num(row, "alpha_deg")
        cl = _num(row, "cl")
        cd = _num(row, "cd")
        Re = _num(row, "Re")
        chord = _num(row, "chord_m")
        W = _num(row, "W_mps")
        if not math.isfinite(t) or not math.isfinite(a) or not math.isfinite(cl) \
                or not math.isfinite(cd) or not math.isfinite(Re) \
                or not math.isfinite(chord) or not math.isfinite(W):
            raise CalibrationError(f"case {cid}: non-finite numeric value at t={t}")
        if cd < -1e-9 or Re <= 0.0 or chord <= 0.0 or W <= 0.0:
            raise CalibrationError(f"case {cid}: unphysical value at t={t}")
        cases.setdefault(cid, []).append(
            {"time": t, "alpha": a, "cl": cl, "cd": cd, "Re": Re, "chord": chord, "W": W}
        )

    for cid, pts in cases.items():
        pts.sort(key=lambda p: p["time"])
        dts = [pts[i + 1]["time"] - pts[i]["time"] for i in range(len(pts) - 1)]
        if dts and (min(dts) <= 0.0 or max(dts) / max(min(dts), 1e-9) > 100.0):
            raise CalibrationError(f"case {cid}: non-uniform time steps")
    return cases, cols


def _case_split(cases: dict[str, list[dict[str, float]]],
                fraction: float,
                cal: list[str] | None,
                hold: list[str] | None) -> tuple[list[str], list[str]]:
    ids = sorted(cases)
    if cal is not None and hold is not None:
        cal_set, hold_set = set(cal), set(hold)
        unknown = (cal_set | hold_set) - set(ids)
        if unknown:
            raise CalibrationError(f"unknown case id(s) in split: {sorted(unknown)}")
        overlap = cal_set & hold_set
        if overlap:
            raise CalibrationError(f"case(s) in both sets: {sorted(overlap)}")
        return sorted(cal_set), sorted(hold_set)
    cal_ids, hold_ids = [], []
    for cid in ids:
        bucket = int(hashlib.sha256(cid.encode()).hexdigest(), 16) % 100
        (cal_ids if bucket < fraction * 100 else hold_ids).append(cid)
    return cal_ids, hold_ids


# ---------------------------------------------------------------------------
# Model evaluation
# ---------------------------------------------------------------------------

class ModelRunner:
    """Evaluate the DS-enhanced aerodynamics over an alpha time series.

    Uses the production aerodynamic routine with the same aerodynamic policy as
    the rotor engine: the same packaged polars and variant, the same global
    ``PolarDatabase.Cl_max`` clamp, the same ``cm_scale``, and the same
    dynamic-stall on/off choice.  Rotor-only corrections (curvature, finite-span
    lift loss, induced drag, added parasitic drag) are not applied: the input is
    an externally imposed airfoil trace, not a rotating-blade element.
    """

    def __init__(self, aero: AeroConfig | None = None,
                 pdb: PolarDatabase | None = None):
        if aero is None:
            aero = cfg.AeroConfig()
        if pdb is None:
            pdb = PolarDatabase(aero.polar_dir, variant=aero.polar_variant)
        self.aero = aero
        self.pdb = pdb
        self.clmax = self.pdb.Cl_max
        self.cm_scale = self.aero.cm_scale
        self.dyn = int(self.aero.use_dynamic_stall)

    def simulate(self, points: list[dict[str, float]], params: dict[str, float]) -> list[tuple[float, float, float]]:
        """Return per-step (Cl, Cd, Cm) predictions for one trace."""
        p = dict(DEFAULTS)
        p.update(params)
        out: list[tuple[float, float, float]] = []
        ds = [0.0, 0.0, 0.0, 0.0, 0.0]  # alpha_eff, f_dyn, v_vortex, alpha_prev, initialised
        prev_t = None
        for pt in points:
            t = pt["time"]
            dt = (t - prev_t) if prev_t is not None else 0.05 * pt["chord"] / max(pt["W"], 1e-3)
            prev_t = t
            Cl, Cd, _Cl_nc, _f, Cm = _aero_coeffs(
                ds, math.radians(pt["alpha"]), pt["W"], pt["chord"], dt, pt["Re"],
                self.dyn,
                p["ds_Tf"], p["ds_Tv"], p["ds_Ta"],
                p["ds_Kv"], self.clmax,
                self.pdb.logRe_grid, self.pdb.alpha_grid, self.pdb.cla_re,
                self.pdb.Cl, self.pdb.Cd, self.pdb.Cm, self.cm_scale,
            )
            out.append((float(Cl), float(Cd), float(Cm)))
        return out


# ---------------------------------------------------------------------------
# Residuals
# ---------------------------------------------------------------------------

def residuals_for_params(runner: ModelRunner, case_ids: list[str], cases: dict[str, list[dict[str, float]]],
                         params: dict[str, float], fit_cm: bool) -> list[float]:
    res: list[float] = []
    for cid in case_ids:
        pts = cases[cid]
        preds = runner.simulate(pts, params)
        meas_cl = [p["cl"] for p in pts]
        meas_cd = [p["cd"] for p in pts]
        meas_cm = [p.get("cm", math.nan) for p in pts]
        rms_cl = math.sqrt(sum(v * v for v in meas_cl) / len(meas_cl)) or 1.0
        rms_cd = math.sqrt(sum(v * v for v in meas_cd) / len(meas_cd)) or 1.0
        for i, (Cl, Cd, Cm) in enumerate(preds):
            res.append((Cl - meas_cl[i]) / rms_cl)
            res.append((Cd - meas_cd[i]) / rms_cd)
            if fit_cm and math.isfinite(meas_cm[i]):
                res.append((Cm - meas_cm[i]) / 1.0)
    return res


def rmse_for_params(runner: ModelRunner, case_ids: list[str], cases: dict[str, list[dict[str, float]]],
                    params: dict[str, float], fit_cm: bool) -> dict[str, float]:
    errs: dict[str, list[float]] = {"cl": [], "cd": [], "cm": []}
    for cid in case_ids:
        pts = cases[cid]
        preds = runner.simulate(pts, params)
        for i, (Cl, Cd, Cm) in enumerate(preds):
            errs["cl"].append(Cl - pts[i]["cl"])
            errs["cd"].append(Cd - pts[i]["cd"])
            if math.isfinite(pts[i].get("cm", math.nan)):
                errs["cm"].append(Cm - pts[i]["cm"])
    out = {}
    for k in ("cl", "cd"):
        out[k] = math.sqrt(sum(e * e for e in errs[k]) / len(errs[k])) if errs[k] else float("nan")
    out["cm"] = (math.sqrt(sum(e * e for e in errs["cm"]) / len(errs["cm"]))
                 if errs["cm"] else float("nan"))
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="calibration CSV dataset")
    ap.add_argument("--out", required=True, help="calibration report JSON")
    ap.add_argument("--calibration-cases", nargs="*", default=None)
    ap.add_argument("--heldout-cases", nargs="*", default=None)
    ap.add_argument("--calibration-fraction", type=float, default=0.60)
    ap.add_argument("--fit", nargs="*", default=list(_CALIBRATABLE))
    ap.add_argument("--provenance", choices=["measured", "synthetic"], default="synthetic")
    args = ap.parse_args(argv)

    invalid_fit = [p for p in args.fit if p not in BOUNDS]
    if invalid_fit:
        raise CalibrationError(f"unknown --fit parameter(s): {invalid_fit}")
    if not args.fit:
        raise CalibrationError("--fit must select at least one parameter")
    if not 0.0 < args.calibration_fraction < 1.0:
        raise CalibrationError("--calibration-fraction must lie strictly between 0 and 1")

    cases, cols = load_dataset(args.data)
    cal_ids, hold_ids = _case_split(cases, args.calibration_fraction,
                                    args.calibration_cases, args.heldout_cases)
    if len(cal_ids) < 2 or len(hold_ids) < 2:
        raise CalibrationError("need at least 2 calibration and 2 held-out cases")
    hold_samples = sum(len(cases[c]) for c in hold_ids)
    if hold_samples < 50:
        raise CalibrationError(f"need at least 50 held-out samples (have {hold_samples})")

    runner = ModelRunner()

    # Deep-stall lag/strength parameters are SimConfig/AeroConfig fields;
    # these defaults match sharp_vawt/config.py and must not drift from it.
    defaults = dict(DEFAULTS)

    # Bounds for fitted params; unfitted params fixed at default.
    lb = [BOUNDS[p][0] for p in args.fit]
    ub = [BOUNDS[p][1] for p in args.fit]
    x0 = [defaults[p] for p in args.fit]

    try:
        from scipy.optimize import least_squares
    except Exception as exc:  # pragma: no cover
        raise CalibrationError("scipy is required for calibration") from exc

    def fun(x):
        params = dict(defaults)
        for p, v in zip(args.fit, x):
            params[p] = float(v)
        return residuals_for_params(runner, cal_ids, cases, params, fit_cm="cm" in cols)

    res = least_squares(fun, x0, bounds=(lb, ub), method="trf")
    fitted = {p: float(v) for p, v in zip(args.fit, res.x)}

    held_defaults = rmse_for_params(runner, hold_ids, cases, defaults, fit_cm="cm" in cols)
    held_candidate = rmse_for_params(runner, hold_ids, cases, fitted, fit_cm="cm" in cols)

    cm_present = "cm" in cols
    cl_imp = (held_defaults["cl"] - held_candidate["cl"]) / max(held_defaults["cl"], 1e-12)
    cd_imp = (held_defaults["cd"] - held_candidate["cd"]) / max(held_defaults["cd"], 1e-12)
    cm_imp = None
    if cm_present and math.isfinite(held_defaults["cm"]) and held_defaults["cm"] > 0:
        cm_imp = (held_defaults["cm"] - held_candidate["cm"]) / held_defaults["cm"]

    inside_bounds = all(
        BOUNDS[p][0] * 1.001 < fitted[p] < BOUNDS[p][1] * 0.999 for p in args.fit
    )
    cond, cond_ok = _identifiability(res.jac)

    import numpy as np
    try:
        cov = np.linalg.inv(res.jac.T @ res.jac) * (
            res.cost * 2 / max(len(res.fun) - len(res.x), 1))
        intervals = {p: float(2.0 * math.sqrt(max(cov[i, i], 0.0)))
                     for i, p in enumerate(args.fit)}
    except Exception:  # noqa: BLE001 - covariance may be singular
        intervals = {p: float("nan") for p in args.fit}
    intervals_finite = all(math.isfinite(v) for v in intervals.values())
    identifiable = bool(cond_ok and intervals_finite)
    converged = bool(res.success)

    criteria = {
        "holdout_min_cases": len(hold_ids) >= 2,
        "holdout_min_samples": hold_samples >= 50,
        "fit_converged": converged,
        "rmse_cl_threshold": bool(math.isfinite(held_candidate["cl"])) and held_candidate["cl"] <= 0.08,
        "rmse_cd_threshold": bool(math.isfinite(held_candidate["cd"])) and held_candidate["cd"] <= 0.06,
        "rmse_cm_threshold": (not cm_present) or (
            math.isfinite(held_candidate["cm"]) and held_candidate["cm"] <= 0.05
        ),
        "cl_improvement": cl_imp >= 0.20,
        "cd_improvement": cd_imp >= 0.20,
        "cm_improvement": (not cm_present) or (cm_imp is not None and cm_imp >= 0.20),
        "identifiable": identifiable,
        "not_pinned": inside_bounds,
    }

    all_met = all(criteria.values())

    calibration_claim_allowed = bool(args.provenance == "measured" and all_met)
    status = "calibrated" if calibration_claim_allowed else "not_calibrated"

    report = {
        "status": status,
        "provenance": args.provenance,
        "calibration_claim_allowed": calibration_claim_allowed,
        "statement": (
            "The DS constants remain uncalibrated defaults unless status is "
            "'calibrated' AND provenance is 'measured'.  Synthetic-data runs "
            "demonstrate tooling only."
        ),
        "data_file": str(Path(args.data).resolve()),
        "data_sha256": _sha256_file(Path(args.data)),
        "n_cases": len(cases),
        "n_calibration_cases": len(cal_ids),
        "n_heldout_cases": len(hold_ids),
        "n_heldout_samples": hold_samples,
        "calibration_cases": cal_ids,
        "heldout_cases": hold_ids,
        "fit_parameters": list(args.fit),
        "fitted_parameters": fitted,
        "fixed_parameters": {p: defaults[p] for p in _CALIBRATABLE if p not in args.fit},
        "defaults": defaults,
        "bounds": {p: list(BOUNDS[p]) for p in _CALIBRATABLE},
        "heldout_rmse_defaults": held_defaults,
        "heldout_rmse_candidate": held_candidate,
        "improvement_vs_defaults": {"cl": cl_imp, "cd": cd_imp, "cm": cm_imp},
        "cost": float(res.cost),
        "fit_success": converged,
        "fit_message": str(res.message),
        "n_function_evaluations": int(res.nfev),
        "condition_number": cond,
        "intervals_95": intervals,
        "criteria": criteria,
        "criteria_met": all_met,
    }

    stamp = make_stamp("scripts/calibrate_dynamic_stall.py",
                       script_version="1.1.0",
                       n=len(cases),
                       extra_files=[str(Path(args.data).resolve())],
                       extra_data={"provenance": args.provenance,
                                   "status": status,
                                   "calibratable": list(_CALIBRATABLE)})
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"stamp": stamp, **report}, fh, indent=2)
        fh.write("\n")

    print(f"Wrote {out_path}")
    print(f"Status: {status}  claim_allowed: {calibration_claim_allowed}")
    print(f"  held-out RMSE Cl: default={held_defaults['cl']:.4f} candidate={held_candidate['cl']:.4f} "
          f"improvement={cl_imp:.1%}")
    print(f"  held-out RMSE Cd: default={held_defaults['cd']:.4f} candidate={held_candidate['cd']:.4f} "
          f"improvement={cd_imp:.1%}")
    print(f"  condition number: {cond:.3g}  identifiable={identifiable}  inside_bounds={inside_bounds}")
    if not calibration_claim_allowed:
        print("  Not calibrated: held-out criteria not met and/or provenance is not 'measured'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
