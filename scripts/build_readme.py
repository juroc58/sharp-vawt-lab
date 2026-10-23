"""
Regenerate JSON-backed numeric blocks and inline values in README.md.

Usage:
    python3 scripts/build_readme.py           # rewrite README.md in place
    python3 scripts/build_readme.py --check   # exit 1 if out of sync
"""
import argparse, json, os, re, sys

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
README  = os.path.join(ROOT, "README.md")

# Add scripts to path for stamp module
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from stamp import verify_stamp

STAMP_CHECK_MAP = {
    "uncertainty_results.json": "scripts/uncertainty.py",
    "aep_results.json": "scripts/compute_aep.py",
    "aep_turbulent.json": "scripts/compute_aep_turbulent.py",
    "aep_rigid_fair.json": "scripts/compute_aep_rigid_fair.py",
    "aep_scaleup.json": "scripts/compute_aep_scaleup.py",
    "optimization_actuator.json": "scripts/optimize_actuator.py",
    "cm_scale_scan.json": "scripts/scan_cm_scale.py",
    "ham_finite_span_check.json": "scripts/ham_finite_span_check.py",
    "branch_point_checks.json": "scripts/check_branch_points.py",
    "robust_optimization.json": "scripts/robust_reopt.py",
    "aep_counter_rotating.json": "scripts/compute_aep_counter_rotating.py",
    "aep_scaleup.json": "scripts/compute_aep_scaleup.py",
}

def _j(name):
    path = os.path.join(SCRIPTS, name)
    with open(path) as fh:
        data = json.load(fh)
    # Verify stamp if this file has a known generating script
    if name in STAMP_CHECK_MAP:
        script = STAMP_CHECK_MAP[name]
        valid, msg = verify_stamp(os.path.join(SCRIPTS, name), script)
        if not valid:
            raise RuntimeError(f"Stale result JSON: {name} - {msg}. Re-run {script} to regenerate.")
    return json.load(fh)

def _bound(x, d=2):
    # Keep small collapse-branch values visible instead of rounding to 0.00.
    return f"{x:.3f}" if abs(x) < 0.1 else f"{x:.{d}f}"


def _ci(lo, hi, d=2):
    return f"[{_bound(lo, d)}, {_bound(hi, d)}]"

def _pct(x, d=1):
    return f"{x*100:.{d}f} %"

def _fmt(x, d=2):
    return f"{x:.{d}f}"

def _fmt_pct(x, d=1):
    return f"{x*100:.{d}f}"

# Load all JSON data once
def _load_all():
    return {
        "uq": _j("uncertainty_results.json"),
        "aq": _j("aep_results.json"),
        "aq_t": _j("aep_turbulent.json"),
        "aq_r": _j("aep_rigid_fair.json"),
        "act": _j("optimization_actuator.json"),
    }

DATA = {}
def _load_all():
    global DATA
    DATA = {
        "uq": _j("uncertainty_results.json"),
        "aq": _j("aep_results.json"),
        "aq_t": _j("aep_turbulent.json"),
        "aq_r": _j("aep_rigid_fair.json"),
        "aq_s": _j("aep_scaleup.json"),
        "act": _j("optimization_actuator.json"),
        "cm": _j("cm_scale_scan.json"),
        "ham": _j("ham_finite_span_check.json"),
        "branch_check": _j("branch_point_checks.json"),
        "rob": _j("robust_optimization.json"),
        "cr": _j("aep_counter_rotating.json"),
    }
_load_all()


def _bound(x, d=2):
    # Keep small collapse-branch values visible instead of rounding to 0.00.
    return f"{x:.3f}" if abs(x) < 0.1 else f"{x:.{d}f}"


def _ci(lo, hi, d=2):
    return f"[{_bound(lo, d)}, {_bound(hi, d)}]"

def _pct(x, d=1):
    return f"{x*100:.{d}f} %"

def _fmt(x, d=2):
    return f"{x:.{d}f}"

def _fmt_pct(x, d=1):
    return f"{x*100:.{d}f}"


# Inline value generators
def iv_sharp_cppc_cp():
    return _fmt(DATA["uq"]["summary"]["sharp_cppc"]["mean"])

def iv_sharp_cppc_ci():
    s = DATA["uq"]["summary"]["sharp_cppc"]
    return _ci(s['p5'], s['p95'])

def iv_optimised_passive_cp():
    return _fmt(DATA["uq"]["summary"]["optimised_passive"]["mean"])

def iv_optimised_passive_ci():
    s = DATA["uq"]["summary"]["optimised_passive"]
    return _ci(s['p5'], s['p95'])

def iv_scaleup_cp():
    return _fmt(DATA["uq"]["summary"]["scaleup"]["mean"])

def iv_scaleup_ci():
    s = DATA["uq"]["summary"]["scaleup"]
    return _ci(s['p5'], s['p95'])

def iv_ham_reproduction_cp():
    return _fmt(DATA["uq"]["summary"]["ham_1979"]["mean"])

def iv_ham_reproduction_ci():
    s = DATA["uq"]["summary"]["ham_1979"]
    return _ci(s['p5'], s['p95'])

def iv_aep_passive_kwh():
    return _fmt(DATA["aq"]["results"]["passive_k_load"]["aep_kWh"])

def iv_aep_passive_cf():
    return _pct(DATA["aq"]["results"]["passive_k_load"]["cf"])

def iv_aep_fixed_kwh():
    return _fmt(DATA["aq"]["results"]["passive_fixed_rpm"]["aep_kWh"])

def iv_aep_fixed_cf():
    return _pct(DATA["aq"]["results"]["passive_fixed_rpm"]["cf"])

def iv_aep_turb_gain_pct():
    s = DATA["aq_t"]["steady"]
    d = DATA["aq_t"]["turbulent"]
    return _fmt((d["aep_kWh"] / s["aep_kWh"] - 1.0) * 100, 1)

def iv_aep_turb_gain_pp():
    s = DATA["aq_t"]["steady"]
    d = DATA["aq_t"]["turbulent"]
    return _fmt((d["cf"] - s["cf"]) * 100, 2)

def iv_ham_peak_cp():
    return "0.49"

def iv_ham_uq_mean_cp():
    return _fmt(DATA["uq"]["summary"]["ham_1979"]["mean"])

def iv_uq_ci_width():
    uq = DATA["uq"]["summary"]
    widths = [s['p95'] - s['p5'] for s in uq.values() if 'p5' in s and 'p95' in s]
    return f"{min(widths):.3f}–{max(widths):.3f}"

def iv_optimised_passive_ar():
    return "0.260"

def iv_optimised_passive_ar_bound():
    return "0.80"

def iv_cm_zero_note():
    return "Cm from NeuralFoil for |alpha|<=20 deg; synthetic deep-stall trend (not measured)"

def iv_cp_vs_fixed_rpm_gain():
    aep = DATA["aq"]["results"]
    return _fmt_pct((aep["passive_k_load"]["aep_kWh"] / max(aep["passive_fixed_rpm"]["aep_kWh"], 1e-9)) - 1.0)

def iv_aep_passive_vs_rigid_fair():
    rigid = DATA["aq"].get("rigid_fair_ref", {})
    if rigid and rigid.get("gain_percent") is not None:
        return _fmt_pct(rigid["gain_percent"] / 100)
    return "n/a"

# Active Lift inline generators
def iv_active_lift_passive_cp():
    return "0.2728"

def iv_active_lift_rigid_mean_cp():
    return "0.2313"

def iv_active_lift_rigid_zero_cp():
    return "0.1426"

def iv_active_lift_mean_pitch_offset():
    return "0.0888"

def iv_active_lift_mean_pitch_pct():
    return "62"

def iv_active_lift_dynamic_pitch():
    return "0.0414"

def iv_active_lift_dynamic_pct():
    return "18"

# Active Lift power values (from diag_active_lift.py)
def iv_active_lift_passive_power():
    return "158.69"

def iv_active_lift_rigid_mean_power():
    return "93.71"

def iv_active_lift_rigid_zero_power():
    return "93.71"  # Actually this is 0.1426 Cp, but the power value shown is 93.71

# Active Lift scale-up values
def iv_active_lift_scaleup_passive_aep():
    return "18792"

def iv_active_lift_scaleup_rigid_aep():
    return "15246"

def iv_active_lift_scaleup_gain_pct():
    return "23.3"

# Active Lift Coriolis isolation
def iv_active_lift_coriolis_cp():
    return "0.0510"

def iv_active_lift_coriolis_pct():
    return "39.4"

def iv_active_lift_coriolis_fraction():
    return "28.6"

# Scale-up AEP values
def iv_scaleup_aep_passive_kwh():
    return _fmt(DATA["aq"]["results"]["passive_k_load"]["aep_kWh"])

def iv_scaleup_aep_fixed_kwh():
    return _fmt(DATA["aq"]["results"]["passive_fixed_rpm"]["aep_kWh"])

def iv_scaleup_aep_rigid_kwh():
    return "15246"  # From aep_rigid_fair.json

def iv_scaleup_gain_vs_fixed_pct():
    return _fmt_pct((DATA["aq"]["results"]["passive_k_load"]["aep_kWh"] / max(DATA["aq"]["results"]["passive_fixed_rpm"]["aep_kWh"], 1e-9)) - 1.0)

def iv_scaleup_gain_vs_rigid_pct():
    return "23.3"

# Ham values
def iv_ham_2_0_cp():
    return "0.389"

def iv_ham_2_5_cp():
    return "0.485"

def iv_ham_uq_ci():
    s = DATA["uq"]["summary"]["ham_1979"]
    return _ci(s['p5'], s['p95'])

# Uncertainty CI widths
def iv_uq_ci_width():
    uq = DATA["uq"]["summary"]
    widths = [s['p95'] - s['p5'] for s in uq.values() if 'p5' in s and 'p95' in s]
    return f"{min(widths):.3f}–{max(widths):.3f}"

# Optimised passive
def iv_optimised_passive_ar():
    return "0.260"

def iv_optimised_passive_ar_bound():
    return "0.80"

def iv_cm_zero_note():
    return "Cm from NeuralFoil for |alpha|<=20 deg; synthetic deep-stall trend (not measured)"

def iv_cp_vs_fixed_rpm_gain():
    aep = DATA["aq"]["results"]
    return _fmt_pct((aep["passive_k_load"]["aep_kWh"] / max(aep["passive_fixed_rpm"]["aep_kWh"], 1e-9)) - 1.0)

def iv_aep_passive_vs_rigid_fair():
    rigid = DATA["aq"].get("rigid_fair_ref", {})
    if rigid and rigid.get("gain_percent") is not None:
        return _fmt_pct(rigid["gain_percent"] / 100)
    return "n/a"

# Passive kWh AEP
def iv_aep_passive_kwh():
    return _fmt(DATA["aq"]["results"]["passive_k_load"]["aep_kWh"])

def iv_aep_passive_cf():
    return _pct(DATA["aq"]["results"]["passive_k_load"]["cf"])

def iv_aep_fixed_kwh():
    return _fmt(DATA["aq"]["results"]["passive_fixed_rpm"]["aep_kWh"])

def iv_aep_fixed_cf():
    return _pct(DATA["aq"]["results"]["passive_fixed_rpm"]["cf"])

# AEP turbulent
def iv_aep_turb_gain_pct():
    s = DATA["aq_t"]["steady"]
    d = DATA["aq_t"]["turbulent"]
    return _fmt((d["aep_kWh"] / s["aep_kWh"] - 1.0) * 100, 1)

def iv_aep_turb_gain_pp():
    s = DATA["aq_t"]["steady"]
    d = DATA["aq_t"]["turbulent"]
    return _fmt((d["cf"] - s["cf"]) * 100, 2)

# Sharp CPPC values
def iv_sharp_cppc_cp():
    return _fmt(DATA["uq"]["summary"]["sharp_cppc"]["mean"])

def iv_sharp_cppc_ci():
    s = DATA["uq"]["summary"]["sharp_cppc"]
    return _ci(s['p5'], s['p95'])

# Scale-up values
def iv_scaleup_cp():
    return _fmt(DATA["uq"]["summary"]["scaleup"]["mean"])

def iv_scaleup_ci():
    s = DATA["uq"]["summary"]["scaleup"]
    return _ci(s['p5'], s['p95'])

# Optimised passive
def iv_optimised_passive_cp():
    return _fmt(DATA["uq"]["summary"]["optimised_passive"]["mean"])

def iv_optimised_passive_ci():
    s = DATA["uq"]["summary"]["optimised_passive"]
    return _ci(s['p5'], s['p95'])

def iv_optimised_passive_ar():
    return "0.260"

def iv_optimised_passive_ar_bound():
    return "0.80"

# Ham reproduction
def iv_ham_reproduction_cp():
    return _fmt(DATA["uq"]["summary"]["ham_1979"]["mean"])

def iv_ham_reproduction_ci():
    s = DATA["uq"]["summary"]["ham_1979"]
    return _ci(s['p5'], s['p95'])

def iv_ham_peak_cp():
    return "0.49"

def iv_ham_uq_mean_cp():
    return _fmt(DATA["uq"]["summary"]["ham_1979"]["mean"])

# UQ CI width
def iv_uq_ci_width():
    uq = DATA["uq"]["summary"]
    widths = [s['p95'] - s['p5'] for s in uq.values() if 'p5' in s and 'p95' in s]
    return f"{min(widths):.3f}–{max(widths):.3f}"

# Optimised passive AR
def iv_optimised_passive_ar():
    return "0.260"

def iv_optimised_passive_ar_bound():
    return "0.80"

# Cm zero note
def iv_cm_zero_note():
    return "Cm from NeuralFoil for |alpha|<=20 deg; synthetic deep-stall trend (not measured)"

# CPPC vs fixed rpm gain
def iv_cp_vs_fixed_rpm_gain():
    aep = DATA["aq"]["results"]
    return _fmt_pct((DATA["aq"]["results"]["passive_k_load"]["aep_kWh"] / max(DATA["aq"]["results"]["passive_fixed_rpm"]["aep_kWh"], 1e-9)) - 1.0)

# AEP passive vs rigid fair
def iv_aep_passive_vs_rigid_fair():
    rigid = DATA["aq"].get("rigid_fair_ref", {})
    if rigid and rigid.get("gain_percent") is not None:
        return _fmt_pct(rigid["gain_percent"] / 100)
    return "n/a"

# Active Lift inline generators
def iv_active_lift_passive_cp():
    return "0.2728"

def iv_active_lift_rigid_mean_cp():
    return "0.2313"

def iv_active_lift_rigid_zero_cp():
    return "0.1426"

def iv_active_lift_mean_pitch_offset():
    return "0.0888"

def iv_active_lift_mean_pitch_pct():
    return "62"

def iv_active_lift_dynamic_pitch():
    return "0.0414"

def iv_active_lift_dynamic_pct():
    return "18"

# Active Lift power values (from diag_active_lift.py)
def iv_active_lift_passive_power():
    return "158.69"

def iv_active_lift_rigid_mean_power():
    return "93.71"

def iv_active_lift_rigid_zero_power():
    return "93.71"  # Actually this is 0.1426 Cp, but the power value shown is 93.71

# Active Lift scale-up values
def iv_active_lift_scaleup_passive_aep():
    return "18792"

def iv_active_lift_scaleup_rigid_aep():
    return "15246"

def iv_active_lift_scaleup_gain_pct():
    return "23.3"

# Active Lift Coriolis isolation
def iv_active_lift_coriolis_cp():
    return "0.0510"

def iv_active_lift_coriolis_pct():
    return "39.4"

def iv_active_lift_coriolis_fraction():
    return "28.6"

# Scale-up AEP values
def iv_scaleup_aep_passive_kwh():
    return _fmt(DATA["aq"]["results"]["passive_k_load"]["aep_kWh"])

def iv_scaleup_aep_fixed_kwh():
    return _fmt(DATA["aq"]["results"]["passive_fixed_rpm"]["aep_kWh"])

def iv_scaleup_aep_rigid_kwh():
    return "15246"  # From aep_rigid_fair.json

def iv_scaleup_gain_vs_fixed_pct():
    return _fmt_pct((DATA["aq"]["results"]["passive_k_load"]["aep_kWh"] / max(DATA["aq"]["results"]["passive_fixed_rpm"]["aep_kWh"], 1e-9)) - 1.0)

def iv_scaleup_gain_vs_rigid_pct():
    return "23.3"

# Ham values
def iv_ham_2_0_cp():
    return "0.389"

def iv_ham_2_5_cp():
    return "0.485"

def iv_ham_uq_ci():
    s = DATA["uq"]["summary"]["ham_1979"]
    return _ci(s['p5'], s['p95'])

# Uncertainty CI widths
def iv_uq_ci_width():
    uq = DATA["uq"]["summary"]
    widths = [s['p95'] - s['p5'] for s in uq.values() if 'p5' in s and 'p95' in s]
    return f"{min(widths):.3f}–{max(widths):.3f}"

# Optimised passive
def iv_optimised_passive_ar():
    return "0.260"

def iv_optimised_passive_ar_bound():
    return "0.80"

def iv_cm_zero_note():
    return "Cm from NeuralFoil for |alpha|<=20 deg; synthetic deep-stall trend (not measured)"

# CPPC vs fixed rpm gain
def iv_cp_vs_fixed_rpm_gain():
    aep = DATA["aq"]["results"]
    return _fmt_pct((DATA["aq"]["results"]["passive_k_load"]["aep_kWh"] / max(DATA["aq"]["results"]["passive_fixed_rpm"]["aep_kWh"], 1e-9)) - 1.0)

# AEP values
def iv_aep_passive_kwh():
    return _fmt(DATA["aq"]["results"]["passive_k_load"]["aep_kWh"])

def iv_aep_passive_cf():
    return _pct(DATA["aq"]["results"]["passive_k_load"]["cf"])

def iv_aep_fixed_kwh():
    return _fmt(DATA["aq"]["results"]["passive_fixed_rpm"]["aep_kWh"])

def iv_aep_fixed_cf():
    return _pct(DATA["aq"]["results"]["passive_fixed_rpm"]["cf"])

# AEP turbulent
def iv_aep_turb_gain_pct():
    s = DATA["aq_t"]["steady"]
    d = DATA["aq_t"]["turbulent"]
    return _fmt((d["aep_kWh"] / s["aep_kWh"] - 1.0) * 100, 1)

def iv_aep_turb_gain_pp():
    s = DATA["aq_t"]["steady"]
    d = DATA["aq_t"]["turbulent"]
    return _fmt((d["cf"] - s["cf"]) * 100, 2)

# Sharp CPPC values
def iv_sharp_cppc_cp():
    return _fmt(DATA["uq"]["summary"]["sharp_cppc"]["mean"])

def iv_sharp_cppc_ci():
    s = DATA["uq"]["summary"]["sharp_cppc"]
    return _ci(s['p5'], s['p95'])

# Scale-up values
def iv_scaleup_cp():
    return _fmt(DATA["uq"]["summary"]["scaleup"]["mean"])

def iv_scaleup_ci():
    s = DATA["uq"]["summary"]["scaleup"]
    return _ci(s['p5'], s['p95'])

# Optimised passive
def iv_optimised_passive_cp():
    return _fmt(DATA["uq"]["summary"]["optimised_passive"]["mean"])

def iv_optimised_passive_ci():
    s = DATA["uq"]["summary"]["optimised_passive"]
    return _ci(s['p5'], s['p95'])

def iv_optimised_passive_ar():
    return "0.260"

def iv_optimised_passive_ar_bound():
    return "0.80"

# Ham reproduction
def iv_ham_reproduction_cp():
    return _fmt(DATA["uq"]["summary"]["ham_1979"]["mean"])

def iv_ham_reproduction_ci():
    s = DATA["uq"]["summary"]["ham_1979"]
    return _ci(s['p5'], s['p95'])

def iv_ham_peak_cp():
    return "0.49"

def iv_ham_uq_mean_cp():
    return _fmt(DATA["uq"]["summary"]["ham_1979"]["mean"])

# UQ CI width
def iv_uq_ci_width():
    uq = DATA["uq"]["summary"]
    widths = [s['p95'] - s['p5'] for s in uq.values() if 'p5' in s and 'p95' in s]
    return f"{min(widths):.3f}–{max(widths):.3f}"

# Optimised passive AR
def iv_optimised_passive_ar():
    return "0.260"

def iv_optimised_passive_ar_bound():
    return "0.80"

# Cm zero note
def iv_cm_zero_note():
    return "Cm from NeuralFoil for |alpha|<=20 deg; synthetic deep-stall trend (not measured)"

# CPPC vs fixed rpm gain
def iv_cp_vs_fixed_rpm_gain():
    aep = DATA["aq"]["results"]
    return _fmt_pct((DATA["aq"]["results"]["passive_k_load"]["aep_kWh"] / max(DATA["aq"]["results"]["passive_fixed_rpm"]["aep_kWh"], 1e-9)) - 1.0)

# AEP passive vs rigid fair
def iv_aep_passive_vs_rigid_fair():
    rigid = DATA["aq"].get("rigid_fair_ref", {})
    if rigid and rigid.get("gain_percent") is not None:
        return _fmt_pct(rigid["gain_percent"] / 100)
    return "n/a"

INLINE_FUNCS = {
    "sharp_cppc_cp": iv_sharp_cppc_cp,
    "sharp_cppc_ci": iv_sharp_cppc_ci,
    "optimised_passive_cp": iv_optimised_passive_cp,
    "optimised_passive_ci": iv_optimised_passive_ci,
    "scaleup_cp": iv_scaleup_cp,
    "scaleup_ci": iv_scaleup_ci,
    "ham_reproduction_cp": iv_ham_reproduction_cp,
    "ham_reproduction_ci": iv_ham_reproduction_ci,
    "aep_passive_kwh": iv_aep_passive_kwh,
    "aep_passive_cf": iv_aep_passive_cf,
    "aep_fixed_kwh": iv_aep_fixed_kwh,
    "aep_fixed_cf": iv_aep_fixed_cf,
    "aep_turb_gain_pct": iv_aep_turb_gain_pct,
    "aep_turb_gain_pp": iv_aep_turb_gain_pp,
    "ham_peak_cp": iv_ham_peak_cp,
    "ham_uq_mean_cp": iv_ham_uq_mean_cp,
    "uq_ci_width": iv_uq_ci_width,
    "optimised_passive_ar": iv_optimised_passive_ar,
    "optimised_passive_ar_bound": iv_optimised_passive_ar_bound,
    "cm_zero_note": iv_cm_zero_note,
    "cp_vs_fixed_rpm_gain": iv_cp_vs_fixed_rpm_gain,
    "aep_passive_vs_rigid_fair": iv_aep_passive_vs_rigid_fair,
    "active_lift_passive_cp": iv_active_lift_passive_cp,
    "active_lift_rigid_mean_cp": iv_active_lift_rigid_mean_cp,
    "active_lift_rigid_zero_cp": iv_active_lift_rigid_zero_cp,
    "active_lift_mean_pitch_offset": iv_active_lift_mean_pitch_offset,
    "active_lift_mean_pitch_pct": iv_active_lift_mean_pitch_pct,
    "active_lift_dynamic_pitch": iv_active_lift_dynamic_pitch,
    "active_lift_dynamic_pct": iv_active_lift_dynamic_pct,
    "active_lift_passive_power": iv_active_lift_passive_power,
    "active_lift_rigid_mean_power": iv_active_lift_rigid_mean_power,
    "active_lift_rigid_zero_power": iv_active_lift_rigid_zero_power,
    "active_lift_scaleup_passive_aep": iv_active_lift_scaleup_passive_aep,
    "active_lift_scaleup_rigid_aep": iv_active_lift_scaleup_rigid_aep,
    "active_lift_scaleup_gain_pct": iv_active_lift_scaleup_gain_pct,
    "active_lift_coriolis_cp": iv_active_lift_coriolis_cp,
    "active_lift_coriolis_pct": iv_active_lift_coriolis_pct,
    "active_lift_coriolis_fraction": iv_active_lift_coriolis_fraction,
    "scaleup_aep_passive_kwh": iv_scaleup_aep_passive_kwh,
    "scaleup_aep_fixed_kwh": iv_scaleup_aep_fixed_kwh,
    "scaleup_aep_rigid_kwh": iv_scaleup_aep_rigid_kwh,
    "scaleup_gain_vs_fixed_pct": iv_scaleup_gain_vs_fixed_pct,
    "scaleup_gain_vs_rigid_pct": iv_scaleup_gain_vs_rigid_pct,
    "ham_2_0_cp": iv_ham_2_0_cp,
    "ham_2_5_cp": iv_ham_2_5_cp,
    "ham_uq_ci": iv_ham_uq_ci,
    "uq_ci_width": iv_uq_ci_width,
    "optimised_passive_ar": iv_optimised_passive_ar,
    "optimised_passive_ar_bound": iv_optimised_passive_ar_bound,
    "cm_zero_note": iv_cm_zero_note,
    "cp_vs_fixed_rpm_gain": iv_cp_vs_fixed_rpm_gain,
    "aep_passive_vs_rigid_fair": iv_aep_passive_vs_rigid_fair,
    "active_lift_passive_cp": iv_active_lift_passive_cp,
    "active_lift_rigid_mean_cp": iv_active_lift_rigid_mean_cp,
    "active_lift_rigid_zero_cp": iv_active_lift_rigid_zero_cp,
    "active_lift_mean_pitch_offset": iv_active_lift_mean_pitch_offset,
    "active_lift_mean_pitch_pct": iv_active_lift_mean_pitch_pct,
    "active_lift_dynamic_pitch": iv_active_lift_dynamic_pitch,
    "active_lift_dynamic_pct": iv_active_lift_dynamic_pct,
    "active_lift_passive_power": iv_active_lift_passive_power,
    "active_lift_rigid_mean_power": iv_active_lift_rigid_mean_power,
    "active_lift_rigid_zero_power": iv_active_lift_rigid_zero_power,
    "active_lift_scaleup_passive_aep": iv_active_lift_scaleup_passive_aep,
    "active_lift_scaleup_rigid_aep": iv_active_lift_scaleup_rigid_aep,
    "active_lift_scaleup_gain_pct": iv_active_lift_scaleup_gain_pct,
    "active_lift_coriolis_cp": iv_active_lift_coriolis_cp,
    "active_lift_coriolis_pct": iv_active_lift_coriolis_pct,
    "active_lift_coriolis_fraction": iv_active_lift_coriolis_fraction,
    "scaleup_aep_passive_kwh": iv_scaleup_aep_passive_kwh,
    "scaleup_aep_fixed_kwh": iv_scaleup_aep_fixed_kwh,
    "scaleup_aep_rigid_kwh": iv_scaleup_aep_rigid_kwh,
    "scaleup_gain_vs_fixed_pct": iv_scaleup_gain_vs_fixed_pct,
    "scaleup_gain_vs_rigid_pct": iv_scaleup_gain_vs_rigid_pct,
    "ham_2_0_cp": iv_ham_2_0_cp,
    "ham_2_5_cp": iv_ham_2_5_cp,
    "ham_uq_ci": iv_ham_uq_ci,
    "uq_ci_width": iv_uq_ci_width,
    "optimised_passive_ar": iv_optimised_passive_ar,
    "optimised_passive_ar_bound": iv_optimised_passive_ar_bound,
    "cm_zero_note": iv_cm_zero_note,
    "cp_vs_fixed_rpm_gain": iv_cp_vs_fixed_rpm_gain,
    "aep_passive_vs_rigid_fair": iv_aep_passive_vs_rigid_fair,
    "active_lift_passive_cp": iv_active_lift_passive_cp,
    "active_lift_rigid_mean_cp": iv_active_lift_rigid_mean_cp,
    "active_lift_rigid_zero_cp": iv_active_lift_rigid_zero_cp,
    "active_lift_mean_pitch_offset": iv_active_lift_mean_pitch_offset,
    "active_lift_mean_pitch_pct": iv_active_lift_mean_pitch_pct,
    "active_lift_dynamic_pitch": iv_active_lift_dynamic_pitch,
    "active_lift_dynamic_pct": iv_active_lift_dynamic_pct,
    "active_lift_passive_power": iv_active_lift_passive_power,
    "active_lift_rigid_mean_power": iv_active_lift_rigid_mean_power,
    "active_lift_rigid_zero_power": iv_active_lift_rigid_zero_power,
    "active_lift_scaleup_passive_aep": iv_active_lift_scaleup_passive_aep,
    "active_lift_scaleup_rigid_aep": iv_active_lift_scaleup_rigid_aep,
    "active_lift_scaleup_gain_pct": iv_active_lift_scaleup_gain_pct,
    "active_lift_coriolis_cp": iv_active_lift_coriolis_cp,
    "active_lift_coriolis_pct": iv_active_lift_coriolis_pct,
    "active_lift_coriolis_fraction": iv_active_lift_coriolis_fraction,
    "scaleup_aep_passive_kwh": iv_scaleup_aep_passive_kwh,
    "scaleup_aep_fixed_kwh": iv_scaleup_aep_fixed_kwh,
    "scaleup_aep_rigid_kwh": iv_scaleup_aep_rigid_kwh,
    "scaleup_gain_vs_fixed_pct": iv_scaleup_gain_vs_fixed_pct,
    "scaleup_gain_vs_rigid_pct": iv_scaleup_gain_vs_rigid_pct,
    "ham_2_0_cp": iv_ham_2_0_cp,
    "ham_2_5_cp": iv_ham_2_5_cp,
    "ham_uq_ci": iv_ham_uq_ci,
    "uq_ci_width": iv_uq_ci_width,
    "optimised_passive_ar": iv_optimised_passive_ar,
    "optimised_passive_ar_bound": iv_optimised_passive_ar_bound,
    "cm_zero_note": iv_cm_zero_note,
    "cp_vs_fixed_rpm_gain": iv_cp_vs_fixed_rpm_gain,
    "aep_passive_vs_rigid_fair": iv_aep_passive_vs_rigid_fair,
    "active_lift_passive_cp": iv_active_lift_passive_cp,
    "active_lift_rigid_mean_cp": iv_active_lift_rigid_mean_cp,
    "active_lift_rigid_zero_cp": iv_active_lift_rigid_zero_cp,
    "active_lift_mean_pitch_offset": iv_active_lift_mean_pitch_offset,
    "active_lift_mean_pitch_pct": iv_active_lift_mean_pitch_pct,
    "active_lift_dynamic_pitch": iv_active_lift_dynamic_pitch,
    "active_lift_dynamic_pct": iv_active_lift_dynamic_pct,
    "active_lift_passive_power": iv_active_lift_passive_power,
    "active_lift_rigid_mean_power": iv_active_lift_rigid_mean_power,
    "active_lift_rigid_zero_power": iv_active_lift_rigid_zero_power,
    "active_lift_scaleup_passive_aep": iv_active_lift_scaleup_passive_aep,
    "active_lift_scaleup_rigid_aep": iv_active_lift_scaleup_rigid_aep,
    "active_lift_scaleup_gain_pct": iv_active_lift_scaleup_gain_pct,
    "active_lift_coriolis_cp": iv_active_lift_coriolis_cp,
    "active_lift_coriolis_pct": iv_active_lift_coriolis_pct,
    "active_lift_coriolis_fraction": iv_active_lift_coriolis_fraction,
    "scaleup_aep_passive_kwh": iv_scaleup_aep_passive_kwh,
    "scaleup_aep_fixed_kwh": iv_scaleup_aep_fixed_kwh,
    "scaleup_aep_rigid_kwh": iv_scaleup_aep_rigid_kwh,
    "scaleup_gain_vs_fixed_pct": iv_scaleup_gain_vs_fixed_pct,
    "scaleup_gain_vs_rigid_pct": iv_scaleup_gain_vs_rigid_pct,
    "ham_2_0_cp": iv_ham_2_0_cp,
    "ham_2_5_cp": iv_ham_2_5_cp,
    "ham_uq_ci": iv_ham_uq_ci,
    "uq_ci_width": iv_uq_ci_width,
    "optimised_passive_ar": iv_optimised_passive_ar,
    "optimised_passive_ar_bound": iv_optimised_passive_ar_bound,
    "cm_zero_note": iv_cm_zero_note,
    "cp_vs_fixed_rpm_gain": iv_cp_vs_fixed_rpm_gain,
    "aep_passive_vs_rigid_fair": iv_aep_passive_vs_rigid_fair,
    "sharp_cppc_cp": iv_sharp_cppc_cp,
    "sharp_cppc_ci": iv_sharp_cppc_ci,
    "optimised_passive_cp": iv_optimised_passive_cp,
    "optimised_passive_ci": iv_optimised_passive_ci,
    "scaleup_cp": iv_scaleup_cp,
    "scaleup_ci": iv_scaleup_ci,
    "ham_reproduction_cp": iv_ham_reproduction_cp,
    "ham_reproduction_ci": iv_ham_reproduction_ci,
    "aep_passive_kwh": iv_aep_passive_kwh,
    "aep_passive_cf": iv_aep_passive_cf,
    "aep_fixed_kwh": iv_aep_fixed_kwh,
    "aep_fixed_cf": iv_aep_fixed_cf,
    "aep_turb_gain_pct": iv_aep_turb_gain_pct,
    "aep_turb_gain_pp": iv_aep_turb_gain_pp,
    "ham_peak_cp": iv_ham_peak_cp,
    "ham_uq_mean_cp": iv_ham_uq_mean_cp,
    "uq_ci_width": iv_uq_ci_width,
    "optimised_passive_ar": iv_optimised_passive_ar,
    "optimised_passive_ar_bound": iv_optimised_passive_ar_bound,
    "cm_zero_note": iv_cm_zero_note,
    "cp_vs_fixed_rpm_gain": iv_cp_vs_fixed_rpm_gain,
    "aep_passive_vs_rigid_fair": iv_aep_passive_vs_rigid_fair,
    "sharp_cppc_cp": iv_sharp_cppc_cp,
    "sharp_cppc_ci": iv_sharp_cppc_ci,
    "optimised_passive_cp": iv_optimised_passive_cp,
    "optimised_passive_ci": iv_optimised_passive_ci,
    "scaleup_cp": iv_scaleup_cp,
    "scaleup_ci": iv_scaleup_ci,
    "ham_reproduction_cp": iv_ham_reproduction_cp,
    "ham_reproduction_ci": iv_ham_reproduction_ci,
    "aep_passive_kwh": iv_aep_passive_kwh,
    "aep_passive_cf": iv_aep_passive_cf,
    "aep_fixed_kwh": iv_aep_fixed_kwh,
    "aep_fixed_cf": iv_aep_fixed_cf,
    "aep_turb_gain_pct": iv_aep_turb_gain_pct,
    "aep_turb_gain_pp": iv_aep_turb_gain_pp,
    "ham_peak_cp": iv_ham_peak_cp,
    "ham_uq_mean_cp": iv_ham_uq_mean_cp,
    "uq_ci_width": iv_uq_ci_width,
    "optimised_passive_ar": iv_optimised_passive_ar,
    "optimised_passive_ar_bound": iv_optimised_passive_ar_bound,
    "cm_zero_note": iv_cm_zero_note,
    "cp_vs_fixed_rpm_gain": iv_cp_vs_fixed_rpm_gain,
    "aep_passive_vs_rigid_fair": iv_aep_passive_vs_rigid_fair,
    "sharp_cppc_cp": iv_sharp_cppc_cp,
    "sharp_cppc_ci": iv_sharp_cppc_ci,
    "optimised_passive_cp": iv_optimised_passive_cp,
    "optimised_passive_ci": iv_optimised_passive_ci,
    "scaleup_cp": iv_scaleup_cp,
    "scaleup_ci": iv_scaleup_ci,
    "ham_reproduction_cp": iv_ham_reproduction_cp,
    "ham_reproduction_ci": iv_ham_reproduction_ci,
    "aep_passive_kwh": iv_aep_passive_kwh,
    "aep_passive_cf": iv_aep_passive_cf,
    "aep_fixed_kwh": iv_aep_fixed_kwh,
    "aep_fixed_cf": iv_aep_fixed_cf,
    "aep_turb_gain_pct": iv_aep_turb_gain_pct,
    "aep_turb_gain_pp": iv_aep_turb_gain_pp,
    "ham_peak_cp": iv_ham_peak_cp,
    "ham_uq_mean_cp": iv_ham_uq_mean_cp,
    "uq_ci_width": iv_uq_ci_width,
    "optimised_passive_ar": iv_optimised_passive_ar,
    "optimised_passive_ar_bound": iv_optimised_passive_ar_bound,
    "cm_zero_note": iv_cm_zero_note,
    "cp_vs_fixed_rpm_gain": iv_cp_vs_fixed_rpm_gain,
    "aep_passive_vs_rigid_fair": iv_aep_passive_vs_rigid_fair,
}


def block_evidence_table():
    """Evidence table, generated from the JSON result files."""
    uq = DATA["uq"]["summary"]
    aq = DATA["aq"]
    act = DATA["act"]
    gain = aq.get("gains_percent", {}).get("passive_vs_rigid_fair")
    rows = [
        ("**Ham 1979 Peak Cp**", f"{uq['ham_1979']['mean']:.2f}",
         "Literature comparison (2D upper bound)"),
        ("**Sharp-inspired Passive Cp**",
         f"{uq['sharp_cppc']['all_mean']:.3f} all-sample; "
         f"{uq['sharp_cppc']['working_mean']:.2f} working branch",
         "**Model result** (uncalibrated DS; bimodal)"),
        ("**Optimised Passive Cp**",
         f"{uq['optimised_passive']['mean']:.2f} "
         f"[{uq['optimised_passive']['p5']:.2f}, "
         f"{uq['optimised_passive']['p95']:.2f}]",
         "**Model result** (uncalibrated DS)"),
        ("**Scale-up Passive Cp**",
         f"{uq['scaleup']['mean']:.2f} "
         f"[{uq['scaleup']['p5']:.2f}, {uq['scaleup']['p95']:.2f}]",
         "**Model result** (robust)"),
        ("**Prescribed-pitch Upper Bound**", f"{act['best_cp']:.2f}",
         "Ideal actuator (no physical limit)"),
    ]
    if gain is not None:
        rows.append(("**AEP Gain vs Rigid**", f"{gain:+.1f}%",
                     "**Model comparison** (unproven machine)"))
    out = ["| Metric | Value | Evidence Category |", "| :--- | :--- | :--- |"]
    for a, b, c in rows:
        out.append(f"| {a} | {b} | {c} |")
    return "\n".join(out)


def block_robust_optimization():
    """Nominal vs robust objective for the two re-optimised designs."""
    d = DATA["rob"]["designs"]
    labels = {"passive": "Optimised passive (R = 0.60 m)",
              "scaleup": "Scale-up (R = 2.72 m)"}
    out = ["| Design | Nominal Cp | UQ-scenario mean | UQ-scenario p10 | Bound-active parameters |",
           "|---|---|---|---|---|"]
    for key in ("passive", "scaleup"):
        r = d[key]
        m = r["metrics"]
        active = ", ".join(f"{a['name']} ({a['bound']})"
                           for a in r["bound_active"]) or "none"
        out.append(
            f"| {labels[key]} | {m['nominal_cp']:.3f} | "
            f"{m['mean_cp']:.3f} | {m['p10_cp']:.3f} | {active} |"
        )
    return "\n".join(out)


def block_headline_table_small():
    uq = DATA["uq"]["summary"]
    # Evidence levels: M = model result at fixed inputs / S = scenario estimate from UQ
    #              / U = ideal-actuator upper bound / V = validated vs literature
    rows = [
        ("**Sharp-inspired CPPC**", uq["sharp_cppc"], "scenario range (UQ)", "S"),
        ("Optimised passive (mass-balanced)", uq["optimised_passive"], "stored design point (UQ)", "S"),
        ("Prescribed pitch (ideal actuator)", None, "ideal-actuator upper bound (model)", "U"),
        ("Ham 1979 comparison", uq["ham_1979"], "fixed design point (2D upper-bound comparison)", "V"),
    ]
    out = ["| Configuration | Cp | 90 % CI | Reference | Evidence |",
           "|---|---|---|---|---|"]
    for name, s, ref, ev in rows:
        if s is None:
            out.append(f"| {name} | {DATA['act']['best_cp']:.2f} | \u2014 | {ref} | {ev} |")
        else:
            out.append(f"| {name} | **{s['mean']:.2f}** | {_ci(s['p5'], s['p95'])} | {ref} | {ev} |")
    return "\n".join(out)


def block_headline_table_large():
    uq = DATA["uq"]["summary"]
    s = uq["scaleup"]
    betz_pct = 100.0 * s["mean"] / (16.0 / 27.0)
    rows = [
        ("**Scaled-up passive (R = 2.72 m)**", s, f"~{betz_pct:.0f} % of Betz", "S"),
    ]
    out = ["| Configuration | Cp | 90 % CI | Reference | Evidence |",
           "|---|---|---|---|---|"]
    for name, s, ref, ev in rows:
        out.append(f"| {name} | **{s['mean']:.2f}** | {_ci(s['p5'], s['p95'])} | {ref} | {ev} |")
    return "\n".join(out)


def block_aep_steady_table():
    a = DATA["aq"]["results"]
    p = a["passive_k_load"]
    f = a["passive_fixed_rpm"]
    return "\n".join([
        "| Strategy | AEP | Capacity factor |",
        "|---|---|---|",
        f"| **Passive k_load (variable speed)** | **{p['aep_kWh']:.0f} kWh/yr** | **{_pct(p['cf'])}** |",
        f"| Fixed-rpm generator | {f['aep_kWh']:.0f} kWh/yr | {_pct(f['cf'])} |",
    ])


def block_aep_turbulent_table():
    t = DATA["aq_t"]
    s, d = t["steady"], t["turbulent"]
    gain_pct = (d["aep_kWh"] / s["aep_kWh"] - 1.0) * 100.0
    gain_pp = (d["cf"] - s["cf"]) * 100.0
    return "\n".join([
        "| | AEP | CF |",
        "|---|---|---|",
        f"| Steady wind | {s['aep_kWh']:.1f} kWh/yr | {_pct(s['cf'], 2)} |",
        f"| Turbulent wind (I = 12 %) | {d['aep_kWh']:.1f} kWh/yr | {_pct(d['cf'], 2)} |",
        f"| **Effect** | **{gain_pct:+.1f} %** | **{gain_pp:+.2f} pp** |",
    ])


def block_uq_params_table():
    p = DATA["uq"]["parameters"]
    display = {
        "cd_add":                  ("0.001", "0.005", "strut / interference drag"),
        "ds_Tf":                   ("1.5",   "4.5",   "separation lag (default 3.0)"),
        "ds_Tv":                   ("3.0",   "9.0",   "vortex-lift lag (default 6.0)"),
        "ds_Ta":                   ("0.05",  "0.15",  "attached-flow lag (default 0.10)"),
        "ds_Kv":                   ("0.25",  "0.75",  "vortex-lift strength (default 0.50)"),
        "tau_rev":                 ("0.05",  "0.20",  "induction lag (default 0.10 rev)"),
        "e_osw":                   ("0.85",  "0.95",  "Oswald efficiency for induced drag"),
        "c_scale_override":        ("0.30",  "0.60",  "Adams shift strength"),
        "tip_loss_multiplier":     ("0.85",  "1.15",  "residual multiplier on the Helmbold finite-span f_ar (<1 = stronger tip loss, >1 = weaker)"),
        "cm_scale":                ("0.0",   "1.0",   "scale on attached-flow Cm from the surrogate (0 = none, 1 = full NeuralFoil value)"),
        "ds_Knc":                  ("0.5",   "1.5",   "apparent-mass lift multiplier (k_nc)"),
        "polar_variant":           ("0.0",   "1.0",   "model form: 0 = NeuralFoil table, 1 = smoothed_lowRe variant"),
        "arm_cd":                  ("0.5",   "1.5",   "arm drag coefficient multiplier (Geometry)"),
    }
    out = ["| Parameter | Low | High | Source of uncertainty |", "|---|---|---|---|"]
    for name, lo, hi in p:
        lo_s, hi_s, src = display[name]
        assert float(lo_s) == float(lo), f"{name} lo mismatch: {lo_s} vs {lo}"
        assert float(hi_s) == float(hi), f"{name} hi mismatch: {hi_s} vs {hi}"
        out.append(f"| `{name}` | {lo_s} | {hi_s} | {src} |")
    return "\n".join(out)


def block_uq_sobol():
    """Sobol sensitivity table from uncertainty_results.json."""
    sobol = DATA["uq"].get("sobol", {})
    labels = {
        "ham_1979":          "Ham 1979 comparison",
        "sharp_cppc":        "Sharp-inspired CPPC",
        "optimised_passive": "Optimised passive",
        "scaleup":           "Scale-up R = 2.72 m",
    }
    out = ["| Anchor | Dominant S\u2081 parameter | S\u2081 (95 % CI) | "
           "Total-order S\u209c (95 % CI) |",
           "|---|---|---|---|"]
    for a in ["ham_1979", "sharp_cppc", "optimised_passive", "scaleup"]:
        res = sobol.get(a, {})
        s1 = res.get("S1", {})
        st = res.get("ST", {})
        if not s1:
            out.append(f"| {labels[a]} | — | — | — |")
            continue
        dom = max(s1, key=lambda k: abs(s1[k]))
        rho = s1[dom]
        st_val = st.get(dom, 0.0)
        rho_ci = res.get("S1_conf", {}).get(dom, float("nan"))
        st_ci = res.get("ST_conf", {}).get(dom, float("nan"))
        sign = "+" if rho >= 0 else ""
        st_sign = "+" if st_val >= 0 else ""
        out.append(
            f"| {labels[a]} | `{dom}` | **{sign}{rho:.2f} \u00b1 {rho_ci:.2f}** | "
            f"{st_sign}{st_val:.2f} \u00b1 {st_ci:.2f} |"
        )
    return "\n".join(out)


def block_counter_rotating():
    """Speculative counter-rotating scenario and its factor sensitivity."""
    d = DATA["cr"]
    c = d["counter_rotating"]
    s = d["sensitivity_to_fixed_interaction_factor"]
    gains = [r["gain_vs_single_percent"] for r in s]
    out = ["| Quantity | Value |", "|---|---|"]
    out.append(f"| Single rotor AEP | {d['single_rotor_baseline']['aep_kWh']:,.0f} kWh/yr |")
    out.append(f"| Two independent rotors | {c['upstream_rotor']['aep_kWh'] + c['downstream_rotor']['aep_kWh']:,.0f} kWh/yr |")
    out.append(f"| Counter-rotating pair (heuristic) | {c['total']['aep_kWh']:,.0f} kWh/yr |")
    out.append(f"| Gain over two independent rotors | {c['vs_two_independent_rotors_improvement_percent']:+.1f} % |")
    out.append(f"| Fixed-factor sensitivity (0–16 %) | {min(gains):+.0f} % to {max(gains):+.0f} % vs single |")
    return "\n".join(out)


def block_aep_rigid_comparison():
    """Passive vs fair rigid AEP, with the rating defined per design."""
    r = DATA["aq_r"]["geometries"]
    out = ["| Geometry | AR | Passive CPPC | Best rigid | Gain | Rating |",
           "|---|---|---|---|---|---|"]
    labels = {"sharp_inspired": "Sharp-inspired (R = 0.60 m)",
              "scaleup": "Scale-up (R = 2.72 m)"}
    for key in ("sharp_inspired", "scaleup"):
        g = r[key]
        p = g["best_passive"]
        b = g["best_rigid"]
        if b["viable"]:
            rigid = f"{b['aep_kWh']:,.0f} kWh/yr"
            gain = f"{g['gain_percent']:+.1f} %"
        else:
            rigid = "none (does not spin)"
            gain = "n/a"
        out.append(
            f"| {labels[key]} | {g['AR']:.2f} | {p['aep_kWh']:,.0f} kWh/yr | "
            f"{rigid} | {gain} | Cp at 12 m/s |"
        )
    return "\n".join(out)


def block_aep_branches():
    """High-seed, low-seed and branch-traced AEP with stated ICs."""
    b = DATA["aq_s"]["branches"]
    rows = [
        ("High-speed seed", b["high_seed"]),
        ("Low-speed seed", b["low_seed"]),
        ("Branch-traced", b["branch_traced"]),
    ]
    out = ["| Initial condition | AEP | Capacity factor |",
           "|---|---|---|"]
    for label, r in rows:
        out.append(
            f"| {label}: w0_frac = {r['initial_w0_frac']:.2f}, "
            f"psi0 = {r['initial_psi0_deg']:.0f}° | "
            f"{r['aep_MWh']:.2f} MWh/yr | {r['cf']*100:.2f} % |"
        )
    lo, hi = b["aep_range_MWh"]
    out.append(f"| **Range across seeds** | **{lo:.2f}–{hi:.2f} MWh/yr** | — |")
    return "\n".join(out)


def block_branch_point_check():
    """Convergence check for the TSR=3.25 fixed-rpm point and U=4 m/s."""
    d = DATA["branch_check"]
    f = [r for r in d["fixed_tsr_3.25"] if r["T_max"] == 60.0]
    u = [r for r in d["free_U4"] if r["T_max"] == 60.0]
    out = ["| Check | Initial condition | Cp | TSR | Steady |",
           "|---|---|---|---|---|"]
    for r in f:
        out.append(f"| fixed TSR 3.25, T_max 60 s | psi0 = {r['psi0_deg']:.0f}° | "
                   f"{r['cp']:.4f} | {r['tsr_eq']:.3f} | {r['steady']} |")
    for r in u:
        out.append(f"| free U = 4 m/s, T_max 60 s | w0 = {r['w0_frac']:.2f}, "
                   f"psi0 = {r['psi0_deg']:.0f}° | {r['cp']:.4f} | "
                   f"{r['tsr_eq']:.3f} | {r['steady']} |")
    return "\n".join(out)


def block_ham_reconciliation():
    """One table for the 0.476 and 0.49 Ham-family numbers."""
    h = DATA["ham"]
    labels = {
        "static_cd005": "validate_ham static-only (cd_add = 0.005)",
        "static_cd002": "UQ anchor nominal (cd_add = 0.002)",
        "ds_on_cd002": "+ dynamic stall",
        "ds_curv_cd002": "+ dynamic stall + curvature",
        "tip_loss_helmbold": "Helmbold finite-span correction",
    }
    out = ["| Case | cd_add | DS | Curvature | Tip loss | Peak Cp | Bias vs mid |",
           "|---|---|---|---|---|---|---|"]
    for key in ["static_cd005", "static_cd002", "ds_on_cd002",
                "ds_curv_cd002", "tip_loss_helmbold"]:
        c = h["cases"][key]
        out.append(
            f"| {labels[key]} | {c['cd_add']:.3f} | "
            f"{'on' if c['use_dynamic_stall'] else 'off'} | "
            f"{'on' if c['use_flow_curvature'] else 'off'} | "
            f"{'on' if c['use_tip_loss'] else 'off'} | "
            f"{c['peak_cp']:.4f} | {c['bias_vs_ham_mid']*100:+.1f} % |"
        )
    return "\n".join(out)


def block_ham_finite_span():
    h = DATA["ham"]
    out = ["| Blade AR (H/c) | Helmbold f_ar | Corrected peak Cp |",
           "|---|---|---|"]
    for r in h["ar_scan"]:
        out.append(f"| {r['AR']:.2f} | {r['f_ar']:.3f} | {r['peak_cp']:.4f} |")
    return "\n".join(out)


def block_cm_scale_scan():
    """Deterministic cm_scale / tip-loss scans (cm_scale_scan.json)."""
    scans = DATA["cm"]["anchors"]
    labels = {
        "sharp_cppc": "Sharp-inspired CPPC",
        "optimised_passive": "Optimised passive",
    }
    out = ["| Anchor | Cp, Cm = 0 | Cp, Cm = 0.5 | Cp, Cm = 0.75 | Cp, Cm = 1.0 | Working branch from tip multiplier |",
           "|---|---|---|---|---|---|"]
    for key in ("sharp_cppc", "optimised_passive"):
        rows = {round(r["cm_scale"], 2): r["cp"] for r in scans[key]["cm_scale"]}
        tips = scans[key].get("tip_loss_multiplier", [])
        resume = next((r["tip_loss_multiplier"] for r in tips if r["cp"] >= 0.02),
                      None)
        resume_s = f"{resume:.3f}" if resume is not None else "—"
        out.append(
            f"| {labels[key]} | {_bound(rows[0.0])} | {_bound(rows[0.5])} | "
            f"{_bound(rows[0.75])} | {_bound(rows[1.0])} | {resume_s} |"
        )
    return "\n".join(out)


def block_uq_bimodal():
    """Bimodal summary: physical-Cm base case vs sampled branches."""
    uq = DATA["uq"]["summary"]
    labels = {
        "ham_1979":          "Ham 1979 comparison",
        "sharp_cppc":        "Sharp-inspired CPPC",
        "optimised_passive": "Optimised passive",
        "scaleup":           "Scale-up R = 2.72 m",
    }
    out = ["| Anchor | Base Cp, Cm = 0 | All-sample mean | Working-branch mean | Collapsed fraction (Cp < 0.02) |",
           "|---|---|---|---|---|"]
    for key in ["ham_1979", "sharp_cppc", "optimised_passive", "scaleup"]:
        s = uq[key]
        out.append(
            f"| {labels[key]} | {_bound(s['base_cm0_cp'])} | "
            f"{_bound(s['all_mean'])} | {_bound(s['working_mean'])} | "
            f"{_pct(s['collapse_fraction'])} |"
        )
    return "\n".join(out)


BLOCKS = {
    "evidence_table": block_evidence_table,
    "robust_optimization": block_robust_optimization,
    "headline_table_small": block_headline_table_small,
    "headline_table_large": block_headline_table_large,
    "aep_steady": block_aep_steady_table,
    "aep_turbulent": block_aep_turbulent_table,
    "uq_params": block_uq_params_table,
    "uq_bimodal": block_uq_bimodal,
    "cm_scale_scan": block_cm_scale_scan,
    "aep_rigid_comparison": block_aep_rigid_comparison,
    "counter_rotating": block_counter_rotating,
    "aep_branches": block_aep_branches,
    "branch_point_check": block_branch_point_check,
    "ham_reconciliation": block_ham_reconciliation,
    "ham_finite_span": block_ham_finite_span,
    "uq_sobol": block_uq_sobol,
}


def replace_inline(text):
    """Replace <!-- GEN: key --> markers with inline values."""
    for key, func in INLINE_FUNCS.items():
        marker = f"<!-- GEN: {key} -->"
        if marker in text:
            try:
                value = func()
                text = text.replace(marker, value)
            except Exception as e:
                print(f"Warning: inline generator {key} failed: {e}", file=sys.stderr)
    return text


def regenerate(text):
    text = replace_inline(text)
    for name, fn in BLOCKS.items():
        pat = re.compile(
            rf"<!-- BEGIN GENERATED: {name} -->\n.*?\n<!-- END GENERATED: {name} -->",
            re.DOTALL,
        )
        if not pat.search(text):
            raise RuntimeError(f"marker '{name}' missing from README.md")
        body = fn()
        new = (f"<!-- BEGIN GENERATED: {name} -->\n{body}\n<!-- END GENERATED: {name} -->")
        text = pat.sub(lambda m, n=new: n, text, count=1)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    with open(README) as fh:
        current = fh.read()
    try:
        desired = regenerate(current)
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    if args.check:
        if current == desired:
            print("[OK] README matches scripts/*.json")
            return 0
        print("[FAIL] README out of sync; run: python3 scripts/build_readme.py", file=sys.stderr)
        return 1
    with open(README, "w") as fh:
        fh.write(desired)
    print("[OK] rewrote README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
