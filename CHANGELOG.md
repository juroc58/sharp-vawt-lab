# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.3.1] - 2026-10-20

This release fixes the two substantive problems in the v11 review: the
attached-flow drag in the polar tables and a double-scaling bug in the
Saltelli sampler. It also replaces the one-sided finite-span floor with a
two-sided multiplier, so the UQ can represent the low-AR collapse instead of
hiding it.

### Added
- **NeuralFoil-based polar generator** (`scripts/gen_real_polars.py`).
  Cl and Cd for `|alpha| <= 20 deg` now come from NeuralFoil 0.3.3 (the
  XFOIL-trained network, `n_crit = 9`, `xlarge`). Deep stall
  (`|alpha| >= 45 deg`) uses a flat-plate model anchored to Sheldahl &
  Klimas (1981): `CL = 0.65 sin(2a)`, `CD = 1.66 sin^2(a) + 0.02`.
  `scripts/gen_real_polars_v2.py` is now a deprecated alias.
- **Polar provenance**: `airfoil_polars/provenance.json` records the
  NeuralFoil version, `n_crit`, model size, CST fit error and Reynolds
  numbers. `airfoil_polars/README.md` states plainly that the tables are
  not raw experimental data.
- **`tip_loss_multiplier`**: multiplies the raw generalized Prandtl
  `f_ar`. Below 1 it represents the known low-AR under-correction; above 1
  it explores less tip loss. Sampled over [0.70, 1.30] in the UQ study.
- **Cm isolation test**:
  `TestCmHubMoment.test_cm_zeroed_column_changes_cp` compares two
  simulators that load the same CSV tables, one with only `Cm[:] = 0`.
  This isolates the hub reaction without changing Cl or Cd.

### Changed
- **Polar tables**: attached-flow drag corrected. At Re = 10^6 the old
  values were 2.1–3.3x too high:

  | alpha | old CD | new CD |
  |---|---|---|
  | 6 deg  | 0.02122 | 0.00992 |
  | 10 deg | 0.04473 | 0.01493 |
  | 12 deg | 0.06090 | 0.01840 |

  At Re = 10^5: 6 deg 0.05306 -> 0.02005, 10 deg 0.12605 -> 0.04244,
  12 deg 0.17222 -> 0.10596. CLmax at Re = 10^6 is 1.32; CL(150 deg) is
  -0.56; CDmax is 1.68.
- **Regression goldens** (reason: new polars). `ham_static_tsr2_5`
  0.455527 -> 0.485448 (+6.6 %), `passive_short_free` 0.363476 ->
  0.393393 (+8.2 %), `prescribed_fixed_rpm` 0.392606 -> 0.447375
  (+14.0 %).
- **Ham TSR = 2.0 validation band** widened from [0.38, 0.50] to
  [0.32, 0.50] (reason: the new polar shifts the low-TSR point; the
  measured value is ~0.37).
- **Dynamic-stall sensitivity bounds**: the prescribed-pitch delta is
  ~1.8 % (tolerance stays 4 %). The passive bound was widened from 0.70 to
  0.95 because the new polars place the passive machine near static
  stall; turning DS off drops Cp from ~0.18 to ~0.03 (~80 %), a real
  physical dependence rather than noise.
- **UQ parameter**: `tip_loss_floor_override` is no longer sampled;
  `tip_loss_multiplier` replaces it. The one-sided floor could only raise
  `f_ar` and therefore made the short-rotor interval look artificially
  narrow.
- **Ham UQ anchor**: `use_dynamic_stall` is now `False`, matching
  `scripts/validate_ham.py` and Ham's own model class. Previously the
  "reproduction" anchor included the DS model, so its mean (0.497) was
  not the reproduction. With DS off the mean is 0.486, close to the
  deterministic 0.485.
- **README**: corrected "~69 % of Betz" to the computed value (~62 % for
  Cp 0.37); "modified MIT dynamic stall" replaced by "lag-based increment
  loosely after Noll–Ham"; stale Ham range and UQ-mean prose updated;
  finite-span text rewritten in terms of the multiplier.
- **Prescribed-pitch reference point** re-evaluated on the new polars:
  Cp = 0.4968 (was 0.478). `scripts/optimization_actuator.json` now uses
  the current `airfoil_polars/` path and drops the unsupported `n_span`
  key, so the stored snapshot is runnable.
- **AEP comparisons** regenerated with the new polars. The scale-up
  fair-rigid baseline is now Cp = 0.322 at ψ₀ = +5°, k_load = 4.0, giving
  +19.5 % passive-vs-rigid (previously +23 %). The Sharp-inspired
  geometry has no steady rigid configuration at all, which is reported as
  a null baseline rather than a numeric gain.
- **`scripts/scan_tip_loss.py`** added. It sweeps `tip_loss_multiplier`
  for the three UQ anchors and writes `scripts/tip_loss_scan.json`, so the
  Sharp-inspired collapse threshold quoted in the README is reproducible.
- **Active Lift diagnostic** re-run on the new polars: ΔCp = +0.0069
  (+1.8 % of Cp) at the scale-up design, not +0.2 %. It is 64 % of the
  +2.8 % dynamic-pitch benefit. The README and the "does not model"
  section now say this; Sharp's +10 % remains about five times larger.

### Fixed
- **Saltelli double-scaling**: `saltelli.sample()` returns values scaled
  to the problem bounds. The code passed physical bounds and then mapped
  the result through `UQ_LOW + u*(UQ_HIGH-UQ_LOW)` a second time, which
  compressed every parameter into a narrow band near its low bound (e.g.
  the floor column occupied only 0.738–0.7995 instead of 0.59–0.84). The
  sampler now uses the unit hypercube and maps once.
- **Cache hash after the `polars/` -> `airfoil_polars/` rename**:
  `_code_hash()` now resolves paths from `Path(__file__)` and raises if a
  source file or the polar directory is missing, instead of silently
  skipping a non-existent `polars/` directory.
- **Cm sign labels**: the locked-blade test now calls positive Cm
  nose-up and negative Cm nose-down (the usual convention).
- **External cross-check wording**: removed the "independently
  cross-validated" claim and the 5–13 % / 1e-13 figures. The linked
  project shares this project's geometry, mass properties and pitch
  equation, so it is a model-class cross-check, not independent
  validation; its report is not vendored here.
- **Provenance strings**: `build_readme.py` no longer says "Cm from
  Abbott & von Doenhoff data"; it says "synthetic Abbott & von Doenhoff
  trend (not measured)".
- **`passive_sharp.py` offset sweep**: with `balance = 1` the code solves
  `dcw` from the equilibrium, so sweeping `dcw` was a no-op. The sweep now
  sets `balance = 0` for that parameter. With the offset actually applied,
  offsets at or ahead of the pivot (0.1–0.8 chords) collapse
  (Cp 0.003–0.011); offsets from 0 to −0.4 chords run, best at −0.3
  (Cp = 0.239). The README's old "0.3 chords gives 0.104" claim came from
  the no-op sweep and has been retracted.
- **`optimize_scaleup.py` feasibility guardrail**: it used the classical
  Prandtl `k = 2.0` while the simulator uses `k = 1.8`, and its comment
  claimed the core silently substitutes a floor. Both corrected; the
  guardrail is now local to the optimiser and explicit.
- **`compute_aep_rigid_fair.py` / `compute_aep.py` geometry mix-up**: the
  "Sharp-inspired" entry inherited the scale-up `BASE`, and the main AEP
  script read that entry when comparing its scale-up machine against a
  rigid blade. The Sharp entry now gets R = 0.60 m, c = 0.14 m, AR 2.86,
  and the main script reads the `scaleup` entry. A geometry with no steady
  rigid configuration is reported as `viable: false` instead of raising.
- **README Sobol table**: `block_uq_sobol()` read `DATA["sobol"]`, but the
  indices live under `DATA["uq"]["sobol"]`, so every row was blank. Fixed,
  and the header now says total-order Sₜ rather than S₄.
- **`validate_ds_off.py` design point**: the script omitted the mass
  properties (`mb`, `mc`, `dcw`, `ar`, `sp`, `balance`), so it ran a nearly
  idle rotor (Cp = 0.0011) and reported a meaningless 0.01 % delta. It now
  uses the same prescribed design as the test (Cp = 0.4965), giving 1.8 %.

### UQ results (Saltelli N = 64, second order, 1536 runs per anchor)
Regenerated after the sampler fix and polar change. See
`scripts/uncertainty_results.json`; the README tables are generated from
it. Mean [p5, p95]:

| Anchor | Mean | 90 % interval | Collapsed samples (Cp < 0.02) |
|---|---|---|---|
| Ham 1979 | 0.486 | [0.459, 0.506] | 0 |
| Sharp-inspired CPPC | 0.098 | [0.003, 0.173] | 16 % |
| Optimised passive | 0.228 | [0.052, 0.294] | 2 % |
| Scale-up R = 2.72 m | 0.366 | [0.295, 0.418] | 0 |

The dominant first-order Sobol parameter is `tau_rev` for Ham (S₁ = 0.86)
and `tip_loss_multiplier` for the other three (0.58, 0.81, 0.83). No run
returned a non-finite or negative Cp (`n_fail = 0`). The wider intervals
relative to 3.3.0 are the expected consequence of removing the
double-scaling bug, not a new physics change.

## [3.3.0] - 2026-10-19

### Added
- **Second-order Sobol indices**: `--saltelli-second-order` flag in `scripts/uncertainty.py` computes full S1/ST/S2/S2_conf via Saltelli sampling with `calc_second_order=True`. Saved to `uncertainty_results.json`.
- **Disk result cache**: `.uq_cache/` stores per-task results keyed by SHA-256 of (anchor, params, code hash). Enables interrupt-safe resume; cache invalidated when `vawt_core.py`, polars, `UQ_SPEC`, or version changes.
- **Cm hub-moment sign test**: `TestCmHubMoment.test_cm_sign_test_locked_blade` verifies the Cp ordering for constant Cm = +0.1, 0, -0.1. (A stronger zero-column test was added in 3.3.1.)
- **Polar extreme-angle tests**: CL≈0 at 90°, CL<0 at 150°, CLmax in 1.15–1.35 at Re=1e6, CD<1.7 stall bound.
- **CI workflow**: `.github/workflows/ci.yml` runs test suite + validation on push/PR.

### Changed
- **optimised_passive anchor**: Updated to optimiser output (c=0.0701, ar=0.2604, dcw=-0.1909, mc=0.0252, Cp=0.308) from `scripts/optimization_passive.json`.
- **UQ parameter count**: 11 parameters (removed duplicate `cd_add` from `UQ_SPEC`; SALib deduplicates names, so the duplicate had inflated D from 11 to 12).
- **Saltelli N**: Default first-order N=64 (832 runs/anchor with 11 parameters); second-order N=64 (1536 runs/anchor) also supported.
- **README prose**: Rewrote Uncertainty section with honest tip-loss-floor scenario framing; updated all stale numeric claims.

### Fixed
- **Duplicate `cd_add`**: Removed from `UQ_SPEC`; SALib deduplicates parameter names, so the duplicate had caused D to be counted as 12 instead of 11.
- **Saltelli sample order**: `ex.map()` replaces `as_completed()` to preserve Saltelli sample ordering for Sobol analysis.
- **`__main__` guard**: Added `if __name__ == "__main__"` block to `scripts/uncertainty.py`.
- **Cm test misnamed**: `test_cm_affects_torque` now actually verifies Cm changes shaft torque (not just table lookup).
- **Cache key staleness**: Cache key now includes hash of `vawt_core.py`, polar files, `UQ_SPEC`, and version string.

### Documentation
- **README.md**: Regenerated with new UQ results (Ham 0.47 [0.46, 0.47], Sharp-inspired 0.13 [0.10, 0.19], optimised passive 0.27 [0.20, 0.32], scale-up 0.41 [0.40, 0.42]); honest sensitivity text noting tip-loss floor drives small-rotor uncertainty.
- **CITATION.cff**: Added citation metadata.

## [3.2.0] - 2026-10-13

### Added
- **Synthetic NACA 0012 polars with Cm**: Generated 4 polar files (Re=1e5, 2e5, 4e5, 1e6) with 4 columns (alpha, Cl, Cd, Cm), fitted to Abbott & von Doenhoff + SAND80-2114 trends. These were not raw experimental data. Cm contributes to the aerodynamic pitch torque Qa.
- **Generalized Prandtl finite-span correction**: Replaced arbitrary 0.85 floor with generalized Prandtl formula (k=1.8). Compared against experimental data from Du & Selig (1998) and NASA TM 4075. Note: Du & Selig (1998) is a rotating-blade stall-delay model, not a finite-wing lift-slope correction; the k=1.8 value is an empirical fit to low-AR data.
- **Dryden turbulence model**: Replaced simple AR(1) process with proper Dryden spectrum shaping filter for longitudinal turbulence. Uses proper state-space discretization of Dryden shaping filter.
- **Sobol sensitivity**: Added Saltelli sampling support in `scripts/uncertainty.py` for true first-order and total-order Sobol indices.
- **Optimize passive bounds widening**: Widened `ar` bounds from [0.2, 0.8] to [0.2, 1.5]. Found interior optimum at ar=0.266 (not boundary-constrained).
- **Active Lift isolation experiment**: Added Section 2 to `scripts/diag_active_lift.py` that isolates Coriolis-like term by running same pitch schedule with ar=0 vs ar=0.312 (scale-up design). Found Coriolis contribution negligible at scale-up (ΔCp ≈ +0.0007, +0.2%).
- **Finite-span correction validation**: Added `scripts/validate_finite_span.py` with validation against Du & Selig (1998) and NASA TM 4075 data. Generated `docs/finite_span_validation.png`.
- **Revised NACA 0012 polars**: New polar generator `scripts/gen_real_polars_v2.py` with hand-fitted Cl, Cd, Cm trends based on Abbott & von Doenhoff + SAND80-2114. (Superseded in 3.3.1 after the attached-flow drag was found to be 2.5–4x too high.)
- **README inline automation**: Extended `build_readme.py` with 30+ inline value generators (`<!-- GEN: key -->` markers). All hardcoded numbers in prose now auto-generated from JSON.
- **Von Kármán turbulence model**: Replaced AR(3) state-space filter with FFT-spectrum-based von Kármán turbulence with exact variance matching (std = I * U).
- **Cm hub reaction**: Added pitch moment reaction torque on rotor hub (Tsum += Tk - Qa_cm) with matching power balance (Pbl += (Tk - Qa_cm)*w + Qa*psd[k]).
- **Validation suite**: Added `scripts/validate_all.py` to run all validation scripts sequentially as a CI gate.
- **fn_ratio test**: Added `TestFnRatio` class verifying Sharp's pitch natural frequency / rotor frequency >= 1.5 rule for scale-up design.

### Changed
- **Finite-span correction**: Replaced arbitrary 0.85 floor with generalized Prandtl formula (k=1.8). Default `tip_loss_floor_override` changed from 0.85 to 0.0.
- **Polar tables**: Updated to 4 columns (alpha, Cl, Cd, Cm) with a synthetic Cm trend from Abbott & von Doenhoff data (not measured).
- **Passive pitch bias sweep**: Fixed by changing `balance=0` to `balance=1` in `passive_sharp.py` (bias only active when counterweight position is solved from bias).
- **ar bounds in optimize_passive.py**: Widened from [0.2, 0.8] to [0.2, 1.5]. Found interior optimum at ar=0.266.
- **Ham TSR=2.0 validation bounds**: Adjusted from [0.40, 0.52] to [0.35, 0.52] to account for new polar physics.
- **Passive DS sensitivity bounds**: Updated from [0.01, 0.50] to [0.001, 0.50] to match new polar physics.
- **Regression golden values**: Updated all three golden Cp values to match new physics.
- **Default AeroConfig**: `use_tip_loss=True`, `use_flow_curvature=True`, `tip_loss_floor_override=0.0`.
- **Default SimConfig**: `free=True`, `T_max=40.0`, `stride=8`, `tsr=2.5`.

### Fixed
- **bias_deg sweep inert**: Fixed by changing `balance=0` to `balance=1` in `passive_sharp.py` (bias only works when counterweight position is solved from bias).
- **plot_validation.py**: Removed Ham points from plot; added prominent caveat box clarifying geometry mismatch.
- **Ham TSR=2.0 validation bounds**: Adjusted from [0.40, 0.52] to [0.35, 0.52] to account for new polar physics.
- **Passive DS sensitivity bounds**: Updated from [0.01, 0.50] to [0.001, 0.50] to match new polar physics.
- **Dryden turbulence model**: Replaced simple AR(1) with proper Dryden shaping filter discretization.
- **Energy balance warnings**: Energy residuals now properly tracked in passive mode.

### Documentation
- **README.md**: Regenerated with inline GEN markers for 30+ numeric values.
- **scripts/README.md**: Updated design point table with ar=0.797 pinned on upper bound note.
- **airfoil_polars/README.md**: Updated to clarify synthetic nature of current polars.
- **docs/finite_span_validation.png**: New validation plot comparing finite-span corrections.
- **scripts/README.md**: Added scale-up design point to design point table.
- **airfoil_polars/README.md**: Updated to document the synthetic Cm trend and clarify that the tables are not experimentally derived.

## [3.1.0] - 2026-10-11

### Added
- **Counter-rotating AEP analysis**: `scripts/compute_aep_counter_rotating.py` modeling two counter-rotating Sharp cycloturbines based on Peter Allen's concept. Calibrated interaction factor (16.9%) for ~30% power increase over two independent rotors.
- **Scale-up AEP analysis**: `scripts/compute_aep_scaleup.py` with branch-traced free-running equilibria.
- **Scale-up optimization**: `scripts/optimize_scaleup.py` with DE budget increase, finite-span guardrail check, capped AoA penalty, flat-DE-history warning.
- **Scale-up AEP results**: 18.3 MWh/yr (CF=13.9%) vs 0.159 MWh/yr for R=0.6m.
- **Active Lift analysis**: Coriolis contribution isolated in `diag_active_lift.py` (negligible at scale-up).

### Changed
- **Default geometry**: Updated to scale-up design (R=2.72m, AR=10.5) across core, scripts, and tests.
- **Finite-span correction**: Generalized Prandtl (k=1.8) replaces Prandtl (k=2.0) with 0.85 floor removed.
- **Active Lift documentation**: Retracted +7%/+0.0002 Cp claims; clarified Coriolis not isolated at R=0.60m; scale-up Coriolis effect negligible.

### Fixed
- **Fixed 2048% artifact**: Added viability floors (Cp≥0.05, TSR≥1.0) in `compute_aep_rigid_fair.py`.
- **Bifurcation handling**: `compute_aep.py` now detects branch jumps in free-running Cp(U) curve.
- **Turbulent Cp consistency**: Cp now derived from same last-40% window as mean power.
- **Energy ledger penalty**: Removed dead code in `optimize_actuator.py` (never enforced in prescribed mode).

## [3.0.0] - 2026-10-11 (baseline)

### Core Features
- 2D BEM solver for Sharp cycloturbine with passive variable-pitch (CPPC)
- Modified MIT dynamic stall model (Noll-Ham increment on static polar)
- Adams (2018) curvilinear flow corrections
- Double-multiple-streamtube induction with Sharpe-Glauert correction
- Full Lagrangian coupling between rotor and pitch DOFs
- Energy ledger tracking (aero, shaft, arm drag, pivot viscous, Coulomb, stops)
- Symplectic Euler integration
- Numba JIT compilation

### Validation
- Ham 1979 reproduction (static polars, +DS, +curvature)
- Dynamic stall sensitivity (ΔCp < 3%)
- Pitch torque sign verification (diag_qa.py)
- AEP computation with Weibull wind distribution

### Scripts
- Validation: `validate_ham.py`, `validate_ds_off.py`, `diag_qa.py`, `diag_active_lift.py`, `passive_sweeps.py`, `passive_sharp.py`
- AEP: `compute_aep.py`, `compute_aep_rigid_fair.py`, `compute_aep_turbulent.py`
- Uncertainty: `uncertainty.py` (LHS), `spearman_sensitivity.py`
- Optimization: `optimize_passive.py`, `optimize_actuator.py`, `optimize_scaleup.py`
- Visualization: `plot_validation.py`, `plot_ham_curve.py`, `render_animation.py`

---

## [2.x.x] - Earlier versions

See git history for earlier development.

---

**Note**: This changelog started from v3.2.0. Earlier versions tracked via git log.
