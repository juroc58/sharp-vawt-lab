#!/usr/bin/env python3
"""
Shared freshness-stamp helper for every result JSON in this repository.

A stamp records enough provenance for an independent reader to tell whether a
result still corresponds to the code and data that produced it:

* generating script path and a **per-script semantic version**,
* schema version of the stamp itself,
* UTC creation time, Python version and git commit (recorded, not hashed — a
  new commit must not invalidate every result),
* random seed and sample/run count where applicable,
* command-line arguments that affect the result (hashed),
* SHA-256 of every source module that can affect results
  (``sharp_vawt/*``, ``vawt_core.py``, ``vawt_presets.py``, the script itself),
* SHA-256 of every polar CSV and the polar provenance/README,
* SHA-256 of the UQ specification and of the configuration/preset module,
* any script-specific extra files/data.

Paths are always resolved relative to this file (``scripts/stamp.py``), never
``Path.cwd()``.  The freshness CLI therefore works from the repository root,
from ``scripts/``, or from any external directory.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import platform
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

STAMP_SCHEMA_VERSION = "2"

# Per-script semantic versions.  Bump the relevant entry whenever a change can
# move that script's output.  Generic placeholders such as "v1.0" are rejected.
SCRIPT_VERSIONS: dict[str, str] = {
    "scripts/check_branch_points.py": "2.0.0",
    "scripts/compute_aep.py": "2.0.0",
    "scripts/compute_aep_counter_rotating.py": "2.0.0",
    "scripts/compute_aep_rigid_fair.py": "2.0.0",
    "scripts/compute_aep_scaleup.py": "2.0.0",
    "scripts/compute_aep_turbulent.py": "2.0.0",
    "scripts/diag_aep_branches.py": "2.0.0",
    "scripts/finite_span_ablation.py": "3.0.0",
    "scripts/ham_finite_span_check.py": "2.0.0",
    "scripts/optimize_actuator.py": "2.0.0",
    "scripts/optimize_passive.py": "2.0.0",
    "scripts/optimize_scaleup.py": "2.0.0",
    "scripts/robust_reopt.py": "2.0.0",
    "scripts/scan_cm_scale.py": "2.0.0",
    "scripts/scan_tip_loss.py": "2.0.0",
    "scripts/spearman_sensitivity.py": "2.0.0",
    "scripts/uncertainty.py": "2.0.0",
    "scripts/import_prototype_data.py": "1.0.0",
    "scripts/compare_prototype.py": "1.1.0",
    "scripts/calibrate_dynamic_stall.py": "1.1.0",
    "scripts/validate_ds_off.py": "1.1.0",
}

_GENERIC_VERSIONS = {"", "v1.0", "1.0", "1.0.0", "v1"}


def _repo_root() -> Path:
    """Repository root, derived from this file — never from the cwd."""
    return Path(__file__).resolve().parent.parent


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _git_commit(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:  # noqa: BLE001 - git may be unavailable; graceful degradation
        return None


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _source_files(root: Path) -> list[str]:
    """Every source module that can change a simulation result."""
    fixed = [
        "sharp_vawt/__init__.py",
        "sharp_vawt/config.py",
        "sharp_vawt/database.py",
        "sharp_vawt/engine.py",
        "vawt_core.py",
        "vawt_presets.py",
    ]
    missing = [rel for rel in fixed if not (root / rel).is_file()]
    if missing:
        raise FileNotFoundError(f"Stamp: missing source file(s): {missing}")
    return fixed


def _data_files(root: Path) -> list[str]:
    polar_dir = root / "sharp_vawt" / "airfoil_polars"
    csvs = sorted(p.relative_to(root).as_posix()
                  for p in polar_dir.glob("**/*.csv"))
    if not csvs:
        raise FileNotFoundError(f"Stamp: no polar CSVs found under {polar_dir}")
    fixed = [
        "sharp_vawt/airfoil_polars/provenance.json",
        "sharp_vawt/airfoil_polars/README.md",
    ]
    missing = [rel for rel in fixed if not (root / rel).is_file()]
    if missing:
        raise FileNotFoundError(f"Stamp: missing polar metadata: {missing}")
    return csvs + fixed


def _hash_files(root: Path, rels: Iterable[str]) -> dict[str, str]:
    return {rel: _sha256_file(root / rel) for rel in rels}


def _resolve_version(script_path: str, version: str) -> str:
    """Return the per-script semantic version, rejecting generic placeholders."""
    if version and version not in _GENERIC_VERSIONS:
        return version
    mapped = SCRIPT_VERSIONS.get(script_path)
    if not mapped:
        raise ValueError(
            f"Stamp: no semantic version registered for {script_path!r}. "
            f"Add it to SCRIPT_VERSIONS in scripts/stamp.py."
        )
    return mapped


def _collect(
    script_path: str,
    version: str,
    extra_files: list[str] | None,
    extra_data: dict[str, Any] | None,
    script_args: list[str] | None,
    seed: int | None,
    n: int | None,
) -> dict[str, Any]:
    root = _repo_root()

    script_rel = Path(script_path).as_posix()
    script_file = root / script_rel
    if not script_file.is_file():
        raise FileNotFoundError(f"Stamp: missing script file {script_file}")

    src = _source_files(root)
    extra = [Path(p).as_posix() for p in (extra_files or [])]
    for rel in extra:
        if not (root / rel).is_file():
            raise FileNotFoundError(f"Stamp: missing extra file {root / rel}")

    data = _data_files(root)
    source_hashes = _hash_files(root, src + [script_rel] + extra)
    data_hashes = _hash_files(root, data)

    # UQ specification hash (only present for UQ scripts).
    uq_spec = (extra_data or {}).get("UQ_SPEC")
    uq_spec_hash = _sha256_bytes(_canonical_json(uq_spec).encode()) if uq_spec else None

    # Configuration/preset hash: frozen dataclasses + named machines.
    config_hash = _sha256_bytes(
        (root / "sharp_vawt/config.py").read_bytes()
         + (root / "vawt_presets.py").read_bytes()
    )

    payload = {
        "schema_version": STAMP_SCHEMA_VERSION,
        "script": script_rel,
        "script_version": _resolve_version(script_rel, version),
        "seed": seed,
        "n": n,
        "script_args": list(script_args or []),
        "extra_data": extra_data,
        "source_hashes": source_hashes,
        "data_hashes": data_hashes,
        "uq_spec_hash": uq_spec_hash,
        "config_hash": config_hash,
    }
    code_hash = _sha256_bytes(_canonical_json(payload).encode())
    return {**payload, "code_hash": code_hash}


def compute_code_hash(
    script_path: str,
    extra_files: list[str] | None = None,
    extra_data: dict[str, Any] | None = None,
    version: str = "",
    script_args: list[str] | None = None,
    seed: int | None = None,
    n: int | None = None,
) -> str:
    """Return the 64-char SHA-256 digest of all result-affecting inputs."""
    rec = _collect(script_path, version, extra_files, extra_data, script_args, seed, n)
    return rec["code_hash"]


def make_stamp(
    script_path: str,
    script_version: str = "",
    n: int | None = None,
    seed: int | None = None,
    extra_files: list[str] | None = None,
    extra_data: dict[str, Any] | None = None,
    script_args: list[str] | None = None,
) -> dict[str, Any]:
    """Build the provenance stamp embedded under the ``stamp`` key."""
    args = list(script_args) if script_args is not None else list(sys.argv[1:])
    rec = _collect(script_path, script_version, extra_files, extra_data, args, seed, n)
    stamp = {
        "schema_version": STAMP_SCHEMA_VERSION,
        "code_hash": rec["code_hash"],
        "script": rec["script"],
        "script_version": rec["script_version"],
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "python_version": platform.python_version(),
        "git_commit": _git_commit(_repo_root()),
        "seed": seed,
        "n": n,
        "script_args": args,
        "extra_files": extra_files,
        "extra_data": extra_data,
        "uq_spec_hash": rec["uq_spec_hash"],
        "config_hash": rec["config_hash"],
        "source_hashes": rec["source_hashes"],
        "data_hashes": rec["data_hashes"],
    }
    return stamp


def write_json_with_stamp(
    path: str,
    data: dict[str, Any],
    script: str,
    version: str = "",
    n: int | None = None,
    seed: int | None = None,
    extra_files: list[str] | None = None,
    extra_data: dict[str, Any] | None = None,
    script_args: list[str] | None = None,
) -> None:
    """Write ``data`` plus a provenance stamp to ``path``."""
    stamp = make_stamp(
        script_path=script,
        script_version=version,
        n=n,
        seed=seed,
        extra_files=extra_files,
        extra_data=extra_data,
        script_args=script_args,
    )
    output = {"stamp": stamp, **data}
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(path_obj, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)
        fh.write("\n")


def verify_stamp(json_path: str, expected_script: str) -> tuple[bool, str]:
    """Verify that a JSON's stamp is structurally complete and current."""
    json_path_obj = Path(json_path)
    try:
        with open(json_path_obj, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001 - report unreadable JSON as invalid stamp
        return False, f"Failed to read JSON: {exc}"

    if "stamp" not in data:
        return False, f"Missing 'stamp' field in {json_path_obj}"
    stamp = data["stamp"]

    required = [
        "schema_version", "code_hash", "script", "script_version", "created_utc",
        "python_version", "git_commit", "script_args", "source_hashes",
        "data_hashes", "config_hash",
    ]
    missing = [f for f in required if f not in stamp]
    if missing:
        return False, f"Stamp missing field(s) {missing} in {json_path_obj}"
    if stamp["schema_version"] != STAMP_SCHEMA_VERSION:
        return False, (
            f"Stamp schema {stamp['schema_version']} != {STAMP_SCHEMA_VERSION}; "
            f"regenerate {json_path_obj.name}"
        )
    if stamp["script"] != expected_script:
        return False, (
            f"Stamp script mismatch: expected {expected_script}, got {stamp['script']}"
        )

    # Ensure every *currently relevant* source/data file is covered.
    root = _repo_root()
    expected_sources = set(_source_files(root)) | {Path(expected_script).as_posix()}
    expected_sources |= {Path(p).as_posix() for p in (stamp.get("extra_files") or [])}
    provided_sources = set(stamp["source_hashes"])
    if expected_sources - provided_sources:
        return False, (
            f"Stamp omits source dependency/dependencies: "
            f"{sorted(expected_sources - provided_sources)}"
        )
    expected_data = set(_data_files(root))
    if expected_data - set(stamp["data_hashes"]):
        return False, (
            f"Stamp omits data dependency/dependencies: "
            f"{sorted(expected_data - set(stamp['data_hashes']))}"
        )

    try:
        rec = _collect(
            script_path=stamp["script"],
            version=stamp["script_version"],
            extra_files=stamp.get("extra_files"),
            extra_data=stamp.get("extra_data"),
            script_args=stamp.get("script_args"),
            seed=stamp.get("seed"),
            n=stamp.get("n"),
        )
    except Exception as exc:  # noqa: BLE001 - report hash-recompute failure as invalid stamp
        return False, f"Failed to recompute hash: {exc}"

    if stamp["code_hash"] != rec["code_hash"]:
        return False, (
            f"Code hash mismatch for {json_path_obj}: "
            f"stored={stamp['code_hash'][:12]}, current={rec['code_hash'][:12]}. "
            f"Re-run {stamp['script']} to regenerate."
        )
    return True, "OK"


# One entry per result JSON.  Keys are unique by construction; the test suite
# asserts this explicitly.
STAMP_CHECK_MAP: dict[str, str] = {
    "aep_counter_rotating.json": "scripts/compute_aep_counter_rotating.py",
    "aep_results.json": "scripts/compute_aep.py",
    "aep_rigid_fair.json": "scripts/compute_aep_rigid_fair.py",
    "aep_scaleup.json": "scripts/compute_aep_scaleup.py",
    "aep_turbulent.json": "scripts/compute_aep_turbulent.py",
    "branch_point_checks.json": "scripts/check_branch_points.py",
    "cm_scale_scan.json": "scripts/scan_cm_scale.py",
    "diag_aep_branches.json": "scripts/diag_aep_branches.py",
    "finite_span_ablation.json": "scripts/finite_span_ablation.py",
    "ham_finite_span_check.json": "scripts/ham_finite_span_check.py",
    "optimization_actuator.json": "scripts/optimize_actuator.py",
    "optimization_passive.json": "scripts/optimize_passive.py",
    "optimization_scaleup.json": "scripts/optimize_scaleup.py",
    "robust_optimization.json": "scripts/robust_reopt.py",
    "spearman_results.json": "scripts/spearman_sensitivity.py",
    "tip_loss_scan.json": "scripts/scan_tip_loss.py",
    "uncertainty_results.json": "scripts/uncertainty.py",
    "validate_ds_off.json": "scripts/validate_ds_off.py",
}


def list_stale_results() -> list[tuple[str, str]]:
    """Return ``(relative_json_path, reason)`` for every stale result."""
    root = _repo_root()
    scripts_dir = root / "scripts"
    stale: list[tuple[str, str]] = []
    for fname, script in STAMP_CHECK_MAP.items():
        fpath = scripts_dir / fname
        if fpath.is_file():
            valid, msg = verify_stamp(str(fpath), script)
            if not valid:
                stale.append((str(fpath.relative_to(root)), msg))
        else:
            stale.append((f"scripts/{fname}", "missing result file"))
    return stale


def main() -> int:
    stale = list_stale_results()
    if stale:
        print("STALE RESULT FILES:")
        for fpath, msg in stale:
            print(f"  {fpath}: {msg}")
        print("\nRun the appropriate script to regenerate each.")
        return 1
    print("All result JSONs are fresh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "SCRIPT_VERSIONS",
    "STAMP_CHECK_MAP",
    "STAMP_SCHEMA_VERSION",
    "compute_code_hash",
    "list_stale_results",
    "make_stamp",
    "verify_stamp",
    "write_json_with_stamp",
]
