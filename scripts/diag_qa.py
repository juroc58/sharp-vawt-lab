"""
Qa diagnostic \u2014 verifies the aerodynamic pitch torque is stabilising.

Sharp's CPPC mechanism relies on the aerodynamic pitch moment being
*restoring*: as the blade's angle of attack approaches stall it must be
pushed back (nose-in at +stall, nose-out at \u2212stall). This script
reconstructs that moment from the passive simulation and asserts the
sign, exiting non-zero if the mechanism has regressed.

Reconstruction. The output array does not carry Qa, so it is recovered
exactly from the blade-0 pitch equation (derivation.md eq. 8.5-8.6):

    Ip * psi_dd + M * Rp * s_r * w_dd  =  M * Rp * s_t * w^2 + Q_tot
    =>  Qa = Ip*psi_dd - (Ip + M*Rp*s_r)*w_dd
             - M*Rp*s_t*w^2 + cb*psi_d + Qfr

with Qfr = mu_c * M * w^2 * (Rp + s_r) * r_b * tanh(psi_d / 0.5) and
s_t, s_r the CG offsets from the pivot. This inverts the kernel's own
integration to machine precision (residual < 1e-4 in steady state).

Sign convention (derivation.md \u00a72.1): a restoring aerodynamic pitch
torque has $Q_a < 0$ at $\alpha > 0$ (nose-in) and $Q_a > 0$ at
$\alpha < 0$ (nose-out).  Equivalently, $Q_a \\cdot \\alpha < 0$.

This script provides two modes:
- --check: run the sign verification and exit with code (0=pass, 1=fail)
- (default): run check + produce figure (exits 0 if figure produced, non-zero
  only on figure failure)
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

import numpy as np

from sharp_vawt import create_sim_from_params

BASE = {
    "R": 2.7179, "H": 4.0568, "N": 3, "c": 0.3861,
    "ar": 0.3121, "sp": 0.2181,
    "mb": 0.92954, "xbcg": 0.20,
    "mc": 2.69306, "dcw": -0.1935,
    "balance": 0, "bias_deg": 0.0,
    "prescribe_pitch": False,
    "cd_add": 0.002,
    "use_dynamic_stall": True,
    "use_flow_curvature": True,
    "use_dmst": True,
    "use_tip_loss": True,
    "win_deg": 45.0, "cb": 2e-5, "mu_c": 3e-4,
    "free": True, "T_max": 20.0, "stride": 1,  # stride=1 for smooth Qa reconstruction
    "w0_frac": 0.9, "k_load": 4.164352, "tsr": 2.5,
}

# Pass criteria.
# EXTREME_MARGIN: fraction of the *achieved* |alpha|_max for the extreme check
# (replaces the old fraction-of-stall which was vacuous when the cycle
# didn't reach stall).
EXTREME_MARGIN = 0.75   # evaluate at extremes if |alpha| > this * |alpha|_max
FRACTION_BAND = 0.50    # |alpha| band as fraction of |alpha|_max for restoring-fraction check
FRACTION_MIN = 0.70     # minimum restoring fraction in that band
MIN_SAMPLES = 5         # minimum samples required in band for the fraction check to be meaningful


def reconstruct_qa(out, sim):
    """Invert the pitch equation to recover Qa per output sample."""
    t = out[:, 0]
    w = out[:, 2]
    psi = out[:, 3]
    psd = out[:, 11]
    dt = float(np.mean(np.diff(t)))
    wd = np.gradient(w, dt)
    psdd = np.gradient(psd, dt)

    M, Rp, Ip = sim.M, sim.Rp, sim.Ip
    ar, xg = sim.ar_len, sim.xg
    cb = sim.aero.cb
    mu_c = sim.aero.mu_c
    r_b = sim.aero.r_bearing

    cp_, sn_ = np.cos(psi), np.sin(psi)
    st = -xg * cp_ - ar * sn_
    sr = -xg * sn_ + ar * cp_
    Fcen = M * w * w * (Rp + sr)
    Qfr = mu_c * Fcen * r_b * np.tanh(psd / 0.5)
    Qa = (Ip * psdd - (Ip + M * Rp * sr) * wd
          - M * Rp * st * w * w + cb * psd + Qfr)
    return Qa


def evaluate_restoring(alpha_deg, qa, stall_deg, steady=True):
    """Pure sign check on (alpha, Qa) histories. Returns a report dict.

    No simulation or paradigm dependency, so the pass/fail logic is
    unit-testable (see tests/test_diag_qa.py). A restoring aerodynamic
    pitch moment is negative at +stall and positive at -stall.
    """
    alpha = np.asarray(alpha_deg, dtype=float)
    qa = np.asarray(qa, dtype=float)

    i_max = int(np.argmax(alpha))
    i_min = int(np.argmin(alpha))
    a_max, a_min = float(alpha[i_max]), float(alpha[i_min])
    qa_max, qa_min = float(qa[i_max]), float(qa[i_min])

    # Use the *achieved* |alpha|_max for thresholds, not the stall angle
    a_abs_max = max(abs(a_max), abs(a_min))

    checks = []  # (label, required_sign, actual_sign, satisfied)
    if abs(a_max) > EXTREME_MARGIN * a_abs_max:
        checks.append(("alpha_max (+)", qa_max < 0.0,
                       "nose-in" if qa_max < 0.0 else "nose-out"))
    if abs(a_min) > EXTREME_MARGIN * a_abs_max:
        checks.append(("alpha_min (\u2212)", qa_min > 0.0,
                       "nose-out" if qa_min > 0.0 else "nose-in"))

    # Band: |alpha| > FRACTION_BAND * |alpha|_max
    band = np.abs(alpha) > FRACTION_BAND * a_abs_max
    n_band = int(band.sum())
    frac = float((np.sign(qa[band]) == -np.sign(alpha[band])).mean()) \
        if n_band >= MIN_SAMPLES else float("nan")

    extreme_ok = all(ok for _, ok, _ in checks) and len(checks) > 0
    frac_ok = np.isfinite(frac) and frac >= FRACTION_MIN
    passed = bool(extreme_ok and frac_ok and steady)

    # Determine status: PASS, FAIL (wrong sign), or INCONCLUSIVE (insufficient data)
    if not extreme_ok and len(checks) > 0:
        status = "FAIL_WRONG_SIGN"
    elif len(checks) == 0:
        status = "INCONCLUSIVE_NO_EXTREMES"
    elif not np.isfinite(frac) or n_band < MIN_SAMPLES:
        status = "INCONCLUSIVE_INSUFFICIENT_SAMPLES"
    elif not frac_ok:
        status = "FAIL_LOW_FRACTION"
    else:
        status = "PASS"

    return {
        "alpha_max": a_max, "alpha_min": a_min,
        "qa_max": qa_max, "qa_min": qa_min,
        "stall_deg": float(stall_deg),
        "checks": checks,
        "fraction": frac, "n_band": n_band,
        "extreme_ok": extreme_ok, "frac_ok": frac_ok,
        "passed": passed,
        "status": status,
    }


def restoring_report(params):
    """Run the passive case and return (report_dict, out, sim)."""
    sim = create_sim_from_params(params)
    r = sim.run()
    out = r["out"]

    Qa = reconstruct_qa(out, sim)
    th = out[:, 1]
    mask = th > th[-1] - 2.0 * np.pi          # last revolution
    if mask.sum() < 5:
        mask = np.ones(len(th), bool)

    alpha = np.degrees(out[mask, 5])
    qa = Qa[mask]
    stall = float(np.degrees(sim.polar_db.alpha_stall))

    report = evaluate_restoring(alpha, qa, stall, steady=r.get("steady", True))
    report["cp"] = float(r["cp"])
    report["steady"] = bool(r.get("steady", True))
    return report, out, sim


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--out", default="docs/diag_qa.png")
    ap.add_argument("--no-plot", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="Run verification only, exit with status code (0=pass, 1=fail). No figure.")
    args = ap.parse_args(argv)

    print("Running passive Sharp case...")
    report, out, sim = restoring_report(BASE)

    print(f"  Cp = {report['cp']:+.4f}   steady = {report['steady']}")
    print(f"  stall angle = {report['stall_deg']:.1f} deg")
    print(f"  cycle extremes: alpha_max = {report['alpha_max']:+.1f} deg "
          f"(Qa = {report['qa_max']:+.5f}), "
          f"alpha_min = {report['alpha_min']:+.1f} deg "
          f"(Qa = {report['qa_min']:+.5f})")
    print()
    print(f"{'extreme':<22} {'required':>10} {'actual':>10}  {'ok':>4}")
    print("-" * 52)
    for label, ok, actual in report["checks"]:
        req = "nose-in" if "max" in label else "nose-out"
        print(f"{label:<22} {req:>10} {actual:>10}  {'yes' if ok else 'NO':>4}")
    if not report["checks"]:
        print("  (no extreme check: cycle does not reach EXTREME_MARGIN of |alpha|_max)")
    print()
    print(f"  restoring fraction over |alpha| > "
          f"{FRACTION_BAND * 100:.0f}% of |alpha|_max "
          f"(n = {report['n_band']}, min {MIN_SAMPLES}): "
          f"{report['fraction']:.3f} "
          f"(min {FRACTION_MIN:.2f})")
    if report["n_band"] < MIN_SAMPLES:
        print("  (insufficient samples in band for fraction check)")
    print()

    if args.check:
        status = report.get("status", "UNKNOWN")
        if status == "PASS":
            print("PASS: aerodynamic pitch torque is restoring at the cycle "
                  "extremes; CPPC sign convention is intact.")
            return 0
        elif status == "FAIL_WRONG_SIGN":
            print("FAIL: aerodynamic pitch torque has the wrong sign at the cycle "
                  "extremes; check the alpha = wrap(phi_f + psi) convention "
                  "(derivation.md \u00a72.1).")
            return 1
        elif status == "FAIL_LOW_FRACTION":
            print("FAIL: restoring fraction below threshold at the cycle "
                  "extremes; check the alpha = wrap(phi_f + psi) convention "
                  "(derivation.md \u00a72.1).")
            return 1
        elif status == "INCONCLUSIVE_INSUFFICIENT_SAMPLES":
            print("INCONCLUSIVE: insufficient samples in the restoring band "
                  f"(n = {report['n_band']} < {MIN_SAMPLES}) to verify "
                  "the sign of the aerodynamic pitch torque.")
            return 1
        elif status == "INCONCLUSIVE_NO_EXTREMES":
            print("INCONCLUSIVE: cycle does not reach EXTREME_MARGIN of |alpha|_max; "
                  "cannot verify the sign of the aerodynamic pitch torque.")
            return 1
        else:
            print(f"UNKNOWN STATUS: {status}")
            return 1

    if not args.no_plot:
        _make_plot(out, sim, args.out)

    if report["passed"]:
        print("PASS: aerodynamic pitch torque is restoring at the cycle "
              "extremes; CPPC sign convention is intact.")
        return 0

    status = report.get("status", "UNKNOWN")
    if status == "FAIL_WRONG_SIGN":
        print("FAIL: aerodynamic pitch torque has the wrong sign at the cycle "
              "extremes; check the alpha = wrap(phi_f + psi) convention "
              "(derivation.md \u00a72.1).")
        return 1
    elif status == "FAIL_LOW_FRACTION":
        print("FAIL: restoring fraction below threshold at the cycle "
              "extremes; check the alpha = wrap(phi_f + psi) convention "
              "(derivation.md \u00a72.1).")
        return 1
    elif status == "INCONCLUSIVE_INSUFFICIENT_SAMPLES":
        print("INCONCLUSIVE: insufficient samples in the restoring band "
              f"(n = {report['n_band']} < {MIN_SAMPLES}) to verify "
              "the sign of the aerodynamic pitch torque.")
        return 1
    elif status == "INCONCLUSIVE_NO_EXTREMES":
        print("INCONCLUSIVE: cycle does not reach EXTREME_MARGIN of |alpha|_max; "
              "cannot verify the sign of the aerodynamic pitch torque.")
        return 1
    else:
        print(f"UNKNOWN STATUS: {status}")
        return 1


def _make_plot(out, sim, out_path="docs/diag_qa.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.signal import savgol_filter

    th = out[:, 1]
    m = th >= th[-1] - 2.0 * np.pi
    phi = np.degrees(th[m] % (2.0 * np.pi))
    psi = np.degrees(out[m, 3])
    alpha = np.degrees(out[m, 5])
    qa = reconstruct_qa(out, sim)[m]
    order = np.argsort(phi)

    # Smooth Qa in TIME domain (before phi-sorting) to remove numerical noise
    # from gradient-based reconstruction, then sort for plotting
    # Use a large window to suppress high-frequency numerical artifacts
    if len(qa) > 401:
        qa = savgol_filter(qa, window_length=401, polyorder=3)
    qa = qa[order]

    fig, ax = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    ax[0].plot(phi[order], psi[order], "b-", lw=1.6)
    ax[0].axhline(0, color="k", lw=0.5)
    ax[0].set_ylabel("psi [deg]")
    ax[0].set_title("Blade pitch (rocking angle)")
    ax[0].grid(alpha=0.3)

    ax[1].plot(phi[order], alpha[order], color="darkorange", lw=1.6)
    ax[1].axhline(0, color="k", lw=0.5)
    stall = np.degrees(sim.polar_db.alpha_stall)
    ax[1].axhline(stall, color="r", ls=":", lw=0.9, label=f"+-{stall:.0f} deg stall")
    ax[1].axhline(-stall, color="r", ls=":", lw=0.9)
    ax[1].set_ylabel("alpha [deg]")
    ax[1].set_title("Effective angle of attack")
    ax[1].legend(loc="upper right", fontsize=8)
    ax[1].grid(alpha=0.3)

    ax[2].plot(phi[order], qa, color="purple", lw=1.6)
    ax[2].axhline(0, color="k", lw=0.5)
    ax[2].set_ylabel("Qa [N m]")
    ax[2].set_xlabel("rotor angle [deg]   (0 = with wind,  180 = upwind)")
    ax[2].set_title("Aerodynamic pitch torque on blade 0 (reconstructed)")
    ax[2].grid(alpha=0.3)

    fig.tight_layout()
    outpath = (out_path if os.path.isabs(out_path)
               else os.path.join(_ROOT, out_path))
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print(f"  wrote {outpath}")


if __name__ == "__main__":
    raise SystemExit(main())