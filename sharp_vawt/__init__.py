"""
sharp_vawt
==========

A 2-D blade-element momentum (BEM) solver for the Sharp cycloturbine with
passive centrifugal-pendulum pitch control.

Module layout
-------------
* :mod:`sharp_vawt.config` — frozen dataclasses and constants (no physics).
* :mod:`sharp_vawt.database` — polar CSV loading/interpolation and provenance.
* :mod:`sharp_vawt.engine` — the one and only kernel, ``CycloturbineSim``, and
  ``create_sim_from_params``.

Example
-------
>>> from sharp_vawt import create_sim_from_params
>>> sim = create_sim_from_params({"R": 0.6, "H": 0.4, "c": 0.14, "free": True})
>>> result = sim.run()
>>> print(f"Cp = {result['cp']:.4f}")
"""

from __future__ import annotations

from .config import (
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
    POLAR_VARIANTS,
    AeroConfig,
    Geometry,
    MassProps,
    SimConfig,
)
from .database import (
    PolarDatabase,
    _deep_stall,
    _neuralfoil_attached,
    _normal_force_coefficient,
    _post_stall_cm,
    _smoothstep,
    _synthetic_cm,
    surrogate_cla,
    surrogate_polar,
)
from .engine import CycloturbineSim, create_sim_from_params

__version__ = "3.4.0"

__all__ = [
    "DEEP_STALL_CD_AMP",
    "DEEP_STALL_CD_OFFSET",
    "DEEP_STALL_CL_AMP",
    "DEEP_STALL_CM_AMP",
    "DEFAULT_POLAR_DIR",
    "POLAR_VARIANTS",
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
    "__version__",
    "_deep_stall",
    "_neuralfoil_attached",
    "_normal_force_coefficient",
    "_post_stall_cm",
    "_smoothstep",
    "_synthetic_cm",
    "create_sim_from_params",
    "surrogate_cla",
    "surrogate_polar",
]
