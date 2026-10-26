"""Generated-README provenance tests.

Covers:
* ``scripts/build_readme.py`` idempotency and on-disk sync,
* Sobol labelling (``base_n`` in JSON + stamp, quick-mode sentence,
  "not resolved" for overlapping 95 % intervals),
* consistency of named quantities with their stamped JSON sources.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
SCRIPTS_README = ROOT / "scripts" / "README.md"
UQ_JSON = ROOT / "scripts" / "uncertainty_results.json"
HAM_JSON = ROOT / "scripts" / "ham_finite_span_check.json"
TL_JSON = ROOT / "scripts" / "tip_loss_scan.json"
OPT_SCALEUP = ROOT / "scripts" / "optimization_scaleup.json"

sys.path.insert(0, str(ROOT))
import scripts.build_readme as br


def _gen_ranges(text: str):
    """Return (name, start_line, end_line) for every generated block."""
    out = []
    for m in re.finditer(
        r"<!-- BEGIN GENERATED: (\w+) -->\n(.*?)\n<!-- END GENERATED: \1 -->",
        text,
        re.DOTALL,
    ):
        start = text[: m.start()].count("\n") + 1
        end = text[: m.end()].count("\n") + 1
        out.append((m.group(1), start, end, m.group(2)))
    return out


def _block(text: str, name: str) -> str:
    for n, _s, _e, body in _gen_ranges(text):
        if n == name:
            return body
    raise AssertionError(f"generated block {name!r} not found")


# ---------------------------------------------------------------------------
# Idempotency / sync
# ---------------------------------------------------------------------------
def test_build_readme_is_idempotent():
    text = README.read_text(encoding="utf-8")
    once = br.regenerate(text)
    twice = br.regenerate(once)
    assert once == twice, "build_readme.py is not idempotent"


def test_build_readme_matches_on_disk():
    text = README.read_text(encoding="utf-8")
    assert br.regenerate(text) == text, "README.md is out of sync; run build_readme.py"


# ---------------------------------------------------------------------------
# Sobol labelling (item 1)
# ---------------------------------------------------------------------------
def test_base_n_present_in_json_and_stamp():
    d = json.loads(UQ_JSON.read_text(encoding="utf-8"))
    assert "base_n" in d, "uncertainty_results.json body missing base_n"
    assert "runs_per_anchor" in d
    extra = d["stamp"]["extra_data"]
    assert "base_n" in extra, "uncertainty stamp extra_data missing base_n"
    assert extra["base_n"] == d["base_n"]
    assert "runs_per_anchor" in extra
    assert d["base_n"] >= 1
    assert d["runs_per_anchor"] >= d["base_n"]


def test_quick_mode_sentence_when_base_n_below_512():
    d = json.loads(UQ_JSON.read_text(encoding="utf-8"))
    base_n = d["base_n"]
    if base_n >= 512:
        return
    expected = f"base N = {base_n} (quick mode); indices are qualitative"
    assert expected in README.read_text(encoding="utf-8")
    assert expected in SCRIPTS_README.read_text(encoding="utf-8")


def _with_sobol(sobol, fn):
    saved = br.DATA["uq"]["sobol"]
    try:
        br.DATA["uq"]["sobol"] = sobol
        return fn()
    finally:
        br.DATA["uq"]["sobol"] = saved


def test_overlapping_sobol_intervals_emit_not_resolved():
    """A synthetic overlapping pair must print 'not resolved', not a ranking."""
    overlapping = {
        "S1": {"alpha": 0.50, "beta": 0.45},
        "S1_conf": {"alpha": 0.20, "beta": 0.20},
        "ST": {"alpha": 0.60, "beta": 0.50},
        "ST_conf": {"alpha": 0.10, "beta": 0.10},
    }
    out = _with_sobol({"ham_1979": overlapping}, br.block_uq_sobol)
    assert "not resolved" in out
    table = _with_sobol({"ham_1979": overlapping}, br.block_uq_sobol)
    line = next(ln for ln in table.splitlines() if ln.startswith("| Ham"))
    assert "not resolved" in line
    assert "alpha" not in line


def test_disjoint_sobol_intervals_are_resolved():
    """Negative control: disjoint intervals must produce a ranking."""
    disjoint = {
        "S1": {"alpha": 0.80, "beta": 0.10},
        "S1_conf": {"alpha": 0.05, "beta": 0.05},
        "ST": {"alpha": 0.85, "beta": 0.12},
        "ST_conf": {"alpha": 0.04, "beta": 0.04},
    }
    line = _with_sobol(
        {"ham_1979": disjoint},
        lambda: next(ln for ln in br.block_uq_sobol().splitlines() if ln.startswith("| Ham")),
    )
    assert "not resolved" not in line
    assert "`alpha`" in line


# ---------------------------------------------------------------------------
# Named-quantity consistency (item 4)
# ---------------------------------------------------------------------------
def test_headline_cp_matches_uq_json():
    uq = json.loads(UQ_JSON.read_text(encoding="utf-8"))["summary"]
    text = README.read_text(encoding="utf-8")
    small = _block(text, "headline_table_small")
    large = _block(text, "headline_table_large")

    def cell(block, label):
        for ln in block.splitlines():
            if label in ln:
                cells = [c.strip() for c in ln.strip("|").split("|")]
                return cells[1].replace("*", "")
        raise AssertionError(f"{label!r} not found")

    checks = [
        ("Sharp-inspired CPPC", uq["sharp_cppc"]),
        ("Optimised passive", uq["optimised_passive"]),
        ("Ham 1979 comparison", uq["ham_1979"]),
    ]
    for label, s in checks:
        assert cell(small, label) == f"{s['mean']:.2f}", label
    assert cell(large, "Scaled-up passive") == f"{uq['scaleup']['mean']:.2f}"


def test_ham_peak_matches_json():
    ham = json.loads(HAM_JSON.read_text(encoding="utf-8"))
    expected = f"{ham['cases']['static_cd005']['peak_cp']:.4f}"
    text = README.read_text(encoding="utf-8")
    body = _block(text, "ham_reconciliation")
    row = next(ln for ln in body.splitlines() if "static-only" in ln)
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[-2] == expected, f"Ham peak {cells[-2]} != JSON {expected}"


def test_nominal_cp_prose_matches_json():
    tl = json.loads(TL_JSON.read_text(encoding="utf-8"))
    opt = json.loads(OPT_SCALEUP.read_text(encoding="utf-8"))
    text = README.read_text(encoding="utf-8")

    def nominal(anchor):
        entries = tl["anchors"][anchor]
        e = min(entries, key=lambda r: abs(r["multiplier"] - 1.0))
        return f"{e['cp']:.3f}"

    expected = {
        "sharp": nominal("sharp_cppc"),
        "scaleup": f"{opt['best_cp']:.3f}",
    }
    patterns = {
        "sharp": r"nominal design point \(Helmbold multiplier 1\.0\) gives Cp = `([0-9.]+)`",
        "scaleup": r"The fixed design point evaluates to Cp ≈ `([0-9.]+)`",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        assert m, f"nominal-Cp sentence for {key} not found"
        assert m.group(1) == expected[key], f"{key}: README {m.group(1)} != JSON {expected[key]}"
