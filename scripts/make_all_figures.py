#!/usr/bin/env python3
"""
Regenerate every committed figure from the current result JSON / analysis code.

Design rules
------------
* No smoothing, filtering, hiding or manual alteration of data happens here or
  in the plot scripts this driver calls.
* Every figure is produced by a command run with the repository root as cwd, so
  the driver works from any working directory.
* A manifest (``docs/figure_manifest.json``) records, for each figure, the
  SHA-256 of the image and of every source JSON/module used.  ``check_figures``
  and the test suite use it to detect stale images.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
PY = sys.executable

# (output name, argv, source files)
FIGURES = [
    ("aep_small.png", ["scripts/plot_aep.py", "--json", "scripts/aep_small.json",
                       "--out", "docs/aep_small.png", "--type", "small"],
     ["scripts/aep_small.json"]),
    ("aep_scaleup.png", ["scripts/plot_aep.py", "--json", "scripts/aep_scaleup.json",
                         "--out", "docs/aep_scaleup.png", "--type", "scaleup"],
     ["scripts/aep_scaleup.json"]),
    ("aep_turbulent.png", ["scripts/plot_aep.py", "--json", "scripts/aep_turbulent.json",
                           "--out", "docs/aep_turbulent.png", "--type", "turbulent"],
     ["scripts/aep_turbulent.json"]),
    ("aep_counter_rotating.png", ["scripts/plot_aep.py", "--json", "scripts/aep_counter_rotating.json",
                                  "--out", "docs/aep_counter_rotating.png", "--type", "counter"],
     ["scripts/aep_counter_rotating.json"]),
    ("ham_curve.png", ["scripts/plot_ham_curve.py"], []),
    ("validation.png", ["scripts/plot_validation.py"], []),
    ("uncertainty.png", ["scripts/plot_uncertainty.py"], ["scripts/uncertainty_results.json"]),
    ("spearman.png", ["scripts/plot_spearman.py"], ["scripts/spearman_results.json"]),
    ("diag_qa.png", ["scripts/diag_qa.py", "--check"], []),
    ("diag_qa.png", ["scripts/diag_qa.py", "--out", "docs/diag_qa.png"], []),
    ("finite_span_ablation.png", ["scripts/finite_span_ablation.py"],
     ["scripts/finite_span_ablation.json"]),
    ("finite_span_validation.png", ["scripts/validate_finite_span.py"], []),
]

# Labels that must appear in the counter-rotating figure and manifest.
COUNTER_LABELS = ["SPECULATIVE SCENARIO", "NOT A VALIDATED ARRAY PREDICTION"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _output_path(argv: list[str]) -> Path | None:
    """Return the ``--out <path>`` argument if present, else None."""
    for i, a in enumerate(argv):
        if a == "--out" and i + 1 < len(argv):
            return ROOT / argv[i + 1]
    return None


def _run(argv) -> bool:
    """Run one figure command.

    Returns True if the figure was produced/refreshed.

    Exit codes: any non-zero exit is a hard failure (RuntimeError), including
    ``diag_qa.py --check``. A figure produced by a failing command is not
    accepted, so a failed check can never be hidden by a regenerated image.
    """
    out_path = _output_path(argv)
    mtime_before = out_path.stat().st_mtime if out_path and out_path.is_file() else None
    print(f"  $ {' '.join(argv)}")
    env = dict(os.environ)
    env.setdefault("MPLBACKEND", "Agg")
    result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True)  # noqa: PLW1510 - returncode handled manually below
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    mtime_after = out_path.stat().st_mtime if out_path and out_path.is_file() else None
    produced = mtime_after is not None and (mtime_before is None or mtime_after > mtime_before)

    if result.returncode != 0:
        if produced:
            raise RuntimeError(
                f"Figure command exited {result.returncode} but figure was produced: {' '.join(argv)}"
            )
        raise RuntimeError(
            f"Figure command failed and did not produce output "
            f"(exit {result.returncode}): {' '.join(argv)}"
        )
    return produced


def build_manifest() -> dict:
    figures = {}
    for name, argv, sources in FIGURES:
        out = DOCS / name
        if not out.is_file():
            raise RuntimeError(f"figure was not produced: {out}")
        figures[name] = {
            "sha256": _sha256(out),
            "bytes": out.stat().st_size,
            "sources": {rel: _sha256(ROOT / rel) for rel in sources},
        }
        if name == "aep_counter_rotating.png":
            figures[name]["labels"] = COUNTER_LABELS
    return {
        "schema": 1,
        "generated_utc": datetime.now(UTC).isoformat(),
        "figures": figures,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="*", default=None,
                    help="optional subset of output filenames")
    ap.add_argument("--no-manifest", action="store_true",
                    help="skip writing docs/figure_manifest.json")
    args = ap.parse_args(argv)

    selected = set(args.only) if args.only else None
    DOCS.mkdir(parents=True, exist_ok=True)
    print("Regenerating figures from current results...")
    for name, fig_argv, _sources in FIGURES:
        if selected and name not in selected:
            continue
        _run([PY] + fig_argv)

    if not args.no_manifest:
        manifest = build_manifest()
        path = DOCS / "figure_manifest.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())