#!/usr/bin/env python3
"""
Compare frozen-model predictions with processed prototype measurements.

Scientific contract
-------------------
* This script NEVER prints or returns "validated" unless the measured data are
  declared ``measured`` (not synthetic), the frozen-settings file is marked
  ``FROZEN``, and **all** pre-registered acceptance criteria pass.
* Synthetic data are supported for testing the tooling.  Synthetic provenance
  can never yield a validation status.
* The primary prediction is a free-running rotor at the measured wind speed and
  the frozen load model (so RPM is genuinely predicted).  An RPM-prescribed run
  is reported separately as an aerodynamic diagnostic and is not used for
  acceptance.
* Nothing is filtered: every input row appears in the output with its status.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.stamp import make_stamp
from sharp_vawt import create_sim_from_params

# Model fields copied from the measured-geometry JSON.
_GEO_MAP = {
    "R_m": "R", "c_m": "c", "H_m": "H", "N": "N", "ar": "ar", "sp": "sp",
    "arm_d_m": "arm_d", "n_arm": "n_arm", "arm_cd": "arm_cd",
    "mb_kg": "mb", "xbcg_over_c": "xbcg", "mc_kg": "mc", "dcw": "dcw",
    "J_hub_kgm2": "J_hub",
}

# Settings copied directly when present.
_MODEL_KEYS = [
    "polar_variant", "use_dynamic_stall", "ds_Tf", "ds_Tv", "ds_Ta",
    "ds_Kv", "ds_Knc", "use_dmst", "use_dynamic_inflow", "tau_rev", "a_fix",
    "use_tip_loss", "use_flow_curvature", "tip_loss_multiplier",
    "tip_loss_floor_override", "e_osw", "ind_drag_scale", "cd_add",
    "use_flow_curvature", "cm_scale",
]

ACCEPTANCE = {
    "mean_rel_cp_max": 0.15,
    "rmse_cp_max": 0.03,
    "mean_rel_rpm_max": 0.10,
    "abs_bias_cp_max": 0.02,
    "coverage_min": 0.70,
    "min_repeats_per_condition": 3,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _base_params(geo: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for src, dst in _GEO_MAP.items():
        if src in geo and geo[src] is not None:
            params[dst] = geo[src]
    for key in _MODEL_KEYS:
        if key in settings and settings[key] is not None:
            params[key] = settings[key]
    return params


def _run(params: dict[str, Any]) -> dict[str, Any]:
    res = create_sim_from_params(params).run()
    if not math.isfinite(res["cp"]) or not math.isfinite(res["rpm"]):
        raise RuntimeError("non-finite model output")
    return res


def predict_row(row: dict[str, Any], geo: dict[str, Any],
                settings: dict[str, Any]) -> dict[str, Any]:
    U = float(row["wind_speed_mps"])
    rho = float(row["air_density_kgm3"])
    R = float(geo["R_m"])
    H = float(geo["H_m"])
    area = 2.0 * R * H
    eta = float(row["drivetrain_efficiency_assumption"])
    T_max = float(settings.get("T_max_s", 20.0))
    stride = int(settings.get("stride", 5))
    base = _base_params(geo, settings)

    # Primary: free-running prediction (RPM is predicted, not prescribed).
    free_params = dict(base, U=U, free=True, T_max=T_max, stride=stride,
                       k_load=float(settings.get("k_load", 0.0025)),
                       w0_frac=float(settings.get("w0_frac", 0.9)), seed=0)
    free = _run(free_params)
    p_shaft = free["cp"] * 0.5 * rho * area * U ** 3
    p_elec = p_shaft * eta

    # Diagnostic: prescribed RPM equal to the measurement.
    tsr_meas = float(row["tsr"])
    fixed_params = dict(base, U=U, free=False, tsr=tsr_meas,
                        T_max=T_max, stride=stride, seed=0)
    fixed = _run(fixed_params)
    p_shaft_fixed = fixed["cp"] * 0.5 * rho * area * U ** 3

    return {
        "pred_rpm": free["rpm"],
        "pred_cp": free["cp"],
        "pred_tsr": free["tsr_eq"],
        "pred_shaft_power_W": p_shaft,
        "pred_electrical_power_W": p_elec,
        "pred_cp_at_measured_rpm": fixed["cp"],
        "pred_shaft_power_at_measured_rpm_W": p_shaft_fixed,
        "model_steady": bool(free["steady"]),
        "model_energy_balance": free["energy_balance"],
    }


def evaluate_criteria(rows: list[dict[str, Any]], settings: dict[str, Any],
                      provenance: str) -> tuple[str, dict[str, Any], list[str]]:
    accepted = [r for r in rows if r["accepted"] and r.get("pred") and not r.get("error")]
    blockers: list[str] = []

    if provenance != "measured":
        blockers.append("data provenance is not 'measured' (synthetic tooling run)")
    if not str(settings.get("status", "")).upper().startswith("FROZEN"):
        blockers.append("frozen settings file is not marked FROZEN")

    if not accepted:
        return "not_yet_available", {"n_evaluated": 0}, blockers + ["no accepted rows with successful predictions"]

    cps_m = [r["cp"] for r in accepted]
    cps_p = [r["pred"]["pred_cp"] for r in accepted]
    rpms_m = [r["rpm"] for r in accepted]
    rpms_p = [r["pred"]["pred_rpm"] for r in accepted]

    rel_cp = [abs(p - m) / max(abs(m), 1e-12) for m, p in zip(cps_m, cps_p)]
    rel_rpm = [abs(p - m) / max(abs(m), 1e-12) for m, p in zip(rpms_m, rpms_p)]
    err_cp = [p - m for m, p in zip(cps_m, cps_p)]
    mean_rel_cp = sum(rel_cp) / len(rel_cp)
    mean_rel_rpm = sum(rel_rpm) / len(rel_rpm)
    rmse_cp = math.sqrt(sum(e * e for e in err_cp) / len(err_cp))
    bias_cp = sum(err_cp) / len(err_cp)

    band = float(settings.get("model_scenario_band_cp", 0.0) or 0.0)
    if band > 0.0:
        covered = sum(1 for m, p in zip(cps_m, cps_p) if abs(m - p) <= band)
        coverage = covered / len(accepted)
    else:
        coverage = 0.0
        blockers.append("no model_scenario_band_cp declared; coverage criterion cannot pass")

    # Repeat count per measured condition.
    groups: dict[tuple[float, float], int] = {}
    for r in accepted:
        key = (round(float(r["wind_speed_mps"]), 1), round(float(r["load_ohms"]), 3))
        groups[key] = groups.get(key, 0) + 1
    min_repeats = min(groups.values()) if groups else 0

    torque_sign_ok = all(
        (r["torque_used_Nm"] >= 0.0) == (r["pred"]["pred_shaft_power_W"] >= 0.0)
        for r in accepted
    )
    all_steady = all(r["pred"]["model_steady"] for r in accepted)

    criteria = {
        "mean_rel_cp": mean_rel_cp <= ACCEPTANCE["mean_rel_cp_max"],
        "rmse_cp": rmse_cp <= ACCEPTANCE["rmse_cp_max"],
        "mean_rel_rpm": mean_rel_rpm <= ACCEPTANCE["mean_rel_rpm_max"],
        "abs_bias_cp": abs(bias_cp) <= ACCEPTANCE["abs_bias_cp_max"],
        "coverage": coverage >= ACCEPTANCE["coverage_min"],
        "torque_sign": torque_sign_ok,
        "min_repeats": min_repeats >= ACCEPTANCE["min_repeats_per_condition"],
        "all_steady": all_steady,
    }
    metrics = {
        "n_evaluated": len(accepted),
        "n_groups": len(groups),
        "min_repeats_per_condition": min_repeats,
        "mean_rel_cp": mean_rel_cp,
        "rmse_cp": rmse_cp,
        "mean_rel_rpm": mean_rel_rpm,
        "bias_cp": bias_cp,
        "model_band_cp": band,
        "coverage": coverage,
        "criteria": criteria,
        "thresholds": ACCEPTANCE,
    }
    if blockers:
        return "not_yet_available", metrics, blockers
    return ("validation_criteria_met" if all(criteria.values()) else "discrepancy"), metrics, blockers


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="processed prototype CSV")
    ap.add_argument("--geometry", required=True, help="geometry_<id>.json")
    ap.add_argument("--settings", required=True, help="frozen_model_settings.json")
    ap.add_argument("--out", required=True, help="comparison JSON")
    ap.add_argument("--provenance", choices=["measured", "synthetic"], default="synthetic",
                    help="synthetic data can test the tooling but never yield validation")
    args = ap.parse_args(argv)

    geo = load_json(args.geometry)
    settings = load_json(args.settings)
    if settings.get("geometry_id") not in (None, geo.get("geometry_id")):
        raise ValueError("settings geometry_id does not match geometry file")

    data_path = Path(args.data)
    with open(data_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        raw_rows = list(reader)

    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        row: dict[str, Any] = {
            "run_id": raw.get("run_id"),
            "wind_speed_mps": float(raw["wind_speed_mps"]),
            "rpm": float(raw["rpm"]),
            "cp": float(raw["cp"]),
            "tsr": float(raw["tsr"]),
            "load_ohms": float(raw["load_ohms"]),
            "torque_used_Nm": float(raw["torque_used_Nm"]),
            "torque_source": raw.get("torque_source", "unknown"),
            "drivetrain_efficiency_assumption": float(raw["drivetrain_efficiency_assumption"]),
            "air_density_kgm3": float(raw["air_density_kgm3"]),
            "accepted": (raw.get("accepted", "false").strip().lower() == "true"),
            "exclusion_reason": raw.get("exclusion_reason", ""),
        }
        if row["accepted"]:
            try:
                row["pred"] = predict_row(row, geo, settings)
            except Exception as exc:  # noqa: BLE001 - keep the row visible; never silently drop
                row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)

    status, metrics, blockers = evaluate_criteria(rows, settings, args.provenance)

    for row in rows:
        pred = row.get("pred")
        if pred and not row.get("error"):
            row["error_cp"] = pred["pred_cp"] - row["cp"]
            row["rel_error_cp"] = row["error_cp"] / max(abs(row["cp"]), 1e-12)
            row["error_rpm"] = pred["pred_rpm"] - row["rpm"]
            row["rel_error_rpm"] = row["error_rpm"] / max(abs(row["rpm"]), 1e-12)

    result = {
        "status": status,
        "provenance": args.provenance,
        "statement": (
            "This comparison does not by itself validate the model. "
            "Only status='validation_criteria_met' on independent measured data, "
            "and only for the tested envelope, may be described as validation."
        ),
        "blockers": blockers,
        "data_file": str(data_path.resolve()),
        "data_sha256": _sha256(data_path),
        "geometry_file": str(Path(args.geometry).resolve()),
        "geometry_sha256": _sha256(Path(args.geometry)),
        "settings_file": str(Path(args.settings).resolve()),
        "settings_sha256": _sha256(Path(args.settings)),
        "metrics": metrics,
        "rows": rows,
        "non_claims": [
            "agreement with sharp-fsi is not validation",
            "literature comparison is not validation",
            "uncertainty bands are not validation",
            "counter-rotating array results are not validated predictions",
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = make_stamp("scripts/compare_prototype.py",
                       script_version="1.0.0",
                       n=len(rows),
                       extra_files=[str(Path(args.settings).resolve()),
                                    str(Path(args.geometry).resolve())],
                       extra_data={"provenance": args.provenance,
                                   "status": status})
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"stamp": stamp, **result}, fh, indent=2)
        fh.write("\n")

    print(f"Wrote {out_path}")
    print(f"Status: {status}")
    for blocker in blockers:
        print(f"  blocker: {blocker}")
    if metrics.get("n_evaluated"):
        print(f"  evaluated rows: {metrics['n_evaluated']}, "
              f"mean |rel Cp| = {metrics['mean_rel_cp']:.1%}, "
              f"RMSE Cp = {metrics['rmse_cp']:.4f}, "
              f"mean |rel RPM| = {metrics['mean_rel_rpm']:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
