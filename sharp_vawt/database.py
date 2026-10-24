"""
sharp_vawt.database
===================

Airfoil polar database for the Sharp cycloturbine.

The canonical polar data live in ``sharp_vawt/airfoil_polars/naca0012/`` and are
resolved relative to this module (never the process working directory), so the
same tables are found from the repository root, ``scripts/``, or an external
working directory.

This module contains one and only one implementation of:

* :class:`PolarDatabase` (CSV loading, interpolation, provenance),
* the analytic NACA-0012 surrogate used when no CSV directory is supplied,
* the provisional flat-plate deep-stall helpers used by the polar generator.

No simulation kernel or configuration class lives here.
"""

from __future__ import annotations

import glob
import math
import os
import re
import warnings
from pathlib import Path

import numpy as np

from .config import (
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
    Geometry,
)

try:  # pragma: no cover - importlib.resources is stdlib on supported Pythons
    from importlib.resources import files as _resource_files  # noqa: F401  (reserved for future path resolution)
except ImportError:  # pragma: no cover
    pass

try:
    from numba import njit
    HAVE_NUMBA = True
except Exception:  # pragma: no cover - numba unavailable; graceful degradation  # noqa: BLE001
    HAVE_NUMBA = False

    def njit(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f


# =============================================================================
# SURROGATE POLAR MODEL (ANALYTIC NACA-0012-LIKE, NOT MEASURED DATA)
# =============================================================================

def surrogate_cla(Re: float) -> float:
    """Attached lift slope (per rad) as a function of Reynolds number."""
    return float(np.interp(math.log10(max(Re, 1.0)), _RE_PTS, _CLA))


def surrogate_polar(Re: float, alpha: float) -> tuple[float, float]:
    """Analytic NACA-0012-like surrogate over 360 deg (NOT measured data)."""
    lr = math.log10(max(Re, 1.0))
    cla = float(np.interp(lr, _RE_PTS, _CLA))
    clmax = float(np.interp(lr, _RE_PTS, _CLMAX))
    cd0 = float(np.interp(lr, _RE_PTS, _CD0))
    s = clmax / max(cla, 1e-9)
    a = np.arctan2(np.sin(alpha), np.cos(alpha))
    w = 1.0 / (1.0 + np.exp((np.abs(a) - s) / 0.04))
    cl_att = cla * np.sin(a) * np.cos(a)
    cl = w * cl_att + (1.0 - w) * np.sin(2.0 * a)
    cd = cd0 + w * 0.02 * cl_att ** 2 + (1.0 - w) * 1.98 * np.sin(a) ** 2
    return float(cl), float(cd)


# =============================================================================
# DEEP-STALL / FLAT-PLATE HELPERS (PROVISIONAL, UNVERIFIED)
# =============================================================================

def _deep_stall(abs_deg: float) -> tuple[float, float, float]:
    """Flat-plate deep-stall coefficients, SAND80-2114-anchored.

    PROVISIONAL: literature-typical amplitudes, not calibrated to data.
    """
    a = math.radians(abs_deg)
    cl = DEEP_STALL_CL_AMP * math.sin(2.0 * a)
    cd = DEEP_STALL_CD_AMP * math.sin(a) ** 2 + DEEP_STALL_CD_OFFSET
    cm = DEEP_STALL_CM_AMP * math.sin(a) ** 2
    return cl, cd, cm


def _synthetic_cm(abs_deg: float) -> float:
    """Abbott & von Doenhoff trend: Cm ~ 0 attached, -0.05 at 20 deg."""
    stall = 14.0
    if abs_deg <= stall:
        return -0.008 - 0.042 * (abs_deg / stall) ** 1.5
    if abs_deg <= 20.0:
        return -0.05
    if abs_deg <= 45.0:
        return -0.05 + 0.03 * (abs_deg - 20.0) / 25.0
    if abs_deg <= 90.0:
        return -0.02 + 0.01 * (abs_deg - 45.0) / 45.0
    return -0.01 * (180.0 - abs_deg) / 90.0


def _smoothstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 3.0 * t * t - 2.0 * t * t * t


def _neuralfoil_attached(nf, kulfan, re: float) -> dict[int, tuple[float, float, float]]:
    """NeuralFoil CL, CD, CM at 0..20 deg, indexed by integer angle."""
    out: dict[int, tuple[float, float, float]] = {}
    for a in range(21):
        r = nf.get_aero_from_kulfan_parameters(
            kulfan,
            alpha=float(a),
            Re=float(re),
            n_crit=9.0,
            model_size="xlarge",
        )
        out[a] = (float(r["CL"][0]), float(r["CD"][0]), float(r["CM"][0]))
    return out


def _normal_force_coefficient(abs_deg: float, cl: float, cd: float) -> float:
    """CN = Cl*cos(a) + Cd*sin(a) for a flat plate / symmetric airfoil."""
    a = math.radians(abs_deg)
    return cl * math.cos(a) + cd * math.sin(a)


def _post_stall_cm(abs_deg: float, cn: float, stall_deg: float) -> float:
    """Post-stall Cm from centre-of-pressure shift (x_cp: 0.25c -> 0.5c)."""
    if abs_deg <= stall_deg:
        return 0.0
    if abs_deg >= 90.0:
        x_cp = 0.5
    else:
        x_cp = 0.25 + 0.25 * (abs_deg - stall_deg) / (90.0 - stall_deg)
    return -cn * (x_cp - 0.25)


# =============================================================================
# INTERPOLATION
# =============================================================================

@njit(cache=True)
def _lookup(logRe, alpha, logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t, Cm_t=None):
    """Bilinear lookup on uniform alpha and log-Re grids.

    Returns ``(Cl, Cd, Cm, Cl_alpha)``.  Kept NumPy-only so it can be reused by
    tests and by the polar generator.
    """
    nRe = Cl_t.shape[0]
    nA = Cl_t.shape[1]
    a = min(max(alpha, alpha_grid[0]), alpha_grid[nA - 1])
    ia = (a - alpha_grid[0]) / (alpha_grid[nA - 1] - alpha_grid[0]) * (nA - 1)
    i0 = min(int(ia), nA - 2)
    i1 = i0 + 1
    wa = ia - i0
    if nRe == 1:
        j0 = j1 = 0
        wr = 0.0
    else:
        lr = min(max(logRe, logRe_grid[0]), logRe_grid[nRe - 1])
        ir = (lr - logRe_grid[0]) / (logRe_grid[nRe - 1] - logRe_grid[0]) * (nRe - 1)
        j0 = min(int(ir), nRe - 2)
        j1 = j0 + 1
        wr = ir - j0
    Cl = (Cl_t[j0, i0] * (1.0 - wa) * (1.0 - wr) + Cl_t[j0, i1] * wa * (1.0 - wr)
          + Cl_t[j1, i0] * (1.0 - wa) * wr + Cl_t[j1, i1] * wa * wr)
    Cd = (Cd_t[j0, i0] * (1.0 - wa) * (1.0 - wr) + Cd_t[j0, i1] * wa * (1.0 - wr)
          + Cd_t[j1, i0] * (1.0 - wa) * wr + Cd_t[j1, i1] * wa * wr)
    Cm = 0.0
    if Cm_t is not None:
        Cm = (Cm_t[j0, i0] * (1.0 - wa) * (1.0 - wr) + Cm_t[j0, i1] * wa * (1.0 - wr)
              + Cm_t[j1, i0] * (1.0 - wa) * wr + Cm_t[j1, i1] * wa * wr)
    cla = cla_re[j0] * (1.0 - wr) + cla_re[j1] * wr
    return Cl, Cd, Cm, cla


# =============================================================================
# POLAR DATABASE
# =============================================================================

class PolarDatabase:
    """Static polar tables (Cl, Cd, Cm over log Re x alpha)."""

    def __init__(self, polar_dir: str = DEFAULT_POLAR_DIR, geo: Geometry | None = None,
                 variant: str = "neuralfoil"):
        if variant not in POLAR_VARIANTS:
            raise ValueError(
                f"PolarDatabase: unknown polar variant {variant!r}; "
                f"choose one of {POLAR_VARIANTS}"
            )
        self.variant = variant

        resolved = self._resolve_dir(polar_dir)
        self.polar_dir = resolved
        self.alpha_grid = np.radians(np.linspace(-180.0, 180.0, 721))

        files = sorted(glob.glob(os.path.join(resolved, "*.csv"))) if resolved else []

        if files:
            self._load_csv(files)
            self.source = "csv:" + str(polar_dir)
        else:
            if polar_dir:
                warnings.warn(
                    f"PolarDatabase: no CSVs found in '{resolved}'. "
                    f"Falling back to the analytic NACA-0012 surrogate. "
                    f"Results are NOT based on the committed polar tables. "
                    f"Check that {resolved}/*.csv exist.",
                    RuntimeWarning,
                    stacklevel=2,
                )
            self.logRe_grid = np.log(np.array([2e4, 6.3e4, 2e5, 6.3e5, 2e6]))
            Cl = np.zeros((len(self.logRe_grid), len(self.alpha_grid)))
            Cd = np.zeros_like(Cl)
            Cm = np.zeros_like(Cl)
            for r, lre in enumerate(self.logRe_grid):
                Cl[r], Cd[r] = surrogate_polar(math.exp(lre), self.alpha_grid)
            self.Cl, self.Cd, self.Cm = Cl, Cd, Cm
            self.cla_re = np.array([surrogate_cla(math.exp(l)) for l in self.logRe_grid])
            self.source = "analytic surrogate"
        self._finish()

    @staticmethod
    def _resolve_dir(polar_dir: str) -> str:
        """Resolve ``polar_dir`` relative to the package, never the cwd."""
        if not polar_dir:
            return ""
        expanded = os.path.expanduser(str(polar_dir))
        if os.path.isabs(expanded):
            return expanded
        package_root = Path(__file__).resolve().parent
        return str(package_root / expanded)

    @classmethod
    def from_callable(cls, fn, cla: float, geo: Geometry | None = None):
        """Build a Re-independent table from ``fn(alpha_array) -> (Cl, Cd)``."""
        self = cls.__new__(cls)
        self.variant = "callable"
        self.polar_dir = ""
        self.alpha_grid = np.radians(np.linspace(-180.0, 180.0, 721))
        self.logRe_grid = np.array([math.log(1e5)])
        cl, cd = fn(self.alpha_grid)
        self.Cl, self.Cd = np.array([cl]), np.array([cd])
        self.Cm = np.zeros_like(self.Cl)
        self.cla_re = np.array([float(cla)])
        self.source = "callable"
        self._finish()
        return self

    def lookup(self, Re: float, alpha: float) -> tuple[float, float, float, float]:
        """Bilinear lookup of ``(Cl, Cd, Cm, Cl_alpha)`` at given Re and alpha."""
        return _lookup(math.log(max(Re, 1e3)), alpha,
                       self.logRe_grid, self.alpha_grid,
                       self.cla_re, self.Cl, self.Cd, self.Cm)

    def _load_csv(self, files: list[str]):
        res, cls_, cds, cms = [], [], [], []
        ag = np.degrees(self.alpha_grid)
        for f in files:
            m = re.search(r"[Rr][Ee]_(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", os.path.basename(f))
            if not m:
                continue
            Re = float(m.group(1))
            d = np.genfromtxt(f, delimiter=",", comments="#")
            d = d[~np.isnan(d).any(axis=1)] if d.ndim == 2 else d
            a, cl, cd = d[:, 0], d[:, 1], d[:, 2]
            # Column 3 is the default (physical, Cm=0 attached) table;
            # column 4 is the raw NeuralFoil Cm used by the sensitivity variant.
            cm_default = d[:, 3] if d.shape[1] >= 4 else np.zeros_like(a)
            cm_nf = d[:, 4] if d.shape[1] >= 5 else cm_default
            cm = cm_nf if self.variant == "neuralfoil_cm" else cm_default
            o = np.argsort(a)
            res.append(Re)
            cls_.append(np.interp(ag, a[o], cl[o]))
            cds.append(np.interp(ag, a[o], cd[o]))
            cms.append(np.interp(ag, a[o], cm[o]))
        if not res:
            raise ValueError(f"PolarDatabase: no usable Re numbers found in {files}")
        o = np.argsort(res)
        self.logRe_grid = np.log(np.array(res)[o])
        self.Cl = np.array(cls_)[o]
        self.Cd = np.array(cds)[o]
        self.Cm = np.array(cms)[o]
        if self.variant == "smoothed_lowRe":
            self._apply_smoothed_low_re(np.array(res)[o])
        sel = np.abs(ag) <= 4.0
        self.cla_re = np.array([np.polyfit(self.alpha_grid[sel], self.Cl[r][sel], 1)[0]
                                for r in range(len(res))])
        if len(self.logRe_grid) > 1:
            d = np.diff(self.logRe_grid)
            if np.max(np.abs(d - d[0])) > 1e-6:      # kernel assumes a uniform log-Re grid
                lg = np.linspace(self.logRe_grid[0], self.logRe_grid[-1], len(self.logRe_grid))
                self.Cl = np.array([[np.interp(l, self.logRe_grid, self.Cl[:, i])
                                     for i in range(self.Cl.shape[1])] for l in lg])
                self.Cd = np.array([[np.interp(l, self.logRe_grid, self.Cd[:, i])
                                     for i in range(self.Cd.shape[1])] for l in lg])
                self.Cm = np.array([[np.interp(l, self.logRe_grid, self.Cm[:, i])
                                     for i in range(self.Cm.shape[1])] for l in lg])
                self.cla_re = np.interp(lg, self.logRe_grid, self.cla_re)
                self.logRe_grid = lg

    def _apply_smoothed_low_re(self, re_rows: np.ndarray):
        """Cap low-Re attached lift and remove the laminar-bubble kink.

        Model-form sensitivity variant, NOT data.  For Re <= 1e5 and
        |alpha| <= 20 deg the lift magnitude is capped by
        ``2*pi*1.1*sin(a)*cos(a)`` and made monotone in |alpha|.  Higher-Re
        rows and the drag/moment columns are untouched.
        """
        ag = np.degrees(self.alpha_grid)
        for r, Re in enumerate(re_rows):
            if Re > _SMOOTH_LOW_RE_MAX_RE:
                continue
            for sgn, mask in ((1.0, (ag >= 0.0) & (ag <= 20.0)),
                              (-1.0, (ag < 0.0) & (ag >= -20.0))):
                idx = np.where(mask)[0]
                if len(idx) == 0:
                    continue
                order = idx[np.argsort(np.abs(ag[idx]))]
                a = np.radians(np.abs(ag[order]))
                vals = sgn * self.Cl[r, order]
                cap = _SMOOTH_LOW_RE_CAP * np.sin(a) * np.cos(a)
                vals = np.minimum(vals, cap)
                vals = np.maximum.accumulate(vals)
                self.Cl[r, order] = sgn * vals

    def _finish(self):
        self.Cl = np.ascontiguousarray(self.Cl, dtype=np.float64)
        self.Cd = np.ascontiguousarray(self.Cd, dtype=np.float64)
        self.Cm = np.ascontiguousarray(self.Cm, dtype=np.float64)
        self.logRe_grid = np.ascontiguousarray(self.logRe_grid, dtype=np.float64)
        self.cla_re = np.ascontiguousarray(self.cla_re, dtype=np.float64)
        sel = np.abs(self.alpha_grid) <= math.radians(30.0)
        self.Cl_max = float(np.max(np.abs(self.Cl[:, sel])))
        self.Cd_min = float(np.min(self.Cd[:, sel]))
        self.alpha_stall = float(self.alpha_grid[sel][np.argmax(self.Cl[-1][sel])])
        self.Cl_alpha = float(np.mean(self.cla_re))


__all__ = [
    "PolarDatabase",
    "_deep_stall",
    "_lookup",
    "_neuralfoil_attached",
    "_normal_force_coefficient",
    "_post_stall_cm",
    "_smoothstep",
    "_synthetic_cm",
    "surrogate_cla",
    "surrogate_polar",
]
