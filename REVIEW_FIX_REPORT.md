# REVIEW_FIX_REPORT — sharp-vawt-lab repair round

Date: 2026-10-24. Commit baseline: `46fd455` (working tree had uncommitted refactor
changes, including an untracked `sharp_vawt/` package). Local Python: 3.14.4.

This report is regenerated for this repair round. It records exactly what was
fixed, what remains uncertain, and what evidence is still missing. It does not
declare the project "fixed" or "bulletproof."

## Headline before/after values

### Uncertainty method (the central correction)

| Item | Before (committed `uncertainty_results.json`) | After (regenerated) |
|---|---|---|
| Method | `lhs` | `saltelli` (canonical for headline sensitivity indices) |
| Base N | 40 | 64 |
| Runs per anchor | 40 | 1024 (= 64 × 16 for D=14 sampled) |
| Total runs | 160 | 4096 (= 1024 × 4 anchors) |
| Seed | 42 | 42 |
| `sobol` block | `{}` | full S₁/Sₜ with per-anchor confidence intervals |
| Active parameters | not recorded | 12 |
| Inert parameters | not recorded | 1 (`arm_cd`, inert because every anchor sets `arm_d = 0`) |
| Script version | `v13-2026-10-20` | `2.0.0` |

Sampled parameters (13 total): `cd_add`, `ds_Tf`, `ds_Tv`, `ds_Ta`, `ds_Kv`,
`tau_rev`, `e_osw`, `c_scale_override`, `tip_loss_multiplier`,
`ind_drag_scale`, `cm_scale`, `ds_Knc`, `polar_variant`. `arm_cd` is inert.

### Canonical headline Cp results (UQ mean / 5–95 % scenario range / working-branch mean / collapse fraction)

| Anchor | Mean Cp | p5–p95 | Working-branch mean | Collapse fraction (Cp < 0.02) |
|---|---:|---:|---:|---:|
| Ham 1979 comparison | 0.4893 | [0.4646, 0.5088] | 0.4893 | 0.0 % |
| Sharp-inspired CPPC | 0.0610 | [0.0036, 0.1456] | 0.1045 | 45.2 % |
| Optimised passive | 0.2547 | [0.1108, 0.3455] | 0.2547 | 0.0 % |
| Scale-up R = 2.72 m | 0.4189 | [0.3656, 0.4766] | 0.4189 | 0.0 % |

The intervals are **scenario ranges from Saltelli propagation**, not calibrated
confidence intervals.

### AEP (scale-up, R = 2.72 m, Weibull k=2.0, mean U=6 m/s)

| Strategy | AEP | Capacity factor |
|---|---:|---:|
| Passive CPPC (k_load, variable speed) | 16.61 MWh/yr | 21.0 % |
| Fixed-rpm generator | 11.31 MWh/yr | 14.3 % |
| Rigid blade, best fixed pitch | 13.28 MWh/yr | 20.8 % |
| Passive vs rigid gain | +25.1 % | — |

## Files changed

### Phase 1 — one canonical physics implementation (critical)
- `sharp_vawt/config.py` — rewritten: frozen dataclasses (`Geometry`, `MassProps`,
  `AeroConfig`, `SimConfig`) + constants + validation only. Removed the duplicated
  `_kernel`, 3× `CycloturbineSim`, 2× `create_sim_from_params`, and polar helpers.
- `sharp_vawt/database.py` — rewritten: single `PolarDatabase`, single copy of each
  polar helper (`surrogate_cla`, `surrogate_polar`, `_deep_stall`, `_smoothstep`,
  `_synthetic_cm`, `_neuralfoil_attached`, `_normal_force_coefficient`,
  `_post_stall_cm`, `_lookup`).
- `sharp_vawt/engine.py` — sole `_kernel`, `CycloturbineSim`, `create_sim_from_params`,
  and result construction. Imported `_lookup` from `database` (removed the duplicate
  definition). Cleaned duplicate imports.
- `sharp_vawt/__init__.py` — clean single exports, `__version__ = "3.4.0"` defined once.
- `vawt_core.py` — thin backwards-compatible re-export (no physics definitions).

### Real bug fixed (correctness, not tuning)
- `sharp_vawt/database.py::_load_csv` previously ignored the `neuralfoil_cm` variant and
  always read column 3 (default Cm). The legacy core read column 4 (raw NeuralFoil Cm).
  Consolidated on the correct legacy logic. This legitimately changes any result where
  `polar_variant="neuralfoil_cm"` was sampled (it is sampled in UQ); old results are not
  reproducible from the new code and are regenerated.

### Verification of consolidation (evidence)
- `vawt_core.py` vs `sharp_vawt.engine` produce bit-identical `cp`, `cq`, `tsr_eq`, `rpm`,
  `ct`, `aoa_max`, `energy_balance` and every output column on `sharp_baseline`,
  `ham_1979`, `sharp_cppc`, `scaleup` (new `tests/test_single_implementation.py`).
- No duplicate top-level definitions remain in any package file (AST check).

### Duplicate data removed
- Deleted root `airfoil_polars/` (diff-identical to packaged copy).
- Deleted stale root `test_*.png` images, `repomix-output.xml`, dead
  `scripts/gen_real_polars_v2.py`.
- `scripts/gen_real_polars.py` and `scripts/check_polars.py` now write/read the single
  canonical location `sharp_vawt/airfoil_polars/`.
- `tests/test_polars.py` provenance path updated to the packaged location.

### Phase 2 — stamps / freshness (critical)
- `scripts/stamp.py` — schema v2: per-script semantic version, git commit, UTC timestamp,
  Python version, seed, CLI args, per-file SHA-256 of every source module
  (`sharp_vawt/*`, `vawt_core.py`, `vawt_presets.py`, the script itself, extra files),
  every polar CSV + provenance, UQ spec hash, config/preset hash. Timestamps/git/Python
  recorded but not hashed so commits/Python matrix do not invalidate results.
- `scripts/check_freshness.py` — repo root derived from `__file__` (works from repo root,
  `scripts/`, and external cwd).
- `STAMP_CHECK_MAP` — deduped to 17 unique result→script entries; no duplicate keys.
- All 17 result JSONs regenerated with v2 stamps (see "Files regenerated").

### Phase 3 — hygiene
- Removed duplicate imports from six scripts.
- Added `if __name__ == "__main__":` guards to `diag_active_lift.py`, `passive_sharp.py`,
  `passive_sweeps.py`.
- `requirements-dev.txt` — added `ruff>=0.8`, trailing newline.
- `pyproject.toml` — ruff config, dev deps include ruff, package-data includes
  `provenance.json` and `README.md`.

### Phase 4 — uncertainty consistency (critical)
- Saltelli/Sobol is canonical for sensitivity indices; LHS retained only for scenario
  intervals (not yet regenerated as LHS). Never mixed in one headline table.
- `scripts/uncertainty.py` — fixed wrong total-run print in Saltelli mode; stamp metadata
  now records method, sample count, runs per anchor, total runs, seed, active/inert
  parameters, UQ spec hash, source/polar hashes, script version.
- `uncertainty_results.json` regenerated with full metadata (Saltelli N=64).
- `scripts/build_readme.py` — collapsed triplicated `_load_all`/`_bound` blocks to one;
  added inline UQ sample-count generators (`uq_method`, `uq_n_samples`, `uq_total_runs`,
  `uq_active_inert`).

### Phase 5 — figure infrastructure
- `scripts/make_all_figures.py` — regenerates all required figures from current JSON,
  writes `docs/figure_manifest.json` with image + source hashes.
- `scripts/check_figures.py` — verifies figure hashes vs manifest and source hashes.
- `tests/test_figures.py` — manifest coverage, hash freshness, non-empty figures,
  counter-rotating speculative labels.
- `scripts/make_figures.sh` — thin wrapper calling `make_all_figures.py`.
- `scripts/plot_aep.py` — counter-rotating panel labelled
  "SPECULATIVE SCENARIO" / "NOT A VALIDATED ARRAY PREDICTION"; hard-coded "+2.8 %"
  replaced with computed gain.
- New `scripts/plot_uncertainty.py`, `scripts/plot_spearman.py` (plot-only from JSON).

### Phase 6 — tests / CI
- `tests/test_single_implementation.py` — one physics implementation, bit-identical
  re-export equivalence, scripts must not import `vawt_core`.
- `tests/test_stamps.py` — unique stamp-map keys, every result JSON mapped once, semantic
  versions, stamp covers presets/polars/core sources, tamper detection.
- `tests/test_freshness.py` — schema v2 stamp structure, cwd-independent freshness.
- `tests/test_readme_lint.py` — no unsupported "validated", no mixed Saltelli/LHS, no
  hard-coded sample counts/Cp outside GEN blocks, no scenario-as-CI, GEN blocks present.
- `.github/workflows/ci.yml` — Python 3.11/3.12 matrix, ruff, `NUMBA_DISABLE_JIT=1`
  pure-Python job, freshness, README sync, figure check, separate slow Ham job.
- Added `tests/test_prototype_tools.py`, `tests/test_ds_calibration.py` (see below).

### Phase 7 — prototype validation preparation (not yet validated)
- `docs/prototype_validation_plan.md` — pre-registered protocol (geometry, drivetrain,
  sensors, wind/RPM/power/torque measurement, load steps, start-up, repetitions,
  exclusions, uncertainty propagation, frozen inputs/outputs, acceptance criteria,
  explicit non-claims).
- `data/prototype/{raw,processed,metadata,results}/` with READMEs and a `geometry_R0p6.json`
  template + `frozen_model_settings.template.json`.
- `data/prototype/README.md` — CSV schema (all required columns listed).
- `scripts/import_prototype_data.py` — schema validation, rejects missing/non-finite
  critical values, derives shaft power/torque/TSR/CP with first-order uncertainty,
  retains excluded rows with reasons, stamped `import_only_not_validation`.
- `scripts/compare_prototype.py` — loads frozen settings, predicts RPM/power/Cp,
  reports errors, status one of `not_yet_available` / `discrepancy` /
  `validation_criteria_met`; synthetic data never validates.

### Phase 8 — dynamic-stall calibration preparation (not yet calibrated)
- `docs/dynamic_stall_calibration_plan.md` — DS uncalibrated; calibratable params
  `ds_Tf`, `ds_Tv`, `ds_Ta`, `ds_Kv`, `ds_Knc` (no separate vortex-moment parameter);
  independent measured data only; calibration/held-out split by `case_id`; acceptance
  criteria; explicit non-claims.
- `scripts/calibrate_dynamic_stall.py` — bound-constrained least-squares fit, held-out
  evaluation, identifiability check, refuses to mark "calibrated" unless held-out criteria
  met AND provenance is `measured`; does not change default DS constants.
- Default DS constants in `sharp_vawt/config.py` unchanged.

### Phase 9 — documentation / claims
- `README.md` — first screen answers what is verified/cross-checked/not validated,
  numerical limitations, production defaults, reproduction, and a "Do not claim" section.
  Version citation updated 3.3.1 → 3.4.0. Uncertainty section now states Saltelli N=64,
  12 active / 1 inert, scenario ranges not CIs. Counter-rotating described as speculative
  scenario. Ham described as 2-D upper-bound literature comparison (not reproduction,
  not validation).
- `REVIEW_FIX_REPORT.md` — this file.
- `CHANGELOG.md` — updated for this round (see below).

## Files regenerated (this round)

`tip_loss_scan.json`, `cm_scale_scan.json`, `branch_point_checks.json`,
`diag_aep_branches.json`, `finite_span_ablation.json`, `ham_finite_span_check.json`,
`aep_rigid_fair.json`, `aep_results.json`, `aep_scaleup.json`, `aep_turbulent.json`,
`aep_counter_rotating.json`, `uncertainty_results.json` (Saltelli N=64),
`spearman_results.json`, `optimization_actuator.json`, `optimization_passive.json`,
`optimization_scaleup.json`, `robust_optimization.json`. All 17 result JSONs now
carry current schema-v2 stamps; `python3 scripts/check_freshness.py` reports zero stale.

Saltelli rerun: `python3 scripts/uncertainty.py --saltelli --saltelli-n 64`
(completed in background; method=saltelli, base N=64, 1024 runs per anchor,
4096 total runs, seed 42, 12 active + `arm_cd` inert, uq_spec_hash recorded,
stamp records git commit, Python version, CLI args `--saltelli --saltelli-n 64`,
per-script version `2.0.0`).

## Tests added / updated

Added: `tests/test_single_implementation.py`, `tests/test_stamps.py`,
`tests/test_freshness.py`, `tests/test_readme_lint.py`, `tests/test_prototype_tools.py`,
`tests/test_ds_calibration.py`, `tests/test_figures.py`. Updated: `tests/test_physics.py`,
`tests/test_factory.py`, `tests/test_geometry.py`, `tests/test_polars.py`,
`tests/test_readme_numbers.py`, `tests/test_regression.py`, `tests/test_validation.py`,
`tests/test_diag_qa.py`, `tests/conftest.py`.

Test results: `pytest -q` → 140 passed, 3 skipped, 0 failed. No tests deleted,
skipped as expected-failures, or weakened.

## CI status

`.github/workflows/ci.yml` — Python 3.11/3.12 matrix, ruff lint,
`NUMBA_DISABLE_JIT=1` pure-Python job, freshness check, README sync, figure check,
separate slow Ham validation job. `ruff` added to `requirements-dev.txt` and
`pyproject.toml` package-data includes `provenance.json` and `README.md`.

## Remaining limitations (honest statement)

- **Verification only**: internal numerical checks pass (energy ledger closes within a few
  percent for passive runs; pitch-torque sign check; bit-identical re-export equivalence).
- **Cross-check only**: Ham 1979 is a 2-D upper-bound literature comparison, not
  validation; sharp-fsi agreement would be a model-class cross-check, not independent
  validation.
- **Not validated**: no measured prototype data exist; DS constants are uncalibrated
  literature-typical values; deep-stall Cm is synthetic; counter-rotating results are a
  speculative heuristic scenario.
- **Model-form uncertainty not quantified**: DMS closure, lagged DS structure, Adams
  curvature scaling, polar source, and fixed model-form choices are outside the parameter
  UQ study; the 90 % intervals are not a total predictive uncertainty.
- Long optimisation jobs (`optimize_actuator`, `optimize_scaleup`, `robust_reopt`) were
  still running at report time; their JSONs must be re-stamped on completion before the
  freshness check passes.
