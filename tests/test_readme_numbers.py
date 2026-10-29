import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CHANGELOG = ROOT / "CHANGELOG.md"
README = ROOT / "README.md"
SCRIPTS = ROOT / "scripts"


def test_readme_in_sync():
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "build_readme.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, (
        "README.md drifted from scripts/*.json. "
        "Run: python3 scripts/build_readme.py\n" + r.stdout + r.stderr
    )


def test_aep_results_json_not_claimed_deleted_in_changelog():
    """Documentation must not claim aep_results.json was deleted: it remains
    a supported scale-up AEP artifact produced by compute_aep.py."""
    changelog = CHANGELOG.read_text(encoding="utf-8")
    # The file must not be described as deleted/removed/stale in the changelog.
    assert "aep_results.json" in changelog, "changelog should mention aep_results.json"
    assert "aep_results.json deleted" not in changelog.lower(), (
        "changelog must not state aep_results.json was deleted"
    )
    assert "stale aep_results.json" not in changelog.lower(), (
        "changelog must not call aep_results.json stale"
    )


def test_aep_results_json_has_producer_and_scaleup_geometry():
    """aep_results.json must carry its producer script and scale-up geometry."""
    data = json.loads((SCRIPTS / "aep_results.json").read_text(encoding="utf-8"))
    stamp = data["stamp"]
    assert stamp["script"] == "scripts/compute_aep.py", (
        f"unexpected producer: {stamp['script']}"
    )
    geo = data["geometry"]
    assert geo["R"] > 2.0, f"expected scale-up R > 2.0 m, got {geo['R']}"
    assert geo["H"] > 3.0, f"expected scale-up H > 3.0 m, got {geo['H']}"


def test_counter_rotating_independent_baseline_is_twice_single():
    """two_independent_rotors must equal exactly 2 x single_rotor_baseline
    within the same counter-rotating workflow JSON."""
    data = json.loads(
        (SCRIPTS / "aep_counter_rotating.json").read_text(encoding="utf-8")
    )
    single = data["single_rotor_baseline"]["aep_kWh"]
    two_indep = data["two_independent_rotors"]["aep_kWh"]
    assert two_indep == pytest.approx(2.0 * single, rel=1e-9), (
        f"two_independent_rotors ({two_indep}) != 2 x single ({single})"
    )


def test_counter_rotating_pair_gain_uses_independent_baseline():
    """Pair gain over two independent rotors must be computed from that same
    baseline, not from an external AEP workflow."""
    data = json.loads(
        (SCRIPTS / "aep_counter_rotating.json").read_text(encoding="utf-8")
    )
    total = data["counter_rotating"]["total"]["aep_kWh"]
    two_indep = data["two_independent_rotors"]["aep_kWh"]
    gain = data["counter_rotating"]["vs_two_independent_rotors_improvement_percent"]
    expected_gain = (total / two_indep - 1.0) * 100.0
    assert gain == pytest.approx(expected_gain, rel=1e-6), (
        f"pair gain {gain}% != (total/two_indep - 1)*100 = {expected_gain}%"
    )


def test_readme_counter_rotating_table_matches_json():
    """The generated README counter-rotating table must reflect the JSON's
    own single-rotor baseline, not an externally imported value."""
    data = json.loads(
        (SCRIPTS / "aep_counter_rotating.json").read_text(encoding="utf-8")
    )
    text = README.read_text(encoding="utf-8")
    single = data["single_rotor_baseline"]["aep_kWh"]
    two_indep = data["two_independent_rotors"]["aep_kWh"]
    total = data["counter_rotating"]["total"]["aep_kWh"]
    gain = data["counter_rotating"]["vs_two_independent_rotors_improvement_percent"]
    assert f"{single:,.0f} kWh/yr" in text, (
        f"README missing single-rotor baseline {single:,.0f}"
    )
    assert f"{two_indep:,.0f} kWh/yr" in text, (
        f"README missing two-independent value {two_indep:,.0f}"
    )
    assert f"{total:,.0f} kWh/yr" in text, (
        f"README missing counter-rotating total {total:,.0f}"
    )
    assert f"{gain:+.1f} %" in text, (
        f"README missing pair gain {gain:+.1f}%"
    )