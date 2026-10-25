#!/usr/bin/env python3
"""
Validate and process measured prototype data into the pre-registered schema.

This script is deliberately strict and non-destructive:

* it never deletes a row; pre-registered exclusions are retained with
  ``accepted=false`` and their ``exclusion_reason``,
* it refuses to continue when a required column is missing, a run_id is
  duplicated, or a numeric value is non-finite/negative where that is
  unphysical,
* it records whether torque was measured or inferred, and propagates
  first-order uncertainty to shaft power, torque, tip speed, TSR and CP.

Importing data does **not** validate the model.  The summary JSON is stamped
with ``status = "import_only_not_validation"``.
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

REQUIRED_TEXT = [
    "run_id", "date_utc", "operator", "rotor_id", "geometry_id",
    "generator_model",
]
REQUIRED_NUMERIC = [
    "wind_speed_mps", "wind_speed_uncertainty_mps",
    "rpm", "rpm_uncertainty",
    "electrical_power_W", "electrical_power_uncertainty_W",
    "load_ohms",
    "drivetrain_efficiency_assumption",
    "air_density_kgm3",
    "temperature_C", "pressure_hPa", "humidity_percent",
]
OPTIONAL = ["torque_Nm", "torque_uncertainty_Nm", "notes", "exclusion_reason",
            "air_density_uncertainty_kgm3"]

DERIVED = [
    "shaft_power_W", "shaft_power_uncertainty_W",
    "torque_source", "torque_used_Nm", "torque_used_uncertainty_Nm",
    "tip_speed_mps", "tip_speed_uncertainty_mps",
    "tsr", "tsr_uncertainty",
    "cp", "cp_uncertainty",
    "accepted",
]


class SchemaError(ValueError):
    pass


def _num(row: dict[str, str], key: str, *, required: bool = True) -> float:
    raw = (row.get(key) or "").strip()
    if raw == "":
        if required:
            raise SchemaError(f"{row.get('run_id', '?')}: missing required value {key!r}")
        return math.nan
    try:
        val = float(raw)
    except ValueError as exc:
        raise SchemaError(
            f"{row.get('run_id', '?')}: {key!r} is not numeric: {raw!r}"
        ) from exc
    return val


def load_geometry(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        geo = json.load(fh)
    required = ["R_m", "c_m", "H_m", "N", "ar", "sp"]
    missing = [k for k in required if k not in geo]
    if missing:
        raise SchemaError(f"geometry {path}: missing {missing}")
    if geo["R_m"] <= 0 or geo["c_m"] <= 0 or geo["H_m"] <= 0:
        raise SchemaError(f"geometry {path}: R, c, H must be positive")
    return geo


def process_row(row: dict[str, str], geo: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(row)

    for key in REQUIRED_TEXT:
        if not (row.get(key) or "").strip():
            raise SchemaError(f"{row.get('run_id', '?')}: missing required text field {key!r}")

    vals = {key: _num(row, key) for key in REQUIRED_NUMERIC}
    eta = vals["drivetrain_efficiency_assumption"]
    if not math.isfinite(eta):
        raise SchemaError(f"{row['run_id']}: drivetrain efficiency must be finite")
    if not (0.0 < eta <= 1.0):
        raise SchemaError(f"{row['run_id']}: drivetrain efficiency must be in (0, 1]")

    for key, value in vals.items():
        if not math.isfinite(value):
            raise SchemaError(f"{row['run_id']}: {key} must be finite")

    for key in ("wind_speed_mps", "wind_speed_uncertainty_mps", "rpm", "rpm_uncertainty",
                "electrical_power_W", "electrical_power_uncertainty_W",
                "air_density_kgm3"):
        if vals[key] < 0.0:
            raise SchemaError(f"{row['run_id']}: {key} must be non-negative")

    U = vals["wind_speed_mps"]
    uU = vals["wind_speed_uncertainty_mps"]
    rpm = vals["rpm"]
    urpm = vals["rpm_uncertainty"]
    P_elec = vals["electrical_power_W"]
    uP_elec = vals["electrical_power_uncertainty_W"]
    rho = vals["air_density_kgm3"]
    urho = _num(row, "air_density_uncertainty_kgm3", required=False)
    if math.isnan(urho):
        urho = 0.0
    elif not math.isfinite(urho) or urho < 0.0:
        raise SchemaError(
            f"{row['run_id']}: air_density_uncertainty_kgm3 must be finite and non-negative")

    if U == 0.0:
        raise SchemaError(f"{row['run_id']}: wind speed is zero; TSR undefined")
    if rpm == 0.0:
        raise SchemaError(f"{row['run_id']}: RPM is zero; torque/TSR undefined")

    R_m = float(geo["R_m"])
    H_m = float(geo["H_m"])
    A = 2.0 * R_m * H_m
    omega = 2.0 * math.pi * rpm / 60.0
    uomega = 2.0 * math.pi * urpm / 60.0

    P_shaft = P_elec / eta
    uP_shaft = uP_elec / eta

    q_meas = _num(row, "torque_Nm", required=False)
    if math.isfinite(q_meas):
        q_unc = _num(row, "torque_uncertainty_Nm", required=False)
        if not math.isfinite(q_unc):
            raise SchemaError(
                f"{row['run_id']}: torque_Nm present but torque_uncertainty_Nm missing"
            )
        torque = q_meas
        u_torque = q_unc
        torque_source = "measured"
    else:
        torque = P_shaft / omega
        u_torque = torque * math.hypot(uP_shaft / max(P_shaft, 1e-12),
                                       uomega / max(omega, 1e-12))
        torque_source = "inferred"

    tip = omega * R_m
    u_tip = uomega * R_m
    tsr = tip / U
    u_tsr = tsr * math.hypot(u_tip / max(tip, 1e-12), uU / max(U, 1e-12))

    cp = P_shaft / (0.5 * rho * A * U ** 3)
    u_cp = abs(cp) * math.sqrt(
        (uP_shaft / max(P_shaft, 1e-12)) ** 2
        + (urho / max(rho, 1e-12)) ** 2
        + (3.0 * uU / U) ** 2
    )

    exclusion = (row.get("exclusion_reason") or "").strip()
    accepted = not exclusion

    out.update({
        "shaft_power_W": f"{P_shaft:.9g}",
        "shaft_power_uncertainty_W": f"{uP_shaft:.9g}",
        "torque_source": torque_source,
        "torque_used_Nm": f"{torque:.9g}",
        "torque_used_uncertainty_Nm": f"{u_torque:.9g}",
        "tip_speed_mps": f"{tip:.9g}",
        "tip_speed_uncertainty_mps": f"{u_tip:.9g}",
        "tsr": f"{tsr:.9g}",
        "tsr_uncertainty": f"{u_tsr:.9g}",
        "cp": f"{cp:.9g}",
        "cp_uncertainty": f"{u_cp:.9g}",
        "accepted": "true" if accepted else "false",
    })
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="raw CSV export")
    ap.add_argument("--geometry", required=True, help="geometry_<id>.json")
    ap.add_argument("--out", required=True, help="processed CSV path")
    ap.add_argument("--provenance", choices=["measured", "synthetic"], default="synthetic",
                    help="synthetic data may be tested but must never be called validation")
    args = ap.parse_args(argv)

    geo = load_geometry(args.geometry)

    with open(args.input, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    missing = [c for c in REQUIRED_TEXT + REQUIRED_NUMERIC
               if c not in fieldnames]
    if missing:
        raise SchemaError(f"input CSV missing required column(s): {missing}")
    if not rows:
        raise SchemaError("input CSV has no data rows")

    seen = set()
    processed: list[dict[str, Any]] = []
    for row in rows:
        rid = (row.get("run_id") or "").strip()
        if rid in seen:
            raise SchemaError(f"duplicate run_id: {rid!r}")
        seen.add(rid)
        processed.append(process_row(row, geo))

    out_fields = fieldnames + [c for c in DERIVED if c not in fieldnames]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(processed)

    accepted = sum(1 for r in processed if r["accepted"] == "true")
    inferred = sum(1 for r in processed if r["torque_source"] == "inferred")
    summary = {
        "status": "import_only_not_validation",
        "provenance": args.provenance,
        "statement": (
            "This file describes data import only. It is not a model comparison "
            "and does not validate any model."
        ),
        "input_file": str(Path(args.input).resolve()),
        "input_sha256": _sha256(Path(args.input)),
        "geometry_file": str(Path(args.geometry).resolve()),
        "geometry_sha256": _sha256(Path(args.geometry)),
        "processed_file": str(out_path.resolve()),
        "n_rows": len(processed),
        "n_accepted": accepted,
        "n_excluded": len(processed) - accepted,
        "n_torque_inferred": inferred,
        "n_torque_measured": len(processed) - inferred,
        "exclusion_reasons": sorted({r.get("exclusion_reason", "").strip()
                                      for r in processed
                                      if r["accepted"] == "false"}),
    }
    summary_path = out_path.with_suffix(out_path.suffix + ".summary.json")
    stamp = make_stamp("scripts/import_prototype_data.py",
                       script_version="1.0.0",
                       n=len(processed),
                       extra_files=[str(out_path.relative_to(_ROOT))
                                    if out_path.is_relative_to(_ROOT) else str(out_path)],
                       extra_data={"provenance": args.provenance,
                                   "input_sha256": summary["input_sha256"]})
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump({"stamp": stamp, **summary}, fh, indent=2)
        fh.write("\n")

    print(f"Wrote {out_path} ({len(processed)} rows, {accepted} accepted)")
    print(f"Wrote {summary_path}")
    print("Status: import only — NOT validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
