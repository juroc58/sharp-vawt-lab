#!/usr/bin/env python3
"""
Shared module for computing freshness stamps (code hashes) for result JSONs.

A stamp includes a code_hash that covers:
- vawt_core.py (core physics)
- All polar CSV files in airfoil_polars/
- airfoil_polars/provenance.json
- The script's own source file
- Any script-specific version string

This ensures that result JSONs can be validated for freshness.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _repo_root() -> Path:
    """Return the repository root directory."""
    # This file is in scripts/, so parent is repo root
    return Path(__file__).resolve().parent.parent


def compute_code_hash(
    script_path: str,
    extra_files: Optional[List[str]] = None,
    extra_data: Optional[Dict[str, Any]] = None,
    version: str = "",
) -> str:
    """
    Compute a SHA-256 hash (16-char prefix) of all inputs that affect results.

    Args:
        script_path: Path to the script generating results (relative to repo root)
        extra_files: Additional files to include in the hash (relative to repo root)
        extra_data: Additional data to include in the hash (will be JSON-serialized)
        version: Version string for the script (e.g., "v1.0")

    Returns:
        16-character hex string (SHA-256 prefix)
    """
    root = _repo_root()
    h = hashlib.sha256()

    # Core physics (always included)
    core_files = ["vawt_core.py"]
    for rel in core_files:
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"Stamp: missing core file {path}")
        h.update(path.read_bytes())

    # All polar CSV files
    polar_dir = root / "airfoil_polars"
    polar_files = sorted(polar_dir.glob("**/*.csv"))
    if not polar_files:
        raise FileNotFoundError(f"Stamp: no polar CSVs found under {polar_dir}")
    for f in polar_files:
        h.update(f.read_bytes())

    # Polar provenance
    provenance = polar_dir / "provenance.json"
    if not provenance.is_file():
        raise FileNotFoundError(f"Stamp: missing polar provenance {provenance}")
    h.update(provenance.read_bytes())

    # The generating script itself
    script_file = root / script_path
    if not script_file.is_file():
        raise FileNotFoundError(f"Stamp: missing script file {script_file}")
    h.update(script_file.read_bytes())

    # Extra files (e.g., vawt_presets.py, uncertainty.py, etc.)
    if extra_files:
        for rel in extra_files:
            path = root / rel
            if not path.is_file():
                raise FileNotFoundError(f"Stamp: missing extra file {path}")
            h.update(path.read_bytes())

    # Extra data (e.g., UQ_SPEC, parameter bounds, etc.)
    if extra_data:
        h.update(json.dumps(extra_data, sort_keys=True).encode())

    # Version string
    if version:
        h.update(version.encode())

    return h.hexdigest()[:16]


def make_stamp(
    script_path: str,
    script_version: str = "",
    n: Optional[int] = None,
    seed: Optional[int] = None,
    extra_files: Optional[List[str]] = None,
    extra_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a stamp dictionary for embedding in result JSONs.

    Args:
        script_path: Path to the generating script (relative to repo root)
        script_version: Version string for the script
        n: Number of samples/runs
        seed: Random seed used
        extra_files: Additional files to hash
        extra_data: Additional data to hash

    Returns:
        Dictionary with stamp fields
    """
    import datetime

    code_hash = compute_code_hash(script_path, extra_files, extra_data, script_version)

    stamp = {
        "code_hash": code_hash,
        "script": script_path,
        "script_version": script_version,
        "created_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "extra_files": extra_files,
        "extra_data": extra_data,
    }
    if n is not None:
        stamp["n"] = n
    if seed is not None:
        stamp["seed"] = seed

    return stamp


def verify_stamp(json_path: str, expected_script: str) -> tuple[bool, str]:
    """
    Verify that a result JSON has a valid, current stamp.

    Args:
        json_path: Path to the result JSON file
        expected_script: Expected script path that should have generated it

    Returns:
        (is_valid, message)
    """
    try:
        with open(json_path) as f:
            data = json.load(f)
    except Exception as e:
        return False, f"Failed to read JSON: {e}"

    if "stamp" not in data:
        return False, f"Missing 'stamp' field in {json_path}"

    stamp = data["stamp"]

    # Check required fields
    required = ["code_hash", "script", "script_version", "created_utc"]
    for field in required:
        if field not in stamp:
            return False, f"Missing stamp field '{field}' in {json_path}"

    # Check script matches
    if stamp["script"] != expected_script:
        return False, f"Stamp script mismatch: expected {expected_script}, got {stamp['script']}"

    # Recompute hash and compare
    try:
        current_hash = compute_code_hash(
            stamp["script"],
            extra_files=stamp.get("extra_files"),
            extra_data=stamp.get("extra_data"),
            version=stamp["script_version"],
        )
    except Exception as e:
        return False, f"Failed to recompute hash: {e}"

    if stamp["code_hash"] != current_hash:
        return False, (
            f"Code hash mismatch for {json_path}: "
            f"stored={stamp['code_hash']}, current={current_hash}. "
            f"Re-run {stamp['script']} to regenerate."
        )

    return True, "OK"


# Map of result JSON filename -> expected generating script
STAMP_CHECK_MAP = {
    "uncertainty_results.json": "scripts/uncertainty.py",
    "robust_optimization.json": "scripts/robust_reopt.py",
    "aep_results.json": "scripts/compute_aep.py",
    "aep_scaleup.json": "scripts/compute_aep_scaleup.py",
    "aep_turbulent.json": "scripts/compute_aep_turbulent.py",
    "aep_rigid_fair.json": "scripts/compute_aep_rigid_fair.py",
    "aep_scaleup.json": "scripts/compute_aep_scaleup.py",
    "aep_counter_rotating.json": "scripts/compute_aep_counter_rotating.py",
    "cm_scale_scan.json": "scripts/scan_cm_scale.py",
    "ham_finite_span_check.json": "scripts/ham_finite_span_check.py",
    "branch_point_checks.json": "scripts/check_branch_points.py",
    "diag_aep_branches.json": "scripts/diag_aep_branches.py",
    "tip_loss_scan.json": "scripts/scan_tip_loss.py",
    "cm_scale_scan.json": "scripts/scan_cm_scale.py",
    "optimization_passive.json": "scripts/optimize_passive.py",
    "optimization_scaleup.json": "scripts/optimize_scaleup.py",
    "optimization_actuator.json": "scripts/optimize_actuator.py",
    "sobol_results.json": "scripts/sobol_sensitivity.py",
    "spearman_results.json": "scripts/spearman_sensitivity.py",
    "aep_counter_rotating.json": "scripts/compute_aep_counter_rotating.py",
    "aep_turbulent.json": "scripts/compute_aep_turbulent.py",
    "aep_rigid_fair.json": "scripts/compute_aep_rigid_fair.py",
    "tip_loss_scan.json": "scripts/scan_tip_loss.py",
}


def list_stale_results(results_dir: str = "scripts") -> List[tuple[str, str]]:
    """
    Scan for result JSONs and check their freshness.

    Returns:
        List of (json_path, error_message) for stale/invalid files.
    """
    stale = []
    script_dir = Path(__file__).parent
    root = script_dir.parent

    scripts_dir = root / "scripts"
    for fname, script in STAMP_CHECK_MAP.items():
        fpath = scripts_dir / fname
        if fpath.is_file():
            valid, msg = verify_stamp(fpath, script)
            if not valid:
                stale.append((str(fpath.relative_to(root)), msg))

    return stale


def main():
    """CLI: list stale result files and how to regenerate them."""
    stale = list_stale_results()
    if stale:
        print("STALE RESULT FILES:")
        for fpath, msg in stale:
            print(f"  {fpath}: {msg}")
        print("\nRun the appropriate script to regenerate each.")
        sys.exit(1)
    else:
        print("All result JSONs are fresh.")
        sys.exit(0)


if __name__ == "__main__":
    main()