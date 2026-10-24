#!/usr/bin/env python3
"""Check freshness of all result JSONs by verifying their provenance stamps.

The repository root is derived from this file's location, not from the current
working directory, so the check behaves identically when run from the repo root,
from ``scripts/``, or from an external directory.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
sys.path.insert(0, str(_REPO_ROOT))

from scripts.stamp import list_stale_results


def main() -> int:
    print(f"Repository root: {_REPO_ROOT}")
    print(f"Checking freshness of result JSONs in {_SCRIPTS_DIR}...")
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
    print("Run the generating script for each stale file.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
