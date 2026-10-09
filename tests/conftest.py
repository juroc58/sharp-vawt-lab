"""Shared pytest fixtures for the sharp-vawt-lab test suite."""
import os
import sys
import warnings

import pytest

# Add project root to sys.path so `from vawt_core import ...` works when
# pytest is invoked from anywhere.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)


# Small, fast reference design used throughout the tests.
BASE_QUICK = dict(
    R=0.60, H=0.40, N=3, c=0.14,
    ar=0.50, sp=0.25,
    mb=0.010, xbcg=0.20,
    mc=0.002, dcw=0.30,
    balance=0, bias_deg=0.0,
    prescribe_pitch=False,
    cd_add=0.002,
    use_dynamic_stall=True,
    use_flow_curvature=True,
    use_dmst=True,
    use_tip_loss=True,
    win_deg=45.0, cb=2e-5, mu_c=3e-4,
    free=True, T_max=10.0, stride=10,
    w0_frac=0.9, k_load=0.0025, tsr=2.0,
)


@pytest.fixture(scope="session", autouse=True)
def numba_warmup():
    """Compile the numba kernels once so the first test isn't 30 s slower."""
    from vawt_core import create_sim_from_params
    try:
        create_sim_from_params({**BASE_QUICK, 'T_max': 0.5}).run()
    except Exception as exc:
        warnings.warn(f"warm-up failed: {exc!r}")


@pytest.fixture
def quick_design():
    return dict(BASE_QUICK)


@pytest.fixture
def sharp_conforming():
    """Sharp's own design rules: light cw, dcw = 0.30, ar = 0.50, sp = 0.25."""
    return dict(
        R=0.60, H=0.40, N=3, c=0.14,
        ar=0.50, sp=0.25,
        mb=0.010, xbcg=0.20,
        mc=0.002, dcw=0.30,
        balance=0, bias_deg=0.0,
        prescribe_pitch=False,
        cd_add=0.002,
        use_dynamic_stall=True,
        use_flow_curvature=True,
        use_dmst=True,
        use_tip_loss=True,
        win_deg=45.0, cb=2e-5, mu_c=3e-4,
        free=True, T_max=20.0, stride=5,
        w0_frac=0.9, k_load=0.0025, tsr=2.0,
    )
