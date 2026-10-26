"""Version consistency across pyproject.toml, CITATION.cff, and CHANGELOG.md."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CITATION = ROOT / "CITATION.cff"
CHANGELOG = ROOT / "CHANGELOG.md"
DERIVATION = ROOT / "docs" / "derivation.md"


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


def _migration_new_columns() -> list[str]:
    """Parse the Migration table in docs/derivation.md and return its 'new'
    column names."""
    text = DERIVATION.read_text(encoding="utf-8")
    m = re.search(
        r"## 14\. Migration.*?(?=\n## |\Z)", text, re.DOTALL
    )
    assert m, "Migration section not found in docs/derivation.md"
    section = m.group(0)
    new_cols = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if len(cells) >= 2:
            new_cols.append(cells[1])
    # Drop the header row ("New column").
    if new_cols and new_cols[0].lower() == "new column":
        new_cols = new_cols[1:]
    return new_cols


def test_migration_table_covers_all_out_cols():
    """Every column in engine.OUT_COLS must appear in the Migration table's
    'new' column."""
    from sharp_vawt.engine import OUT_COLS
    new_cols = _migration_new_columns()
    assert new_cols, "Migration table has no new columns"
    for col in OUT_COLS:
        assert col in new_cols, (
            f"OUT_COLS column {col!r} missing from Migration table new column: {new_cols}"
        )


def test_ci_no_jit_job_excludes_needs_jit():
    """The NUMBA_DISABLE_JIT test run must deselect needs_jit tests."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'NUMBA_DISABLE_JIT=1 python -m pytest tests/ -q -m "not slow and not needs_jit"' in ci


def test_needs_jit_marker_is_still_used():
    """At least one test must carry @pytest.mark.needs_jit.

    Guards against silently removing the marker, which would make the CI
    deselection meaningless.
    """
    import ast

    count = 0
    for tf in (ROOT / "tests").glob("test_*.py"):
        tree = ast.parse(tf.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if isinstance(dec, ast.Attribute) and dec.attr == "needs_jit":
                    count += 1
    assert count >= 1, "no @pytest.mark.needs_jit tests found"
