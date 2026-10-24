"""Invariants that keep the single-physics refactor from silently regressing.

The historical failure mode was a duplicated kernel in ``vawt_core.py`` and
``sharp_vawt/config.py``.  Scripts imported one copy while tests exercised the
other.  These tests fail if a second implementation is reintroduced, or if the
two import paths stop returning bit-identical results.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_FILES = [
    ROOT / "sharp_vawt" / "__init__.py",
    ROOT / "sharp_vawt" / "config.py",
    ROOT / "sharp_vawt" / "database.py",
    ROOT / "sharp_vawt" / "engine.py",
]
PHYSICS_NAMES = {"_kernel", "CycloturbineSim", "create_sim_from_params"}
POLAR_NAMES = {"PolarDatabase"}


def _top_level_defs(path: Path) -> dict[str, list[int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, list[int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.setdefault(node.name, []).append(node.lineno)
    return out


@pytest.mark.parametrize("path", PACKAGE_FILES, ids=lambda p: p.name)
def test_no_duplicate_top_level_definitions(path):
    dups = {k: v for k, v in _top_level_defs(path).items() if len(v) > 1}
    assert not dups, f"{path.name} contains duplicate definitions: {dups}"


def test_exactly_one_kernel_and_simulation_class_in_package():
    owners: dict[str, list[str]] = {}
    for path in PACKAGE_FILES:
        for name in _top_level_defs(path):
            if name in PHYSICS_NAMES | POLAR_NAMES:
                owners.setdefault(name, []).append(path.name)
    for name in PHYSICS_NAMES:
        assert owners.get(name) == ["engine.py"], (
            f"{name} must be defined only in sharp_vawt/engine.py; found {owners.get(name)}"
        )
    assert owners.get("PolarDatabase") == ["database.py"], (
        f"PolarDatabase must be defined only in database.py; found {owners.get('PolarDatabase')}"
    )


def test_config_contains_no_physics_kernel_or_simulation_class():
    names = set(_top_level_defs(ROOT / "sharp_vawt" / "config.py"))
    assert not (names & PHYSICS_NAMES)
    assert "PolarDatabase" not in names


def test_vawt_core_is_a_thin_reexport():
    path = ROOT / "vawt_core.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    defs = [n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    assert defs == [], f"vawt_core.py must contain no definitions, found {defs}"
    imports = [n for n in tree.body if isinstance(n, ast.ImportFrom)]
    modules = {n.module for n in imports}
    assert "sharp_vawt.engine" in modules
    assert "sharp_vawt.config" in modules
    assert "sharp_vawt.database" in modules


def test_legacy_and_canonical_paths_are_bit_identical():
    from sharp_vawt import create_sim_from_params as canonical
    from vawt_core import create_sim_from_params as legacy
    from vawt_presets import PRESETS

    for name in ("sharp_baseline", "sharp_cppc", "scaleup"):
        params = dict(PRESETS[name])
        a = legacy(params).run()
        b = canonical(params).run()
        for key in ("cp", "cq", "tsr_eq", "rpm", "ct", "aoa_max",
                    "pitch_min", "pitch_max", "energy_balance"):
            assert a[key] == b[key], f"{name}.{key}: {a[key]!r} != {b[key]!r}"
        assert a["out"].shape == b["out"].shape
        assert (a["out"] == b["out"]).all()


def test_scripts_do_not_import_the_legacy_core():
    offenders = []
    for path in (ROOT / "scripts").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import vawt_core" in text or "from vawt_core" in text:
            offenders.append(path.name)
    assert not offenders, f"scripts must import sharp_vawt, not vawt_core: {offenders}"


def test_polar_data_exists_in_one_canonical_location():
    assert not (ROOT / "airfoil_polars").exists(), (
        "root airfoil_polars/ is a duplicate; data live in sharp_vawt/airfoil_polars/"
    )
    csvs = list((ROOT / "sharp_vawt" / "airfoil_polars").glob("naca0012/*.csv"))
    assert len(csvs) >= 4
