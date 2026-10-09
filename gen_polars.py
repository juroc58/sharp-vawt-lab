# gen_polars.py
"""
Viterna-extended NACA-0012 polar generator for SHARP Cycloturbine.

v3.3 fix
--------
* `logRe.npy` now stores **natural log** of Re (previously it stored
  log10 which silently mismatched vawt_core's internal math.log(Re)).
* Correct print of the physical Re range.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

DEFAULT_N_RE = 12
DEFAULT_N_ALPHA = 361
DEFAULT_RE_MIN = 1.0e4
DEFAULT_RE_MAX = 1.0e7
DEFAULT_ALPHA_LIM_DEG = 180.0
DEFAULT_ASPECT_RATIO = 10.0
OUTPUT_DIR = Path("polars") / "naca0012"


def _cl_alpha_2d(re: float) -> float:
    if re < 5.0e4: return 5.4
    if re < 1.0e5: return 5.7
    if re < 5.0e5: return 5.9
    if re < 2.0e6: return 6.0
    return 6.1


def _stall_angle_deg(re: float) -> float:
    if re < 5.0e4: return 10.0
    if re < 1.0e5: return 12.0
    if re < 5.0e5: return 14.0
    if re < 2.0e6: return 15.5
    return 16.5


def _cd0(re: float) -> float:
    return 0.008 + 0.020 * math.exp(-(re - 1.0e4) / 5.0e4)


def _clmax(re: float) -> float:
    base = 1.35
    if re < 5.0e4: return 0.85 * base
    if re < 1.0e5: return 0.95 * base
    if re < 1.0e6: return base
    return 1.05 * base


def _cm_quarter(alpha_rad: np.ndarray) -> np.ndarray:
    return -0.02 * np.sin(2.0 * alpha_rad)


def _viterna_extension(alpha_rad, alpha_stall_rad, cl_stall, cd_stall,
                       aspect_ratio=DEFAULT_ASPECT_RATIO):
    cd_max = 1.11 + 0.018 * aspect_ratio
    b1 = cd_max
    a1 = 0.5 * b1
    s_s = math.sin(alpha_stall_rad)
    c_s = math.cos(alpha_stall_rad)
    a2 = (cl_stall - cd_max * s_s * c_s) * s_s / max(c_s * c_s, 1e-9)
    b2 = (cd_stall - cd_max * s_s * s_s) / max(c_s, 1e-9)
    s = np.sin(alpha_rad); c = np.cos(alpha_rad)
    s_safe = np.where(np.abs(s) < 1e-6, 1e-6, s)
    cl_ext = a1 * np.sin(2.0 * alpha_rad) + a2 * c * c / s_safe
    cd_ext = b1 * s * s + b2 * c
    return cl_ext, cd_ext


def generate_polar_tables(n_re=DEFAULT_N_RE,
                          n_alpha=DEFAULT_N_ALPHA,
                          re_min=DEFAULT_RE_MIN,
                          re_max=DEFAULT_RE_MAX,
                          alpha_lim_deg=DEFAULT_ALPHA_LIM_DEG,
                          aspect_ratio=DEFAULT_ASPECT_RATIO):
    # Natural-log grid (matches vawt_core's `math.log(Re)` lookup).
    re_grid = np.geomspace(re_min, re_max, n_re)
    log_re = np.log(re_grid)

    alpha_deg = np.linspace(-alpha_lim_deg, alpha_lim_deg, n_alpha)
    alpha_rad = np.radians(alpha_deg)

    cl_table = np.zeros((n_re, n_alpha))
    cd_table = np.zeros((n_re, n_alpha))
    cm_table = np.zeros((n_re, n_alpha))

    for i, re in enumerate(re_grid):
        cla = _cl_alpha_2d(re)
        a_stall = math.radians(_stall_angle_deg(re))
        cl_max = _clmax(re)
        cd_min = _cd0(re)
        cl_stall = cl_max
        cd_stall = cd_min + 0.020

        lin = np.abs(alpha_rad) <= a_stall
        cl_table[i, lin] = cla * alpha_rad[lin]
        cd_table[i, lin] = cd_min + 0.006 * alpha_rad[lin] ** 2

        post = ~lin
        cl_ext_pos, cd_ext_pos = _viterna_extension(
            np.abs(alpha_rad[post]), a_stall, cl_stall, cd_stall, aspect_ratio)
        sign = np.sign(alpha_rad[post]); sign[sign == 0.0] = 1.0
        cl_table[i, post] = sign * cl_ext_pos
        cd_table[i, post] = cd_ext_pos
        cm_table[i, :] = _cm_quarter(alpha_rad)

    return {"logRe": log_re.astype(np.float64),
            "alpha": alpha_rad.astype(np.float64),
            "Cl": cl_table, "Cd": cd_table, "Cm": cm_table}


def save_polar_tables(tables, output_dir=OUTPUT_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    np.save(output_dir / "logRe.npy", tables["logRe"])
    np.save(output_dir / "alpha.npy", tables["alpha"])
    np.save(output_dir / "Cl.npy", tables["Cl"])
    np.save(output_dir / "Cd.npy", tables["Cd"])
    np.save(output_dir / "Cm.npy", tables["Cm"])
    meta = {
        "airfoil": "NACA-0012",
        "nRe": int(tables["logRe"].size),
        "nAlpha": int(tables["alpha"].size),
        "Re_range": [float(np.exp(tables["logRe"][0])),
                     float(np.exp(tables["logRe"][-1]))],
        "alpha_range_deg": [float(np.degrees(tables["alpha"][0])),
                            float(np.degrees(tables["alpha"][-1]))],
        "alpha_units": "radians",
        "logRe_units": "natural log",
        "source": "gen_polars.py (Viterna-extended analytic model)",
    }
    with (output_dir / "meta.json").open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return output_dir


def polars_exist(output_dir=OUTPUT_DIR) -> bool:
    output_dir = Path(output_dir)
    return all((output_dir / n).exists() for n in
               ("logRe.npy", "alpha.npy", "Cl.npy", "Cd.npy", "Cm.npy"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-re", type=int, default=DEFAULT_N_RE)
    parser.add_argument("--n-alpha", type=int, default=DEFAULT_N_ALPHA)
    parser.add_argument("--re-min", type=float, default=DEFAULT_RE_MIN)
    parser.add_argument("--re-max", type=float, default=DEFAULT_RE_MAX)
    parser.add_argument("--aspect-ratio", type=float,
                        default=DEFAULT_ASPECT_RATIO)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if polars_exist(args.out) and not args.force:
        print(f"[gen_polars] tables already present in {args.out.resolve()}")
        return 0
    tables = generate_polar_tables(n_re=args.n_re, n_alpha=args.n_alpha,
                                   re_min=args.re_min, re_max=args.re_max,
                                   aspect_ratio=args.aspect_ratio)
    out = save_polar_tables(tables, args.out)
    print(f"[gen_polars] Wrote polar database to {out.resolve()}")
    print(f"[gen_polars] Re range   : "
          f"{np.exp(tables['logRe'][0]):.3e} → "
          f"{np.exp(tables['logRe'][-1]):.3e}")
    print(f"[gen_polars] α range    : "
          f"{np.degrees(tables['alpha'][0]):+.1f}° → "
          f"{np.degrees(tables['alpha'][-1]):+.1f}°")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())