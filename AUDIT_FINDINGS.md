# AUDIT_FINDINGS.md — Phase 0 audit of `sharp-vawt-lab`

Audit date: 2026-10-24. Commit at audit start: `46fd455d87614b9281be0b1a5ab6c513b8ac4cfb` (working tree had uncommitted
refactor changes, including an untracked `sharp_vawt/` package).

This audit was performed **before** any refactoring in this repair round. Every statement below is backed by a
command or file:line evidence collected from the repository as found. No physics constants, polar tables,
regression goldens, or test tolerances were changed to produce this document.

---

## Executive summary

The repository is **not** in the state described by its own README/CHANGELOG. The previous refactor created a
`sharp_vawt/` package but left the old implementation in place, and in several files concatenated multiple
generations of the same code. Concretely:

| Severity | Finding |
|---|---|
| **Critical** | Four copies of the physics kernel / simulation class exist (`vawt_core.py`, `sharp_vawt/config.py` ×3, `sharp_vawt/engine.py`). |
| **Critical** | `scripts/*` run `sharp_vawt.engine`; `tests/*` run `vawt_core.py`. They happen to agree numerically today, but nothing enforced this and one import change would silently change every test. |
| **Critical** | Uncertainty provenance is false: `uncertainty_results.json` is LHS `n_samples=40` with `"sobol": {}`, while README/CHANGELOG/CLAUDE.md claim Saltelli N=64, 960 runs/anchor, 3840 total. |
| **Critical** | Result stamps hash only `sharp_vawt/*`, the script itself, and polar CSVs. They omit `vawt_presets.py`, `UNCERTAINTY` configuration details, Python version, git commit, active/inert UQ parameters, and CLI arguments. |
| **Major** | `STAMP_CHECK_MAP` contains duplicate keys (8 + duplicates); `uncertainty.py` uses a bespoke hash path rather than the shared helper. |
| **Major** | `sharp_vawt/database.py` contains 5 copies of `_deep_stall`, 9 of `_normal_force_coefficient`, 8 of `_post_stall_cm`, 2 of `surrogate_cla`/`surrogate_polar`, and 3+ copies of `PolarDatabase` internals. |
| **Major** | Figure infrastructure is a 4-figure bash script; no `make_all_figures.py`, no `check_figures.py`, no `tests/test_figures.py`. |
| **Major** | CI is Python 3.11 only, no ruff, no `NUMBA_DISABLE_JIT=1` job, no figure/freshness gate, and runs the slow validation suite in the fast job. |
| **Major** | No prototype validation plan/tooling and no DS calibration plan/tooling. |
| **Major** | README/CLAUDE/CONTEXT contain stale, mutually inconsistent UQ counts and several unsupported "validation" labels. |
| **Minor** | Stale root images (`test_*.png`), `repomix-output.xml`, dead `gen_real_polars_v2.py`, duplicate `airfoil_polars/`. |
| **Minor** | Scripts without `if __name__ == "__main__":` execute simulations at import time (`diag_active_lift.py`, `passive_sharp.py`, `passive_sweeps.py`). |
| **Minor** | `requirements-dev.txt` has no trailing newline, missing `ruff`; `pyproject.toml` package-data misses `provenance.json`/README. |
| **Documentation** | README "How to cite" still says 3.3.1 while version is 3.4.0. |

---

## 1. Duplicate physics implementations

### 1.1 Full copies of kernel / simulation / factory

`ast` inventory of top-level definitions:

```
vawt_core.py            : _kernel, _aero_coeffs, _energy, PolarDatabase, CycloturbineSim, create_sim_from_params
sharp_vawt/engine.py    : _kernel, _aero_coeffs, _energy, CycloturbineSim, create_sim_from_params
sharp_vawt/config.py    : _kernel (line 242), CycloturbineSim (581, 855, 1140),
                          create_sim_from_params (545, 1105), PolarDatabase (684),
                          _deep_stall (630, 674), _smoothstep (625, 669)
sharp_vawt/database.py  : PolarDatabase (363) plus duplicated helper blocks
```

Evidence: `python - <<'PY' ... ast.parse ...` duplicate report:

```
config.py defs=19 dups={'create_sim_from_params':[545,1105],'CycloturbineSim':[581,855,1140],
                        '_smoothstep':[625,669],'_deep_stall':[630,674]}
database.py defs=15 dups={'surrogate_cla':[68,580],'surrogate_polar':[73,585],
                          '_deep_stall':[98,126,244,287,609,623,637], '_synthetic_cm':[107,253],
                          '_smoothstep':[121,239,282,604,618,632], '_neuralfoil_attached':[267,323],
                          '_normal_force_coefficient':[296,317,338,646,667,688,709,730,751],
                          '_post_stall_cm':[302,344,652,673,694,715,736,757]}
```

### 1.2 Which copy actually runs

- Every `scripts/*` file imports `from sharp_vawt import create_sim_from_params` (22 scripts).
- `sharp_vawt/__init__.py` first imports `create_sim_from_params` from `.config` (line ~40), then later from
  `.engine` (line ~57). The **engine copy wins** because it is bound last.
- Every test imports `from vawt_core import ...` (except `test_ds_sensitivity.py`, which uses `sharp_vawt`).
- Therefore **scripts and tests exercise different modules**.

### 1.3 Are the copies numerically identical?

Measured with `vawt_core.create_sim_from_params` vs `sharp_vawt.engine.create_sim_from_params` on the committed
presets, comparing every common output column over the full run:

```
sharp_baseline : cp=0.04683053890902435  identical (all columns max diff 0)
ham_1979       : cp=0.4893349383106992   identical
sharp_cppc     : cp=0.0794189439786603   identical
```

So today `engine.py` reproduces `vawt_core.py` **exactly** for these presets, but the duplication is a live
correctness hazard, not a cosmetic one.

### 1.4 Behavioural difference that must be preserved

`OUT_COLS` differs:

- `vawt_core.py`: `["t","th","w","psi","beta","alpha","Tsum","Qshaft","a","Fx","P_blade","psd"]`
- `sharp_vawt/engine.py`: `["t","theta","omega","psi_0","pitch_deg","aoa_deg","torque_total","Q_shaft","a_ind","Fx_total","P_aero","psidot_0"]`

Consolidation must either keep both names or update every consumer. `scripts/render_animation.py`,
`scripts/diag_qa.py`, `scripts/compute_aep_turbulent.py` read `result["out"]` **positionally**, so column order
(index) is the compatibility contract; the name list is cosmetic and can be standardised.

### 1.5 Duplicate polar data

```
airfoil_polars/                 (root, 4 CSVs + provenance + README + __init__.py)
sharp_vawt/airfoil_polars/      (same files)
```

`scripts/stamp.py` hashes only `sharp_vawt/airfoil_polars`; `vawt_core.py` uses `_MODULE_DIR/airfoil_polars`
(root) before the package fallback. Two data origins remain possible.

---

## 2. Duplicate functions, classes, constants, JSON writers, stamp entries

### 2.1 Duplicate constants

`PI`, `TWO_PI`, `NU_AIR`, `_RE_PTS`, `_CLA`, `_CLMAX`, `_CD0`, `POLAR_VARIANTS`, `_SMOOTH_LOW_RE_CAP`,
`_SMOOTH_LOW_RE_MAX_RE`, `DEEP_STALL_*`, `_ALIASES` are defined in `vawt_core.py`, `sharp_vawt/config.py`,
`sharp_vawt/database.py`, and partly in `engine.py` imports.

### 2.2 Duplicate JSON-writing paths

- `scripts/stamp.py`: `write_json_with_stamp` (canonical).
- `scripts/uncertainty.py`: its own `_code_hash()` + manual `{"stamp": ...}` assembly (lines ~120–140, 505–530).
- `scripts/spearman_sensitivity.py`: imports the helper but also has ad-hoc structure.
- Several scripts write raw `json.dump` without the helper (verify per script in Phase 2).

### 2.3 Duplicate stamp-map keys

`scripts/stamp.py::STAMP_CHECK_MAP` as found contains **34 entries but only 24 unique keys**. Repeated keys:

```
cm_scale_scan.json (3×), tip_loss_scan.json (2×), ham_finite_span_check.json (3×),
branch_point_checks.json (3×), diag_aep_branches.json (3×), sobol_results.json (1×, no such file),
spearman_results.json (2×), aep_counter_rotating.json (2×), aep_turbulent.json (2×),
aep_rigid_fair.json (2×), aep_results.json (2×), aep_scaleup.json (2×)
```

### 2.4 Duplicate `__version__`

`sharp_vawt/__init__.py` assigns `__version__ = "3.4.0"` twice.

---

## 3. Modules that can affect simulation results

Verified dependency surface:

- `sharp_vawt/engine.py` — kernel, factory, simulation class.
- `sharp_vawt/config.py` — dataclass defaults and constants (uses `_CD0`, deep-stall constants, etc.).
- `sharp_vawt/database.py` — polar loading, surrogate, deep-stall blending, `Cm` synthesis.
- `vawt_presets.py` — **every headline anchor** is defined here, and the current stamp does **not** hash it.
- `sharp_vawt/airfoil_polars/**` — CSV polars + provenance.
- `vawt_core.py` — legacy copy used by tests/`regenerate_golden.py`.
- `scripts/*.py` — each generating script; per-script version strings.
- Environment: Python version, NumPy/Numba versions, seed, and (for UQ) SALib availability.

`sharp_vawt/config.py` contains `_CD0` but `engine.py` imports `_CD0` and never uses it in the kernel; check for
dead imports.

---

## 4. Result JSON freshness coverage

All 16 result JSONs currently carry a stamp, but **none is sufficient**:

| JSON | Stamp script | Version | Covers presets? | Covers UQ spec? | Covers Python/git/args? |
|---|---|---|---|---|---|
| aep_results.json | compute_aep.py | `v1.0` | ❌ | n/a | ❌ |
| aep_scaleup.json | compute_aep_scaleup.py | `v1.0` | ❌ | n/a | ❌ |
| aep_turbulent.json | compute_aep_turbulent.py | `v1.0` | ❌ | n/a | ❌ |
| aep_rigid_fair.json | compute_aep_rigid_fair.py | `v1.0` | ❌ | n/a | ❌ |
| aep_counter_rotating.json | compute_aep_counter_rotating.py | `v1.0` | ❌ | n/a | ❌ |
| cm_scale_scan.json | scan_cm_scale.py | `v1.0` | ❌ | n/a | ❌ |
| tip_loss_scan.json | scan_tip_loss.py | `v1.0` | ❌ | n/a | ❌ |
| ham_finite_span_check.json | ham_finite_span_check.py | `v1.0` | ❌ | n/a | ❌ |
| branch_point_checks.json | check_branch_points.py | `v1.0` | ❌ | n/a | ❌ |
| diag_aep_branches.json | diag_aep_branches.py | `v1.0` | ❌ | n/a | ❌ |
| finite_span_ablation.json | finite_span_ablation.py | `v1.0` | ❌ | n/a | ❌ |
| optimization_passive.json | optimize_passive.py | `v1.0` | ❌ | n/a | ❌ |
| optimization_scaleup.json | optimize_scaleup.py | `v1.0` | ❌ | n/a | ❌ |
| optimization_actuator.json | optimize_actuator.py | `v1.0` | ❌ | n/a | ❌ |
| robust_optimization.json | robust_reopt.py | `v1.0` | ❌ | n/a | ❌ |
| spearman_results.json | spearman_sensitivity.py | `v1.0` | ❌ | ❌ | ❌ |
| uncertainty_results.json | uncertainty.py | `v13-2026-10-20` | ❌ | partially (hash only) | ❌ |

Missing from `STAMP_CHECK_MAP` entirely: none of the JSONs are absent, but `sobol_results.json` is mapped to a
non-existent script `scripts/sobol_sensitivity.py`, so that entry can never validate.

`check_freshness.py` locates the repo root by walking up from `Path.cwd()` looking for `.git`. It **fails outside
the repository** and is therefore not cwd-independent despite its docstring. `stamp.py::list_stale_results`
correctly uses `__file__`, but `check_freshness.py` gates everything on the cwd-derived root.

---

## 5. Scripts lacking `if __name__ == "__main__":`

Simulation-executing scripts (dangerous: import runs minutes of physics):

- `scripts/diag_active_lift.py` — top-level runs two `create_sim_from_params(...).run()`.
- `scripts/passive_sharp.py` — top-level sweeps.
- `scripts/passive_sweeps.py` — top-level sweeps.

Plot modules lacking guards but harmless on import (`plot_style.py`, `plot_validation.py`) should still get guards
for execution hygiene. Library modules (`vawt_core.py`, `vawt_presets.py`, `sharp_vawt/*`) and test modules are
exempt.

---

## 6. Dead files, stale reports, leftovers, obsolete aliases

- Root images: `test_counter.png`, `test_debug.png`, `test_final.png`, `test_scaleup.png`, `test_small.png`,
  `test_turbulent.png`.
- `repomix-output.xml` (generated repository dump, not source).
- `scripts/gen_real_polars_v2.py` — 18-line shim, superseded by `gen_real_polars.py`; unused (grep: no import).
- Root `airfoil_polars/` duplicate of packaged data.
- `UNCERTAINTY_AUDIT.md` — interim note, now superseded by this document.
- `REVIEW_FIX_REPORT.md` — stale: its own section says "UQ Results (N=40 LHS)" and elsewhere "Saltelli N=64,
  960 samples, 3840 runs per anchor". Both cannot describe the same run.
- `CONTEXT.md` says N=64, D=12, second-order → 6656 runs; `CLAUDE.md` says N=64 first order; neither matches JSON.
- `vawt_presets.py` docstring tells users to import from `vawt_core`; will be updated to `sharp_vawt`.
- `docs/finite_span_validation.png` and `docs/validation.png` names overstate what is shown.

---

## 7. Saltelli/Sobol versus LHS inconsistency

Ground truth from `scripts/uncertainty_results.json` as found:

```
"method": "lhs"
"n_samples": 40
"seed": 42
"sobol": {}
"raw" length: 160  (40 samples × 4 anchors)
```

Claims elsewhere:

- `README.md:425`: "Saltelli sampling (N = 64, 960 runs per anchor …)".
- `README.md:513`: reproduce with `--saltelli --saltelli-n 64`.
- `README.md:561`: "Saltelli Sobol sensitivity indices (N = 64, 960 runs per anchor …)".
- `CHANGELOG.md:84-85`: "The Saltelli run was regenerated (960 samples, 3840 runs)."
- `CHANGELOG.md:303`: "Saltelli N = 64, second order … 1664 runs per anchor".
- `CHANGELOG.md:424`: "Default first-order N=64 (832 runs/anchor with 11 parameters)".
- `CLAUDE.md:142`: "UQ (Saltelli N=64, 4 anchors)".
- `CONTEXT.md:34`: "N=64, D=12, second-order → 6656 runs/anchor".
- `README.md:900`: "uncertainty.py # LHS over eight uncalibrated constants" (eight is also wrong; spec has 13).

So at least **six mutually inconsistent run counts** exist, and the committed JSON supports **none** of the
Saltelli claims.

Additional defects found in `scripts/uncertainty.py`:

- Line 328 prints `N_SAMPLES * len(ANCHORS)` even in Saltelli mode, which under-reports the run count.
- The stamp's `extra_data` only carries `{"UQ_SPEC": ..., "N_SAMPLES": ...}`; it does not record `method`,
  active/inert parameter lists, runs per anchor, or total runs.
- `arm_cd` is inert in every anchor (`arm_d=0`), but the JSON's `parameters` list does not distinguish active
  from inert.

**Decision:** Saltelli/Sobol is the canonical method for **sensitivity indices**; LHS is retained only for
**scenario intervals**. They will never share a headline table. Because a full Saltelli N=64 run is ~20+ minutes
and was interrupted, the committed JSON must not be relabelled; it must be regenerated before the claim is made.

---

## 8. Unsupported uses of "validated"

- `README.md:12,36`: "a set of validation scripts" — acceptable only if scripts are renamed/qualified.
- `README.md:50`: embeds `docs/validation.png`, a prescribed-pitch geometry comparison, not validation.
- `README.md:228–240`: labels a design-point comparison "validation.png"; explicitly not measured data.
- `README.md:976`: counter-rotating pair described as "validated at the modelled spacing".
- `README.md:623,629`: "validation against the primary" (literature) — must be "2D upper-bound literature
  comparison".
- `docs/finite_span_validation.png` name.
- `CLAUDE.md:16`: "Ham 1979 validation (2D upper-bound comparison)" — contradictory phrasing.
- `CHANGELOG.md:447`: "validation against Du & Selig (1998) and NASA TM 4075 data" — literature comparison.
- `CHANGELOG.md:469`: "validation bounds".

No measured prototype data exist anywhere in the repository (`find data/` — absent). Therefore **no** claim of
experimental validation is supportable.

---

## 9. README numbers not generated from current JSON

- UQ sample/run counts and Sobol indices are hand-typed prose (lines 95, 425–470, 561–572, 955).
- `README.md:144` "working-branch mean is 0.095", `:172` "about 1 %" — hand-typed.
- `README.md:466` "0.02" collapse threshold — duplicated in prose.
- `README.md:900` "LHS over eight uncalibrated constants" — wrong count.
- `README.md:955` second-order Sobol claim — no second-order results in JSON.
- "How to cite" version `3.3.1` vs `3.4.0`.

`scripts/build_readme.py` has generated blocks, but only for a subset; the lint tests do not currently reject
hard-coded sample counts or Cp values outside GEN blocks.

`build_readme.py` also contains **triplicated block generators** (`block_*` families around lines 100–600),
apparently copies for different anchors; this must be collapsed to one parameterised implementation.

---

## 10. Missing or weak tests

Present: physics, geometry, factory, polars, regression, validation, freshness, README lint/numbers, DS
sensitivity, diag QA.

Missing or weak:

- No test asserting exactly one physics implementation / no duplicate top-level definitions.
- No test that `cp`, `cq`, `rpm`, `ct`, `aoa_max` are identical between `vawt_core` and `sharp_vawt` (the property
  that made the duplication invisible).
- No test that every script imports safely (would catch top-level simulation runs).
- No test of energy-ledger conservation on a controlled case.
- No test of dynamic-stall state advancement semantics (first-call initialisation, steady-state recovery).
- No test of pitch-torque sign.
- `test_freshness.py` does not test duplicate keys, missing dependencies, cwd independence, or tamper detection.
- No figure tests.
- No UQ metadata completeness test.
- No prototype or calibration tests (tooling absent).

---

## 11. CI gaps

Current `.github/workflows/ci.yml`:

- Python 3.11 only (no 3.12 matrix).
- No `ruff`.
- No `NUMBA_DISABLE_JIT=1` pure-Python job.
- No `check_freshness.py`.
- No figure generation/check.
- No README lint beyond `build_readme.py --check`.
- Runs `validate_ham.py` and `validate_all.py` in the fast job (slow, and conflates validation with comparison).
- `requirements-dev.txt` lacks `ruff` and has no trailing newline.
- `pyproject.toml` package-data omits `provenance.json` and `README.md`; a wheel install would lack provenance and
  the polar README.

---

## 12. Prioritised repair plan

### Critical (must fix this round)

1. Collapse to **one** physics implementation:
   - `sharp_vawt/engine.py` = sole kernel/sim/factory.
   - `sharp_vawt/config.py` = dataclasses + validation + constants only.
   - `sharp_vawt/database.py` = one `PolarDatabase` + one copy of each polar helper.
   - `vawt_core.py` = re-export only.
   - `sharp_vawt/__init__.py` = clean single exports.
2. Delete duplicate root `airfoil_polars/`; resolve data via `importlib.resources`/`__file__`.
3. Add equivalence regression test (`vawt_core` vs `sharp_vawt`) before deleting the old copy.
4. Rebuild stamps: dependency hashing (incl. `vawt_presets.py`), per-script versions, git, Python, seed, args,
   UQ spec, active/inert params; dedupe `STAMP_CHECK_MAP`; make freshness cwd-independent.
5. Regenerate `uncertainty_results.json` with the canonical Saltelli N=64 workflow, full metadata, and remove
   every stale UQ claim from docs. If the run cannot finish, stop and document — do not relabel LHS.

### Major

6. Split uncertainty methods explicitly: Saltelli = sensitivity indices; LHS = scenario intervals.
7. Build `scripts/make_all_figures.py`, `scripts/check_figures.py`, `tests/test_figures.py`; label
   counter-rotating figures.
8. Add missing tests (single implementation, import safety, energy ledger, DS state, pitch sign, stamps,
   freshness tamper/cwd, UQ metadata).
9. Expand CI (3.11/3.12, ruff, no-JIT, freshness, README sync, figure smoke, separate slow job).
10. Add `docs/prototype_validation_plan.md`, `data/prototype/**`, import/compare scripts + synthetic-data tests.
11. Add `docs/dynamic_stall_calibration_plan.md`, `scripts/calibrate_dynamic_stall.py` + synthetic-data tests.
12. Regenerate `REVIEW_FIX_REPORT.md` with before/after values.

### Minor

13. Delete stale images, `repomix-output.xml`, `gen_real_polars_v2.py`.
14. Add `__main__` guards; convert top-level scripts to functions.
15. Fix `requirements-dev.txt`, `pyproject.toml` package data.

### Documentation

16. Rewrite README first screen (what is verified / cross-checked / not validated / limitations / defaults /
    reproduction / do-not-claim).
17. Correct Ham, counter-rotating, CPPC, and "validated" language everywhere.
18. Update CHANGELOG/CLAUDE/CONTEXT to match generated JSON only.
19. Update "How to cite" to 3.4.0.

---

## Audit limitations

- The full test suite was not run during Phase 0 to avoid modifying caches or consuming time needed for the
  audit; it will be run after each repair phase.
- The Saltelli claim cannot be independently confirmed from stored artifacts because no Saltelli result file
  exists; only the LHS JSON is present.
- No prototype data exist, so no empirical validation can be audited.
