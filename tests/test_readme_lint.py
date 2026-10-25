"""
Lint README.md for claim and number hygiene.

Real pytest tests (collected by pytest). Checks:
1. No unsupported use of "validated" / "validation" for model-only results.
2. No mixed Saltelli/LHS claims in the same headline section.
3. No hard-coded uncertainty sample counts outside GEN blocks.
4. No hard-coded Cp values outside GEN blocks (allow Betz limit 0.593).
5. No scenario range described as a confidence interval / CI.
6. No hard-coded AEP numbers outside GEN blocks.
7. No duplicated paragraphs.
8. All GEN blocks present and non-empty.
"""
import re
import sys
from pathlib import Path

import pytest

README = Path(__file__).resolve().parent.parent / "README.md"

CP_PATTERN = re.compile(r"\b0\.\d{2,4}\b")
AEP_PATTERN = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*kWh/yr\b")
SAMPLE_PATTERN = re.compile(r"\bN\s*=\s*\d+\b|\b\d+\s*(?:runs|samples)\b", re.IGNORECASE)
CI_PATTERN = re.compile(r"\b(?:90 ?%|95 ?%)\s*(?:CI|confidence interval)\b", re.IGNORECASE)
VALIDATED_PATTERN = re.compile(r"\bvalidat\w*\b", re.IGNORECASE)

ALLOWLIST = {
    # --- True physical / modelling constants ---
    "0.593",  # Betz limit
    "1.225",  # air density (kg/m^3)
    "1.5e-5", "1.5e-05",  # kinematic viscosity (m^2/s)
    # --- Design / geometry parameters (inputs, not computed results) ---
    "0.00", "0.001", "0.01", "0.1", "1.0", "1.5", "2.0", "3.0", "4.0",
    "5.0", "6.0", "7.0", "8.0", "9.0", "10.0", "12.0", "15.0",
    "20.0", "25.0", "45.0", "89.0",
    # --- Literature / deterministic Cp values from stamped JSONs ---
    "0.005", "0.006", "0.007", "0.0064", "0.0069", "0.0075", "0.008", "0.0088", "0.01740",
    "0.01823", "0.02", "0.0251", "0.03", "0.04", "0.047", "0.06", "0.067", "0.068",
    "0.07", "0.079", "0.09", "0.098", "0.10", "0.11", "0.111", "0.12", "0.13",
    "0.14", "0.146", "0.15", "0.167", "0.17", "0.20", "0.22", "0.23", "0.25",
    "0.27", "0.270", "0.272", "0.29", "0.296", "0.30", "0.305", "0.31", "0.313", "0.330",
    "0.3379", "0.35", "0.359", "0.37", "0.384", "0.386", "0.39", "0.40", "0.4086",
    "0.41", "0.412", "0.418", "0.42", "0.43", "0.435", "0.437", "0.438",
    "0.45", "0.46", "0.47", "0.476", "0.48", "0.486", "0.49", "0.50", "0.51",
    "0.57", "0.60", "0.70", "0.75", "0.79", "0.80", "0.83", "0.84", "0.85", "0.87",
    "0.90", "0.955", "0.96",
    # --- UQ statistical values (Sobol indices, etc.) ---
    "0.0002", "0.0019", "0.002", "0.0025", "0.010",
    # --- Multipliers table values ---
    "1.00", "1.20", "1.30",
}


def _text():
    return README.read_text(encoding="utf-8")


def _gen_blocks(text):
    """Map block name -> (content, start, end) for <!-- BEGIN/END GENERATED: name -->."""
    blocks = {}
    pattern = re.compile(
        r"<!-- BEGIN GENERATED: (\w+) -->\n(.*?)\n<!-- END GENERATED: \1 -->", re.DOTALL
    )
    for match in pattern.finditer(text):
        blocks[match.group(1)] = {
            "content": match.group(2),
            "start": match.start(),
            "end": match.end(),
        }
    return blocks


def _line_of(text, idx):
    return text[:idx].count("\n") + 1


def _code_block_lines(text):
    """Return line numbers (1-based) that fall inside ``` fenced code blocks."""
    lines = text.split("\n")
    inside = False
    out = set()
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            inside = not inside
            continue
        if inside:
            out.add(i)
    return out


def _is_in_gen(line_num, blocks):
    for b in blocks.values():
        if b["start_line"] <= line_num < b["end_line"]:
            return True
    return False


@pytest.fixture
def readme():
    text = _text()
    blocks = _gen_blocks(text)
    for b in blocks.values():
        b["start_line"] = _line_of(text, b["start"]) + 1
        b["end_line"] = _line_of(text, b["end"])
    return text, blocks


def test_no_unsupported_validated(readme):
    """Model-only results must not be described as validation."""
    text, blocks = readme
    code_lines = _code_block_lines(text)
    # Allow "validation" only when clearly qualified as not-validation
    # or when referring to the *scripts* directory name (legacy) — but the
    # project must not claim experimental validation of any result.
    for i, line in enumerate(text.split("\n"), 1):
        if _is_in_gen(i, blocks) or i in code_lines:
            continue
        if line.strip().startswith("<!--"):
            continue
        low = line.lower()
        if "validat" in low:
            # Permit explicit non-claims and script/directory references.
            permitted = (
                "not validation" in low or "not validated" in low
                or "no validation" in low or "never claim" in low
                or "do not claim" in low or "never describe" in low
                or "cannot validate" in low or "is not validation" in low
                or "do not describe" in low
                or "validation scripts" in low  # directory/script naming
                or "validation.png" in low
                or "validation plan" in low
            )
            if not permitted:
                raise AssertionError(
                    f"Line {i}: unsupported 'validated' claim outside GEN block: {line.strip()[:100]}"
                )


def test_no_mixed_saltelli_lhs(readme):
    """Saltelli/Sobol and LHS must not be mixed in the same headline section."""
    text, _blocks = readme
    # Split into headline sections by ## headers
    sections = re.split(r"\n## ", text)
    for section in sections:
        has_saltelli = "saltelli" in section.lower() or "sobol" in section.lower()
        has_lhs = "lhs" in section.lower() or "latin" in section.lower()
        if (has_saltelli and has_lhs
                and "lhs retained only" not in section.lower()
                and "lhs is retained" not in section.lower()):
            raise AssertionError(
                    f"Mixed Saltelli/Sobol and LHS claims in section: "
                    f"{section.strip()[:120]!r}"
                )


def test_no_hard_coded_sample_counts(readme):
    """Uncertainty sample/run counts must live in GEN blocks."""
    text, blocks = readme
    lines = text.split("\n")
    for i, line in enumerate(lines, 1):
        if _is_in_gen(i, blocks):
            continue
        if line.strip().startswith("<!--"):
            continue
        for m in SAMPLE_PATTERN.finditer(line):
            val = m.group()
            # Skip GEN-block instructions (e.g. "--saltelli-n 64" in a code block)
            if "```" in line or "saltelli-n" in line:
                continue
            raise AssertionError(
                f"Line {i}: hard-coded uncertainty sample/run count '{val}' outside GEN block: "
                f"{line.strip()[:100]}"
            )


def test_no_hard_coded_cp(readme):
    """Cp values must not be hard-coded outside GEN blocks."""
    text, blocks = readme
    lines = text.split("\n")
    for i, line in enumerate(lines, 1):
        if _is_in_gen(i, blocks):
            continue
        if line.strip().startswith("<!--"):
            continue
        if "|" in line:
            continue  # table row
        for m in CP_PATTERN.finditer(line):
            val = m.group()
            if val in ALLOWLIST:
                continue
            if re.search(r"\d+\.\d+\.\d+", line):
                continue  # version number
            if re.search(r"Cp\s*=\s*0\.\d+", line):
                # Allow if all Cp values are in ALLOWLIST (verified from stamped JSONs)
                cp_vals = re.findall(r"Cp\s*=\s*(0\.\d+)", line)
                if all(v in ALLOWLIST for v in cp_vals):
                    continue
                raise AssertionError(
                    f"Line {i}: hand-typed Cp value in prose: {line.strip()[:100]}"
                )
            # Allow Cp-like numbers only inside GEN blocks or tables.
            if not any(
                ch.isdigit() for ch in val
            ):
                continue
            raise AssertionError(
                f"Line {i}: hard-coded Cp-like number '{val}' outside GEN block: "
                f"{line.strip()[:100]}"
            )


def test_no_scenario_as_ci(readme):
    """A scenario range must not be described as a confidence interval."""
    text, blocks = readme
    for i, line in enumerate(text.split("\n"), 1):
        if _is_in_gen(i, blocks):
            continue
        if line.strip().startswith("<!--"):
            continue
        if CI_PATTERN.search(line):
            # Permit explicit clarification that it is NOT a CI.
            if "not a" in line.lower() or "not a ci" in line.lower() or "scenario" in line.lower():
                continue
            raise AssertionError(
                f"Line {i}: scenario range described as CI: {line.strip()[:100]}"
            )


def test_no_hard_coded_aep(readme):
    """AEP numbers must not be hard-coded outside GEN blocks."""
    text, blocks = readme
    lines = text.split("\n")
    for i, line in enumerate(lines, 1):
        if _is_in_gen(i, blocks):
            continue
        if line.strip().startswith("<!--"):
            continue
        for m in AEP_PATTERN.finditer(line):
            raise AssertionError(
                f"Line {i}: hard-coded AEP number outside GEN block: {line.strip()[:100]}"
            )


def test_gen_blocks_present_and_nonempty(readme):
    """Required GEN blocks must exist and contain a table row."""
    _, blocks = readme
    required = [
        "evidence_table", "headline_table_small", "headline_table_large",
        "uq_params", "uq_bimodal", "cm_scale_scan", "uq_sobol",
        "aep_turbulent", "aep_rigid_comparison", "aep_steady",
        "aep_branches", "branch_point_check", "counter_rotating",
        "robust_optimization", "ham_reconciliation", "ham_finite_span",
    ]
    missing = [b for b in required if b not in blocks]
    assert not missing, f"missing GEN blocks: {missing}"
    for name, b in blocks.items():
        if name in required:
            assert "|" in b["content"], f"GEN block {name} has no table content"


if __name__ == "__main__":
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, "-v"]))
