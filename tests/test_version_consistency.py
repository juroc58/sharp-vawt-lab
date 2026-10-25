"""Version consistency across pyproject.toml, CITATION.cff, and CHANGELOG.md."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CITATION = ROOT / "CITATION.cff"
CHANGELOG = ROOT / "CHANGELOG.md"


def _pyproject_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', text, re.MULTILINE)
    assert m, f"version not found in {PYPROJECT}"
    return m.group(1)


def _citation_version() -> str:
    text = CITATION.read_text(encoding="utf-8")
    m = re.search(r'^version:\s*(\d+\.\d+\.\d+)', text, re.MULTILINE)
    assert m, f"version not found in {CITATION}"
    return m.group(1)


def _changelog_versions() -> list[str]:
    text = CHANGELOG.read_text(encoding="utf-8")
    return re.findall(r"^## \[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)


def test_version_consistency_across_files():
    """pyproject.toml, CITATION.cff, and the latest CHANGELOG entry must agree."""
    pv = _pyproject_version()
    cv = _citation_version()
    ch = _changelog_versions()
    assert pv == cv, f"pyproject {pv} != CITATION {cv}"
    assert ch, "no versioned entries in CHANGELOG.md"
    assert ch[0] == pv, f"latest CHANGELOG {ch[0]} != pyproject {pv}"


def test_changelog_has_unreleased_section():
    """CHANGELOG.md must have an [Unreleased] section."""
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "## [Unreleased]" in text, "CHANGELOG.md missing [Unreleased] section"


def test_pyproject_version_is_semantic():
    """pyproject.toml version must be a valid semantic version."""
    pv = _pyproject_version()
    parts = pv.split(".")
    assert len(parts) == 3, f"version {pv} must have 3 parts"
    assert all(p.isdigit() for p in parts), f"version {pv} parts must be digits"


def test_subprocess_full_rotor_tests_have_marker():
    """Any test using subprocess to run a full-rotor script must have
    the `slow` or `needs_jit` marker."""
    import ast

    test_files = [f for f in (ROOT / "tests").glob("test_*.py")
                  if f.name != "test_version_consistency.py"]
    required_markers = {"slow", "needs_jit"}
    missing = []

    for tf in test_files:
        source = tf.read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                # Collect markers on this function
                markers = set()
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Attribute):
                            markers.add(decorator.func.attr)
                        elif isinstance(decorator.func, ast.Name):
                            markers.add(decorator.func.id)
                    elif isinstance(decorator, ast.Attribute):
                        markers.add(decorator.attr)
                    elif isinstance(decorator, ast.Name):
                        markers.add(decorator.id)

                # Get function source text
                func_lines = lines[node.lineno - 1:node.end_lineno]
                func_text = "\n".join(func_lines)

                uses_subprocess = "subprocess" in func_text
                runs_rotor_script = any(
                    s in func_text for s in [
                        "scripts/diag_active_lift.py",
                        "scripts/compute_aep",
                        "scripts/optimize",
                        "scripts/validate",
                        "scripts/scan",
                    ]
                )

                if uses_subprocess and runs_rotor_script and not (markers & required_markers):
                    missing.append(f"{tf.name}::{node.name} (markers: {markers})")

    assert not missing, (
        f"Tests using subprocess + full-rotor scripts must have 'slow' or 'needs_jit' marker: {missing}"
    )
