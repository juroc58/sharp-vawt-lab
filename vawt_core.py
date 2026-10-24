"""
vawt_core.py — backwards-compatibility re-export only
=====================================================

This module used to contain a full copy of the simulation kernel.  It is now a
thin facade over the single canonical implementation in :mod:`sharp_vawt`.

There is exactly ONE implementation of the physics:

* ``sharp_vawt.engine``  — ``_kernel``, ``CycloturbineSim``, ``create_sim_from_params``
* ``sharp_vawt.database`` — ``PolarDatabase`` and polar helpers
* ``sharp_vawt.config``  — dataclasses and constants

Do not add physics here.  New code should import from :mod:`sharp_vawt`.
"""

from __future__ import annotations

from sharp_vawt.config import (
    _ALIASES,
    _CD0,
    _CLA,
    _CLMAX,
    _RE_PTS,
    _SMOOTH_LOW_RE_CAP,
    _SMOOTH_LOW_RE_MAX_RE,
    DEEP_STALL_CD_AMP,
    DEEP_STALL_CD_OFFSET,
    DEEP_STALL_CL_AMP,
    DEEP_STALL_CM_AMP,
    DEFAULT_POLAR_DIR,
    NU_AIR,
    PI,
    POLAR_VARIANTS,
    TWO_PI,
    AeroConfig,
    Geometry,
    MassProps,
    SimConfig,
)
from sharp_vawt.database import (
    PolarDatabase,
    _deep_stall,
    _lookup,
    _neuralfoil_attached,
    _normal_force_coefficient,
    _post_stall_cm,
    _smoothstep,
    _synthetic_cm,
    surrogate_cla,
    surrogate_polar,
)
from sharp_vawt.engine import (
    OUT_COLS as ENGINE_OUT_COLS,
)
from sharp_vawt.engine import (
    CycloturbineSim,
    _aero_coeffs,
    _energy,
    _fstat,
    _kernel,
    _wrap,
    create_sim_from_params,
)

# Legacy column names for the same positional output produced by the canonical
# engine.  Positional order is the compatibility contract; names are metadata.
OUT_COLS = ["t", "th", "w", "psi", "beta", "alpha", "Tsum", "Qshaft",
            "a", "Fx", "P_blade", "psd"]

__all__ = [
    "DEEP_STALL_CD_AMP",
    "DEEP_STALL_CD_OFFSET",
    "DEEP_STALL_CL_AMP",
    "DEEP_STALL_CM_AMP",
    "DEFAULT_POLAR_DIR",
    "ENGINE_OUT_COLS",
    "NU_AIR",
    "OUT_COLS",
    "PI",
    "POLAR_VARIANTS",
    "TWO_PI",
    "_ALIASES",
    "_CD0",
    "_CLA",
    "_CLMAX",
    "_RE_PTS",
    "_SMOOTH_LOW_RE_CAP",
    "_SMOOTH_LOW_RE_MAX_RE",
    "AeroConfig",
    "CycloturbineSim",
    "Geometry",
    "MassProps",
    "PolarDatabase",
    "SimConfig",
    "_aero_coeffs",
    "_deep_stall",
    "_energy",
    "_fstat",
    "_kernel",
    "_lookup",
    "_neuralfoil_attached",
    "_normal_force_coefficient",
    "_post_stall_cm",
    "_smoothstep",
    "_synthetic_cm",
    "_wrap",
    "create_sim_from_params",
    "surrogate_cla",
    "surrogate_polar",
]
