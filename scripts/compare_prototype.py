#!/usr/bin/env python3
"""
Compare frozen-model predictions with processed prototype measurements.

Scientific contract
-------------------
* This script NEVER prints or returns ``validation_criteria_met`` unless the
  measured data are declared ``measured`` (not synthetic), the settings file
  passes the complete frozen-settings schema with valid provenance, and **all**
  pre-registered acceptance criteria pass.
* A settings file whose status merely starts with ``FROZEN`` is not sufficient:
  geometry and polar identities are hash-checked and the model/numerical
  configuration must be complete and internally consistent.
* Synthetic data are supported for testing the tooling.  Synthetic provenance
  can never yield a validation status.
* The primary prediction is a free-running rotor at the measured wind speed,
  air density and the frozen load model (so RPM is genuinely predicted).  An
  RPM-prescribed run is reported separately as an aerodynamic diagnostic and is
  not used for acceptance.
* Nothing is filtered: every input row appears in the output with its status.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.stamp import make_stamp
from sharp_vawt import create_sim_from_params
from sharp_vawt.config import POLAR_VARIANTS
from sharp_vawt.database import PolarDatabase

SETTINGS_SCHEMA_VERSION = 1
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")

# Model fields copied from the measured-geometry JSON.
_GEO_MAP = {
    "R_m": "R", "c_m": "c", "H_m": "H", "N": "N", "ar": "ar", "sp": "sp",
    "arm_d_m": "arm_d", "n_arm": "n_arm", "arm_cd": "arm_cd",
    "mb_kg": "mb", "xbcg_over_c": "xbcg", "mc_kg": "mc", "dcw": "dcw",
    "J_hub_kgm2": "J_hub",
}


class SettingsError(ValueError):
    """The frozen-settings file is incomplete, malformed or inconsistent."""


# ---------------------------------------------------------------------------
# Primitive validators
# ---------------------------------------------------------------------------

def _number(lo=None, hi=None, *, lo_open=False, hi_open=False, integer=False):
    def check(name: str, value: Any):
        if integer:
            if isinstance(value, bool) or not isinstance(value, int):
                raise SettingsError(f"frozen_model.{name}: expected an integer, got {value!r}")
            x: float = value
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SettingsError(f"frozen_model.{name}: expected a number, got {value!r}")
            x = float(value)
            if not math.isfinite(x):
                raise SettingsError(f"frozen_model.{name}: must be finite, got {value!r}")
        if lo is not None and (x < lo if not lo_open else x <= lo):
            op = ">" if lo_open else ">="
            raise SettingsError(f"frozen_model.{name}: must be {op} {lo}, got {x}")
        if hi is not None and (x > hi if not hi_open else x >= hi):
            op = "<" if hi_open else "<="
            raise SettingsError(f"frozen_model.{name}: must be {op} {hi}, got {x}")
        return int(x) if integer else x
    return check


def _boolean(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise SettingsError(f"frozen_model.{name}: expected true/false, got {value!r}")
    return value


def _string(*, choices: tuple[str, ...] | None = None, allow_path: bool = False):
    def check(name: str, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise SettingsError(f"frozen_model.{name}: expected a non-empty string")
        if choices is not None and value not in choices:
            raise SettingsError(
                f"frozen_model.{name}: {value!r} not in {sorted(choices)}")
        if not allow_path and Path(value).is_absolute():
            raise SettingsError(f"frozen_model.{name}: absolute paths are not allowed")
        return value
    return check


def _enum_int(allowed: tuple[int, ...]):
    def check(name: str, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value not in allowed:
            raise SettingsError(f"frozen_model.{name}: expected one of {allowed}, got {value!r}")
        return value
    return check


def _const_false(name: str, value: Any) -> bool:
    if value is not False:
        raise SettingsError(
            f"frozen_model.{name}: must be false; the frozen comparison is free-running, "
            "not a prescribed-pitch run")
    return False


# Complete frozen model/numerical schema.  Missing or extra fields are rejected.
_MODEL_FIELDS = {
    # aerodynamic model / polar source
    "polar_dir": _string(),
    "polar_variant": _string(choices=POLAR_VARIANTS),
    "use_dynamic_stall": _boolean,
    "ds_Tf": _number(0.0, lo_open=True),
    "ds_Tv": _number(0.0, lo_open=True),
    "ds_Ta": _number(0.0, lo_open=True),
    "ds_Kv": _number(0.0),
    "ds_Knc": _number(0.0),
    "use_dmst": _boolean,
    "use_dynamic_inflow": _boolean,
    "tau_rev": _number(0.0, lo_open=True),
    "a_fix": _number(0.0, 1.0, hi_open=True),
    "use_tip_loss": _boolean,
    "tip_loss_multiplier": _number(0.0),
    "tip_loss_floor_override": _number(0.0, 1.0),
    "e_osw": _number(0.0, 1.0, lo_open=True),
    "ind_drag_scale": _number(0.0),
    "cd_add": _number(0.0),
    "cm_scale": _number(0.0),
    "c_scale_override": _number(0.0),
    "use_flow_curvature": _boolean,
    # mechanical model
    "balance": _enum_int((0, 1, 2)),
    "bias_deg": _number(),
    # stops / pivot
    "win_deg": _number(0.0, 180.0, lo_open=True),
    "wstop": _number(0.0, lo_open=True),
    "cb": _number(0.0),
    "kc": _number(0.0),
    "mu_c": _number(0.0),
    "r_bearing": _number(0.0),
    "prescribe_pitch": _const_false,
    # numerical integration / initial conditions / environment
    "dt": _number(0.0, 1.0, lo_open=True),
    "T_max_s": _number(0.0, 3600.0, lo_open=True),
    "stride": _number(1, 100_000, integer=True),
    "n_rev_fixed": _number(1, 1_000_000, integer=True),
    "w0_frac": _number(0.0, 10.0, lo_open=True),
    "psi0_deg": _number(),
    "seed": _number(0, 2**32 - 1, integer=True),
    "turb_I": _number(0.0, 10.0),
    "turb_L": _number(0.0, lo_open=True),
    "turb_model": _string(choices=("dryden", "vonkarman")),
    "gust_g": _number(0.0, 10.0),
    "gust_t0": _number(0.0),
    "gust_tg": _number(0.0),
    # load policy and drivetrain
    "load_policy": _string(choices=("quadratic_k_load",)),
    "k_load": _number(0.0),
    "drivetrain_efficiency": _number(0.0, 1.0, lo_open=True),
}

_TOP_KEYS = {
    "schema_version", "status", "instructions", "frozen_model",
    "experimental_inputs", "acceptance", "provenance", "operational_limits",
}
_EXPERIMENTAL_KEYS = {"wind_speed", "air_density", "efficiency_policy"}
_ACCEPTANCE_KEYS = {
    "mean_rel_cp_max", "rmse_cp_max", "mean_rel_rpm_max", "abs_bias_cp_max",
    "coverage_min", "min_repeats_per_condition", "scenario_band",
}
_BAND_KEYS = {
    "available", "cp_half_width", "statistic", "provenance",
    "condition_dependent", "scalar_approximation_justification", "reason",
}
_PROVENANCE_KEYS = {
    "geometry_id", "geometry_sha256", "polar_hashes", "frozen_at_utc",
    "frozen_by", "code_commit", "stamp_schema_version", "notes",
}


@dataclass(frozen=True)
class FrozenContext:
    """Validated frozen configuration plus the resolved engine parameters."""

    settings: dict[str, Any]
    status: str
    is_frozen: bool
    geometry: dict[str, Any]
    geometry_sha256: str
    model_params: dict[str, Any]
    acceptance: dict[str, Any]
    scenario_band: dict[str, Any]
    efficiency_policy: str
    drivetrain_efficiency: float
    polar_dir: str
    polar_variant: str
    polar_source: str
    operational_limits: dict[str, Any]
    effective_config: dict[str, Any]
    effective_config_sha256: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _obj_sha256(obj: Any) -> str:
    return hashlib.sha256(_canonical_json(obj).encode()).hexdigest()


def load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SettingsError(f"{path}: expected a JSON object")
    return data


def _check_keys(section: str, obj: Any, allowed: set[str], required: set[str]):
    if not isinstance(obj, dict):
        raise SettingsError(f"{section}: expected an object")
    unknown = set(obj) - allowed
    if unknown:
        raise SettingsError(f"{section}: unknown key(s) {sorted(unknown)}")
    missing = required - set(obj)
    if missing:
        raise SettingsError(f"{section}: missing required key(s) {sorted(missing)}")


def _validate_geometry(geo: dict[str, Any], path: Path) -> str:
    missing = [k for k in ("geometry_id", *_GEO_MAP) if k not in geo]
    if missing:
        raise SettingsError(f"geometry {path}: missing {missing}")
    if not isinstance(geo["geometry_id"], str) or not geo["geometry_id"].strip():
        raise SettingsError(f"geometry {path}: geometry_id must be a non-empty string")
    for src in _GEO_MAP:
        value = geo[src]
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(float(value)):
            raise SettingsError(f"geometry {path}: {src} must be a finite number")
    for src in ("R_m", "c_m", "H_m", "mb_kg", "J_hub_kgm2"):
        if float(geo[src]) <= 0.0:
            raise SettingsError(f"geometry {path}: {src} must be positive")
    for src in ("N", "n_arm"):
        if not float(geo[src]).is_integer() or int(geo[src]) < 0:
            raise SettingsError(f"geometry {path}: {src} must be a non-negative integer")
    if int(geo["N"]) < 1:
        raise SettingsError(f"geometry {path}: N must be >= 1")
    for src in ("ar", "sp", "arm_d_m", "arm_cd", "mc_kg"):
        if float(geo[src]) < 0.0:
            raise SettingsError(f"geometry {path}: {src} must be non-negative")
    return _sha256(path)


def _resolve_polar_dir(polar_dir: str) -> Path:
    p = Path(polar_dir)
    if not p.is_absolute():
        p = _ROOT / "sharp_vawt" / p
    return p.resolve()


def _validate_model(section: dict[str, Any]):
    _check_keys("frozen_model", section, set(_MODEL_FIELDS), set(_MODEL_FIELDS))
    model: dict[str, Any] = {}
    for name, validator in _MODEL_FIELDS.items():
        model[name] = validator(name, section[name])
    if (model["gust_g"] > 0.0) != (model["gust_tg"] > 0.0):
        raise SettingsError(
            "frozen_model: gust_g and gust_tg must both be positive or both zero")
    if model["gust_tg"] > 0.0 and model["gust_t0"] < 0.0:
        raise SettingsError("frozen_model: gust_t0 must be non-negative")
    return model


def _validate_experimental(section: dict[str, Any]) -> dict[str, Any]:
    _check_keys("experimental_inputs", section, _EXPERIMENTAL_KEYS, _EXPERIMENTAL_KEYS)
    if section["wind_speed"] != "measurement_row":
        raise SettingsError(
            "experimental_inputs.wind_speed: only 'measurement_row' is supported; "
            "wind speed is a per-measurement input, not a frozen constant")
    if section["air_density"] != "measurement_row":
        raise SettingsError(
            "experimental_inputs.air_density: only 'measurement_row' is supported; "
            "air density is a per-measurement input")
    if section["efficiency_policy"] not in ("row_assumption", "frozen_model"):
        raise SettingsError(
            "experimental_inputs.efficiency_policy: expected 'row_assumption' or "
            f"'frozen_model', got {section['efficiency_policy']!r}")
    return dict(section)


def _validate_scenario_band(band: Any) -> dict[str, Any]:
    _check_keys("acceptance.scenario_band", band, _BAND_KEYS, {"available"})
    available = band["available"]
    if not isinstance(available, bool):
        raise SettingsError("acceptance.scenario_band.available: expected true/false")
    out = {
        "available": available,
        "cp_half_width": None,
        "statistic": None,
        "provenance": None,
        "condition_dependent": False,
        "scalar_approximation_justification": None,
        "reason": None,
    }
    if not available:
        reason = band.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise SettingsError(
                "acceptance.scenario_band: an unavailable band requires a non-empty 'reason'")
        if band.get("cp_half_width") is not None:
            raise SettingsError(
                "acceptance.scenario_band: cp_half_width must be null when available=false")
        out["reason"] = reason
        return out

    width = band.get("cp_half_width")
    if isinstance(width, bool) or not isinstance(width, (int, float)) \
            or not math.isfinite(float(width)) or float(width) <= 0.0:
        raise SettingsError(
            "acceptance.scenario_band.cp_half_width: must be a finite number > 0 "
            "(it is a half-width in Cp units)")
    for key in ("statistic", "provenance"):
        value = band.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SettingsError(
                f"acceptance.scenario_band.{key}: required when available=true")
    condition_dependent = band.get("condition_dependent", False)
    if not isinstance(condition_dependent, bool):
        raise SettingsError("acceptance.scenario_band.condition_dependent: expected true/false")
    justification = band.get("scalar_approximation_justification")
    if condition_dependent and (not isinstance(justification, str) or not justification.strip()):
            raise SettingsError(
                "acceptance.scenario_band: a condition-dependent band needs "
                "'scalar_approximation_justification' before a scalar half-width "
                "may be used for acceptance")
    out.update({
        "cp_half_width": float(width),
        "statistic": band["statistic"],
        "provenance": band["provenance"],
        "condition_dependent": condition_dependent,
        "scalar_approximation_justification": justification,
    })
    return out


def _validate_acceptance(section: dict[str, Any]) -> dict[str, Any]:
    _check_keys("acceptance", section, _ACCEPTANCE_KEYS, _ACCEPTANCE_KEYS)
    maxes = {
        "mean_rel_cp_max", "rmse_cp_max", "mean_rel_rpm_max", "abs_bias_cp_max",
    }
    out: dict[str, Any] = {}
    for key in maxes:
        value = section[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(float(value)) or float(value) <= 0.0:
            raise SettingsError(f"acceptance.{key}: must be a finite number > 0")
        out[key] = float(value)
    coverage = section["coverage_min"]
    if isinstance(coverage, bool) or not isinstance(coverage, (int, float)) \
            or not math.isfinite(float(coverage)) or not 0.0 <= float(coverage) <= 1.0:
        raise SettingsError("acceptance.coverage_min: must lie in [0, 1]")
    out["coverage_min"] = float(coverage)
    repeats = section["min_repeats_per_condition"]
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
        raise SettingsError("acceptance.min_repeats_per_condition: must be an integer >= 1")
    out["min_repeats_per_condition"] = repeats
    out["scenario_band"] = _validate_scenario_band(section["scenario_band"])
    return out


def _validate_provenance(section: Any, geo: dict[str, Any],
                         geometry_sha256: str, polar_dir: str) -> dict[str, Any]:
    _check_keys("provenance", section, _PROVENANCE_KEYS,
                _PROVENANCE_KEYS - {"notes"})
    if section["geometry_id"] != geo["geometry_id"]:
        raise SettingsError(
            "provenance.geometry_id does not match the geometry file "
            f"({section['geometry_id']!r} != {geo['geometry_id']!r})")
    if section["geometry_sha256"] != geometry_sha256:
        raise SettingsError(
            "provenance.geometry_sha256 does not match the geometry file")
    if section["stamp_schema_version"] != "2":
        raise SettingsError("provenance.stamp_schema_version: expected '2'")
    if not isinstance(section["frozen_by"], str) or not section["frozen_by"].strip():
        raise SettingsError("provenance.frozen_by: must be a non-empty string")
    if not isinstance(section["code_commit"], str) \
            or not _COMMIT.match(section["code_commit"]):
        raise SettingsError(
            "provenance.code_commit: expected a 7-40 character lowercase hex commit hash")
    try:
        frozen_at = datetime.fromisoformat(section["frozen_at_utc"])
    except (AttributeError, TypeError, ValueError) as exc:
        raise SettingsError(
            "provenance.frozen_at_utc: expected an ISO 8601 timestamp") from exc
    if frozen_at.tzinfo is None:
        raise SettingsError("provenance.frozen_at_utc: must include a timezone")
    if not isinstance(section["notes"], (str, type(None))):
        raise SettingsError("provenance.notes: expected a string or null")

    declared = section["polar_hashes"]
    if not isinstance(declared, dict) or not declared:
        raise SettingsError("provenance.polar_hashes: expected a non-empty object")
    resolved = _resolve_polar_dir(polar_dir)
    expected = {
        p.relative_to(_ROOT).as_posix(): _sha256(p)
        for p in sorted(resolved.glob("*.csv"))
    }
    if not expected:
        raise SettingsError(f"no polar CSV files found in {resolved}")
    for key, value in declared.items():
        if not isinstance(key, str) or not isinstance(value, str) or not _HEX64.match(value):
            raise SettingsError(
                "provenance.polar_hashes: each entry must map a relative path to a "
                "64-character lowercase hex digest")
    if set(declared) != set(expected):
        raise SettingsError(
            "provenance.polar_hashes does not match the declared polar directory; "
            f"missing={sorted(set(expected) - set(declared))}, "
            f"extra={sorted(set(declared) - set(expected))}")
    bad = sorted(k for k in expected if declared[k] != expected[k])
    if bad:
        raise SettingsError(
            f"provenance.polar_hashes mismatch for {bad}; the polar tables changed "
            "after the settings file was frozen")
    return dict(section)


def _validate_operational_limits(section: Any) -> dict[str, Any]:
    if section is None:
        return {}
    _check_keys("operational_limits", section,
                {"cut_in_mps", "cut_out_mps"}, {"cut_in_mps", "cut_out_mps"})
    cut_in = section["cut_in_mps"]
    cut_out = section["cut_out_mps"]
    for key, value in (("cut_in_mps", cut_in), ("cut_out_mps", cut_out)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(float(value)) or float(value) < 0.0:
            raise SettingsError(f"operational_limits.{key}: must be a finite number >= 0")
    if not float(cut_in) < float(cut_out):
        raise SettingsError("operational_limits: cut_in_mps must be < cut_out_mps")
    return {"cut_in_mps": float(cut_in), "cut_out_mps": float(cut_out)}


def _build_model_params(model: dict[str, Any], geo: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {dst: geo[src] for src, dst in _GEO_MAP.items()}
    for key, value in model.items():
        if key in ("T_max_s", "drivetrain_efficiency", "load_policy"):
            continue
        params[key] = value
    params["T_max"] = model["T_max_s"]
    params["N"] = int(params["N"])
    params["n_arm"] = int(params["n_arm"])
    return params


def resolve_settings(settings: dict[str, Any], geometry_path: str | Path) -> FrozenContext:
    """Validate the complete frozen-settings schema and build engine parameters.

    Raises :class:`SettingsError` for any missing, unknown, contradictory or
    unverifiable entry.  There is no fallback to dataclass defaults.
    """
    _check_keys("settings", settings, _TOP_KEYS,
                {"schema_version", "status", "frozen_model",
                 "experimental_inputs", "acceptance", "provenance"})
    if isinstance(settings["schema_version"], bool) \
            or not isinstance(settings["schema_version"], int) \
            or settings["schema_version"] != SETTINGS_SCHEMA_VERSION:
        raise SettingsError(
            f"settings.schema_version: expected {SETTINGS_SCHEMA_VERSION}, "
            f"got {settings['schema_version']!r}")
    status = settings["status"]
    if not isinstance(status, str) or not status.strip():
        raise SettingsError("settings.status: expected a non-empty string")

    geometry_path = Path(geometry_path).resolve()
    geo = load_json(str(geometry_path))
    geometry_sha256 = _validate_geometry(geo, geometry_path)

    model = _validate_model(settings["frozen_model"])
    experimental = _validate_experimental(settings["experimental_inputs"])
    acceptance = _validate_acceptance(settings["acceptance"])
    _validate_provenance(
        settings["provenance"], geo, geometry_sha256, model["polar_dir"])
    limits = _validate_operational_limits(settings.get("operational_limits"))

    resolved_polar = _resolve_polar_dir(model["polar_dir"])
    pdb = PolarDatabase(model["polar_dir"], variant=model["polar_variant"])
    if Path(pdb.polar_dir).resolve() != resolved_polar:
        raise SettingsError(
            "declared polar_dir was not the directory actually loaded by PolarDatabase")
    if pdb.variant != model["polar_variant"]:
        raise SettingsError("declared polar_variant was not the variant actually used")
    if not pdb.source.startswith("csv:"):
        raise SettingsError(
            "declared polar source fell back to the analytic surrogate; refusing to "
            "treat this comparison as using the frozen polar tables")

    model_params = _build_model_params(model, geo)
    effective_config = {
        "engine_params": model_params,
        "drivetrain_efficiency": model["drivetrain_efficiency"],
        "efficiency_policy": experimental["efficiency_policy"],
        "load_policy": model["load_policy"],
        "operational_limits": limits,
    }
    return FrozenContext(
        settings=settings,
        status=status,
        is_frozen=status == "FROZEN",
        geometry=geo,
        geometry_sha256=geometry_sha256,
        model_params=model_params,
        acceptance=acceptance,
        scenario_band=acceptance["scenario_band"],
        efficiency_policy=experimental["efficiency_policy"],
        drivetrain_efficiency=model["drivetrain_efficiency"],
        polar_dir=model["polar_dir"],
        polar_variant=model["polar_variant"],
        polar_source=pdb.source,
        operational_limits=limits,
        effective_config=effective_config,
        effective_config_sha256=_obj_sha256(effective_config),
    )


def _finite_float(value: Any, name: str) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} is not numeric: {value!r}") from exc
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return x


def _run(params: dict[str, Any]) -> dict[str, Any]:
    res = create_sim_from_params(params).run()
    if not math.isfinite(res["cp"]) or not math.isfinite(res["rpm"]):
        raise RuntimeError("non-finite model output")
    return res


def predict_row(row: dict[str, Any], ctx: FrozenContext) -> dict[str, Any]:
    geo = ctx.geometry
    U = _finite_float(row["wind_speed_mps"], "wind_speed_mps")
    rho = _finite_float(row["air_density_kgm3"], "air_density_kgm3")
    if U <= 0.0:
        raise ValueError("wind_speed_mps must be positive")
    if rho <= 0.0:
        raise ValueError("air_density_kgm3 must be positive")
    R = float(geo["R_m"])
    H = float(geo["H_m"])
    area = 2.0 * R * H

    row_eta = _finite_float(
        row["drivetrain_efficiency_assumption"], "drivetrain_efficiency_assumption")
    if not 0.0 < row_eta <= 1.0:
        raise ValueError("drivetrain_efficiency_assumption must lie in (0, 1]")
    if ctx.efficiency_policy == "frozen_model":
        eta = ctx.drivetrain_efficiency
        eta_source = "frozen_model"
    else:
        eta = row_eta
        eta_source = "row_assumption"

    # Wind speed and air density are per-measurement experimental inputs.
    base = dict(ctx.model_params, U=U, rho=rho)

    # Primary: free-running prediction (RPM is predicted, not prescribed).
    free = _run(dict(base, free=True))
    p_shaft = free["cp"] * 0.5 * rho * area * U ** 3
    p_elec = p_shaft * eta

    # Diagnostic: prescribed RPM equal to the measurement.
    tsr_meas = _finite_float(row["tsr"], "tsr")
    if tsr_meas <= 0.0:
        raise ValueError("tsr must be positive")
    fixed = _run(dict(base, free=False, tsr=tsr_meas))
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
        "drivetrain_efficiency_used": eta,
        "drivetrain_efficiency_source": eta_source,
    }


def evaluate_criteria(rows: list[dict[str, Any]], ctx: FrozenContext,
                      provenance: str) -> tuple[str, dict[str, Any], list[str]]:
    """Apply the pre-registered acceptance criteria to resolved frozen settings."""
    accepted = [r for r in rows if r["accepted"] and r.get("pred") and not r.get("error")]
    blockers: list[str] = []
    acc = ctx.acceptance
    band = ctx.scenario_band

    if provenance != "measured":
        blockers.append("data provenance is not 'measured' (synthetic tooling run)")
    if not ctx.is_frozen:
        blockers.append(
            f"frozen settings status is {ctx.status!r}, not exactly 'FROZEN'")
    if not band["available"]:
        blockers.append(
            "model scenario band unavailable: " + str(band.get("reason") or "no reason declared"))

    if not accepted:
        return "not_yet_available", {
            "n_evaluated": 0,
            "coverage": None,
            "coverage_status": "unavailable" if not band["available"] else "not_evaluated",
            "scenario_band": band,
            "thresholds": acc,
        }, blockers + ["no accepted rows with successful predictions"]

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

    if band["available"]:
        half_width = float(band["cp_half_width"])
        covered = sum(1 for m, p in zip(cps_m, cps_p) if abs(m - p) <= half_width)
        coverage: float | None = covered / len(accepted)
        coverage_status = "available"
    else:
        coverage = None
        coverage_status = "unavailable"

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
        "mean_rel_cp": mean_rel_cp <= acc["mean_rel_cp_max"],
        "rmse_cp": rmse_cp <= acc["rmse_cp_max"],
        "mean_rel_rpm": mean_rel_rpm <= acc["mean_rel_rpm_max"],
        "abs_bias_cp": abs(bias_cp) <= acc["abs_bias_cp_max"],
        "coverage": coverage is not None and coverage >= acc["coverage_min"],
        "torque_sign": torque_sign_ok,
        "min_repeats": min_repeats >= acc["min_repeats_per_condition"],
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
        "coverage": coverage,
        "coverage_status": coverage_status,
        "scenario_band": band,
        "criteria": criteria,
        "thresholds": acc,
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

    try:
        settings = load_json(args.settings)
        ctx = resolve_settings(settings, args.geometry)
    except (SettingsError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    data_path = Path(args.data)
    with open(data_path, newline="", encoding="utf-8") as fh:
        raw_rows = list(csv.DictReader(fh))

    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        try:
            row: dict[str, Any] = {
                "run_id": raw.get("run_id"),
                "wind_speed_mps": _finite_float(raw["wind_speed_mps"], "wind_speed_mps"),
                "rpm": _finite_float(raw["rpm"], "rpm"),
                "cp": _finite_float(raw["cp"], "cp"),
                "tsr": _finite_float(raw["tsr"], "tsr"),
                "load_ohms": _finite_float(raw["load_ohms"], "load_ohms"),
                "torque_used_Nm": _finite_float(raw["torque_used_Nm"], "torque_used_Nm"),
                "torque_source": raw.get("torque_source", "unknown"),
                "drivetrain_efficiency_assumption": _finite_float(
                    raw["drivetrain_efficiency_assumption"],
                    "drivetrain_efficiency_assumption"),
                "air_density_kgm3": _finite_float(
                    raw["air_density_kgm3"], "air_density_kgm3"),
                "accepted": (raw.get("accepted", "false").strip().lower() == "true"),
                "exclusion_reason": raw.get("exclusion_reason", ""),
            }
        except (KeyError, ValueError) as exc:
            print(f"ERROR: malformed row {raw.get('run_id', '?')}: {exc}", file=sys.stderr)
            return 2
        eta = row["drivetrain_efficiency_assumption"]
        if not 0.0 < eta <= 1.0:
            print(
                f"ERROR: row {row['run_id']}: drivetrain_efficiency_assumption "
                f"must lie in (0, 1], got {eta}",
                file=sys.stderr)
            return 2
        if row["accepted"]:
            try:
                row["pred"] = predict_row(row, ctx)
            except Exception as exc:  # noqa: BLE001 - keep the row visible; never silently drop
                row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)

    status, metrics, blockers = evaluate_criteria(rows, ctx, args.provenance)

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
        "geometry_sha256": ctx.geometry_sha256,
        "settings_file": str(Path(args.settings).resolve()),
        "settings_sha256": _sha256(Path(args.settings)),
        "frozen_settings": {
            "schema_version": settings["schema_version"],
            "status": ctx.status,
            "geometry_id": ctx.geometry["geometry_id"],
            "polar_dir": ctx.polar_dir,
            "polar_variant": ctx.polar_variant,
            "polar_source": ctx.polar_source,
            "operational_limits": ctx.operational_limits,
        },
        "effective_model_config": ctx.effective_config,
        "effective_model_config_sha256": ctx.effective_config_sha256,
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
                       script_version="1.1.0",
                       n=len(rows),
                       extra_files=[str(Path(args.geometry).resolve()),
                                    str(Path(args.settings).resolve())],
                       extra_data={"provenance": args.provenance,
                                   "status": status,
                                   "effective_model_config_sha256":
                                       ctx.effective_config_sha256})
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
