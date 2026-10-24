# FINAL_REPAIR_STATUS.md

Generated during final repair workflow (2026-10-24).

## MANDATORY FINAL WORKFLOW — status

| Step | Command | Status |
|------|---------|--------|
| 1. Current state | `git status`, `git diff --stat`, `check_freshness.py`, `pytest`, `ruff` | DONE |
| 2. Saltelli N=64 rerun | `python3 scripts/uncertainty.py --saltelli --saltelli-n 64` | COMPLETE |
| 3. Regenerate figures | `python3 scripts/make_all_figures.py` + `check_figures.py` | COMPLETE |
| 4. Optimisation results | `optimize_actuator.py`, `optimize_scaleup.py`, `robust_reopt.py` | COMPLETE |
| 5. Regenerate README | `python3 scripts/build_readme.py` + `--check` | COMPLETE |
| 6. Freshness check | `python3 scripts/check_freshness.py` (incl. cwd `/`) | COMPLETE |
| 7. Full test suite | `pytest -q` | COMPLETE |
| 8. Linting | `ruff check .` | COMPLETE |
| 9. No-JIT | `NUMBA_DISABLE_JIT=1 pytest -q` | RUNNING (slow, pure-Python numba fallback) |
| 10. CI-representative checks | `check_polars.py --fail-on-warnings`, freshness, `build_readme --check`, `check_figures.py`, pytest | COMPLETE |
| 11. Final reproducibility audit | this document + reports | IN PROGRESS |
| 12. Update reports | REVIEW_FIX_REPORT.md, CHANGELOG.md, FINAL_REPAIR_STATUS.md | IN PROGRESS |
| 13. Commit | logical commits | PENDING |

## Git status

- Modified tracked files: ~90 files (package consolidation, stamp v2, new tests, CI, README, reports)
- Deleted tracked files: root `airfoil_polars/` (duplicated), root `test_*.png`, `scripts/gen_real_polars_v2.py`
- Untracked (kept): `data/prototype/`, `docs/*_plan.md`, new scripts (`calibrate_dynamic_stall.py`, `check_figures.py`, `compare_prototype.py`, `import_prototype_data.py`, `make_all_figures.py`, `plot_spearman.py`, `plot_uncertainty.py`), new tests, `AUDIT_FINDINGS.md`, `FINAL_REPAIR_STATUS.md`
- Removed before commit: `repomix-output.xml` (non-artifact)

## Stale result JSONs

None. `python3 scripts/check_freshness.py` reports: "All result JSONs are fresh."

## Failing tests

None. `pytest -q`: 140 passed, 3 skipped, 0 failed.

## Linting

`ruff check .`: All checks passed (0 errors). Legacy scripts have justified per-file-ignores in `pyproject.toml` (`lint.per-file-ignores`); canonical package files and new scripts/tests are ruff-clean.

## No-JIT verification

Correctness confirmed on subset (test_regression, test_factory, test_geometry: 29 passed). Full `NUMBA_DISABLE_JIT=1 pytest -q` is running in background (pure-Python numba fallback is very slow but numerically identical).

## Headline results (regenerated, Saltelli N=64)

- Ham 1979: mean Cp = 0.4893 [0.4646, 0.5088], collapse 0.0 %
- Sharp-inspired CPPC: mean Cp = 0.0610 [0.0036, 0.1456], collapse 45.2 %
- Optimised passive: mean Cp = 0.2547 [0.1108, 0.3455], collapse 0.0 %
- Scale-up R = 2.72 m: mean Cp = 0.4189 [0.3656, 0.4766], collapse 0.0 %

Method: saltelli; base N = 64; 1024 runs/anchor; 4096 total runs; seed 42; 12 active parameters; inert: arm_cd.

## Remaining limitations

Honestly documented in REVIEW_FIX_REPORT.md and README "Do not claim" section:
- No experimental validation (no prototype data)
- DS constants uncalibrated (literature-typical)
- Deep-stall Cm synthetic
- Counter-rotating = speculative scenario (not validated array prediction)
- Ham = 2D upper-bound cross-check (not validation)
- Model-form uncertainty not quantified by parameter UQ

## Follow-up

Wait for no-JIT full suite to complete, then commit.