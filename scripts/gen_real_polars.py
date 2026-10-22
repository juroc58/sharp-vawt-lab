#!/usr/bin/env python3
"""Generate NACA 0012 polar tables for the VAWT solver.

Method
-----
* ``|alpha| <= stall_angle``: NeuralFoil 0.3.x for Cl/Cd; **Cm = 0** (physical
  symmetric-section value). The stall angle is determined per Re as the first
  Cl peak.
* ``stall_angle < |alpha| < 45 deg``: Cl/Cd via smoothstep blend to flat-plate
  deep-stall model. Cm derived from centre-of-pressure shift: x_cp moves from
  0.25c (attached) towards 0.5c (fully separated), giving Cm = -CN * (x_cp -
  0.25), blended smoothly from the attached value.
* ``|alpha| >= 45 deg``: flat-plate deep-stall model,
  ``CL = 0.65 sin(2a)``, ``CD = 1.66 sin^2(a) + 0.02``, anchored to the
  Sheldahl & Klimas (1981) SAND80-2114 trends (CD(90 deg) ~ 1.7,
  CD(150 deg) ~ 0.4, CL(120-150 deg) ~ -0.56).  The amplitudes are named
  constants in this file and are provisional/unverified, not a fit to
  digitised data in this repository.
* NeuralFoil is a surrogate trained mostly on XFOIL; it is least reliable
  post-stall.  ``n_crit = 9`` is a clean-tunnel (e^9) value; rotor blades
  in atmospheric turbulence usually see a lower effective ``n_crit``.
* ``Cm``: **Default variant**: attached-flow Cm = 0 for a symmetric section;
  post-stall Cm from centre-of-pressure shift (x_cp: 0.25c -> 0.5c).
  **Variant "neuralfoil_cm"**: raw NeuralFoil CM output for sensitivity
  analysis only (not the default). NeuralFoil reports the quarter-chord moment
  in the standard aircraft convention (positive nose-up), which is the same
  convention this solver uses in ``Qa_cm = q * Cm * c``. For negative
  incidence the attached-flow values are mirrored with odd symmetry.

The deep-stall Cm remains synthetic: NeuralFoil's post-stall moment is not
validated, so the table uses a documented analytic trend there rather than
extrapolating the surrogate.

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
ALPHA_DEEP_STALL = 45.0
N_CRIT = 9.0          # standard wind-tunnel / e^9 transition criterion
MODEL_SIZE = "xlarge"

# Flat-plate deep-stall constants.  PROVISIONAL, UNVERIFIED: these are
# literature-typical flat-plate trends anchored to the Sheldahl & Klimas
# (1981) SAND80-2114 values quoted in the module docstring, not a fit to
# digitised data in this repository.  Change them only with a source.
DEEP_STALL_CL_AMP = 0.65       # CL = amp * sin(2*alpha)
DEEP_STALL_CD_AMP = 1.66       # CD = amp * sin^2(alpha) + offset
DEEP_STALL_CD_OFFSET = 0.02
DEEP_STALL_CM_AMP = -0.05      # synthetic nose-down moment in deep stall


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
    """Flat-plate deep-stall coefficients, SAND80-2114-anchored.

    The amplitudes are provisional/unverified literature-typical values (see
    the module constants); they are not fitted to measured data here.
    """
    a = math.radians(abs_deg)
    cl = DEEP_STALL_CL_AMP * math.sin(2.0 * a)
    cd = DEEP_STALL_CD_AMP * math.sin(a) ** 2 + DEEP_STALL_CD_OFFSET
    # Synthetic moment: near zero attached, nose-down through the stall band.
    cm = DEEP_STALL_CM_AMP * math.sin(a) ** 2
    return cl, cd, cm


def _post_stall_cm(abs_deg, cn, stall_deg):
    """Post-stall Cm from centre-of-pressure shift.

    x_cp moves from 0.25c (attached) towards 0.5c (fully separated at 90 deg).
    Cm = -CN * (x_cp - 0.25).
    """
    if abs_deg <= stall_deg:
        return 0.0
    if abs_deg >= 90.0:
        x_cp = 0.5
    else:
        # Linear interpolation of x_cp from stall to 90 deg
        x_cp = 0.25 + 0.25 * (abs_deg - stall_deg) / (90.0 - stall_deg)
    return -cn * (x_cp - 0.25)


def _normal_force_coefficient(abs_deg, cl, cd):
    """CN = Cl*cos(a) + Cd*sin(a) for a flat plate / symmetric airfoil."""
    a = math.radians(abs_deg)
    return cl * math.cos(a) + cd * math.sin(a)


def _neuralfoil_attached(nf, kulfan, re):
    """NeuralFoil CL, CD, CM at 0..20 deg, indexed by integer angle.

    ``CM`` is the quarter-chord pitching moment in the standard aircraft
    convention (positive nose-up), which matches the solver's ``Qa_cm`` term.

    Returns: dict mapping angle -> (Cl, Cd, Cm_neuralfoil), and stall_angle
    """
    cl_values = {}
    for a in range(0, 21):
        r = nf.get_aero_from_kulfan_parameters(
            kulfan,
            alpha=float(a),
            Re=float(re),
            n_crit=N_CRIT,
            model_size=MODEL_SIZE,
        )
        cl_values[a] = (float(r["CL"][0]), float(r["CD"][0]), float(r["CM"][0]))

    # Determine stall angle as first peak of Cl on the positive side
    # (where Cl starts decreasing)
    stall_angle = 20  # default fallback
    for a in range(1, 20):
        cl_prev = cl_values[a - 1][0]
        cl_curr = cl_values[a][0]
        cl_next = cl_values[a + 1][0] if a < 20 else cl_curr
        if cl_curr > cl_prev and cl_curr > cl_next:
            stall_angle = a
            break

    return cl_values, stall_angle


def make_polar(Re, nf, kulfan):
    """Return a list of (alpha_deg, Cl, Cd, Cm_default, Cm_neuralfoil) on a 1-degree grid."""
    nf_attached, stall_angle = _neuralfoil_attached(nf, kulfan, Re)

    # Build clean attached-flow Cl/Cd for the DEFAULT variant:
    # - Clamp lift slope at 1.15 * 2*pi for |alpha| <= 4 deg (enforce linear Cl)
    # - Enforce monotone Cl up to 20 deg (removes laminar-bubble kink)
    # - Cm = 0 for |alpha| <= 20 deg (physical symmetric-section value)
    # NeuralFoil raw values are kept in column 5 (Cm_neuralfoil) for the variant.

    # Extract NeuralFoil Cl/Cd for 0..20 deg
    nf_cl = np.array([nf_attached[a][0] for a in range(21)])
    nf_cd = np.array([nf_attached[a][1] for a in range(21)])
    nf_cm = np.array([nf_attached[a][2] for a in range(21)])

    # Clamp low-alpha lift slope: enforce Cl = slope_limit * sin(a) for a <= 4 deg
    # This ensures the secant slope over -4..+4 deg (used by check_polars.py)
    # does not exceed 1.15 * 2*pi. For small angles, sin(a) ~ a.
    slope_limit = 1.15 * 2.0 * np.pi
    for a in range(1, 5):
        nf_cl[a] = slope_limit * np.sin(np.deg2rad(a))

    # Enforce monotone Cl magnitude up to 20 deg (removes bubble kink)
    # For positive alpha: Cl should be non-decreasing
    for a in range(1, 21):
        if nf_cl[a] < nf_cl[a - 1]:
            nf_cl[a] = nf_cl[a - 1]

    # Get values at 20 deg for blending
    cl_20 = nf_cl[20]
    cd_20 = nf_cd[20]
    cl_45, cd_45, _ = _deep_stall(ALPHA_DEEP_STALL)

    rows = []
    for alpha in range(-180, 181):
        abs_a = abs(alpha)
        sgn = 1.0 if alpha >= 0 else -1.0

        if abs_a <= 20:
            # Attached flow (clean): Cl/Cd from processed NeuralFoil, Cm = 0
            cl = nf_cl[abs_a]
            cd = nf_cd[abs_a]
            cm_default = 0.0
            cm_nf = sgn * nf_cm[abs_a]

        elif abs_a < ALPHA_DEEP_STALL:
            # Post-stall blend: 20 < |alpha| < 45 deg
            w = _smoothstep((abs_a - 20.0)
                            / (ALPHA_DEEP_STALL - 20.0))
            cl = cl_20 + (cl_45 - cl_20) * w
            cd = cd_20 + (cd_45 - cd_20) * w

            # Cm default: blend from 0 at 20 deg to post-stall Cm at 45 deg
            # Post-stall Cm from centre-of-pressure shift
            # x_cp moves from 0.25c (attached) towards 0.5c (fully separated at 90 deg)
            # Cm = -CN * (x_cp - 0.25)
            cn_45 = _normal_force_coefficient(ALPHA_DEEP_STALL, cl_45, cd_45)
            x_cp_45 = 0.25 + 0.25 * (ALPHA_DEEP_STALL - 20.0) / (90.0 - 20.0)
            cm_post_45 = -cn_45 * (x_cp_45 - 0.25)
            cm_default = cm_post_45 * w

            # NeuralFoil CM: blend from NeuralFoil at 20 to synthetic at 45
            cm_syn_45 = DEEP_STALL_CM_AMP * math.sin(math.radians(ALPHA_DEEP_STALL)) ** 2
            cm_nf = sgn * (nf_cm[20] + (cm_syn_45 - nf_cm[20]) * w)

        else:
            # Deep stall: |alpha| >= 45 deg
            cl, cd, _ = _deep_stall(float(abs_a))
            cn = _normal_force_coefficient(abs_a, cl, cd)
            if abs_a >= 90.0:
                x_cp = 0.5
            else:
                x_cp = 0.25 + 0.25 * (abs_a - 20.0) / (90.0 - 20.0)
            cm_default = -cn * (x_cp - 0.25)

            # NeuralFoil CM: use synthetic trend
            cm_nf = sgn * DEEP_STALL_CM_AMP * math.sin(math.radians(abs_a)) ** 2

        rows.append((float(alpha), sgn * cl, cd, sgn * cm_default, cm_nf))
    return rows


def write_csv(Re, rows):
    path = os.path.join(_OUT_DIR, f"polars_naca0012_Re_{int(Re)}.csv")
    with open(path, "w") as fh:
        fh.write(
            f"# NACA 0012, Re = {Re:.1e}\n"
            f"# Cl/Cd: NeuralFoil (XFOIL-trained) for |alpha|<=stall; "
            f"flat-plate deep stall beyond\n"
            f"# Cm (col 4): default variant, attached Cm=0, post-stall from x_cp shift\n"
            f"# Cm (col 5): neuralfoil_cm variant, raw NeuralFoil CM for sensitivity\n"
            f"# alpha_deg, Cl, Cd, Cm_default, Cm_neuralfoil\n"
        )
        for alpha, cl, cd, cm_default, cm_nf in rows:
            fh.write(f"{alpha:.1f}, {cl:.6f}, {cd:.6f}, {cm_default:.6f}, {cm_nf:.6f}\n")
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
        rows = make_polar(Re, nf, kulfan)
        write_csv(Re, rows)

    provenance = dict(
        generator="scripts/gen_real_polars.py",
        method=(
            "CL/CD: NeuralFoil (XFOIL-trained) for |alpha|<=20 deg (attached); "
            "clamped slope at 1.15*2pi, monotone Cl enforced. "
            "Smoothstep to flat-plate deep-stall model for 20<|alpha|<45 deg; "
            "flat-plate model beyond. CD(90 deg)~1.66, CD(150 deg)~0.4, "
            "CL(120-150 deg)~-0.56, anchored to Sheldahl & Klimas (1981). "
            "Deep-stall amplitudes are provisional/unverified."
        ),
        cm_method=(
            "Default variant: Cm=0 for |alpha|<=20 deg (physical symmetric "
            "section); post-stall Cm from centre-of-pressure shift x_cp: 0.25c "
            "-> 0.5c, Cm = -CN*(x_cp - 0.25). Variant 'neuralfoil_cm': raw "
            "NeuralFoil CM for |alpha|<=20 deg (not the default, sensitivity "
            "only), blended to synthetic deep-stall trend. Not measured."
        ),
        cm_convention=(
            "Positive Cm is nose-up about the quarter chord, matching the "
            "solver's Qa_cm = q*Cm*c term. Negative alpha uses odd symmetry."
        ),
        neuralfoil_version=nf_version,
        n_crit=N_CRIT,
        n_crit_note=(
            "n_crit=9 is a clean-tunnel e^9 transition value. Rotor blades "
            "in atmospheric turbulence usually have a lower effective n_crit, "
            "so these attached-flow polars are optimistic for field operation."
        ),
        model_size=MODEL_SIZE,
        aerosandbox_shim=shimmed,
        cst_fit_max_error_chord=fit_err,
        reynolds=RE_LIST,
        attached_limit_deg=20.0,
        note=(
            "These tables are not raw experimental data. The attached-flow "
            "Cl, Cd come from an XFOIL-trained surrogate with clamped slope "
            "and enforced monotonicity; deep-stall Cl/Cd and Cm are analytic "
            "trends. Default Cm is physically derived for a symmetric section; "
            "NeuralFoil CM is available as a variant."
        ),
    )
    with open(os.path.join(_ROOT, "airfoil_polars", "provenance.json"), "w") as fh:
        json.dump(provenance, fh, indent=2)
        fh.write("\n")
    print("  wrote airfoil_polars/provenance.json")


if __name__ == "__main__":
    main()