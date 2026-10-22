#!/bin/bash
# Regenerate all AEP figures from JSON results.
# This script should be run after the compute scripts have produced fresh JSON.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

echo "=== Regenerating AEP figures ==="

echo "1. Scale-up AEP (aep_scaleup.png)"
python3 scripts/plot_aep.py --json scripts/aep_scaleup.json --out docs/aep_scaleup.png --type scaleup

echo "2. Small-rotor AEP (aep.png)"
python3 scripts/plot_aep.py --json scripts/aep_results.json --out docs/aep.png --type small

echo "3. Turbulent AEP (aep_turbulent.png)"
python3 scripts/plot_aep.py --json scripts/aep_turbulent.json --out docs/aep_turbulent.png --type turbulent

echo "4. Counter-rotating AEP (aep_counter_rotating.png)"
python3 scripts/plot_aep.py --json scripts/aep_counter_rotating.json --out docs/aep_counter_rotating.png --type counter

echo ""
echo "=== All figures regenerated ==="
ls -la docs/aep*.png