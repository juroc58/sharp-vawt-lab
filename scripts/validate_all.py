#!/usr/bin/env python3
"""
Run all validation scripts sequentially.

This script runs all validation scripts sequentially and exits with a non-zero
code if any validation fails. It prints outputs from each script to stdout.
"""

import subprocess
import sys


VALIDATION_SCRIPTS = [
    "validate_ham.py",
    "validate_finite_span.py",
    "validate_ds_off.py",
]


def main():
    print("=" * 72)
    print("Running validation suite...")
    print("=" * 72)

    for script in VALIDATION_SCRIPTS:
        print(f"\n>>> Running {script}...")
        try:
            result = subprocess.run(
                [sys.executable, f"scripts/{script}"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)

            if result.returncode != 0:
                print(f"\n❌ {script} FAILED (exit code {result.returncode})")
                return 1
            else:
                print(f"✅ {script} PASSED")

        except subprocess.TimeoutExpired:
            print(f"\n❌ {script} TIMED OUT after 120 seconds")
            return 1
        except Exception as e:
            print(f"\n❌ {script} ERROR: {e}")
            return 1

    print("\n" + "=" * 72)
    print("✅ All validations PASSED!")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())