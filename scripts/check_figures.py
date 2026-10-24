#!/usr/bin/env python3
"""Verify that committed figures match their recorded sources and manifest."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
MANIFEST = DOCS / "figure_manifest.json"

REQUIRED = {
    "aep.png", "aep_scaleup.png", "aep_turbulent.png", "aep_counter_rotating.png",
    "ham_curve.png", "validation.png", "uncertainty.png", "spearman.png",
    "diag_qa.png", "finite_span_ablation.png", "finite_span_validation.png",
}


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check() -> list[str]:
    problems: list[str] = []
    if not MANIFEST.is_file():
        return [f"missing figure manifest: {MANIFEST}"]
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report unreadable manifest as a check failure
        return [f"unreadable figure manifest: {exc}"]

    figs = manifest.get("figures", {})
    missing = REQUIRED - set(figs)
    if missing:
        problems.append(f"manifest missing required figures: {sorted(missing)}")

    for name, rec in figs.items():
        path = DOCS / name
        if not path.is_file():
            problems.append(f"missing figure: {path}")
            continue
        actual = _sha256(path)
        if actual != rec.get("sha256"):
            problems.append(
                f"{name}: image hash differs from manifest "
                f"(stored {rec.get('sha256','?')[:12]}, actual {actual[:12]}); "
                f"re-run scripts/make_all_figures.py"
            )
        for rel, expected in rec.get("sources", {}).items():
            src = ROOT / rel
            if not src.is_file():
                problems.append(f"{name}: missing source {rel}")
            elif _sha256(src) != expected:
                problems.append(
                    f"{name}: source {rel} changed since the figure was made"
                )

    counter = figs.get("aep_counter_rotating.png", {})
    labels = set(counter.get("labels", []))
    if not {"SPECULATIVE SCENARIO", "NOT A VALIDATED ARRAY PREDICTION"} <= labels:
        problems.append("counter-rotating figure manifest lacks required speculative labels")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    problems = check()
    if problems:
        print("FIGURE CHECK FAILED:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    if not args.quiet:
        print(f"✓ All {len(REQUIRED)} required figures match their manifest and sources.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
