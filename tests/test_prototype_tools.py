"""Synthetic-data tests for the prototype import/compare tooling.

No measured data exist. These tests prove the tooling rejects malformed data,
retains excluded rows, never silently infers a measured torque, and can never
label synthetic data as validation.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import import_prototype_data as imp
from scripts.compare_prototype import evaluate_criteria

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


def test_import_rejects_invalid_efficiency(tmp_path):
    geo = _write_formats(tmp_path)
    raw = tmp_path / "raw.csv"
    _write_csv(raw, [_row(drivetrain_efficiency_assumption="1.5")])
    with pytest.raises(imp.SchemaError, match="efficiency"):
        imp.main(["--input", str(raw), "--geometry", str(geo),
                  "--out", str(tmp_path / "out.csv")])


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


FROZEN = {"status": "FROZEN", "model_scenario_band_cp": 0.02}


def test_criteria_pass_on_measured_perfect_agreement():
    status, metrics, blockers = evaluate_criteria(
        _criterion_rows(), FROZEN, "measured")
    assert status == "validation_criteria_met", blockers
    assert metrics["criteria"]["min_repeats"]
    assert metrics["coverage"] == 1.0


def test_synthetic_data_never_validates_even_with_perfect_agreement():
    status, _metrics, blockers = evaluate_criteria(
        _criterion_rows(), FROZEN, "synthetic")
    assert status == "not_yet_available"
    assert any("synthetic" in b for b in blockers)


def test_unfrozen_settings_never_validate():
    status, _metrics, blockers = evaluate_criteria(
        _criterion_rows(), {"status": "TEMPLATE"}, "measured")
    assert status == "not_yet_available"
    assert any("FROZEN" in b for b in blockers)


def test_failed_criterion_is_discrepancy_not_validation():
    status, metrics, blockers = evaluate_criteria(
        _criterion_rows(pred_cp=0.40), FROZEN, "measured")
    assert status == "discrepancy"
    assert not blockers
    assert not metrics["criteria"]["mean_rel_cp"]


def test_too_few_repeats_fails():
    status, metrics, _ = evaluate_criteria(
        _criterion_rows(repeat=1), FROZEN, "measured")
    assert status == "discrepancy"
    assert not metrics["criteria"]["min_repeats"]


def test_compare_cli_keeps_every_row_and_never_validates_synthetic(tmp_path):
    geo = _write_formats(tmp_path)
    settings = dict(FROZEN, geometry_id="TEST", k_load=1e-5, T_max_s=1.5,
                    stride=20, use_dynamic_stall=False,
                    use_flow_curvature=False, use_tip_loss=False,
                    use_dmst=False, polar_variant="neuralfoil")
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
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
