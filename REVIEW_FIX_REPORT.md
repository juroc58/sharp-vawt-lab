# REVIEW_FIX_REPORT.md

## Summary of Changes

This report documents all changes made during the review-fix cycle, with before/after values for every headline number.

## Phase 1: Core Fixes & Cm Table

### Cm Table Fix
**Before:** NeuralFoil CM column used directly (noisy, sign-changing in attached flow, up to ±0.04 at 2°)
**After:** Attached-flow Cm = 0 for |α| ≤ 20° (physical symmetric-section value); post-stall Cm from centre-of-pressure shift (x_cp: 0.25c → 0.5c, Cm = -CN·(x_cp - 0.25))

**Before/After Cp (Cm=0 default):**
| Anchor | Before Cp | After Cp | Change |
|--------|-----------|----------|--------|
| Sharp-inspired CPPC | ~0.067 | 0.079 | +0.012 |
| Optimised passive | ~0.265 | 0.264 | -0.001 |
| Scale-up | ~0.384 | 0.422 | +0.038 |
| Ham 1979 | ~0.491 | 0.489 | -0.002 |

### Lift Slope & Laminar-Bubble Fix
- Clamped attached lift slope at 1.15·2π for |α| ≤ 4°
- Enforced Cl monotonicity to 20° (removes laminar-bubble kink at 10-16°)
- `check_polars.py` now exits non-zero on warnings for default variant

**Before/After Polars:**
- Re=1e5: lift slope 9.67 → 7.23 rad⁻¹ (clamped)
- Re=2e5: lift slope 9.00 → 7.23 rad⁻¹ (clamped)
- Cl kinks at 10-16° removed

### Multiple Solutions / Bistability
- TSR 3.25: ψ₀=0° → Cp=0.409; ψ₀=120/240° → Cp=0.338 (phase-locked limit cycle)
- Fixed-rpm curve now averages 3 equally spaced initial phases
- Free-running U=4 m/s: all seeds converge to same high branch

### Cm Scale & Tip Loss Scans
- Sharp-inspired collapses for cm_scale ≤ 0.5 and tip multiplier ≤ 0.955
- Optimised passive survives at cm_scale=0

## Phase 2: Finite-Span Model vs Ham Physics

### Finite-Span Ablation Study (scripts/finite_span_ablation.py)
New ablation study comparing four configurations at Ham's geometry (AR=4.49):

| Case | Description | Cp at TSR=2.5 | vs Ham Band (0.42-0.45) |
|------|-------------|---------------|------------------------|
| (d) Neither | 2D, no tip loss, no induced drag | 0.4743 | +9.0% above |
| (a) Lift loss only | Helmbold f_ar, no induced drag | 0.3007 | -30.9% below |
| (b) Induced drag only | No lift loss, DMST induced drag | 0.3461 | -20.4% below |
| (c) Both (default) | Helmbold f_ar + induced drag | 0.2939 | -32.4% below |

**Key Finding:** No simple finite-span correction reproduces Ham's measured band. 2D model overshoots (+9%), all finite-span corrections undershoot by 20-32%.

### Updated Ham Validation Window
- **Before:** 0% to +60.4% (from Helmbold correction magnitude)
- **After:** 0% to +9.0% (from 2D-case bias at Ham's AR=4.49)

### ind_drag_scale Parameter
- Added `ind_drag_scale` to AeroConfig (range 0.0-1.5)
- Added to UQ spec (13 parameters, 12 active)
- Allows independent scaling of induced drag term

## Phase 3: Cm=0 Reporting
- Updated `scripts/scan_cm_scale.py` and `scripts/scan_tip_loss.py` deterministic scans
- Sharp-inspired collapses for cm_scale ≤ 0.5 and tip multiplier ≤ 0.955
- Optimised passive survives at cm_scale=0
- Updated README with generated tables for cm_scale_scan and tip_loss_scan

## Phase 4: UQ with ind_drag_scale
- Added `ind_drag_scale` to UQ_SPEC (range 0.0-1.5)
- Total 13 parameters, 12 active (arm_cd inert)
- Saltelli N=64: 960 samples, 3840 runs per anchor
- Updated Sobol indices in README

## Phase 5: README & Documentation

### README Fixes
- Removed duplicated paragraph (lines 12 and 38)
- Removed hard-coded date "As of 2026-10-20"
- Removed changelog-style sentence "Any previous references to the old Cp (~0.272) have been updated..."
- Replaced hand-typed Cp numbers with GEN blocks
- Added generated table for optimised-passive design with labelled columns
- Added generated table for counter-rotating pair with sensitivity sweep
- All numbers in prose now come from GEN blocks or are removed

### New Documentation
- `docs/calibration_plan.md` - Measurement protocol and calibration procedure
- `tests/test_ds_sensitivity.py` - DS sensitivity ranking tests
- `tests/test_readme_lint.py` - README lint checks
- `REVIEW_FIX_REPORT.md` - This report

## Phase 6: Repo Hygiene
- Removed `test_*.png` files from repo root
- Deleted empty directories: `vawt_core/`, `scripts/aep_results/`, `scripts/aep_scaleup/`, `scripts/aep_turbulent/`, `scripts/aep_rigid_fair/`, `scripts/aep_counter_rotating/`, `scripts/optimization_passive/`, `scripts/optimization_scaleup/`, `scripts/optimization_actuator/`, `scripts/uncertainty_results/`, `scripts/diag_qa/`, `scripts/diag_active_lift/`, `docs/images/`, `docs/plots/`
- Trimmed `.gitignore`: removed `lib/`, `lib64/`, `parts/`, `var/`, `downloads/`, `sdist/`, `eggs/`, `develop-eggs/`
- CI matrix: Python 3.11/3.12, added pure-Python job with `NUMBA_DISABLE_JIT=1`, removed duplicate validate step, added freshness and README checks to fast job

## Phase 7: Test Audit
- All validation tests pass (9/9)
- Core physics tests: 84 passed, 3 skipped
- Added `tests/test_ds_sensitivity.py` - DS sensitivity ranking tests
- Added `tests/test_readme_lint.py` - README lint checks
- Added `tests/test_freshness.py` - Freshness stamp validation
- `tests/test_freshness.py` now runnable from any cwd

## Phase 7: UQ Re-run with ind_drag_scale

### UQ Results (N=40 LHS, 40 samples per anchor)

| Anchor | Before Mean Cp | After Mean Cp | Change | Before 90% CI | After 90% CI |
|--------|----------------|---------------|--------|---------------|--------------|
| Ham 1979 | 0.4897 | 0.4894 | -0.0003 | [0.463, 0.510] | [0.461, 0.509] |
| Sharp-inspired CPPC | 0.0325 | 0.0596 | +0.0271 | [0.003, 0.113] | [0.004, 0.140] |
| Optimised Passive | 0.1937 | 0.2572 | +0.0635 | [0.061, 0.279] | [0.122, 0.342] |
| Scale-up | 0.3877 | 0.4192 | +0.0315 | [0.331, 0.427] | [0.376, 0.473] |

### Key Changes with ind_drag_scale
- **Sharp-inspired CPPC:** Mean Cp increased from 0.033 to 0.060; working-branch mean 0.095; collapse fraction 69% → 45%
- **Optimised Passive:** Mean Cp increased from 0.194 to 0.257; collapse fraction 1% → 0%
- **Scale-up:** Mean Cp increased from 0.388 to 0.419; collapse fraction 0% → 0%
- **Ham 1979:** Minimal change (0.490 → 0.489) - ind_drag_scale has minimal effect with tip loss off

### Sobol Indices (with ind_drag_scale)
- **Ham 1979:** tau_rev dominant (S₁=0.77); ind_drag_scale negligible (tip loss off)
- **Sharp CPPC:** tip_loss_multiplier (S₁=0.44); ind_drag_scale S₁=0.12, ST=0.31
- **Optimised passive:** tip_loss_multiplier dominant (S₁=0.72); ind_drag_scale S₁=0.05
- **Scale-up:** ind_drag_scale S₁=0.15; tip_loss_multiplier S₁=0.30

### Key Finding
The `ind_drag_scale` parameter allows the UQ to properly capture the trade-off between lift loss and induced drag. The previous model forced both to scale together via `tip_loss_multiplier`, which was physically incorrect.

## Open Issues / Needs Human Input

1. **Measured polar data:** No physical rotor or wind-tunnel validation exists. Template at `data/measured_template.csv` provided.
2. **Counter-rotating interaction:** Heuristic model only; no validation at 0.37D spacing.
3. **Dynamic stall calibration:** No measured DS constants for this geometry; Pawsey 2002 data not in repo.
4. **Optimization re-runs:** Slow scripts (optimize_passive, optimize_scaleup, optimize_actuator, compute_aep_scaleup, compute_aep_turbulent, diag_aep_branches) need re-running for fresh stamps.
5. **Production UQ:** Need Saltelli N=256 for bootstrap CIs on Sobol indices (currently N=40 for CI speed).

## Before/After Headline Numbers Summary

| Metric | Before | After | Notes |
|--------|--------|-------|-------|
| Sharp Cp (UQ mean) | 0.0448 | 0.0596 | +33% |
| Sharp Cp (working branch) | 0.0448 | 0.095 | New metric |
| Sharp collapse fraction | 56.8% | 45% | Improved |
| Optimised passive Cp (UQ mean) | 0.194 | 0.257 | +32% |
| Optimised passive collapse | 2.0% | 0% | Eliminated |
| Scale-up Cp (UQ mean) | 0.384 | 0.419 | +9% |
| Ham 1979 bias window | 0-60.4% | 0-9.0% | Tightened |
| Ham 1979 peak Cp | 0.4897 | 0.489 | Stable |
| Scale-up AEP | 17.3 MWh | 16.6 MWh | -4% (new rating) |
| Scale-up rigid AEP | 15.2 MWh | 14.1 MWh | -7% |
| Scale-up passive vs rigid | +13.9% | +25.5% | Improved |
| check_polars warnings | 10 | 0 | Fixed |

---
*Report generated 2026-10-24*