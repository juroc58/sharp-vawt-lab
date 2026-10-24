#!/usr/bin/env python3
"""
Run all validation scripts sequentially.

This script runs all validation scripts sequentially and exits with a non-zero
code if any validation fails. It prints outputs from each script to stdout.
"""

import subprocess
import sys
from pathlib import Path

VALIDATION_SCRIPTS = [
    "validate_ham.py",
    "validate_finite_span.py",
    "validate_ds_off.py",
]


def main():
    repo_root = Path(__file__).resolve().parent.parent
    scripts_dir = repo_root / "scripts"

    print("=" * 72)
    print("Running validation suite...")
    print("=" * 72)

    for script_name in VALIDATION_SCRIPTS:
        script_path = scripts_dir / script_name
        print(f"\n>>> Running {script_name}...")
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=repo_root,
            )
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)

            if result.returncode != 0:
                print(f"\n❌ {script_name} FAILED (exit code {result.returncode})")
                return 1
            else:
                print(f"✅ {script_name} PASSED")

        except subprocess.TimeoutExpired:
            print(f"\n❌ {script_name} TIMED OUT after 300 seconds")
            return 1
        except Exception as e:
            print(f"\n❌ {script_name} ERROR: {e}")
            return 1

    print("\n" + "=" * 72)
    print("✅ All validations PASSED!")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())