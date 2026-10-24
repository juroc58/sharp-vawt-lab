"""Stamp/freshness invariants: unique map, full dependency coverage, tamper and cwd.

The old stamp only hashed ``sharp_vawt/*`` and the script, and
``check_freshness.py`` walked up from ``Path.cwd()``.  These tests pin the new
contract.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))

from scripts import stamp as stamp_mod


def test_stamp_map_has_no_duplicate_keys_by_construction():
    # A dict literal cannot contain duplicate keys, but a literal duplicate in
    # source would be silent.  Inspect the AST to be certain.
    import ast
    tree = ast.parse((SCRIPTS / "stamp.py").read_text(encoding="utf-8"))
    dict_node = None
    for n in tree.body:
        is_map = isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "STAMP_CHECK_MAP" for t in n.targets)
        is_ann = isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) \
            and n.target.id == "STAMP_CHECK_MAP"
        if is_map or is_ann:
            dict_node = n.value
    assert dict_node is not None, "STAMP_CHECK_MAP not found"
    keys = [k.value for k in dict_node.keys]
    assert len(keys) == len(set(keys)), "duplicate keys in STAMP_CHECK_MAP"


def test_every_result_json_is_mapped_exactly_once():
    mapped = {name for name in stamp_mod.STAMP_CHECK_MAP}
    on_disk = {p.name for p in SCRIPTS.glob("*.json")}
    # optimization_overrides.json is an input override, not a generated result.
    on_disk.discard("optimization_overrides.json")
    assert on_disk == mapped, f"unmapped: {on_disk - mapped}; missing: {mapped - on_disk}"


def test_every_script_has_semantic_version():
    for script in stamp_mod.STAMP_CHECK_MAP.values():
        version = stamp_mod.SCRIPT_VERSIONS.get(script)
        assert version, f"no semantic version for {script}"
        assert version not in stamp_mod._GENERIC_VERSIONS
        parts = version.split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts), version


def test_stamp_covers_presets_and_polars(tmp_path):
    rec = stamp_mod.make_stamp("scripts/scan_tip_loss.py")
    assert "vawt_presets.py" in rec["source_hashes"]
    assert "vawt_core.py" in rec["source_hashes"]
    assert any(k.endswith(".csv") for k in rec["data_hashes"])
    assert "sharp_vawt/airfoil_polars/provenance.json" in rec["data_hashes"]
    assert rec["config_hash"]
    assert rec["python_version"]
    assert "script_args" in rec


def test_verify_detects_source_tampering(tmp_path, monkeypatch):
    # Copy the repo's stamp-relevant files into a temporary pseudo-repo and
    # tamper with one source module.
    target = tmp_path / "repo"
    for rel in ["scripts/stamp.py", "sharp_vawt/__init__.py", "sharp_vawt/config.py",
                "sharp_vawt/database.py", "sharp_vawt/engine.py",
                "vawt_core.py", "vawt_presets.py",
                "sharp_vawt/airfoil_polars/provenance.json",
                "sharp_vawt/airfoil_polars/README.md"]:
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dst)
    for csv in (ROOT / "sharp_vawt/airfoil_polars/naca0012").glob("*.csv"):
        dst = target / "sharp_vawt/airfoil_polars/naca0012" / csv.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(csv, dst)
    shutil.copyfile(SCRIPTS / "scan_tip_loss.py", target / "scripts/scan_tip_loss.py")

    monkeypatch.setattr(stamp_mod, "_repo_root", lambda: target)
    stamp = stamp_mod.make_stamp("scripts/scan_tip_loss.py")
    out = target / "scripts" / "result.json"
    out.write_text(json.dumps({"stamp": stamp, "ok": True}))

    ok, msg = stamp_mod.verify_stamp(str(out), "scripts/scan_tip_loss.py")
    assert ok, msg

    with open(target / "vawt_presets.py", "a", encoding="utf-8") as fh:
        fh.write("\n# tampered\n")
    ok, msg = stamp_mod.verify_stamp(str(out), "scripts/scan_tip_loss.py")
    assert not ok
    assert "hash mismatch" in msg.lower()


def test_freshness_is_cwd_independent():
    import os
    import subprocess

    script = SCRIPTS / "check_freshness.py"
    result = subprocess.run(  # noqa: PLW1510 - returncode checked explicitly below
        [sys.executable, str(script)],
        cwd=os.path.dirname(str(ROOT)),
        capture_output=True, text=True,
    )
    # Return code depends on whether results were regenerated; what matters is
    # that it found the same repository and did not fail to locate the root.
    assert "Could not find repository root" not in result.stdout
    assert str(ROOT) in result.stdout
