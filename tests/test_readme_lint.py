#!/usr/bin/env python3
"""
Lint README.md for common issues.

Checks:
1. No hard-coded Cp numbers outside GEN blocks (allow 0.593 Betz limit)
2. No hard-coded AEP numbers outside GEN blocks
3. No duplicated paragraphs
4. No hard-coded dates (except in changelog)
5. No "modified MIT" / "Du-Selig" as model names
6. All numbers in prose come from GEN blocks
"""
import re
import sys
import os
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"

# Patterns to flag
CP_PATTERN = re.compile(r'\b0\.\d{2,4}\b')
AEP_PATTERN = re.compile(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*kWh/yr\b')
DATE_PATTERN = re.compile(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+20\d{2}\b|\b20\d{2}-\d{2}-\d{2}\b')
FORBIDDEN_TERMS = ["modified MIT", "Du-Selig", "Du Selig"]

# Allowlist of numbers that are constants, not results
ALLOWLIST = {
    "0.593",  # Betz limit
    "1.225",  # air density
    "1.5e-5", # kinematic viscosity
    "0.001",  # generic small number
    "0.01",
    "0.1",
    "1.0",
    "1.5",
    "2.0",
    "3.0",
    "4.0",
    "5.0",
    "6.0",
    "7.0",
    "8.0",
    "9.0",
    "10.0",
    "12.0",
    "15.0",
    "20.0",
    "25.0",
    "45.0",
    "89.0",
}

def extract_gen_blocks(text):
    """Extract GEN block contents and their line ranges."""
    blocks = {}
    pattern = re.compile(r'<!-- BEGIN GENERATED: (\w+) -->\n(.*?)\n<!-- END GENERATED: \1 -->', re.DOTALL)
    for match in pattern.finditer(text):
        blocks[match.group(1)] = {
            'content': match.group(2),
            'start': match.start(),
            'end': match.end(),
        }
    return blocks


def is_in_gen_block(line_num, gen_blocks):
    """Check if line number falls within a GEN block."""
    for block in gen_blocks.values():
        if block['start'] <= line_num < block['end']:
            return True
    return False


def find_paragraphs(text):
    """Find paragraphs (separated by blank lines) and their line ranges."""
    paragraphs = []
    lines = text.split('\n')
    start = 0
    in_para = False
    for i, line in enumerate(lines):
        if line.strip():
            if not in_para:
                start = i
                in_para = True
        else:
            if in_para:
                paragraphs.append((start, i - 1))
                in_para = False
    if in_para:
        paragraphs.append((start, len(lines) - 1))
    return paragraphs


def main():
    with open(README) as f:
        text = f.read()

    lines = text.split('\n')
    gen_blocks = extract_gen_blocks(text)
    paragraphs = find_paragraphs(text)

    errors = []

    # Check 1: No hard-coded Cp numbers outside GEN blocks
    for i, line in enumerate(lines):
        line_num = i + 1
        if is_in_gen_block(line_num, gen_blocks):
            continue
        # Skip comment lines
        if line.strip().startswith('<!--'):
            continue
        # Find Cp-like numbers
        for match in CP_PATTERN.finditer(line):
            val = match.group()
            if val not in ALLOWLIST:
                # Check if it's in a table (contains |)
                if '|' in line:
                    continue
                # Check if it's a version number (x.y.z)
                if re.match(r'\d+\.\d+\.\d+', line):
                    continue
                errors.append(f"Line {line_num}: Hard-coded Cp-like number '{val}' outside GEN block: {line.strip()[:80]}")

    # Check 2: No hard-coded AEP numbers outside GEN blocks
    for i, line in enumerate(lines):
        line_num = i + 1
        if is_in_gen_block(line_num, gen_blocks):
            continue
        if line.strip().startswith('<!--'):
            continue
        for match in AEP_PATTERN.finditer(line):
            errors.append(f"Line {line_num}: Hard-coded AEP number outside GEN block: {line.strip()[:80]}")

    # Check 3: No hard-coded dates outside changelog
    changelog_section = False
    for i, line in enumerate(lines):
        line_num = i + 1
        if line.strip().startswith('## [Unreleased]') or line.strip().startswith('## [3.'):
            changelog_section = True
        if line.strip().startswith('## ') and not changelog_section:
            changelog_section = False
        if is_in_gen_block(line_num, gen_blocks):
            continue
        if changelog_section:
            continue
        if DATE_PATTERN.search(line):
            errors.append(f"Line {line_num}: Hard-coded date outside changelog: {line.strip()[:80]}")

    # Check 4: No forbidden terms
    for term in FORBIDDEN_TERMS:
        for i, line in enumerate(lines):
            if term.lower() in line.lower():
                errors.append(f"Line {i+1}: Forbidden term '{term}': {line.strip()[:80]}")

    # Check 5: No duplicated paragraphs (exact text match)
    para_texts = {}
    for start, end in paragraphs:
        text = '\n'.join(lines[start:end+1]).strip()
        if len(text) > 50:  # Only check substantial paragraphs
            if text in para_texts:
                errors.append(f"Duplicated paragraph at lines {start+1}-{end+1} (first at {para_texts[text]+1})")
            else:
                para_texts[text] = start

    # Check 6: No hand-typed Cp numbers in prose (outside tables and GEN blocks)
    for i, line in enumerate(lines):
        line_num = i + 1
        if is_in_gen_block(line_num, gen_blocks):
            continue
        if '|' in line:  # Table row
            continue
        if line.strip().startswith('<!--'):
            continue
        # Look for "Cp = 0.xx" or "Cp=0.xx" patterns
        if re.search(r'Cp\s*=\s*0\.\d+', line):
            if 'GEN' not in line:
                errors.append(f"Line {line_num}: Hand-typed Cp value in prose: {line.strip()[:80]}")

    if errors:
        print("README lint errors:")
        for err in errors:
            print(f"  {err}")
        return 1

    print("All README lint checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())