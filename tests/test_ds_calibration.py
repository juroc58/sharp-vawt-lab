"""Synthetic-data tests for scripts/calibrate_dynamic_stall.py.

No measured data exist. These tests prove the tooling fits on calibration
cases, evaluates held-out cases, never changes the default DS constants, and
never marks synthetic data as calibrated.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import calibrate_dynamic_stall as cal

DEFAULT = {"ds_Tf": 3.0, "ds_Tv": 6.0, "ds_Ta": 0.1, "ds_Kv": 0.5, "ds_Knc": 1.0}


def _case(cid: str, n: int, params: dict, seed: int, omega: float = 20.0,
          alpha0: float = 5.0) -> list[dict]:
    """Synthesize one oscillating-alpha trace with the model itself."""
    rng = np.random.default_rng(seed)
    runner = cal.ModelRunner()
    pts = []
    t = 0.0
    dt = 0.02
    for i in range(n):
        a = alpha0 + 12.0 * math.sin(omega * t) + rng.normal(0, 0.15)
        p = {"time": t, "alpha": a, "cl": float("nan"), "cd": float("nan"),
                 "Re": 2.0e5, "chord": 0.14, "W": 8.0}
        t += dt
        pts.append(p)
    preds = runner.simulate(pts, {**DEFAULT, **params})
    for p, (Cl, Cd, Cm) in zip(pts, preds):
        p["cl"] = Cl + rng.normal(0, 0.01)
        p["cd"] = max(0.0, Cd + rng.normal(0, 0.005))
        p["cm"] = Cm + rng.normal(0, 0.002)
    return pts


def _write_cases(tmp_path: Path, cases: dict[str, list[dict]]) -> Path:
    p = tmp_path / "dataset.csv"
    cols = ["case_id", "time_s", "alpha_deg", "cl", "cd", "cm", "Re", "chord_m", "W_mps"]
    with open(p, "w", newline="", encoding="utf-8") as fh:
        import csv
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for cid, pts in cases.items():
            for pt in pts:
                w.writerow({"case_id": cid,
                            "time_s": pt["time"],
                            "alpha_deg": pt["alpha"],
                            "cl": pt["cl"], "cd": pt["cd"], "cm": pt["cm"],
                            "Re": pt["Re"], "chord_m": pt["chord"], "W_mps": pt["W"]})
    return p


def _run_cli(tmp_path: Path, csv_path: Path, out_path: Path, extra: list[str] | None = None,
             provenance: str = "synthetic") -> dict:
    cmd = [sys.executable, str(ROOT / "scripts" / "calibrate_dynamic_stall.py"),
           "--data", str(csv_path), "--out", str(out_path),
           "--provenance", provenance] + (extra or [])
    res = subprocess.run(  # noqa: PLW1510 - returncode checked explicitly below
        cmd, capture_output=True, text=True, timeout=600
    )
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(out_path.read_text(encoding="utf-8"))


def test_default_constants_unchanged():
    import sharp_vawt.config as cfg
    expected = {"ds_Tf": 3.0, "ds_Tv": 6.0, "ds_Ta": 0.1, "ds_Kv": 0.5, "ds_Knc": 1.0}
    for p, v in expected.items():
        # These DS constants live as SimConfig/AeroConfig fields; read from config source.
        cfg_val = getattr(cfg.SimConfig, p, None) or getattr(cfg.AeroConfig, p, None)
        assert cfg_val == v, f"{p}: config default {cfg_val} != documented {v}"


def test_calibration_recovers_known_params_on_heldout(tmp_path):
    true = {"ds_Tf": 4.5, "ds_Kv": 0.8, "ds_Knc": 1.2}
    cases = {
        "A": _case("A", 400, true, 1),
        "B": _case("B", 400, true, 2),
        "C": _case("C", 300, true, 3),   # held out
        "D": _case("D", 300, true, 4),   # held out
    }
    csv_path = _write_cases(tmp_path, cases)
    out_path = tmp_path / "report.json"
    report = _run_cli(tmp_path, csv_path, out_path,
                      extra=["--calibration-cases", "A", "B",
                             "--heldout-cases", "C", "D",
                             "--fit", "ds_Tf", "ds_Kv", "ds_Knc"])
    assert report["status"] == "not_calibrated", report  # synthetic provenance
    assert report["calibration_claim_allowed"] is False
    assert set(report["calibration_cases"]) == {"A", "B"}
    assert set(report["heldout_cases"]) == {"C", "D"}
    # Fitted values should move toward the truth (noise means not exact).
    for p, v in true.items():
        assert abs(report["fitted_parameters"][p] - v) < 1.5, (p, report["fitted_parameters"])
    # Candidate should beat defaults on held out.
    assert report["heldout_rmse_candidate"]["cl"] <= report["heldout_rmse_defaults"]["cl"] + 1e-9


def test_synthetic_data_never_calibrated_even_perfect_fit(tmp_path):
    cases = {"A": _case("A", 500, DEFAULT, 5), "B": _case("B", 500, DEFAULT, 6),
             "C": _case("C", 400, DEFAULT, 7), "D": _case("D", 400, DEFAULT, 8)}
    csv_path = _write_cases(tmp_path, cases)
    out_path = tmp_path / "report.json"
    report = _run_cli(tmp_path, csv_path, out_path,
                      extra=["--calibration-cases", "A", "B",
                             "--heldout-cases", "C", "D",
                             "--fit", "ds_Tf", "ds_Kv"])
    assert report["status"] == "not_calibrated"
    assert report["calibration_claim_allowed"] is False


def test_held_out_case_in_both_sets_rejected(tmp_path):
    cases = {"A": _case("A", 200, DEFAULT, 1), "B": _case("B", 200, DEFAULT, 2)}
    csv_path = _write_cases(tmp_path, cases)
    out_path = tmp_path / "report.json"
    cmd = [sys.executable, str(ROOT / "scripts" / "calibrate_dynamic_stall.py"),
           "--data", str(csv_path), "--out", str(out_path),
           "--provenance", "synthetic",
           "--calibration-cases", "A", "--heldout-cases", "A", "B",
           "--fit", "ds_Tf"]
    res = subprocess.run(  # noqa: PLW1510 - returncode checked explicitly below
        cmd, capture_output=True, text=True, timeout=300
    )
    assert res.returncode != 0


def test_minimum_held_out_cases_rejected(tmp_path):
    # Only one held-out case -> script must fail.
    cases = {"A": _case("A", 300, DEFAULT, 1), "B": _case("B", 300, DEFAULT, 2),
             "C": _case("C", 300, DEFAULT, 3)}
    csv_path = _write_cases(tmp_path, cases)
    out_path = tmp_path / "report.json"
    cmd = [sys.executable, str(ROOT / "scripts" / "calibrate_dynamic_stall.py"),
           "--data", str(csv_path), "--out", str(out_path),
           "--provenance", "synthetic",
           "--calibration-cases", "A", "--heldout-cases", "B",
           "--fit", "ds_Tf"]
    res = subprocess.run(  # noqa: PLW1510 - returncode checked explicitly below
        cmd, capture_output=True, text=True, timeout=300
    )
    assert res.returncode != 0


def test_unknown_fit_parameter_rejected(tmp_path):
    cases = {"A": _case("A", 300, DEFAULT, 1), "B": _case("B", 300, DEFAULT, 2),
             "C": _case("C", 300, DEFAULT, 3), "D": _case("D", 300, DEFAULT, 4)}
    csv_path = _write_cases(tmp_path, cases)
    out_path = tmp_path / "report.json"
    cmd = [sys.executable, str(ROOT / "scripts" / "calibrate_dynamic_stall.py"),
           "--data", str(csv_path), "--out", str(out_path),
           "--provenance", "synthetic", "--fit", "nonexistent_param"]
    res = subprocess.run(  # noqa: PLW1510 - returncode checked explicitly below
        cmd, capture_output=True, text=True, timeout=300
    )
    assert res.returncode != 0
