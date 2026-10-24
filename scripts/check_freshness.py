#!/usr/bin/env python3
"""
Check freshness of all result JSONs by verifying their stamps.

This script can be run from any working directory. It locates the repository
root by finding the .git directory, then validates all result JSONs against
their generating scripts.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Find repo root by looking for .git
def find_repo_root() -> Path:
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists():
            return parent
    raise RuntimeError("Could not find repository root (no .git directory found)")

_REPO_ROOT = find_repo_root()
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from scripts.stamp import STAMP_CHECK_MAP, verify_stamp, list_stale_results


def main() -> int:
    """Check all result JSONs for freshness. Exit 0 if all fresh, 1 if any stale."""
    print(f"Repository root: {_REPO_ROOT}")
    print(f"Checking freshness of result JSONs in {_REPO_ROOT / 'scripts'}...")
    print()

    stale = list_stale_results()

    if not stale:
        print("✓ All result JSONs are fresh.")
        return 0

    print(f"Found {len(stale)} stale result JSON(s):")
    for fpath, msg in stale:
        print(f"  ✗ {fpath}")
        print(f"    Reason: {msg}")
    print()
    print("To fix, run the generating script for each stale file.")
    return 1


if __name__ == "__main__":
    sys.exit(main())