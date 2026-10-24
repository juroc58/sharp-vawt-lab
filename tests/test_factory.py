"""Tests for create_sim_from_params — validation, aliases, forwarding."""
import pytest

from tests.conftest import BASE_QUICK
from vawt_core import CycloturbineSim, create_sim_from_params


class TestFactoryKeyChecking:
    """The factory must reject unknown keys loudly."""

    def test_unknown_key_raises(self):
        with pytest.raises(KeyError) as exc:
            create_sim_from_params({"pp4_deg": 5.0})
        assert "pp4_deg" in str(exc.value)

    def test_multiple_unknown_keys_reported_together(self):
        with pytest.raises(KeyError) as exc:
            create_sim_from_params({"pp4_deg": 5.0, "foobar": 1.0})
        msg = str(exc.value)
        assert "pp4_deg" in msg and "foobar" in msg

    def test_known_key_accepted(self):
        create_sim_from_params({**BASE_QUICK, 'c': 0.10})

    def test_alias_bias_accepted(self):
        create_sim_from_params({**BASE_QUICK, 'bias': 2.0})

    def test_alias_win_accepted(self):
        create_sim_from_params({**BASE_QUICK, 'win': 40.0})

    @pytest.mark.parametrize("dead_key", ["n_span", "use_hub_loss",
                                          "use_rotational_aug"])
    def test_removed_legacy_keys_rejected(self, dead_key):
        """Keys dropped in the Tier-2 dead-code cleanup must stay gone.

        If any of these is silently re-added to a config dataclass, this
        fails and forces a conscious decision instead of bit-rot.
        """
        with pytest.raises(KeyError) as exc:
            create_sim_from_params({**BASE_QUICK, dead_key: 1})
        assert dead_key in str(exc.value)


class TestFactoryForwarding:
    """SimConfig fields the AEP scripts depend on must actually be forwarded."""

    def test_turb_I_forwarded(self):
        s = create_sim_from_params({**BASE_QUICK, 'turb_I': 0.15})
        assert s.sim.turb_I == pytest.approx(0.15)

    def test_turb_L_forwarded(self):
        s = create_sim_from_params({**BASE_QUICK, 'turb_L': 42.0})
        assert s.sim.turb_L == pytest.approx(42.0)

    def test_seed_forwarded(self):
        s = create_sim_from_params({**BASE_QUICK, 'seed': 7})
        assert s.sim.seed == 7

    def test_gust_forwarded(self):
        s = create_sim_from_params({**BASE_QUICK, 'gust_g': 0.5})
        assert s.sim.gust_g == pytest.approx(0.5)


class TestFactoryDefaults:
    """Defaults must stay small and neutral; named designs live in PRESETS."""

    def test_dataclass_defaults_are_neutral(self):
        from vawt_core import AeroConfig, Geometry, MassProps, SimConfig
        g, m, a, s = Geometry(), MassProps(), AeroConfig(), SimConfig()
        assert g.R == pytest.approx(0.60)
        assert g.c == pytest.approx(0.14)
        assert g.H == pytest.approx(0.40)
        assert m.mb == pytest.approx(0.010)
        assert m.mc == pytest.approx(0.002)
        assert a.polar_dir == "airfoil_polars/naca0012"
        assert s.free is False
        assert s.T_max == pytest.approx(10.0)
        assert s.k_load == pytest.approx(0.0025)
        assert s.tsr == pytest.approx(2.0)

    def test_scaleup_preset_preserves_legacy_design(self):
        from vawt_presets import PRESETS
        p = PRESETS["scaleup"]
        assert p["R"] == pytest.approx(2.7179)
        assert p["c"] == pytest.approx(0.3861)
        assert p["H"] == pytest.approx(4.0568)
        assert p["mb"] == pytest.approx(0.92954)
        assert p["mc"] == pytest.approx(2.69306)
        assert p["k_load"] == pytest.approx(4.164352)
        assert p["free"] is True
        assert p["T_max"] == pytest.approx(40.0)

    def test_explicit_free_is_forwarded(self):
        s = create_sim_from_params({**BASE_QUICK, 'free': False})
        assert s.sim.free is False
        s = create_sim_from_params({**BASE_QUICK, 'free': True})
        assert s.sim.free is True

    def test_polar_dir_is_module_relative(self):
        import os
        s = create_sim_from_params({**BASE_QUICK, 'polar_dir': 'airfoil_polars/naca0012'})
        assert os.path.isabs(s.polar_db.polar_dir)
        assert s.polar_db.polar_dir.endswith('airfoil_polars/naca0012')

    def test_N_is_int(self):
        s = create_sim_from_params({**BASE_QUICK, 'N': 3.0})
        assert isinstance(s.geo.N, int)

    def test_returns_sim(self):
        s = create_sim_from_params({**BASE_QUICK})
        assert isinstance(s, CycloturbineSim)
