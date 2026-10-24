"""Figure freshness, manifest coverage, and speculative-label tests."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MANIFEST = DOCS / "figure_manifest.json"


def test_manifest_exists_and_covers_required_figures():
    assert MANIFEST.is_file(), "run scripts/make_all_figures.py"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest.get("schema") == 1
    figs = manifest.get("figures", {})
    from scripts.check_figures import REQUIRED
    missing = REQUIRED - set(figs)
    assert not missing, f"manifest missing: {sorted(missing)}"


def test_figures_match_manifest_and_sources():
    from scripts.check_figures import check
    problems = check()
    assert not problems, "\n".join(problems)


def test_figures_are_not_empty():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for name, rec in manifest["figures"].items():
        assert (DOCS / name).stat().st_size > 1000, f"{name} is suspiciously small"
        assert rec["bytes"] == (DOCS / name).stat().st_size


def test_counter_rotating_figure_is_labelled_speculative():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    labels = set(manifest["figures"]["aep_counter_rotating.png"].get("labels", []))
    assert {"SPECULATIVE SCENARIO", "NOT A VALIDATED ARRAY PREDICTION"} <= labels
    source = (ROOT / "scripts" / "plot_aep.py").read_text(encoding="utf-8")
    assert "SPECULATIVE SCENARIO" in source
    assert "NOT A VALIDATED ARRAY PREDICTION" in source


def test_manifest_is_cwd_independent():
    import os
    import subprocess
    import sys
    script = ROOT / "scripts" / "check_figures.py"
    result = subprocess.run(  # noqa: PLW1510 - returncode checked explicitly below
        [sys.executable, str(script)],
        cwd=os.path.dirname(str(ROOT)),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
