"""Tests for create_sim_from_params — validation, aliases, forwarding."""
import pytest

from vawt_core import create_sim_from_params, CycloturbineSim
from tests.conftest import BASE_QUICK


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
    """Defaults must not drift."""

    def test_default_free_true(self):
        s = create_sim_from_params({**BASE_QUICK})
        assert s.sim.free is True

    def test_N_is_int(self):
        s = create_sim_from_params({**BASE_QUICK, 'N': 3.0})
        assert isinstance(s.geo.N, int)

    def test_returns_sim(self):
        s = create_sim_from_params({**BASE_QUICK})
        assert isinstance(s, CycloturbineSim)
