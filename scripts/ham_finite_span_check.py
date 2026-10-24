#!/usr/bin/env python3
"""Ham 1979 finite-span check and reconciliation of the two Ham numbers.

Two Ham-family numbers appear in this project:

* ``scripts/validate_ham.py`` static-only peak with ``cd_add = 0.005``:
  the 2-D upper-bound comparison used in the validation gate.
* the UQ ``ham_1979`` anchor, whose preset omits ``cd_add`` and therefore
  uses the core default ``0.002``: the number quoted in the headline table.

They are not the same configuration.  This script runs both (plus dynamic
stall and the Helmbold finite-span correction) and writes one table.

Finite-span check
-----------------
Ham's tabulated geometry gives an aspect ratio H/c = 1.37/0.305 = 4.49.
The Ham 1979 paper itself is not in this repository, so the blade aspect
ratio is taken from the geometry table and an AR = 3..6 scan is also
reported.  The Helmbold-corrected peak is compared with Ham's measured
0.42-0.45 band.  The check is a plausibility test of the finite-span
model, not a validation of the rotor.

Writes ``scripts/ham_finite_span_check.json``.

Usage:
    python3 scripts/ham_finite_span_check.py
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from vawt_core import create_sim_from_params  # noqa: E402
from scripts.stamp import write_json_with_stamp
from scripts.stamp import write_json_with_stamp

R_HAM, C_HAM, H_HAM, N_HAM = 1.83, 0.305, 1.37, 3
AR_GEOMETRIC = H_HAM / C_HAM
HAM_BAND_LO, HAM_BAND_HI = 0.42, 0.45
HAM_MID = 0.5 * (HAM_BAND_LO + HAM_BAND_HI)
TSRS = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5)
AR_SCAN = (3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0)

BASE = dict(
    R=R_HAM, c=C_HAM, H=H_HAM, N=N_HAM,
    ar=0.0, sp=0.25,
    mb=0.010, xbcg=0.20, mc=0.002, dcw=0.30,
    balance=0, bias_deg=0.0,
    prescribe_pitch=True, pp0_deg=0.0, pp1_deg=-10.0,
    pp2_deg=0.0, pp3_deg=0.0, pp_ph_deg=0.0,
    free=False, tsr=2.5, T_max=20.0, stride=5,
    use_dmst=True, win_deg=89.0, cb=2e-5, mu_c=0.0,
    k_load=0.0004,
)


def sweep(**overrides):
    rows = []
    for tsr in TSRS:
        r = create_sim_from_params({**BASE, **overrides, "tsr": tsr}).run()
        rows.append(dict(tsr=tsr, cp=float(r["cp"]),
                         tsr_eq=float(r["tsr_eq"]),
                         steady=bool(r.get("steady", True))))
    return rows


def peak(rows):
    row = max(rows, key=lambda r: r["cp"])
    return float(row["cp"]), float(row["tsr"])


def derived_bias_window(peak_no_tip, peak_tip):
    """Expected 2-D bias window implied by the finite-span check.

    The no-tip solver must be at least as good as the measured 3-D rotor
    (lower bound 0 %).  The Helmbold correction magnitude
    ``peak_no_tip / peak_tip - 1`` is the model's own upper estimate of how
    much the missing finite-span loss could add.  It is an upper bound, not
    a validation tolerance; at Ham's AR the correction actually overshoots
    downwards (see the JSON), so the true bias is expected to be well
    inside this interval.
    """
    return 0.0, float(peak_no_tip / max(peak_tip, 1e-9) - 1.0)


def main():
    print("Ham 1979 finite-span check")
    print(f"  geometry AR = H/c = {AR_GEOMETRIC:.3f} "
          "(paper not in repo; AR scan 3..6 also reported)")

    cases = {
        "static_cd005": dict(cd_add=0.005, use_dynamic_stall=False,
                             use_flow_curvature=False, use_tip_loss=False),
        "static_cd002": dict(cd_add=0.002, use_dynamic_stall=False,
                             use_flow_curvature=False, use_tip_loss=False),
        "ds_on_cd002": dict(cd_add=0.002, use_dynamic_stall=True,
                            use_flow_curvature=False, use_tip_loss=False),
        "ds_curv_cd002": dict(cd_add=0.002, use_dynamic_stall=True,
                              use_flow_curvature=True, use_tip_loss=False),
        "tip_loss_helmbold": dict(cd_add=0.005, use_dynamic_stall=False,
                                  use_flow_curvature=False, use_tip_loss=True),
    }
    results = {}
    for name, flags in cases.items():
        rows = sweep(**flags)
        cp, tsr = peak(rows)
        sim = create_sim_from_params({**BASE, **flags})
        results[name] = dict(
            cd_add=flags["cd_add"],
            use_dynamic_stall=flags["use_dynamic_stall"],
            use_flow_curvature=flags["use_flow_curvature"],
            use_tip_loss=flags["use_tip_loss"],
            peak_cp=cp,
            peak_tsr=tsr,
            bias_vs_ham_mid=(cp - HAM_MID) / HAM_MID,
            f_ar=float(sim.f_ar),
            sweep=rows,
        )
        print(f"  {name:20s} peak Cp = {cp:.4f} at TSR {tsr:.1f} "
              f"(f_ar={sim.f_ar:.3f})")

    ar_rows = []
    for ar in AR_SCAN:
        h = ar * C_HAM
        rows = sweep(H=h, cd_add=0.005, use_dynamic_stall=False,
                     use_flow_curvature=False, use_tip_loss=True)
        cp, tsr = peak(rows)
        sim = create_sim_from_params({**BASE, "H": h, "cd_add": 0.005,
                                      "use_dynamic_stall": False,
                                      "use_flow_curvature": False,
                                      "use_tip_loss": True})
        ar_rows.append(dict(AR=ar, H=h, peak_cp=cp, peak_tsr=tsr,
                            f_ar=float(sim.f_ar)))
        print(f"  AR = {ar:4.2f}  peak Cp = {cp:.4f}  f_ar = {sim.f_ar:.3f}")

    no_tip = results["static_cd005"]
    tip = results["tip_loss_helmbold"]
    bias_lo, bias_hi = derived_bias_window(no_tip["peak_cp"], tip["peak_cp"])
    out = {
        "ham_geometry": dict(R=R_HAM, c=C_HAM, H=H_HAM, N=N_HAM,
                             AR=AR_GEOMETRIC),
        "band": [HAM_BAND_LO, HAM_BAND_HI],
        "band_mid": HAM_MID,
        "note": (
            "The Ham 1979 paper is not in this repository. The aspect ratio "
            "comes from the tabulated geometry (H/c); an AR=3..6 scan is "
            "reported because the blade AR could not be read from the paper."
        ),
        "cases": results,
        "peak_no_tip": no_tip["peak_cp"],
        "peak_tip_loss": tip["peak_cp"],
        "tip_loss_undershoots_band": bool(tip["peak_cp"] < HAM_BAND_LO),
        "tip_loss_overshoot_cp": float(HAM_BAND_LO - tip["peak_cp"]),
        "derived_bias_window": [bias_lo, bias_hi],
        "derived_bias_hi": bias_hi,
        "ar_scan": ar_rows,
    }
    path = os.path.join(_HERE, "ham_finite_span_check.json")
    write_json_with_stamp(
        path=path,
        data=out,
        script="scripts/ham_finite_span_check.py",
        version="v1.0",
        n=1,
        seed=0,
        extra_files=["vawt_presets.py", "vawt_core.py"],
        extra_data={},
    )
    print(f"\n  no-tip peak          = {no_tip['peak_cp']:.4f}")
    print(f"  Helmbold-corrected   = {tip['peak_cp']:.4f}")
    print(f"  undershoots band     = {out['tip_loss_undershoots_band']}")
    print(f"  derived bias window  = {bias_lo*100:+.1f} % to "
          f"{bias_hi*100:+.1f} %")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
