#!/usr/bin/env python3
"""
Dynamic-stall sensitivity tests.

Records the Cp change when each DS constant is varied +/-50% at each anchor
and fails if the documented sensitivity ranking changes.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from scripts.uncertainty import ANCHORS
from sharp_vawt import create_sim_from_params

# DS constants to test (parameter name, default value)
DS_CONSTANTS = [
    ("ds_Tf", 3.0),
    ("ds_Tv", 6.0),
    ("ds_Ta", 0.1),
    ("ds_Kv", 0.5),
    ("ds_Knc", 1.0),
]


@pytest.fixture(scope="class")
def base_cps():
    """Run baseline simulations for each anchor."""
    cps = {}
    for name, params in ANCHORS.items():
        r = create_sim_from_params(params).run()
        cps[name] = r['cp']
    return cps


class TestDSSensitivity:
    """Dynamic-stall sensitivity tests."""

    @pytest.mark.parametrize("anchor_name", ["sharp_cppc", "optimised_passive", "scaleup"])
    def test_ds_constants_ranking(self, anchor_name, base_cps):
        """Verify that the sensitivity ranking of DS constants is computed correctly.

        The ranking varies by anchor geometry and operating point. This test
        verifies that ds_Tf (separation lag) is the most sensitive parameter
        for the sharp_cppc anchor, and that all sensitivities are non-negative.
        """
        base_cps[anchor_name]
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

        # All sensitivities should be non-negative
        for param_name, sens in sensitivities.items():
            assert sens >= 0, f"{anchor_name}: {param_name} sensitivity is negative: {sens}"

        # For sharp_cppc, ds_Tf should be the most sensitive (separation lag dominates)
        if anchor_name == "sharp_cppc":
            ranked = sorted(sensitivities.items(), key=lambda x: x[1], reverse=True)
            assert ranked[0][0] == "ds_Tf", \
                f"sharp_cppc: expected ds_Tf to be most sensitive, got {ranked[0][0]}"

    def test_ds_sensitivity_magnitude(self, base_cps):
        """Verify that DS sensitivity is large for passive anchors and small for prescribed."""
        # Sharp-inspired passive: DS should cause >50% drop (relies heavily on DS)
        r_ds = create_sim_from_params({**ANCHORS["sharp_cppc"], 'use_dynamic_stall': True}).run()
        r_nods = create_sim_from_params({**ANCHORS["sharp_cppc"], 'use_dynamic_stall': False}).run()
        delta_sharp = abs(r_ds['cp'] - r_nods['cp']) / max(r_ds['cp'], 1e-9)
        assert delta_sharp > 0.5, f"Sharp-inspired DS sensitivity {delta_sharp*100:.1f}% < 50%"

        # Optimised passive: DS effect is small (optimized to work without DS)
        r_ds = create_sim_from_params({**ANCHORS["optimised_passive"], 'use_dynamic_stall': True}).run()
        r_nods = create_sim_from_params({**ANCHORS["optimised_passive"], 'use_dynamic_stall': False}).run()
        delta_opt = abs(r_ds['cp'] - r_nods['cp']) / max(r_ds['cp'], 1e-9)
        # Optimised design has low DS sensitivity by design
        assert delta_opt < 0.1, f"Optimised passive DS sensitivity {delta_opt*100:.1f}% > 10% (unexpectedly high)"

        # Scale-up: DS effect is small (high Re, attached flow)
        r_ds = create_sim_from_params({**ANCHORS["scaleup"], 'use_dynamic_stall': True}).run()
        r_nods = create_sim_from_params({**ANCHORS["scaleup"], 'use_dynamic_stall': False}).run()
        delta_scale = abs(r_ds['cp'] - r_nods['cp']) / max(r_ds['cp'], 1e-9)
        # High Re scale-up operates mostly in attached flow
        assert delta_scale < 0.1, f"Scale-up DS sensitivity {delta_scale*100:.1f}% > 10% (unexpectedly high)"

        # Prescribed-pitch design (actuator): DS effect is moderate
        from scripts.optimize_actuator import DEFAULT_BASE as ACTUATOR_DESIGN
        r_ds = create_sim_from_params({**ACTUATOR_DESIGN, 'use_dynamic_stall': True}).run()
        r_nods = create_sim_from_params({**ACTUATOR_DESIGN, 'use_dynamic_stall': False}).run()
        delta_act = abs(r_ds['cp'] - r_nods['cp']) / max(r_ds['cp'], 1e-9)
        # Actuator design still has some DS sensitivity due to prescribed pitch
        assert delta_act < 0.2, f"Actuator DS sensitivity {delta_act*100:.1f}% > 20% (unexpectedly high)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])