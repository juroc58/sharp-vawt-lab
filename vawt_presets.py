"""Named parameter sets for the Sharp cycloturbine model.

The dataclass defaults in :mod:`vawt_core` are a small, neutral R = 0.6 m
Sharp-inspired design.  Larger or optimised machines live here as explicit
presets so that no result silently inherits a scale-up design.

Every preset is a flat dictionary of ``create_sim_from_params`` keys.  Add new
named machines here rather than changing the dataclass defaults.
"""
from __future__ import annotations

from typing import Any

# Small neutral baseline: R = 0.6 m, H = 0.4 m, NACA 0012 polars.
SHARP_BASELINE: dict[str, Any] = {
    "R": 0.60, "c": 0.14, "H": 0.40, "N": 3,
    "ar": 0.50, "sp": 0.25,
    "mb": 0.010, "xbcg": 0.20, "mc": 0.002, "dcw": 0.30,
    "balance": 0, "bias_deg": 0.0,
    "prescribe_pitch": False,
    "free": False, "tsr": 2.0, "T_max": 10.0, "stride": 5,
    "use_dynamic_stall": True,
    "use_flow_curvature": True,
    "use_tip_loss": True,
    "use_dmst": True,
    "win_deg": 45.0, "cb": 2e-5, "mu_c": 3e-4,
    "k_load": 0.0025,
    "arm_cd": 1.0,
}

PRESETS: dict[str, dict[str, Any]] = {
    "sharp_baseline": SHARP_BASELINE,
    # Ham 1979 comparison — his model class: DMS induction, static polars,
    # cosine pitch, no curvature and no finite-span correction.
    "ham_1979": {
        "R": 1.83, "c": 0.305, "H": 1.37, "N": 3,
        "ar": 0.0, "sp": 0.25,
        "mb": 0.010, "xbcg": 0.20, "mc": 0.002, "dcw": 0.30,
        "balance": 0, "bias_deg": 0.0,
        "prescribe_pitch": True, "pp0_deg": 0.0, "pp1_deg": -10.0,
        "pp2_deg": 0.0, "pp3_deg": 0.0, "pp_ph_deg": 0.0,
        "free": False, "tsr": 2.5, "T_max": 20.0, "stride": 5,
        "use_dynamic_stall": False,
        "use_flow_curvature": False,
        "use_tip_loss": False,
        "use_dmst": True,
        "win_deg": 89.0, "cb": 2e-5, "mu_c": 0.0,
        "k_load": 0.0004,
        "arm_cd": 1.0,
    },
    # Sharp-inspired CPPC at R = 0.60 m.
    "sharp_cppc": {
        "R": 0.60, "c": 0.14, "H": 0.40, "N": 3,
        "ar": 0.50, "sp": 0.25,
        "mb": 0.010, "xbcg": 0.20, "mc": 0.002, "dcw": 0.30,
        "balance": 0, "bias_deg": 0.0,
        "prescribe_pitch": False,
        "free": True, "tsr": 2.0, "T_max": 30.0, "stride": 5,
        "use_dynamic_stall": True,
        "use_flow_curvature": True,
        "use_tip_loss": True,
        "use_dmst": True,
        "win_deg": 45.0, "cb": 2e-5, "mu_c": 3e-4,
        "k_load": 0.0025,
        "arm_cd": 1.0,
    },
    # Optimised passive (mass-balanced) at R = 0.60 m.  Values mirror
    # scripts/optimization_passive.json.
    "optimised_passive": {
        "R": 0.60, "c": 0.070077, "H": 0.40, "N": 3,
        "ar": 0.260419, "sp": 0.209523,
        "mb": 0.010, "xbcg": 0.20, "mc": 0.025151, "dcw": -0.190913,
        "balance": 0, "bias_deg": 4.676692,
        "prescribe_pitch": False,
        "free": True, "tsr": 2.0, "T_max": 30.0, "stride": 5,
        "use_dynamic_stall": True,
        "use_flow_curvature": True,
        "use_tip_loss": True,
        "use_dmst": True,
        "win_deg": 45.0, "cb": 2e-5, "mu_c": 3e-4,
        "k_load": 0.000535,
        "arm_cd": 1.0,
    },
    # Scale-up R = 2.7179 m machine.
    "scaleup": {
        "R": 2.7179, "c": 0.3861, "H": 4.0568, "N": 3,
        "ar": 0.3121, "sp": 0.2181,
        "mb": 0.92954, "xbcg": 0.20, "mc": 2.69306, "dcw": -0.1935,
        "balance": 0, "bias_deg": 0.0,
        "prescribe_pitch": False,
        "free": True, "tsr": 2.5, "T_max": 40.0, "stride": 8,
        "use_dynamic_stall": True,
        "use_flow_curvature": True,
        "use_tip_loss": True,
        "use_dmst": True,
        "win_deg": 45.0, "cb": 2e-5, "mu_c": 3e-4,
        "k_load": 4.164352,
        "arm_cd": 1.0,
    },
}

__all__ = ["PRESETS", "SHARP_BASELINE"]
