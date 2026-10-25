"""Synthetic-data tests for the prototype import/compare tooling.

No measured data exist. These tests prove the tooling rejects malformed data,
retains excluded rows, never silently infers a measured torque, and can never
label synthetic data as validation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import import_prototype_data as imp
from scripts.compare_prototype import (
    SettingsError,
    evaluate_criteria,
    predict_row,
    resolve_settings,
)

GEOMETRY = {
    "geometry_id": "TEST",
    "R_m": 0.60, "c_m": 0.14, "H_m": 0.40, "N": 3,
    "ar": 0.50, "sp": 0.25, "arm_d_m": 0.0, "n_arm": 2, "arm_cd": 1.0,
    "mb_kg": 0.010, "xbcg_over_c": 0.20, "mc_kg": 0.002, "dcw": 0.30,
    "J_hub_kgm2": 0.02,
}

HEADER = [
    "run_id", "date_utc", "operator", "rotor_id", "geometry_id",
    "wind_speed_mps", "wind_speed_uncertainty_mps", "rpm", "rpm_uncertainty",
    "electrical_power_W", "electrical_power_uncertainty_W", "load_ohms",
    "generator_model", "drivetrain_efficiency_assumption",
    "torque_Nm", "torque_uncertainty_Nm",
    "air_density_kgm3", "temperature_C", "pressure_hPa", "humidity_percent",
    "notes", "exclusion_reason",
]


def _row(**over):
    base = {
        "run_id": "R001", "date_utc": "2026-11-01T10:00:00Z", "operator": "AB",
        "rotor_id": "ROTOR-1", "geometry_id": "TEST",
        "wind_speed_mps": "8.0", "wind_speed_uncertainty_mps": "0.2",
        "rpm": "250.0", "rpm_uncertainty": "1.0",
        "electrical_power_W": "30.0", "electrical_power_uncertainty_W": "1.0",
        "load_ohms": "20.0", "generator_model": "GEN-1",
        "drivetrain_efficiency_assumption": "0.9",
        "torque_Nm": "", "torque_uncertainty_Nm": "",
        "air_density_kgm3": "1.225", "temperature_C": "15.0",
        "pressure_hPa": "1013.0", "humidity_percent": "50.0",
        "notes": "", "exclusion_reason": "",
    }
    base.update(over)
    return base


def _write_csv(path: Path, rows, header=HEADER):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_formats(tmp_path: Path):
    geo = tmp_path / "geometry_TEST.json"
    geo.write_text(json.dumps(GEOMETRY), encoding="utf-8")
    return geo


def _polar_hashes() -> dict[str, str]:
    polar_dir = ROOT / "sharp_vawt" / "airfoil_polars" / "naca0012"
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(polar_dir.glob("*.csv"))
    }


def _make_settings(
    geometry_path: Path,
    *,
    status: str = "FROZEN",
    model: dict | None = None,
    experimental: dict | None = None,
    acceptance: dict | None = None,
    provenance: dict | None = None,
    operational_limits: dict | None = None,
) -> dict:
    """A complete, valid frozen-settings object for synthetic tooling tests."""
    frozen_model = {
        "polar_dir": "airfoil_polars/naca0012",
        "polar_variant": "neuralfoil",
        "use_dynamic_stall": True,
        "ds_Tf": 3.0, "ds_Tv": 6.0, "ds_Ta": 0.1,
        "ds_Kv": 0.5, "ds_Knc": 1.0,
        "use_dmst": True, "use_dynamic_inflow": True,
        "tau_rev": 0.1, "a_fix": 0.2,
        "use_tip_loss": True, "tip_loss_multiplier": 1.0,
        "tip_loss_floor_override": 0.0,
        "e_osw": 0.9, "ind_drag_scale": 1.0,
        "cd_add": 0.002, "cm_scale": 1.0, "c_scale_override": 0.0,
        "use_flow_curvature": True,
        "balance": 0, "bias_deg": 0.0,
        "win_deg": 45.0, "wstop": 300.0,
        "cb": 2e-5, "kc": 0.0, "mu_c": 3e-4, "r_bearing": 0.002,
        "prescribe_pitch": False,
        "dt": 2e-4, "T_max_s": 20.0, "stride": 5, "n_rev_fixed": 16,
        "w0_frac": 0.9, "psi0_deg": 0.0, "seed": 0,
        "turb_I": 0.0, "turb_L": 30.0, "turb_model": "dryden",
        "gust_g": 0.0, "gust_t0": 0.0, "gust_tg": 0.0,
        "load_policy": "quadratic_k_load", "k_load": 0.0025,
        "drivetrain_efficiency": 0.9,
    }
    exp = {
        "wind_speed": "measurement_row",
        "air_density": "measurement_row",
        "efficiency_policy": "row_assumption",
    }
    acc = {
        "mean_rel_cp_max": 0.15,
        "rmse_cp_max": 0.03,
        "mean_rel_rpm_max": 0.10,
        "abs_bias_cp_max": 0.02,
        "coverage_min": 0.70,
        "min_repeats_per_condition": 3,
        "scenario_band": {
            "available": True,
            "cp_half_width": 0.02,
            "statistic": "pre-registered half-width of the declared model scenario range",
            "provenance": "synthetic test fixture; not an experimental uncertainty",
            "condition_dependent": False,
            "scalar_approximation_justification": None,
            "reason": None,
        },
    }
    prov = {
        "geometry_id": GEOMETRY["geometry_id"],
        "geometry_sha256": hashlib.sha256(geometry_path.read_bytes()).hexdigest(),
        "polar_hashes": _polar_hashes(),
        "frozen_at_utc": "2026-10-24T00:00:00+00:00",
        "frozen_by": "tests",
        "code_commit": "0" * 40,
        "stamp_schema_version": "2",
        "notes": "synthetic test fixture",
    }
    if model:
        frozen_model.update(model)
    if experimental:
        exp.update(experimental)
    if acceptance:
        acc.update(acceptance)
    if provenance:
        prov.update(provenance)
    return {
        "schema_version": 1,
        "status": status,
        "instructions": "synthetic test fixture",
        "frozen_model": frozen_model,
        "experimental_inputs": exp,
        "acceptance": acc,
        "provenance": prov,
        "operational_limits": operational_limits,
    }


def _resolved(tmp_path: Path | None = None, **kwargs):
    if tmp_path is None:
        import tempfile as _tf
        tmp_path = Path(_tf.mkdtemp())
    geo = _write_formats(tmp_path)
    return resolve_settings(_make_settings(geo, **kwargs), geo), geo


def test_import_valid_rows_infers_and_keeps_exclusions(tmp_path):
    geo = _write_formats(tmp_path)
    raw = tmp_path / "raw.csv"
    rows = [
        _row(run_id="R001"),
        _row(run_id="R002", exclusion_reason="wind direction drift"),
        _row(run_id="R003", torque_Nm="1.1", torque_uncertainty_Nm="0.05"),
    ]
    _write_csv(raw, rows)
    out = tmp_path / "processed.csv"
    assert imp.main(["--input", str(raw), "--geometry", str(geo),
                     "--out", str(out)]) == 0
    with open(out, newline="", encoding="utf-8") as fh:
        got = list(csv.DictReader(fh))
    assert len(got) == 3
    by_id = {r["run_id"]: r for r in got}
    assert by_id["R001"]["torque_source"] == "inferred"
    assert by_id["R003"]["torque_source"] == "measured"
    assert float(by_id["R003"]["torque_used_Nm"]) == pytest.approx(1.1)
    assert by_id["R001"]["accepted"] == "true"
    assert by_id["R002"]["accepted"] == "false"
    assert by_id["R002"]["exclusion_reason"] == "wind direction drift"
    # First-order propagation: CP = P/(0.5 rho A U^3)
    q = float(by_id["R001"]["cp"])
    expected = (30.0 / 0.9) / (0.5 * 1.225 * (2 * 0.6 * 0.4) * 8.0 ** 3)
    assert q == pytest.approx(expected, rel=1e-6)
    summary = json.loads(Path(str(out) + ".summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "import_only_not_validation"
    assert summary["n_excluded"] == 1


def test_import_rejects_missing_column(tmp_path):
    geo = _write_formats(tmp_path)
    raw = tmp_path / "raw.csv"
    header = [h for h in HEADER if h != "rpm"]
    _write_csv(raw, [_row()], header=header)
    with pytest.raises(imp.SchemaError, match="missing required column"):
        imp.main(["--input", str(raw), "--geometry", str(geo),
                  "--out", str(tmp_path / "out.csv")])


def test_import_rejects_duplicate_run_id(tmp_path):
    geo = _write_formats(tmp_path)
    raw = tmp_path / "raw.csv"
    _write_csv(raw, [_row(run_id="X"), _row(run_id="X")])
    with pytest.raises(imp.SchemaError, match="duplicate run_id"):
        imp.main(["--input", str(raw), "--geometry", str(geo),
                  "--out", str(tmp_path / "out.csv")])


def test_efficiency_is_a_numeric_schema_field():
    """The efficiency assumption is numeric, not duplicated text validation."""
    assert "drivetrain_efficiency_assumption" in imp.REQUIRED_NUMERIC
    assert "drivetrain_efficiency_assumption" not in imp.REQUIRED_TEXT


@pytest.mark.parametrize("value", ["", "abc", "nan", "inf", "0", "-0.2", "1.5"])
def test_import_rejects_invalid_efficiency(tmp_path, value):
    geo = _write_formats(tmp_path)
    raw = tmp_path / "raw.csv"
    _write_csv(raw, [_row(drivetrain_efficiency_assumption=value)])
    with pytest.raises(imp.SchemaError, match="efficiency"):
        imp.main(["--input", str(raw), "--geometry", str(geo),
                  "--out", str(tmp_path / "out.csv")])


def test_import_accepts_valid_efficiency_and_derives_shaft_power(tmp_path):
    geo = _write_formats(tmp_path)
    raw = tmp_path / "raw.csv"
    _write_csv(raw, [_row(drivetrain_efficiency_assumption="0.5")])
    out = tmp_path / "out.csv"
    assert imp.main(["--input", str(raw), "--geometry", str(geo),
                     "--out", str(out)]) == 0
    with open(out, newline="", encoding="utf-8") as fh:
        row = next(csv.DictReader(fh))
    # 30 W electrical at eta = 0.5 -> 60 W shaft.
    assert float(row["shaft_power_W"]) == pytest.approx(60.0)


def test_import_rejects_measured_torque_without_uncertainty(tmp_path):
    geo = _write_formats(tmp_path)
    raw = tmp_path / "raw.csv"
    _write_csv(raw, [_row(torque_Nm="1.2", torque_uncertainty_Nm="")])
    with pytest.raises(imp.SchemaError, match="torque_uncertainty"):
        imp.main(["--input", str(raw), "--geometry", str(geo),
                  "--out", str(tmp_path / "out.csv")])


def _criterion_rows(pred_cp=0.30, pred_rpm=250.0, measured_cp=0.30,
                    measured_rpm=250.0, repeat=3):
    rows = []
    for i in range(repeat):
        rows.append({
            "run_id": f"R{i}", "accepted": True,
            "wind_speed_mps": 8.0, "load_ohms": 20.0,
            "cp": measured_cp, "rpm": measured_rpm, "torque_used_Nm": 1.0,
            "pred": {"pred_cp": pred_cp, "pred_rpm": pred_rpm,
                     "pred_shaft_power_W": 1.0, "model_steady": True},
        })
    return rows


def test_resolve_settings_rejects_unknown_keys(tmp_path):
    _ctx, geo = _resolved(tmp_path)
    bad = dict(_make_settings(geo))
    bad["frozen_model"]["nonexistent_setting"] = 1
    with pytest.raises(SettingsError, match="unknown key"):
        resolve_settings(bad, geo)


def test_resolve_settings_rejects_missing_required_model_field(tmp_path):
    _ctx, geo = _resolved(tmp_path)
    bad = dict(_make_settings(geo))
    bad["frozen_model"].pop("drivetrain_efficiency")
    with pytest.raises(SettingsError, match="drivetrain_efficiency"):
        resolve_settings(bad, geo)


def test_resolve_settings_rejects_invalid_efficiency_range(tmp_path):
    _ctx, geo = _resolved(tmp_path)
    bad = dict(_make_settings(geo))
    bad["frozen_model"]["drivetrain_efficiency"] = 1.5
    with pytest.raises(SettingsError, match="drivetrain_efficiency"):
        resolve_settings(bad, geo)
    bad = dict(_make_settings(geo))
    bad["frozen_model"]["drivetrain_efficiency"] = 0.0
    with pytest.raises(SettingsError, match="drivetrain_efficiency"):
        resolve_settings(bad, geo)


def test_resolve_settings_rejects_frozen_wind_speed(tmp_path):
    _ctx, geo = _resolved(tmp_path)
    bad = dict(_make_settings(geo))
    bad["experimental_inputs"]["wind_speed"] = "frozen_8mps"
    with pytest.raises(SettingsError, match="measurement_row"):
        resolve_settings(bad, geo)


def test_resolve_settings_rejects_condition_dependent_band_without_justification(tmp_path):
    _ctx, geo = _resolved(tmp_path)
    bad = dict(_make_settings(geo))
    bad["acceptance"]["scenario_band"] = {
        "available": True, "cp_half_width": 0.02,
        "statistic": "pre-registered half-width",
        "provenance": "synthetic fixture",
        "condition_dependent": True,
        "scalar_approximation_justification": None,
        "reason": None,
    }
    with pytest.raises(SettingsError, match="justification"):
        resolve_settings(bad, geo)


def test_resolve_settings_accepts_valid_band(tmp_path):
    _ctx, _geo = _resolved(tmp_path)
    assert _ctx.scenario_band["available"] is True
    assert _ctx.scenario_band["cp_half_width"] == 0.02


def test_evaluate_criteria_pass_on_measured_perfect_agreement(tmp_path):
    ctx, _geo = _resolved(tmp_path)
    status, metrics, blockers = evaluate_criteria(
        _criterion_rows(), ctx, "measured")
    assert status == "validation_criteria_met", blockers
    assert metrics["criteria"]["min_repeats"]
    assert metrics["coverage"] == 1.0


def test_synthetic_data_never_validates_even_with_perfect_agreement(tmp_path):
    ctx, _geo = _resolved(tmp_path)
    status, _metrics, blockers = evaluate_criteria(
        _criterion_rows(), ctx, "synthetic")
    assert status == "not_yet_available"
    assert any("synthetic" in b for b in blockers)


def test_unfrozen_settings_never_validate(tmp_path):
    ctx, _geo = _resolved(tmp_path, status="TEMPLATE")
    status, _metrics, blockers = evaluate_criteria(
        _criterion_rows(), ctx, "measured")
    assert status == "not_yet_available"
    assert any("FROZEN" in b for b in blockers)


def test_failed_criterion_is_discrepancy_not_validation(tmp_path):
    ctx, _geo = _resolved(tmp_path)
    status, metrics, blockers = evaluate_criteria(
        _criterion_rows(pred_cp=0.40), ctx, "measured")
    assert status == "discrepancy"
    assert not blockers
    assert not metrics["criteria"]["mean_rel_cp"]


def test_too_few_repeats_fails(tmp_path):
    ctx, _geo = _resolved(tmp_path)
    status, metrics, _ = evaluate_criteria(
        _criterion_rows(repeat=1), ctx, "measured")
    assert status == "discrepancy"
    assert not metrics["criteria"]["min_repeats"]


def test_unavailable_band_blocks_acceptance_but_allows_descriptive_comparison(tmp_path):
    ctx, _geo = _resolved(
        tmp_path,
        acceptance={"scenario_band": {
            "available": False, "cp_half_width": None, "statistic": None,
            "provenance": None, "condition_dependent": False,
            "scalar_approximation_justification": None,
            "reason": "no band pre-registered before data were examined"},
        })
    status, metrics, blockers = evaluate_criteria(
        _criterion_rows(), ctx, "measured")
    assert status == "not_yet_available", blockers
    assert any("band unavailable" in b.lower() for b in blockers)
    assert metrics["coverage_status"] == "unavailable"
    assert metrics["coverage"] is None


def test_zero_and_negative_band_are_invalid(tmp_path):
    _ctx, geo = _resolved(tmp_path)
    for width in (0.0, -0.01):
        bad = dict(_make_settings(geo))
        bad["acceptance"]["scenario_band"] = {
            "available": True, "cp_half_width": width,
            "statistic": "half-width", "provenance": "fixture",
            "condition_dependent": False,
            "scalar_approximation_justification": None, "reason": None,
        }
        with pytest.raises(SettingsError, match="cp_half_width"):
            resolve_settings(bad, geo)


def test_nan_band_is_rejected(tmp_path):
    _ctx, geo = _resolved(tmp_path)
    bad = dict(_make_settings(geo))
    bad["acceptance"]["scenario_band"] = {
        "available": True, "cp_half_width": float("nan"),
        "statistic": "half-width", "provenance": "fixture",
        "condition_dependent": False,
        "scalar_approximation_justification": None, "reason": None,
    }
    with pytest.raises(SettingsError, match="cp_half_width"):
        resolve_settings(bad, geo)


def test_empty_reason_when_band_unavailable_is_rejected(tmp_path):
    _ctx, geo = _resolved(tmp_path)
    bad = dict(_make_settings(geo))
    bad["acceptance"]["scenario_band"] = {
        "available": False, "cp_half_width": None, "statistic": None,
        "provenance": None, "condition_dependent": False,
        "scalar_approximation_justification": None, "reason": "",
    }
    with pytest.raises(SettingsError, match="reason"):
        resolve_settings(bad, geo)


def test_compare_cli_keeps_every_row_and_never_validates_synthetic(tmp_path):
    ctx, geo = _resolved(tmp_path)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps(ctx.settings), encoding="utf-8")
    processed = tmp_path / "processed.csv"
    fields = ["run_id", "wind_speed_mps", "rpm", "cp", "tsr", "load_ohms",
              "torque_used_Nm", "torque_source", "drivetrain_efficiency_assumption",
              "air_density_kgm3", "accepted", "exclusion_reason"]
    rows = [
        {"run_id": "A", "wind_speed_mps": 8.0, "rpm": 250.0, "cp": 0.30,
         "tsr": 1.96, "load_ohms": 20.0, "torque_used_Nm": 1.0,
         "torque_source": "inferred", "drivetrain_efficiency_assumption": 0.9,
         "air_density_kgm3": 1.225, "accepted": "true", "exclusion_reason": ""},
        {"run_id": "B", "wind_speed_mps": 8.0, "rpm": 250.0, "cp": 0.30,
         "tsr": 1.96, "load_ohms": 20.0, "torque_used_Nm": 1.0,
         "torque_source": "measured", "drivetrain_efficiency_assumption": 0.9,
         "air_density_kgm3": 1.225, "accepted": "false",
         "exclusion_reason": "pre-registered"},
    ]
    with open(processed, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    out = tmp_path / "comparison.json"
    result = subprocess.run(  # noqa: PLW1510 - returncode checked explicitly below
        [sys.executable, str(ROOT / "scripts" / "compare_prototype.py"),
         "--data", str(processed), "--geometry", str(geo),
         "--settings", str(settings_path), "--out", str(out),
         "--provenance", "synthetic"],
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] != "validation_criteria_met"
    assert data["status"] == "not_yet_available"
    assert len(data["rows"]) == 2
    assert data["rows"][1]["accepted"] is False
    assert "effective_model_config" in data
    assert "effective_model_config_sha256" in data


def test_predict_row_uses_efficiency_policy_row_assumption():
    ctx, _geo = _resolved()
    assert ctx.efficiency_policy == "row_assumption"
    pred = predict_row(
        {"wind_speed_mps": 8.0, "tsr": 1.96,
         "drivetrain_efficiency_assumption": 0.5,
         "air_density_kgm3": 1.225}, ctx)
    assert pred["drivetrain_efficiency_used"] == pytest.approx(0.5)
    assert pred["drivetrain_efficiency_source"] == "row_assumption"
