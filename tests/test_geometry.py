"""Tests for geometry validation and the mass-balance solver."""
import pytest

from vawt_core import create_sim_from_params
from tests.conftest import BASE_QUICK


class TestGeometryValidation:

    def test_arm_longer_than_radius_rejected(self):
        # R = 0.10, ar*c = 0.5*0.14 = 0.07  (still < R)
        # We need c*ar >= R
        with pytest.raises(ValueError):
            create_sim_from_params({**BASE_QUICK, 'R': 0.10, 'c': 0.14, 'ar': 0.8})

    def test_reasonable_geometry_accepted(self):
        create_sim_from_params({**BASE_QUICK, 'R': 0.60, 'c': 0.14, 'ar': 0.50})


class TestBalance:

    def test_balance_zero_uses_given_mc_dcw(self):
        s = create_sim_from_params({
            **BASE_QUICK, 'balance': 0, 'mc': 0.005, 'dcw': 0.40,
        })
        assert s.mc == pytest.approx(0.005)
        assert s.dcw == pytest.approx(0.40)

    def test_r_cg_is_finite(self):
        s = create_sim_from_params({**BASE_QUICK})
        assert abs(s.xg) < 1.0   # not off by an order of magnitude
        assert s.Ip > 0.0
