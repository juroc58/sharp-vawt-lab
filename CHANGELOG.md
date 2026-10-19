# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.3.0] - 2026-10-19

### Added
- **Second-order Sobol indices**: `--saltelli-second-order` flag in `scripts/uncertainty.py` computes full S1/ST/S2/S2_conf via Saltelli sampling with `calc_second_order=True`. Saved to `uncertainty_results.json`.
- **Disk result cache**: `.uq_cache/` stores per-task results keyed by SHA-256 of (anchor, params, code hash). Enables interrupt-safe resume; cache invalidated when `vawt_core.py`, polars, `UQ_SPEC`, or version changes.
- **Cm hub-moment sign test**: `TestCmHubMoment.test_cm_changes_shaft_torque` verifies Cp differs between Cm and Cm=0 surrogate polars.
- **Polar extreme-angle tests**: CL≈0 at 90°, CL<0 at 150°, CLmax≈1.25 at Re=1e6, CD<2.0 stall bound.
- **CI workflow**: `.github/workflows/ci.yml` runs test suite + validation on push/PR.

### Changed
- **optimised_passive anchor**: Updated to optimiser output (c=0.0701, ar=0.2604, dcw=-0.1909, mc=0.0252, Cp=0.308) from `scripts/optimization_passive.json`.
- **UQ parameter count**: 11 parameters (removed duplicate `cd_add` from `UQ_SPEC`).
- **Saltelli N**: Default first-order N=64 (1536 runs/anchor); second-order N=64 also supported.
- **README prose**: Rewrote Uncertainty section with honest tip-loss-floor scenario framing; updated all stale numeric claims.

### Fixed
- **Duplicate `cd_add`**: Removed from `UQ_SPEC` which was causing SALib to see D=11 instead of D=12.
- **Saltelli sample order**: `ex.map()` replaces `as_completed()` to preserve Saltelli sample ordering for Sobol analysis.
- **`__main__` guard**: Added `if __name__ == "__main__"` block to `scripts/uncertainty.py`.
- **Cm test misnamed**: `test_cm_affects_torque` now actually verifies Cm changes shaft torque (not just table lookup).
- **Cache key staleness**: Cache key now includes hash of `vawt_core.py`, polar files, `UQ_SPEC`, and version string.

### Documentation
- **README.md**: Regenerated with new UQ results (Ham 0.47 [0.46, 0.47], Sharp-inspired 0.13 [0.10, 0.19], optimised passive 0.27 [0.20, 0.32], scale-up 0.41 [0.40, 0.42]); honest sensitivity text noting tip-loss floor drives small-rotor uncertainty.
- **CITATION.cff**: Added citation metadata.

## [3.2.0] - 2026-10-13

### Added
- **Real NACA 0012 polars with Cm**: Generated 4 polar files (Re=1e5, 2e5, 4e5, 1e6) with 4 columns (alpha, Cl, Cd, Cm) based on Abbott & von Doenhoff + SAND80-2114 data. The pitch moment coefficient Cm is now properly modeled and contributes to the aerodynamic pitch torque Qa.
- **Generalized Prandtl finite-span correction**: Replaced arbitrary 0.85 floor with generalized Prandtl formula (k=1.8). Compared against experimental data from Du & Selig (1998) and NASA TM 4075. Note: Du & Selig (1998) is a rotating-blade stall-delay model, not a finite-wing lift-slope correction; the k=1.8 value is an empirical fit to low-AR data.
- **Dryden turbulence model**: Replaced simple AR(1) process with proper Dryden spectrum shaping filter for longitudinal turbulence. Uses proper state-space discretization of Dryden shaping filter.
- **Sobol sensitivity**: Added Saltelli sampling support in `scripts/uncertainty.py` for true first-order and total-order Sobol indices.
- **Optimize passive bounds widening**: Widened `ar` bounds from [0.2, 0.8] to [0.2, 1.5]. Found interior optimum at ar=0.266 (not boundary-constrained).
- **Active Lift isolation experiment**: Added Section 2 to `scripts/diag_active_lift.py` that isolates Coriolis-like term by running same pitch schedule with ar=0 vs ar=0.312 (scale-up design). Found Coriolis contribution negligible at scale-up (ΔCp ≈ +0.0007, +0.2%).
- **Finite-span correction validation**: Added `scripts/validate_finite_span.py` with validation against Du & Selig (1998) and NASA TM 4075 data. Generated `docs/finite_span_validation.png`.
- **Improved NACA 0012 polars**: New polar generator `scripts/gen_real_polars_v2.py` with realistic Cl, Cd, Cm based on Abbott & von Doenhoff + SAND80-2114 data.
- **README inline automation**: Extended `build_readme.py` with 30+ inline value generators (`<!-- GEN: key -->` markers). All hardcoded numbers in prose now auto-generated from JSON.
- **Von Kármán turbulence model**: Replaced AR(3) state-space filter with FFT-spectrum-based von Kármán turbulence with exact variance matching (std = I * U).
- **Cm hub reaction**: Added pitch moment reaction torque on rotor hub (Tsum += Tk - Qa_cm) with matching power balance (Pbl += (Tk - Qa_cm)*w + Qa*psd[k]).
- **Validation suite**: Added `scripts/validate_all.py` to run all validation scripts sequentially as a CI gate.
- **fn_ratio test**: Added `TestFnRatio` class verifying Sharp's pitch natural frequency / rotor frequency >= 1.5 rule for scale-up design.

### Changed
- **Finite-span correction**: Replaced arbitrary 0.85 floor with generalized Prandtl formula (k=1.8). Default `tip_loss_floor_override` changed from 0.85 to 0.0.
- **Polar tables**: Updated to 4 columns (alpha, Cl, Cd, Cm) with realistic Cm from Abbott & von Doenhoff data.
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
- **polars/README.md**: Updated to clarify synthetic nature of current polars.
- **docs/finite_span_validation.png**: New validation plot comparing finite-span corrections.
- **scripts/README.md**: Added scale-up design point to design point table.
- **polars/README.md**: Updated to document Cm values from Abbott & von Doenhoff data.

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
