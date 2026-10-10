"""
Regenerate JSON-backed numeric blocks in README.md.

Usage:
    python3 scripts/build_readme.py           # rewrite README.md in place
    python3 scripts/build_readme.py --check   # exit 1 if out of sync
"""
import argparse, json, os, re, sys

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
README  = os.path.join(ROOT, "README.md")

def _j(name):
    with open(os.path.join(SCRIPTS, name)) as fh:
        return json.load(fh)

def _ci(lo, hi, d=2):
    return f"[{lo:.{d}f}, {hi:.{d}f}]"

def _pct(x, d=1):
    return f"{x*100:.{d}f} %"


def block_headline_table():
    uq = _j("uncertainty_results.json")["summary"]
    rows = [
        ("**Scaled-up passive (R = 2.72 m, Re = 5.1e5)**",
         uq["scaleup"], "~71 % of Betz"),
        ("**Sharp-inspired CPPC**",
         uq["sharp_cppc"], "\u2014"),
        ("Optimised passive (mass-balanced)",
         uq["optimised_passive"], "\u2014"),
        ("Prescribed pitch (ideal actuator)", None,
         "Ham 1979 measured 0.42\u20130.45"),
        ("Ham 1979 reproduction",
         uq["ham_1979"], "matches Ham's method"),
    ]
    out = ["| Configuration | Cp | 90 % CI | Reference |",
           "|---|---|---|---|"]
    for name, s, ref in rows:
        if s is None:
            out.append(f"| {name} | 0.48 | \u2014 | {ref} |")
        else:
            out.append(f"| {name} | **{s['mean']:.2f}** "
                       f"| {_ci(s['p5'], s['p95'])} | {ref} |")
    return "\n".join(out)


def block_aep_steady_table():
    a = _j("aep_results.json")
    p = a["results"]["passive_k_load"]
    f = a["results"]["passive_fixed_rpm"]
    return "\n".join([
        "| Strategy | AEP | Capacity factor |",
        "|---|---|---|",
        f"| **Passive k_load (variable speed)** | **{p['aep_kWh']:.0f} kWh/yr** "
        f"| **{_pct(p['cf'])}** |",
        f"| Fixed-rpm generator | {f['aep_kWh']:.0f} kWh/yr "
        f"| {_pct(f['cf'])} |",
    ])


def block_aep_turbulent_table():
    t = _j("aep_turbulent.json")
    s, d = t["steady"], t["turbulent"]
    gain_pct = (d["aep_kWh"] / s["aep_kWh"] - 1.0) * 100.0
    gain_pp  = (d["cf"] - s["cf"]) * 100.0
    return "\n".join([
        "| | AEP | CF |",
        "|---|---|---|",
        f"| Steady wind | {s['aep_kWh']:.1f} kWh/yr | {_pct(s['cf'], 2)} |",
        f"| Turbulent wind (I = 12 %) | {d['aep_kWh']:.1f} kWh/yr | {_pct(d['cf'], 2)} |",
        f"| **Effect** | **{gain_pct:+.1f} %** | **{gain_pp:+.2f} pp** |",
    ])


def block_uq_params_table():
    p = _j("uncertainty_results.json")["parameters"]
    # Display strings preserve the significant figures of the original bounds.
    # Values are asserted against the JSON so drift is caught here.
    display = {
        "cd_add":                  ("0.001", "0.005", "strut / interference drag"),
        "ds_Tf":                   ("1.5",   "4.5",   "separation lag (default 3.0)"),
        "ds_Tv":                   ("3.0",   "9.0",   "vortex-lift lag (default 6.0)"),
        "ds_Ta":                   ("0.05",  "0.15",  "attached-flow lag (default 0.10)"),
        "ds_Kv":                   ("0.25",  "0.75",  "vortex-lift strength (default 0.50)"),
        "tau_rev":                 ("0.05",  "0.20",  "induction lag (default 0.10 rev)"),
        "c_scale_override":        ("0.30",  "0.60",  "Adams shift strength"),
        "tip_loss_floor_override": ("0.80",  "1.00",  "finite-span correction floor"),
    }
    out = ["| Parameter | Low | High | Source of uncertainty |",
           "|---|---|---|---|"]
    for name, lo, hi in p:
        lo_s, hi_s, src = display[name]
        assert float(lo_s) == float(lo), f"{name} lo mismatch: {lo_s} vs {lo}"
        assert float(hi_s) == float(hi), f"{name} hi mismatch: {hi_s} vs {hi}"
        out.append(f"| `{name}` | {lo_s} | {hi_s} | {src} |")
    return "\n".join(out)


def block_spearman_table():
    sp = _j("spearman_results.json")["anchor_results"]
    labels = {
        "ham_1979":          "Ham 1979 reproduction",
        "sharp_cppc":        "Sharp-inspired CPPC",
        "optimised_passive": "Optimised passive",
        "scaleup":           "Scale-up R = 2.72 m",
    }
    pretty = {
        "cd_add":                  "`cd_add` (strut drag)",
        "ds_Tf":                   "`ds_Tf` (separation lag)",
        "ds_Tv":                   "`ds_Tv` (vortex-lift lag)",
        "ds_Ta":                   "`ds_Ta` (attached-flow lag)",
        "ds_Kv":                   "`ds_Kv` (vortex-lift strength)",
        "tau_rev":                 "`tau_rev` (induction lag)",
        "c_scale_override":        "`c_scale_override` (Adams shift)",
        "tip_loss_floor_override": "`tip_loss_floor_override`",
    }
    out = ["| Anchor | Dominant parameter | \u03c1 | p-value |",
           "|---|---|---|---|"]
    for a in ["ham_1979", "sharp_cppc", "optimised_passive", "scaleup"]:
        d = sp[a]
        dom = max(d, key=lambda k: abs(d[k]["rho"]))
        rho, p = d[dom]["rho"], d[dom]["p"]
        ps = "< 0.001" if p < 1e-3 else f"{p:.3f}"
        out.append(f"| {labels[a]} | {pretty[dom]} "
                   f"| **{'+' if rho >= 0 else ''}{rho:.2f}** | {ps} |")
    return "\n".join(out)


BLOCKS = {
    "headline_table": block_headline_table,
    "aep_steady":     block_aep_steady_table,
    "aep_turbulent":  block_aep_turbulent_table,
    "uq_params":      block_uq_params_table,
    "spearman_table": block_spearman_table,
}


def regenerate(text):
    for name, fn in BLOCKS.items():
        pat = re.compile(
            rf"<!-- BEGIN GENERATED: {name} -->\n.*?\n"
            rf"<!-- END GENERATED: {name} -->",
            re.DOTALL,
        )
        if not pat.search(text):
            raise RuntimeError(f"marker '{name}' missing from README.md")
        body = fn()
        new = (f"<!-- BEGIN GENERATED: {name} -->\n"
               f"{body}\n"
               f"<!-- END GENERATED: {name} -->")
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
        print("[FAIL] README out of sync; run: python3 scripts/build_readme.py",
              file=sys.stderr)
        return 1
    with open(README, "w") as fh:
        fh.write(desired)
    print("[OK] rewrote README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())