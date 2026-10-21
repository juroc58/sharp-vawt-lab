"""Polar generation, provenance and the aerosandbox shim."""
import os
import sys
import types

import numpy as np
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import check_polars
from scripts import gen_real_polars


def test_check_polars_flags_low_re_surrogate_artefacts():
    path = os.path.join(_ROOT, "airfoil_polars", "naca0012",
                        "polars_naca0012_Re_100000.csv")
    warnings = check_polars.check_one(path)
    text = " ".join(warnings)
    assert "lift slope" in text
    assert "kink" in text


def test_aerosandbox_shim_helpers_known_values(monkeypatch):
    """If the shim is used, its helpers must match NumPy's degree math.

    When the real AeroSandbox is installed the shim is not exercised; the
    test then skips rather than importing a package it cannot control.
    """
    # Force the "aerosandbox absent" branch without disturbing the real
    # package (if any) after the test.
    saved = {k: sys.modules.pop(k) for k in list(sys.modules)
             if k == "aerosandbox" or k.startswith("aerosandbox.")}
    try:
        installed = gen_real_polars._install_aerosandbox_shim()
        if not installed:
            pytest.skip("real aerosandbox is installed; shim not exercised")
        import aerosandbox.numpy as anp
        assert anp.sind(30.0) == pytest.approx(0.5, abs=1e-12)
        assert anp.cosd(60.0) == pytest.approx(0.5, abs=1e-12)
        assert anp.tand(45.0) == pytest.approx(1.0, abs=1e-12)
        assert anp.swish(0.0) == pytest.approx(0.0)
        assert anp.swish(1.0) == pytest.approx(1.0 / (1.0 + np.exp(-1.0)))
        assert anp.length(np.zeros((3, 4))) == 12
        assert anp.atleast1d(2.0).shape == (1,)
    finally:
        for k in list(sys.modules):
            if k == "aerosandbox" or k.startswith("aerosandbox."):
                del sys.modules[k]
        sys.modules.update(saved)


def test_deep_stall_constants_are_named():
    """The deep-stall amplitudes must be named constants, not magic numbers."""
    assert gen_real_polars.DEEP_STALL_CL_AMP == pytest.approx(0.65)
    assert gen_real_polars.DEEP_STALL_CD_AMP == pytest.approx(1.66)
    assert gen_real_polars.DEEP_STALL_CD_OFFSET == pytest.approx(0.02)
    cl, cd, cm = gen_real_polars._deep_stall(90.0)
    assert cl == pytest.approx(0.0, abs=1e-9)
    assert cd == pytest.approx(gen_real_polars.DEEP_STALL_CD_AMP
                               + gen_real_polars.DEEP_STALL_CD_OFFSET)
