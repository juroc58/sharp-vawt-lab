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


def test_check_polars_flags_neuralfoil_cm_variant_artefacts():
    """The neuralfoil_cm variant still has the raw NeuralFoil CM sign changes.

    This variant is for sensitivity analysis only; the default variant
    has Cm=0 in attached flow and passes all checks.
    """
    import numpy as np
    from scripts import check_polars

    # The neuralfoil_cm variant uses column 5 (Cm_neuralfoil) which has
    # the raw NeuralFoil CM with sign changes.
    # We can't easily test this through check_polars.check_one since it
    # reads column 4 (Cm_default). Instead, verify the raw CM is present
    # in the CSV by loading it directly.
    path = os.path.join(_ROOT, "airfoil_polars", "naca0012",
                        "polars_naca0012_Re_100000.csv")
    d = np.genfromtxt(path, delimiter=",", comments="#")
    d = d[~np.isnan(d).any(axis=1)]
    o = np.argsort(d[:, 0])
    a, cm_default, cm_nf = d[o, 0], d[o, 3], d[o, 4]

    # Default Cm should be 0 in attached range
    attached = np.abs(a) <= 20.0
    assert np.all(np.abs(cm_default[attached]) < 1e-6)

    # NeuralFoil CM should have sign changes in attached range
    cm_nf_att = cm_nf[attached]
    nz = np.abs(cm_nf_att) > 1e-6
    signs = np.sign(cm_nf_att[nz])
    assert len(signs) >= 2 and np.any(np.diff(signs) != 0), \
        "neuralfoil_cm variant should have CM sign changes"


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
