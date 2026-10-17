"""Regenerate the golden Cp values in tests/test_regression.py.

Usage (from the repo root, in an env with numba installed):

    python3 -c "import tests.regenerate_golden as g; g.main()"

It prints the name -> Cp mapping to paste into test_regression.GOLDEN.
This is a manual maintenance tool, not part of the test suite.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from vawt_core import create_sim_from_params
from tests.test_regression import GOLDEN


def main():
    print("name\tcp")
    for name, (params, _) in GOLDEN.items():
        r = create_sim_from_params(params).run()
        print(f"{name}\t{r['cp']:.10f}\t(steady={r['steady']})")


if __name__ == "__main__":
    main()