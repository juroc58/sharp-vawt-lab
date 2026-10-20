#!/usr/bin/env python3
"""Deprecated alias for :mod:`scripts.gen_real_polars`.

The v2 hand-fitted generator produced attached-flow drag 2.5-4x too high
(CD ~0.021 at Re 1e6 / 6 deg vs the XFOIL-trained value ~0.010). Use
``scripts/gen_real_polars.py``; this wrapper is kept so existing commands
and references do not break.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gen_real_polars import main  # noqa: E402

if __name__ == "__main__":
    main()
