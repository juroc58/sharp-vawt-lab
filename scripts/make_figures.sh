#!/bin/bash
# Thin compatibility wrapper.  The canonical entry point is
#   python3 scripts/make_all_figures.py
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/make_all_figures.py" "$@"
