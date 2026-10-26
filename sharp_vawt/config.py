"""
sharp_vawt.config
=================

Immutable configuration dataclasses for the Sharp cycloturbine model.

This module contains ONLY:

* numerical/model constants shared by the engine and the polar database,
* the four frozen dataclasses that describe a machine and a run,
* lightweight validation performed in ``__post_init__``.

It contains no physics kernel, no simulation class, no file I/O and no
factory function.  The sole factory is
:func:`sharp_vawt.engine.create_sim_from_params`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

PI = math.pi
TWO_PI = 2.0 * PI
NU_AIR = 1.5e-5

# Analytic surrogate polar support points (log10(Re), attached slope, Clmax, Cd0).
_RE_PTS = np.log10([5e4, 1e5, 3e5, 1e6, 1e7])
_CLA = [5.0, 5.5, 5.9, 6.06, 6.06]        # per rad
_CLMAX = [0.80, 0.90, 1.15, 1.40, 1.50]
_CD0 = [0.020, 0.015, 0.010, 0.0075, 0.0065]

# Model-form variants for the CSV polars.
#   "neuralfoil"    committed table (default): physical Cm = 0 in attached flow
#   "neuralfoil_cm" raw NeuralFoil Cm, sensitivity only
#   "smoothed_lowRe" model-form sensitivity variant, NOT data
POLAR_VARIANTS = ("neuralfoil", "neuralfoil_cm", "smoothed_lowRe")
_SMOOTH_LOW_RE_CAP = 2.0 * math.pi * 1.1
_SMOOTH_LOW_RE_MAX_RE = 1.0e5

# Flat-plate deep-stall constants.  PROVISIONAL, UNVERIFIED: literature-typical
# trends anchored to Sheldahl & Klimas (1981) SAND80-2114, not a fit to data in
# this repository.  Do not treat these as calibrated.
DEEP_STALL_CL_AMP = 0.65       # CL = amp * sin(2*alpha)
DEEP_STALL_CD_AMP = 1.66       # CD = amp * sin^2(alpha) + offset
DEEP_STALL_CD_OFFSET = 0.02
DEEP_STALL_CM_AMP = -0.05      # synthetic nose-down moment in deep stall

# Column indices for the committed five-column polar CSVs:
#   alpha_deg, Cl, Cd, Cm_default, Cm_neuralfoil
COL_ALPHA = 0
COL_CL = 1
COL_CD = 2
COL_CM_DEFAULT = 3
COL_CM_NEURALFOIL = 4

# Default polar directory, relative to the ``sharp_vawt`` package directory.
DEFAULT_POLAR_DIR = "airfoil_polars/naca0012"

# Factory aliases (kept for backwards compatibility).
_ALIASES = {"bias": "bias_deg", "win": "win_deg"}


@dataclass(frozen=True)
class Geometry:
    """Neutral R = 0.6 m Sharp-inspired baseline.

    Larger or named machines live in :mod:`vawt_presets`; do not encode a
    scale-up design in these defaults.
    """

    R: float = 0.60
    c: float = 0.14
    H: float = 0.40
    N: int = 3
    ar: float = 0.50           # rocking arm / chord
    sp: float = 0.25           # spar position from LE / chord
    arm_d: float = 0.0         # support-arm width for drag (m)
    n_arm: int = 2             # arms per blade (top + bottom)
    arm_cd: float = 1.0

    def __post_init__(self):
        if self.c <= 0.0:
            raise ValueError("chord c must be positive")
        if self.R <= 0.0:
            raise ValueError("radius R must be positive")
        if self.H <= 0.0:
            raise ValueError("span H must be positive")
        if int(self.N) < 1:
            raise ValueError("blade count N must be >= 1")
        if self.c * self.ar >= self.R:
            raise ValueError("Rocking arm longer than rotor radius")
        if self.arm_d < 0.0:
            raise ValueError("arm_d must be non-negative")


@dataclass(frozen=True)
class MassProps:
    mb: float = 0.010
    xbcg: float = 0.20
    mc: float = 0.002
    dcw: float = 0.30
    # 0: use mc, dcw as given; 1: solve dcw from mc; 2: solve mc from dcw
    balance: int = 0
    bias_deg: float = 0.0
    J_hub: float = 0.02

    def __post_init__(self):
        if self.balance not in (0, 1, 2):
            raise ValueError("balance must be 0, 1 or 2")
        if self.mb < 0.0 or self.mc < 0.0:
            raise ValueError("masses must be non-negative")
        if self.J_hub < 0.0:
            raise ValueError("J_hub must be non-negative")


@dataclass(frozen=True)
class AeroConfig:
    # Folder of Re_<number>.csv files (alpha_deg, Cl, Cd, Cm_default,
    # Cm_neuralfoil); an empty string selects the analytic surrogate.
    polar_dir: str = DEFAULT_POLAR_DIR
    polar_variant: str = "neuralfoil"
    use_dynamic_stall: bool = True
    use_tip_loss: bool = True
    use_dmst: bool = True
    use_dynamic_inflow: bool = True
    use_flow_curvature: bool = True
    cd_add: float = 0.002               # strut / interference drag
    win_deg: float = 45.0
    wstop: float = 300.0
    cb: float = 2e-5
    kc: float = 0.0
    mu_c: float = 3e-4
    r_bearing: float = 0.002
    prescribe_pitch: bool = False
    pp0_deg: float = 0.0
    pp1_deg: float = 0.0
    pp2_deg: float = 0.0
    pp3_deg: float = 0.0
    pp_ph_deg: float = 0.0
    a_fix: float = 0.2                   # induction when use_dmst is False
    tau_rev: float = 0.1                 # induction lag in revolutions
    e_osw: float = 0.9
    ds_Tf: float = 3.0                   # separation lag (convective times c/W)
    ds_Tv: float = 6.0                   # vortex-lift lag
    ds_Ta: float = 0.1                   # attached-flow lag
    ds_Kv: float = 0.5                   # vortex-lift strength (0 disables)
    ds_Knc: float = 1.0                  # apparent-mass lift multiplier
    c_scale_override: float = 0.0        # 0 = geometry-derived
    tip_loss_floor_override: float = 0.0  # 0 = use Helmbold formula
    tip_loss_multiplier: float = 1.0     # residual multiplier on f_ar
    finite_span_model: str = "helmbold"   # "helmbold" | "prandtl_k2" | "prandtl_k18" | "prandtl_k15"
    ind_drag_scale: float = 1.0          # multiplier on induced drag term
    cm_scale: float = 1.0                # scale on polar Cm (0 = no moment)

    def __post_init__(self):
        if self.polar_variant not in POLAR_VARIANTS:
            raise ValueError(
                f"AeroConfig: unknown polar_variant {self.polar_variant!r}; "
                f"choose one of {POLAR_VARIANTS}"
            )
        if self.finite_span_model not in ("helmbold", "prandtl_k2", "prandtl_k18", "prandtl_k15"):
            raise ValueError(
                f"AeroConfig: unknown finite_span_model {self.finite_span_model!r}; "
                f"choose one of helmbold, prandtl_k2, prandtl_k18, prandtl_k15"
            )
        if self.ds_Tf <= 0.0 or self.ds_Tv <= 0.0 or self.ds_Ta <= 0.0:
            raise ValueError("dynamic-stall time constants must be positive")
        if self.tau_rev <= 0.0:
            raise ValueError("tau_rev must be positive")
        if not (0.0 < self.e_osw <= 1.0):
            raise ValueError("e_osw must lie in (0, 1]")
        if self.ind_drag_scale < 0.0:
            raise ValueError("ind_drag_scale must be non-negative")
        if self.cd_add < 0.0:
            raise ValueError("cd_add must be non-negative")


@dataclass(frozen=True)
class SimConfig:
    U: float = 8.0
    tsr: float = 2.0
    free: bool = False
    w0_frac: float = 0.9
    psi0_deg: float = 0.0
    dt: float = 2e-4
    T_max: float = 10.0
    stride: int = 5
    gust_g: float = 0.0
    gust_t0: float = 0.0
    gust_tg: float = 0.0
    turb_I: float = 0.0
    turb_L: float = 30.0
    turb_model: str = "dryden"   # "dryden" or "vonkarman"
    k_load: float = 0.0025
    rho: float = 1.225
    seed: int = 0
    n_rev_fixed: int = 16

    def __post_init__(self):
        if self.U < 0.0:
            raise ValueError("wind speed U must be non-negative")
        if self.dt <= 0.0:
            raise ValueError("time step dt must be positive")
        if int(self.stride) < 1:
            raise ValueError("stride must be >= 1")
        if self.T_max <= 0.0:
            raise ValueError("T_max must be positive")
        if self.rho <= 0.0:
            raise ValueError("air density rho must be positive")
        if self.turb_model not in ("dryden", "vonkarman"):
            raise ValueError("turb_model must be 'dryden' or 'vonkarman'")
        if self.turb_I < 0.0:
            raise ValueError("turb_I must be non-negative")
        if self.k_load < 0.0:
            raise ValueError("k_load must be non-negative")


__all__ = [
    "COL_ALPHA",
    "COL_CD",
    "COL_CL",
    "COL_CM_DEFAULT",
    "COL_CM_NEURALFOIL",
    "DEEP_STALL_CD_AMP",
    "DEEP_STALL_CD_OFFSET",
    "DEEP_STALL_CL_AMP",
    "DEEP_STALL_CM_AMP",
    "DEFAULT_POLAR_DIR",
    "NU_AIR",
    "PI",
    "POLAR_VARIANTS",
    "TWO_PI",
    "AeroConfig",
    "Geometry",
    "MassProps",
    "SimConfig",
]
