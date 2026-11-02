# Known issues and deferred work

This document lists items that are acknowledged but not yet fixed.
It is separate from CHANGELOG.md, which records changes. Each item
either requires a scheduled regeneration pass (see the note on
stamp invalidation) or a decision that has not been made yet.

Items grouped by blocker type:

- **Regeneration-blocked**: changing the file would invalidate one
  or more result JSON stamps (see `scripts/stamp.py::STAMP_CHECK_MAP`).
  Requires a deliberate producer rerun (multi-hour on modest hardware).
- **Decision-blocked**: requires a policy or design choice that has
  not been made yet.
- **Data-blocked**: requires measured data that does not yet exist.
- **Process**: improvement to workflow, not a defect.

## Regeneration-blocked

## Decision-blocked

- **`validate_ds_off.py` DESIGN vs `optimization_actuator.json` best_params**:
  `validate_ds_off.py::DESIGN` (c=0.117607, ar=0.31, sp=0.18, mc=0.040,
  dcw=-0.132) differs from `optimization_actuator.json::best_params`
  (c≈0.101, ar=0.5, sp=0.25, mc=0.008, dcw=0.5). They are different
  configurations; the DS-sensitivity result applies to DESIGN, not to
  best_params. **Fix deferred** because no test or documentation change
  should silently equate them.

- **Dead legacy fallback in `load_fair_rigid_reference`**: retained with
  clearer comment. The `else: g = {}` branch handles non-scaleup geometry
  data (AR <= 5) by returning None. It supports a real legacy-format
  contract where a rigid_fair JSON without a "geometries" key and with
  AR <= 5 is not a valid reference. **Not removed** because changing
  artifact-loading behaviour is out of scope for this pass.

- **Small-rotor free-running / fixed-rpm Cp discrepancy**: measured
  gap is 34-48% across U ∈ {6, 8, 12} m/s at the free-running
  equilibrium TSR (see scripts/diag_small_equilibria.json).
  Four checks discriminate causes:
  (a) Q-omega correlation from ripple contributes < 2% of the gap
  (see ripple_check in the JSON);
  (b) per-revolution ledger channels differ: aero/shaft ~6-11x,
  piv_vis ~7.5-10.5x, piv_cou ~3.4-6.0x, stop and d_stored are 0
  in both modes (no pitch-stop energy dissipated in either);
  (c) waveform differences: psi RMS differs by 0.04-0.09 rad, min/max
  differ modestly, stop fraction is 0% in both modes at all U;
  (d) bistability check shows n_distinct_free=2/n_distinct_fixed=2
  at U=6 (pitch bistability), n_distinct_free=2/n_distinct_fixed=1
  at U=8 (free bistable, fixed single-attractor),
  n_distinct_free=1/n_distinct_fixed=1 at U=12 (single attractor both).

  Current interpretation: the gap is real physics, not a bug or
  accounting error. The pitch equation contains a term proportional
  to the rotor angular acceleration ω̇ (see sharp_vawt/engine.py:
  acc = ((Ip + M·Rp·SR[k])·wd + Xk[k]) / Ip). In free mode wd ≠ 0,
  so this term drives the pitch dynamics at every step. In fixed
  mode wd = 0 identically, so the term is absent. The result is
  different pitch limit cycles at the same mean TSR: free-mode
  psi RMS is 0.12 rad vs fixed-mode 0.08 rad, and pitch damping
  losses (piv_vis) are 7.5-10.5× higher in free mode. These drive
  different mean aoa trajectories and different mean blade torque.
  Bistability is present at U=6 (both modes) and U=8 (free only)
  but is secondary: the gap persists at U=12 where neither mode
  is bistable, ruling out bistability as the primary cause.

  This validates the CPPC advantage claim rather than undermining
  it: even when the fixed-rpm run is given its best possible
  operating point (same mean TSR as the free run), free operation
  wins by 34-48%. The AEP-level gain (121%) is larger because the
  AEP fixed-rpm workflow uses a realistic generator-imposed
  TSR(U) schedule rather than the best-case constant mean TSR.

  Also correct the ledger ratio phrasing: 'aero/shaft ~6-11x' means
  aero energy is 6-11 times shaft energy *within each mode* (most
  aero work is dissipated in pitch damping), not that free-mode
  aero energy is 6-11 times fixed-mode aero energy.

- **Calibration tooling for real measured data**
  (`calibrate_passive.py`, `docs/measurement_protocol.md`,
  `data/measured_template.csv`): deferred. The proposed CSV schema
  (`azimuth_deg, pitch_deg, torque_Nm, U, rpm`) overlaps partially with
  the dynamic-stall calibration schema in
  `docs/dynamic_stall_calibration_plan.md` and the per-measurement
  schema in `data/prototype/README.md`. Adding a third schema without
  first reconciling the three would repeat the multiple-configurations
  problem that KNOWN_ISSUES.md documents for the optimised_passive
  preset. Decision needed: consolidate to one measurement schema before
  implementing the fitting code.

- **Negative-TSR mirror symmetry not testable without a kernel change**:
  `test_mirror_symmetry_prescribed` covers pitch-coefficient reversal at
  positive TSR. The negative-rotation case (mirror symmetry of the full
  state, TSR < 0) raises `ZeroDivisionError` in
  `sharp_vawt/engine.py::_kernel` because the induction update divides by
  TSR. Adding negative-TSR support is a kernel change; not undertaken in
  PASS 33.

## Test invariants not upheld

- **Similarity in wind speed is not an invariant of this model**:
  doubling U at fixed TSR doubles Re, moving across polar-table
  boundaries (Re = 1e5 -> 2e5 for the small rotor at TSR=1.5,
  U=6 -> U=12). The 34% Cp shift measured in PASS 34 is the
  real Re-driven polar change, not a numerical error. A model
  with Reynolds-independent polars would satisfy similarity;
  this one does not. The test was removed rather than widened
  to hide the effect.

- **Geometric scaling is not an invariant of this model**:
  same root cause. Scaling R, H, c by 2x doubles Re at fixed U
  and TSR, crossing a polar-table boundary. The 30% Cp shift
  is the Re-driven polar change, not a physics violation.

- **Pitch-reversal "mirror symmetry" at fixed rotation is not
  a symmetry operation**: reversing pitch coefficients
  (psi -> -psi) at fixed positive rotation is a different pitch
  schedule, not a mirror of the original. True mirror symmetry
  (negate psi AND alpha AND omega simultaneously) requires
  negative TSR, which raises ZeroDivisionError in
  `sharp_vawt/engine.py::_kernel` because the induction update
  divides by TSR. Negative-TSR support is tracked separately
  under "Decision-blocked."

## Process

- **Shared AEP-core extraction**: `aep_core.py` refactor not started.
- **Cross-workflow AEP consistency test**: not added.
- **Branch-continuation regression test**: not added (formula fixed but no
  dedicated unit test for w0_frac continuation).
- **validate_ds_off-versus-actuator consistency test**: not added.
- **Tip-loss threshold documentation test**: not added.
- **Ruff per-file-ignore reduction**: not done.
- **`vawt_core.OUT_COLS` legacy-name migration**: not done.
- **`render_animation.py` historical-design default**: not changed.
- **`validate_ham.py` circular expected-bias window**: not reviewed.
- **Low-severity plot/test cleanups**: not done.
- **Test-isolation root cause**: individual-vs-full-suite discrepancy not
  reproduced; stale README references removed but underlying mechanism
  unknown. Do not claim the interference mechanism is understood.

- **Report/test drift**: PASS 31 and PASS 32 reports claimed analytic
  tests passed that failed when re-run. Test reports must include the
  command that was run and its actual output, not a summary count.
  Logged as a process correction, not a defect in the code.
