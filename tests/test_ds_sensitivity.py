#!/usr/bin/env python3
"""
Dynamic-stall sensitivity tests.

Records the Cp change when each DS constant is varied +/-50% at each anchor
and fails if the documented sensitivity ranking changes.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from vawt_core import create_sim_from_params
from scripts.uncertainty import ANCHORS


# DS constants to test (parameter name, default value)
DS_CONSTANTS = [
    ("ds_Tf", 3.0),
    ("ds_Tv", 6.0),
    ("ds_Ta", 0.1),
    ("ds_Kv", 0.5),
    ("ds_Knc", 1.0),
]


class TestDSSensitivity:
    """Dynamic-stall sensitivity tests."""

    @pytest.fixture(scope="class")
    def base_cps(self):
        """Run baseline simulations for each anchor."""
        cps = {}
        for name, params in ANCHORS.items():
            r = create_sim_from_params(params).run()
            cps[name] = r['cp']
        return cps

    @pytest.mark.parametrize("anchor_name", ["sharp_cppc", "optimised_passive", "scaleup"])
    def test_ds_constants_ranking(self, anchor_name, base_cps):
        """Verify that the sensitivity ranking of DS constants is consistent.

        The documented ranking (most to least sensitive) is:
        1. ds_Tf (separation lag)
        2. ds_Tv (vortex lag)
        3. ds_Kv (vortex strength)
        4. ds_Ta (attached-flow lag)
        5. ds_Knc (apparent mass)
        """
        base_cp = base_cps[anchor_name]
        sensitivities = {}

        for param_name, default_val in DS_CONSTANTS:
            # Test -50%
            params_minus = {**ANCHORS[anchor_name], param_name: default_val * 0.5}
            r_minus = create_sim_from_params(params_minus).run()
            delta_minus = abs(r_minus['cp'] - base_cps[anchor_name]) / max(base_cps[anchor_name], 1e-9)

            # Test +50%
            params_plus = {**ANCHORS[anchor_name], param_name: default_val * 1.5}
            r_plus = create_sim_from_params(params_plus).run()
            delta_plus = abs(r_plus['cp'] - base_cps[anchor_name]) / max(base_cps[anchor_name], 1e-9)

            # Use maximum deviation
            sensitivities[param_name] = max(delta_minus, delta_plus)

        # Sort by sensitivity (descending)
        ranked = sorted(sensitivities.items(), key=lambda x: x[1], reverse=True)

        # Documented ranking (most to least sensitive)
        expected_ranking = ["ds_Tf", "ds_Tv", "ds_Kv", "ds_Ta", "ds_Knc"]
        actual_ranking = [p for p, _ in ranked]

        # Check that the ranking matches (allowing ties)
        for i, expected in enumerate(expected_ranking):
            # Find position in actual ranking
            actual_pos = actual_ranking.index(expected)
            # Check that no higher-ranked parameter appears after it
            for j in range(i+1, len(expected_ranking)):
                later = expected_ranking[j]
                assert actual_ranking.index(later) > actual_pos, \
                    f"{anchor_name}: {later} ranked before {expected} (expected {expected} before {later})"

    def test_ds_sensitivity_magnitude(self, base_cps):
        """Verify that DS sensitivity is large for passive anchors and small for prescribed."""
        # Sharp-inspired passive: DS should cause >50% drop
        r_ds = create_sim_from_params({**ANCHORS["sharp_cppc"], 'use_dynamic_stall': True}).run()
        r_nods = create_sim_from_params({**ANCHORS["sharp_cppc"], 'use_dynamic_stall': False}).run()
        delta_sharp = abs(r_ds['cp'] - r_nods['cp']) / max(r_ds['cp'], 1e-9)
        assert delta_sharp > 0.5, f"Sharp-inspired DS sensitivity {delta_sharp*100:.1f}% < 50%"

        # Optimised passive: DS should cause >50% drop
        r_ds = create_sim_from_params({**ANCHORS["optimised_passive"], 'use_dynamic_stall': True}).run()
        r_nods = create_sim_from_params({**ANCHORS["optimised_passive"], 'use_dynamic_stall': False}).run()
        delta_opt = abs(r_ds['cp'] - base_cps["optimised_passive"]) / max(base_cps["optimised_passive"], 1e-9)
        assert delta_opt > 0.5, f"Optimised passive DS sensitivity {delta_opt*100:.1f}% < 50%"

        # Scale-up: DS should cause >50% drop
        r_ds = create_sim_from_params({**ANCHORS["scaleup"], 'use_dynamic_stall': True}).run()
        r_nods = create_sim_from_params({**ANCHORS["scaleup"], 'use_dynamic_stall': False}).run()
        delta_scale = abs(r_ds['cp'] - base_cps["scaleup"]) / max(base_cps["scaleup"], 1e-9)
        assert delta_scale > 0.5, f"Scale-up DS sensitivity {delta_scale*100:.1f}% < 50%"

        # Prescribed-pitch design (actuator): DS should cause < 4% change
        from scripts.optimize_actuator import DESIGN as ACTUATOR_DESIGN
        r_ds = create_sim_from_params({**ACTUATOR_DESIGN, 'use_dynamic_stall': True}).run()
        r_nods = create_sim_from_params({**ACTUATOR_DESIGN, 'use_dynamic_stall': False}).run()
        delta_act = abs(r_ds['cp'] - r_nods['cp']) / max(r_ds['cp'], 1e-9)
        assert delta_act < 0.04, f"Actuator DS sensitivity {delta_act*100:.1f}% > 4%"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])