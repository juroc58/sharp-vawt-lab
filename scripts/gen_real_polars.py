#!/usr/bin/env python3
"""Generate NACA 0012 polar tables for the VAWT solver.

Method
------
* ``|alpha| <= 20 deg``: NeuralFoil 0.3.x, the XFOIL-trained neural network
  (Sharpe et al., 2024), evaluated at each target Reynolds number with
  ``n_crit = 9`` and the ``xlarge`` model. This fixes the attached-flow drag,
  which the previous hand-fitted tables over-predicted by 2.5-4x.
* ``20 deg < |alpha| < 45 deg``: smoothstep blend between the NeuralFoil value
  at 20 deg and a flat-plate deep-stall model at 45 deg.
* ``|alpha| >= 45 deg``: flat-plate deep-stall model,
  ``CL = 0.65 sin(2a)``, ``CD = 1.7 sin^2(a)``, anchored to the
  Sheldahl & Klimas (1981) SAND80-2114 trends (CD(90 deg) ~ 1.7,
  CD(150 deg) ~ 0.4, CL(120-150 deg) ~ -0.56).
* ``Cm``: synthetic Abbott & von Doenhoff trend (near zero attached,
  nose-down in stall). It is **not** measured data; see
  ``airfoil_polars/README.md``.

NeuralFoil's ``CM`` output is not used: its sign convention disagrees with
the moment convention used by this solver, and the network's post-stall
moment is not validated. Keeping a documented synthetic Cm is more honest
than silently mixing conventions.

Reproduce
---------
    pip install neuralfoil
    python3 scripts/gen_real_polars.py

The script needs only ``numpy`` and ``neuralfoil``. When the real
``aerosandbox`` package is absent, a minimal NumPy-backed shim is injected
for the two helpers NeuralFoil's core uses (``sind``/``cosd``/``swish``).
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_OUT_DIR = os.path.join(_ROOT, "airfoil_polars", "naca0012")

RE_LIST = [100_000, 200_000, 400_000, 1_000_000]
ALPHA_ATTACHED_LIMIT = 20.0
ALPHA_DEEP_STALL = 45.0
N_CRIT = 9.0          # standard wind-tunnel / e^9 transition criterion
MODEL_SIZE = "xlarge"


# ---------------------------------------------------------------------------
# NeuralFoil bootstrap
# ---------------------------------------------------------------------------
def _install_aerosandbox_shim() -> bool:
    """Provide the tiny slice of aerosandbox.numpy that NeuralFoil imports.

    Returns True if a shim was installed (i.e. real aerosandbox was absent).
    """
    try:
        import aerosandbox  # noqa: F401
        return False
    except ImportError:
        pass

    import types

    pkg = types.ModuleType("aerosandbox")
    num = types.ModuleType("aerosandbox.numpy")
    num.__dict__.update(
        {k: v for k, v in np.__dict__.items() if not k.startswith("_")}
    )

    def _deg(fn):
        return lambda x: fn(np.deg2rad(x))

    num.cosd = _deg(np.cos)
    num.sind = _deg(np.sin)
    num.tand = _deg(np.tan)

    def swish(x):
        return x / (1.0 + np.exp(-np.clip(x, -500, 500)))

    def length(x):
        return np.size(x)

    def atleast1d(x):
        return np.atleast_1d(x)

    num.swish = swish
    num.length = length
    num.atleast1d = atleast1d
    pkg.numpy = num
    sys.modules["aerosandbox"] = pkg
    sys.modules["aerosandbox.numpy"] = num
    return True


def _load_neuralfoil():
    try:
        import neuralfoil  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment issue
        raise RuntimeError(
            "NeuralFoil is required to regenerate the polars.\n"
            "Install it with:  pip install neuralfoil\n"
            "The committed CSVs can still be used without regenerating them."
        ) from exc
    return neuralfoil


# ---------------------------------------------------------------------------
# NACA 0012 geometry -> Kulfan (CST) weights
# ---------------------------------------------------------------------------
def naca0012_half_thickness(x):
    """Closed-trailing-edge NACA 0012 half-thickness distribution."""
    x = np.asarray(x, dtype=float)
    return 0.6 * (
        0.2969 * np.sqrt(x)
        - 0.1260 * x
        - 0.3516 * x**2
        + 0.2843 * x**3
        - 0.1036 * x**4
    )


def _bernstein(x, n=8):
    from math import comb

    x = np.asarray(x, dtype=float)
    return np.stack(
        [comb(n - 1, i) * x**i * (1.0 - x) ** (n - 1 - i) for i in range(n)],
        axis=1,
    )


def kulfan_parameters():
    """Least-squares CST fit of the NACA 0012 thickness distribution."""
    x = np.linspace(1e-6, 1.0, 4000)
    basis = np.sqrt(x)[:, None] * (1.0 - x)[:, None] * _bernstein(x, 8)
    weights, *_ = np.linalg.lstsq(basis, naca0012_half_thickness(x), rcond=None)
    fit_err = float(np.max(np.abs(basis @ weights - naca0012_half_thickness(x))))
    return dict(
        upper_weights=weights,
        lower_weights=-weights,
        leading_edge_weight=0.0,
        TE_thickness=0.0,
    ), fit_err


# ---------------------------------------------------------------------------
# Polar model
# ---------------------------------------------------------------------------
def _smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return 3.0 * t * t - 2.0 * t * t * t


def _deep_stall(abs_deg):
    """Flat-plate deep-stall coefficients, SAND80-2114-anchored."""
    a = math.radians(abs_deg)
    cl = 0.65 * math.sin(2.0 * a)
    cd = 1.66 * math.sin(a) ** 2 + 0.02
    # Synthetic moment: near zero attached, nose-down through the stall band.
    cm = -0.05 * math.sin(a) ** 2
    return cl, cd, cm


def _synthetic_cm(abs_deg):
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


def _neuralfoil_attached(nf, kulfan, re):
    """NeuralFoil CL, CD at 0..20 deg. Returns list indexed by integer angle."""
    out = {}
    for a in range(0, int(ALPHA_ATTACHED_LIMIT) + 1):
        r = nf.get_aero_from_kulfan_parameters(
            kulfan,
            alpha=float(a),
            Re=float(re),
            n_crit=N_CRIT,
            model_size=MODEL_SIZE,
        )
        out[a] = (float(r["CL"][0]), float(r["CD"][0]))
    return out


def make_polar(Re, nf, kulfan):
    """Return a list of (alpha_deg, Cl, Cd, Cm) on a 1-degree grid."""
    nf_attached = _neuralfoil_attached(nf, kulfan, Re)
    rows = []
    for alpha in range(-180, 181):
        abs_a = abs(alpha)
        sgn = 1.0 if alpha >= 0 else -1.0

        if abs_a <= ALPHA_ATTACHED_LIMIT:
            cl, cd = nf_attached[int(abs_a)]
        elif abs_a < ALPHA_DEEP_STALL:
            cl20, cd20 = nf_attached[int(ALPHA_ATTACHED_LIMIT)]
            cl45, cd45, _ = _deep_stall(ALPHA_DEEP_STALL)
            w = _smoothstep((abs_a - ALPHA_ATTACHED_LIMIT)
                            / (ALPHA_DEEP_STALL - ALPHA_ATTACHED_LIMIT))
            cl = cl20 + (cl45 - cl20) * w
            cd = cd20 + (cd45 - cd20) * w
        else:
            cl, cd, _ = _deep_stall(float(abs_a))

        cm = _synthetic_cm(float(abs_a))
        rows.append((float(alpha), sgn * cl, cd, sgn * cm))
    return rows


def write_csv(Re, rows):
    path = os.path.join(_OUT_DIR, f"polars_naca0012_Re_{int(Re)}.csv")
    with open(path, "w") as fh:
        fh.write(
            f"# NACA 0012, Re = {Re:.1e}\n"
            f"# Cl/Cd: NeuralFoil (XFOIL-trained) for |alpha|<=20 deg; "
            f"flat-plate deep stall beyond\n"
            f"# Cm: synthetic Abbott & von Doenhoff trend (not measured)\n"
            f"# alpha_deg, Cl, Cd, Cm\n"
        )
        for alpha, cl, cd, cm in rows:
            fh.write(f"{alpha:.1f}, {cl:.6f}, {cd:.6f}, {cm:.6f}\n")
    print(f"  wrote {path} ({len(rows)} points)")


def main():
    shimmed = _install_aerosandbox_shim()
    nf = _load_neuralfoil()
    kulfan, fit_err = kulfan_parameters()
    try:
        nf_version = importlib.metadata.version("neuralfoil")
    except importlib.metadata.PackageNotFoundError:
        nf_version = "unknown"

    print("Generating NACA 0012 polars with NeuralFoil")
    print(f"  NeuralFoil {nf_version}, n_crit={N_CRIT}, model={MODEL_SIZE}")
    print(f"  CST fit max error: {fit_err:.2e} chord")
    print(f"  aerosandbox shim installed: {shimmed}")

    os.makedirs(_OUT_DIR, exist_ok=True)
    for Re in RE_LIST:
        write_csv(Re, make_polar(Re, nf, kulfan))

    provenance = dict(
        generator="scripts/gen_real_polars.py",
        method=(
            "CL/CD: NeuralFoil (XFOIL-trained) for |alpha|<=20 deg; "
            "smoothstep to flat-plate deep-stall model for 20<|alpha|<45 deg; "
            "flat-plate model beyond. CD(90 deg)~1.7, CD(150 deg)~0.4, "
            "CL(120-150 deg)~-0.56, anchored to Sheldahl & Klimas (1981)."
        ),
        cm_method="synthetic Abbott & von Doenhoff trend (not measured)",
        neuralfoil_version=nf_version,
        n_crit=N_CRIT,
        model_size=MODEL_SIZE,
        aerosandbox_shim=shimmed,
        cst_fit_max_error_chord=fit_err,
        reynolds=RE_LIST,
        note=(
            "These tables are not raw experimental data. The attached-flow "
            "Cl/CD come from an XFOIL-trained surrogate; deep-stall and Cm "
            "are analytic trends."
        ),
    )
    with open(os.path.join(_ROOT, "airfoil_polars", "provenance.json"), "w") as fh:
        json.dump(provenance, fh, indent=2)
        fh.write("\n")
    print("  wrote airfoil_polars/provenance.json")


if __name__ == "__main__":
    main()
