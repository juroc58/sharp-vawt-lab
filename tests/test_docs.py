"""Tests that every file in docs/ is referenced somewhere in the repo,
except for explicitly allowed files."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# Files explicitly allowed to exist without being referenced
ALLOWED_FILES = {"derivation.md", "figure_manifest.json"}


def _collect_referenced_names() -> set[str]:
    """Collect all filenames referenced from README, CHANGELOG, scripts, and tests."""
    referenced = set()
    search_roots = [
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / "scripts",
        ROOT / "tests",
    ]
    for root in search_roots:
        if root.is_file():
            text = root.read_text(encoding="utf-8")
        elif root.is_dir():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in {".py", ".md", ".toml", ".yml", ".yaml"}:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                    for m in re.finditer(r'["\']([^"\']*\.(?:png|png|json|md|svg|jpg|jpeg))["\']', text):
                        referenced.add(m.group(1))
                    for m in re.finditer(r"`([^`]*\.(?:png|png|json|md|svg|jpg|jpeg))`", text):
                        referenced.add(m.group(1))
                    for m in re.finditer(r'\bdocs/([\w\-]+\.(?:png|png|json|md|svg|jpg|jpeg))\b', text):
                        referenced.add(m.group(1))
        else:
            continue
    # Always search single-file roots (README.md, CHANGELOG.md) directly.
    for single_file in (ROOT / "README.md", ROOT / "CHANGELOG.md"):
        text = single_file.read_text(encoding="utf-8")
        for m in re.finditer(r'["\']([^"\']*\.(?:png|png|json|md|svg|jpg|jpeg))["\']', text):
            referenced.add(m.group(1))
        for m in re.finditer(r"`([^`]*\.(?:png|png|json|md|svg|jpg|jpeg))`", text):
            referenced.add(m.group(1))
        for m in re.finditer(r'\bdocs/([\w\-]+\.(?:png|png|json|md|svg|jpg|jpeg))\b', text):
            referenced.add(m.group(1))
    return referenced


def test_all_docs_files_referenced():
    """Every file in docs/ must be referenced somewhere, except explicitly allowed ones."""
    referenced = _collect_referenced_names()
    docs_files = {p.name for p in DOCS.iterdir() if p.is_file()}
    missing = docs_files - referenced - {"figure_manifest.json", "derivation.md"}
    assert not missing, f"Docs files not referenced anywhere: {sorted(missing)}"


def test_no_unreferenced_docs():
    """Same as test_all_docs_files_referenced but as a separate test for clarity."""
    referenced = _collect_referenced_names()
    docs_files = {p.name for p in DOCS.iterdir() if p.is_file()}
    unreferenced = docs_files - referenced - {"figure_manifest.json", "derivation.md"}
    assert not unreferenced, f"Unreferenced docs files: {sorted(unreferenced)}"
