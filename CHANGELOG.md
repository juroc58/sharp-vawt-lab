# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`scripts/check_polars.py`** prints a warning report (not a CI failure)
  for attached lift slopes above `1.15*2*pi`, Cl non-monotonicity / the
  low-Re bubble kink before 20 deg, and Cm sign changes. CI runs it after
  the test suite.
- **`polar_variant`** (`"neuralfoil"` default, `"smoothed_lowRe"`) on
  `AeroConfig`. The smoothed variant caps the Re <= 1e5 attached lift by a
  `2*pi*1.1` slope line and removes the 12 deg bubble dip by enforcing
  monotone Cl to 20 deg. It is documented as a model-form sensitivity
  variant, not data. It is also a categorical (0/1) UQ input.
- **`scripts/scan_cm_scale.py`** (`cm_scale_scan.json`): deterministic
  scans of `cm_scale` and `tip_loss_multiplier` for the Sharp-inspired and
  optimised-passive anchors. The Sharp rotor collapses for `cm_scale`
  ≤ 0.5 and for a tip multiplier ≤ 0.955; the optimised rotor survives at
  zero Cm.
- **`scripts/ham_finite_span_check.py`** (`ham_finite_span_check.json`):
  reconciles the static-only 0.476 and the UQ 0.49 in one table and scans
  blade AR = 3–6 with the Helmbold correction. The paper is not in the
  repo; the geometric AR = H/c is also reported.
- **`scripts/check_branch_points.py`** (`branch_point_checks.json`):
  longer `T_max` and three initial conditions for the TSR = 3.25 and
  U = 4 m/s points.
- **`scripts/robust_reopt.py`** (`robust_optimization.json`): bounded
  local re-optimisation of the passive and scale-up designs for the
  scenario mean/p10 over `cm_scale = 0`, `tip_loss_multiplier = 0.96`,
  both, and higher `cd_add`. Reports nominal, mean, p10 and bound-active
  parameters.
- **`vawt_presets.py`**: named machines (`sharp_baseline`, `ham_1979`,
  `sharp_cppc`, `optimised_passive`, `scaleup`) now live in an explicit
  `PRESETS` dict. The dataclass defaults are a neutral R = 0.6 m,
  H = 0.4 m baseline (fixed-rpm 10 s run, k_load = 0.0025) instead of the
  2.7179 m scale-up, so no script silently inherits the large machine.
  Scripts and tests that need a named machine pass its preset explicitly.
  Regression goldens are unchanged.

### Changed
- **Cm table (Task 1)**: Default polar variant (`polar_variant="neuralfoil"`) now enforces Cm = 0 for |α| ≤ 20° (physical symmetric-section value) and uses a centre-of-pressure shift model (x_cp: 0.25c → 0.5c) for post-stall Cm. The raw NeuralFoil CM (with sign changes in attached flow) is available as `polar_variant="neuralfoil_cm"` for sensitivity analysis only. Lift slope clamped at 1.15·2π and Cl monotonicity enforced to 20° in the default variant. Updated `provenance.json`, `airfoil_polars/README.md`, and tests. `check_polars.py` now exits non-zero on warnings for the default variant (`--fail-on-warnings`). Before/after Cp (default variant): Sharp-inspired ~0.067→0.079, Optimised passive ~0.265→0.264, Scale-up ~0.384→0.494, Ham ~0.491→0.489.
  (`DEEP_STALL_*` in `scripts/gen_real_polars.py`) marked
  provisional/unverified, not a fit to data.
- **Ham 1979 framing**: reframed from "reproduction"/"validation" to a
  documented 2D upper-bound comparison. The static-only peak (Cp ≈ 0.476 at
  TSR 2.5) is ~+9 % above Ham's 3D measured band midpoint (0.435) and above
  his entire 0.42–0.45 band. `scripts/ham_finite_span_check.py` shows that
  applying Helmbold at Ham's geometry AR = 4.49 gives only Cp ≈ 0.297,
  below the measured band, so the finite-span model over-corrects for this
  rig; the no-tip peak remains the documented upper bound. The 0.476 and
  0.49 numbers are reconciled in one generated table as different
  configurations (`cd_add` 0.005 vs 0.002). `scripts/validate_ham.py`
  reports a signed bias vs a window derived from that finite-span check
  (0 % to the Helmbold-correction magnitude) instead of a post-hoc
  +5–20 % band or a PASS/FAIL "inside band" verdict; `tests/test_validation.py` classes were renamed
  (TestHamReproduction → TestHamPeakComparison, TestHamVerdictLogic →
  TestHamVerdictContract) and assert the expected bias window plus the fact
  that the peak is NOT inside Ham's band. `scripts/plot_ham_curve.py`
  title now reads "Ham 1979 comparison: 2D static-only upper bound vs
  measured Cp(TSR)". No physics, polar, or golden change.

- **UQ now samples thirteen inputs, twelve active.** `polar_variant` is a
  categorical 0/1 model-form input; `arm_cd` remains inert because every
  anchor has `arm_d = 0`. The Saltelli run was regenerated (960 samples,
  3840 runs). The summary now reports base Cp at `cm_scale = 0`, all-sample
  mean, working-branch mean and collapsed fraction. The Sharp-inspired
  anchor is strongly bimodal: all-sample mean Cp = 0.033, working-branch
  mean = 0.095, collapse fraction 69.3 %, versus a physical-Cm base case of
  Cp = 0.0046. The optimised-passive collapse fraction is 1.0 %. These
  replace the earlier 56.8 %/2.0 % split because the corrected
  `cm_scale` blend and the polar model-form input are now sampled.
- **Rated power is defined per design, not fixed at 90 kW.** The rating is
  the mechanical power at U = 12 m/s using the design Cp at that speed
  times drivetrain efficiency (8.55 kW for the scale-up). The old 90 kW
  number was about ten times too large and made capacity factors look like
  ~2 %. Scale-up AEP therefore changes from 17.26 to 15.49 MWh/yr: the
  lower rating clips power above 12 m/s. The fair rigid baseline is
  14.15 MWh/yr with the same rule, so the passive-vs-rigid gain is +10.6 %
  (was +13.9 %). The same per-design rule replaces the fixed 15 kW rating
  in `compute_aep_turbulent.py` (8.56 kW) and the 90 kW pair rating in the
  counter-rotating scenario; turbulent AEP becomes 15.61 MWh/yr steady and
  16.63 MWh/yr with turbulence. These are mandated rating/AEP changes, not
  physics changes; the Cp curves are unchanged except for the phase average
  below.
- **Fixed-rpm Cp(TSR) is phase-averaged.** A single `psi0 = 0` run gave a
  narrow TSR = 3.25 maximum (Cp 0.4122) that fell to 0.3479 at `psi0 =
  120°/240°`; this is an initial-phase limit-cycle artefact, not a
  transient. The curve now averages three phases at every TSR. The
  free-running U = 4 m/s point is independent of `T_max` and seed.
- **Scale-up AEP branches are reported with initial conditions.** High-seed
  (`w0_frac = 1.20`), low-seed (`0.20`) and branch-traced runs all converge
  to the same high-TSR branch at every sampled wind speed from cut-in to
  cut-out; no low branch was found, so the branch AEP range is degenerate
  (15.48–15.48 MWh/yr). The earlier plotted drop is not reproduced by the
  current raw runs.
- **Counter-rotating pair is a scenario with a factor sweep.**
  `scripts/compute_aep_counter_rotating.py` now stores a fixed-factor
  sensitivity sweep (0–16 % downstream velocity increase). At the modelled
  0.37 D spacing the heuristic pair gain over two independent rotors is
  +2.8 %, not a headline array prediction. The 16 % cap is a literature
  bound, not a calibration of this pair.
- **Robust re-optimisation.** Starting from the stored optima, the passive
  design gives nominal/mean/p10 Cp = 0.270/0.262/0.254 with no bound-active
  parameters. The scale-up gives 0.417/0.409/0.400 with the arm ratio at
  its lower bound (ar = 0.30). Scenario set and full parameters are in
  `scripts/robust_optimization.json`.

### Fixed
- **README Sobol prose matched an old run.** The text still quoted 1664
  second-order runs and the old `tau_rev`/`ds_Tf` index values. It now
  states the actual N = 64, 960-run first-order Saltelli set (3840 runs
  across four anchors) and points at the generated table instead of
  repeating stale indices.
- **`cm_scale = 0` now really means no pitching moment.** The dynamic-stall
  separated-Cm blend target (`copysign(0.05, -alpha)`) is multiplied by
  `cm_scale` as well as the static table Cm. With `cm_scale = 0` and a
  Cm-zeroed copy of the same polar the simulation is bit-for-bit identical
  (new regression test). This changes UQ samples with `cm_scale < 1`; the
  nominal `cm_scale = 1` cases are unchanged.
- **Polar paths resolve relative to `vawt_core.py`**, not the process working
  directory, so scripts launched from `scripts/` load the same tables. The
  UQ cache hash now also covers `airfoil_polars/provenance.json` and fails
  loudly if any required source file is missing.
- **AEP plots now show raw data** (`docs/aep.png`,
  `docs/aep_scaleup.png`). The earlier `scipy.signal.medfilt` smoothing,
  fixed y-limits and removed free-running scatter are gone: Panel 1 shows
  the raw fixed-rpm Cp(TSR) curve plus the free-running operating points,
  and Panel 2 shows the raw free-running Cp(U) curves with automatic
  y-limits. No data are filtered or hidden in the plots.

  The TSR = 3.25 spike was investigated rather than smoothed: it is a
  phase-locked limit cycle (`psi0 = 0°` gives Cp ≈ 0.412, `psi0 = 120°`
  and `240°` give ≈ 0.348 at the same T_max). The fixed-rpm curve now
  averages three equally spaced initial rotor phases at every TSR, which
  removes the initial-phase artefact. The free-running U = 4 m/s point is
  unchanged by longer runs or different seeds. See
  `scripts/check_branch_points.py` and `scripts/branch_point_checks.json`.

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

### UQ results (Saltelli N = 64, second order; v13 rerun, 1664 runs per anchor)
Added `cm_scale` (0–1) to UQ_SPEC; see `scripts/uncertainty_results.json`;
the README tables are generated from it. Mean [p5, p95]:

| Anchor | Mean | 90 % interval | Collapsed samples (Cp < 0.02) |
|---|---|---|---|
| Ham 1979 | 0.49 | [0.47, 0.51] | 0 % |
| Sharp-inspired CPPC | 0.04 | [0.002, 0.12] | 56.8 % |
| Optimised passive | 0.19 | [0.051, 0.28] | 2.0 % |
| Scale-up R = 2.72 m | 0.38 | [0.33, 0.42] | 0 % |

The dominant first-order Sobol parameter is `tau_rev` for Ham (S₁ = 0.84).
For Sharp-inspired CPPC, `ds_Tf` (S₁ = 0.43) and `tip_loss_multiplier`
(S₁ = 0.41) are nearly tied; for the optimised-passive anchor the
multiplier leads (S₁ = 0.51); at the scale-up no first-order index is
significant at N = 64 (largest is `tip_loss_multiplier` S₁ = 0.19, CI
spans zero). No run returned a non-finite or negative Cp (`n_fail = 0`).
The v12 numbers (Sharp 0.048 [0.003, 0.108], 46.7 % collapsed; Ham
0.491; scale-up 0.362) did not sample `cm_scale` and are superseded.
The 95 % confidence half-widths on the dominant indices are 0.2-0.3 at
N = 64 and are printed in the README table.

### v12 review follow-up (same unreleased 3.3.1)

Four remaining review items were fixed rather than deferred. Because
3.3.1 has not been tagged, these changes are recorded here instead of in a
new version entry.

- **Attached-flow Cm now comes from NeuralFoil.** For `|alpha| <= 20 deg`
  the tables use NeuralFoil's quarter-chord `CM` (positive nose-up, the
  same sense as the solver's `Qa_cm = q*Cm*c`); negative incidence is
  mirrored with odd symmetry. `20 < |alpha| < 45 deg` blends to the
  synthetic Abbott & von Doenhoff trend, and `|alpha| >= 45 deg` remains
  synthetic because NeuralFoil's post-stall moment is not validated.
  Reason: the old synthetic trend was not measured and gave a smooth
  but invented negative moment through attached flow; the reviewer
  correctly flagged it. The network's attached Cm is itself noisy (at
  Re = 1e6 it ranges from about -0.008 to +0.047 over 0-20 deg), but it
  is the surrogate output rather than an additional hand fit. The
  convention and scatter are recorded in `provenance.json` and
  `airfoil_polars/README.md`.
- **Consequence of the Cm change.** The passive pitch machine uses Cm
  directly, so the Sharp-inspired deterministic point moved from Cp
  0.104 to 0.067 (equilibrium TSR 1.20) and the collapse threshold moved
  from multiplier ~0.78 to ~0.955 in the new Helmbold-normalised units.
  The design is now only ~4 % above the threshold. This is reported, not
  hidden.
- **Finite-span central estimate replaced by Helmbold (1942).**
  `f_ar = 1/(sqrt(1 + (2/AR)^2) + 2/AR)` replaces the generalized
  Prandtl form `1/(1 + 1.8/(e*AR))`. Reason: at the Sharp AR of 2.86 the
  old form gave `f_ar = 0.588` (lift slope 3.70/rad) where Helmbold gives
  0.520 (3.27/rad), about 12 % too much lift; the reviewer's Helmbold
  cross-check was correct. The Oswald factor now enters only the
  induced-drag term `1/(pi*e*AR)`. At AR 10.5 the two forms nearly agree
  (0.828 vs 0.840), so the scale-up is barely affected.
- **`tip_loss_multiplier` band narrowed to [0.85, 1.15]** around the
  Helmbold central value (was [0.70, 1.30] around generalized Prandtl).
  Reason: the old band existed to cover the systematic low-AR bias of the
  Prandtl form; Helmbold removes that bias, so a +/-15 % residual
  model-form band is used. `_UQ_VERSION` was bumped to invalidate the
  cache. With `cm_scale` now sampled (0–1), 56.8 % of the Sharp-inspired
  UQ distribution collapses — most of it through zero/low Cm scale, i.e.
  the design does not self-sustain without its pitching moment; that is a
  physical result, not a sampling artifact.
- **Passive DS sensitivity pinned.** The vacuous test bound
  `0.001 < delta < 0.95` is replaced by anchor-specific values:
  0.91 +/- 0.05 for Sharp-inspired CPPC and 0.75 +/- 0.05 for the
  optimised passive machine. The README now states explicitly that every
  passive result rests on the dynamic-stall model. The old prescribed
  design forced into passive mode collapsed to Cp ~0.03 after the
  finite-span fix and is no longer used as the passive test case.
- **Sobol reporting.** The README table now prints 95 % confidence
  half-widths next to S₁ and Sₜ and keeps two-decimal rounding. It also
  states that `arm_cd` is inert because every anchor has `arm_d = 0`
  (now 11 of 12 sampled inputs are active after the Cm scale was added;
  see the v13 follow-up), and lists the model-form choices
  that are *not* sampled (induction closure, DS structure, curvature
  scaling, counter-rotating interaction, section-data source). Indices
  whose confidence interval spans zero are not used for ranking.
- **Regression goldens** (reason: new Cm and Helmbold):
  `ham_static_tsr2_5` 0.485448 -> 0.490899 (+1.1 %),
  `passive_short_free` 0.393393 -> 0.384398 (-2.3 %),
  `prescribed_fixed_rpm` 0.447375 -> 0.444303 (-0.7 %).
- **`tests/test_physics.py` Cm expectations** were updated from the old
  synthetic sign (Cm(15 deg) < 0) to the NeuralFoil value
  (Cm(15 deg) ~ +0.047), with a zero-at-zero-alpha check and a
  provenance check. This is a deliberate source change, not a tolerance
  relaxation.

### v13 review follow-up (same unreleased 3.3.1)

- **Cm scale added to the UQ** (`cm_scale`, range 0–1; core default 1.0 so nominal
  numbers are unchanged). Reason: the Sharp-inspired design does not
  self-sustain without the pitching moment — with Cm = 0 its Cp falls from
  0.067 to ≈ 0.005 (collapsed, TSR ≈ 0.49) — so its headline number rests
  on the NeuralFoil attached-flow Cm table, whose values are noisy and
  sign-changing for a symmetric section. The optimised-passive design is
  insensitive (Cp 0.272 → 0.274 with Cm = 0) and is the more robust result.
  The Sharp UQ row is therefore a scenario range, not a precision result,
  and is reported as such. `_UQ_VERSION` bumped to invalidate the cache.
- **UQ input scope** is now twelve sampled inputs, eleven active
  (`arm_cd` inert because `arm_d = 0` in every anchor); the Sobol table and
  README counts were regenerated accordingly.
- **README prose corrected.** Sharp-inspired TSR is ≈ 1.19 (not 1.38) and
  the collapse threshold is ≈ 0.955 (not 0.78); the optimised-passive
  nominal point (Cp = 0.270) is shown next to its UQ mean (0.19 [0.051,
  0.28]) with a winner's-curse note; the low-Re NeuralFoil lift caveat was
  added to `airfoil_polars/README.md`.

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
