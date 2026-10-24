# Dynamic-stall calibration plan

Status: **the dynamic-stall (DS) model is currently uncalibrated.** The five
constants (`ds_Tf`, `ds_Tv`, `ds_Ta`, `ds_Kv`, `ds_Knc`) are literature-typical
values, not fitted to any data in this repository. No independent measured
dynamic-stall dataset exists here, so no calibrated parameter set is claimed.

This plan fixes the calibration protocol *before* data are analysed.

## 1. Parameters in scope

| Name | Default | Meaning | Units | Bounds |
|---|---|---|---|---|
| `ds_Tf` | 3.0 | separation-point lag | convective times `c/W` | 0.5–10 |
| `ds_Tv` | 6.0 | vortex-lift decay lag | convective times `c/W` | 1–20 |
| `ds_Ta` | 0.1 | attached-flow lag | convective times `c/W` | 0.02–1.0 |
| `ds_Kv` | 0.5 | vortex-lift strength | — | 0–2 |
| `ds_Knc` | 1.0 | apparent-mass lift multiplier | — | 0–2 |

The model does not contain a separate vortex-moment constant, so there is no
vortex-moment parameter to calibrate in this version. If a future model version
introduces one, it must be added to this plan and treated as an additional
calibratable parameter before calibration.

The default values in `sharp_vawt/config.py` **must not be changed** by this
process. Calibration writes a separate candidate parameter file; adopting it as
a new default requires its own reviewed change and updated regression evidence.

## 2. Required calibration data

Only **independent measured data** may be used — oscillating-airfoil,
rotating-VAWT blade surface-pressure/force, or full-scale blade-load
measurements, collected by the user or from a documented third-party source.
Comparisons with `sharp-fsi`, other BEM codes, or this repository's own output
are **not** calibration data.

Required CSV schema (one row per time sample):

| Column | Unit | Required | Notes |
|---|---|---|---|
| `case_id` | — | yes | trace identifier; splits are by case |
| `time_s` | s | yes | monotonically increasing within a case |
| `alpha_deg` | deg | yes | geometric angle of attack |
| `cl` | — | yes | measured lift coefficient |
| `cd` | — | yes | measured drag coefficient |
| `cm` | — | no | measured quarter-chord moment; calibrated jointly if present |
| `Re` | — | yes | Reynolds number for static polar lookup |
| `chord_m` | m | yes | physical chord, for convective time scale |
| `W_mps` | m/s | yes | effective inflow speed, for convective time scale |

Rows with non-finite values, negative `cd`, non-positive `Re`/`chord_m`/`W`,
or non-uniform time steps are rejected; nothing is silently repaired.

## 3. Calibration / held-out split

The split is by `case_id`, deterministically: SHA-256 of the case id modulo
100; cases with remainder `< --calibration-fraction * 100` (default 60 %)
form the calibration set, the rest form the held-out set. Explicit lists
(`--calibration-cases`, `--heldout-cases`) override the hash split.

A case must not appear in both sets. Minimum: 2 calibration cases, 2 held-out
cases, ≥ 50 held-out samples. Otherwise the result is `not_calibrated` regardless
of fit quality.

## 4. Calibration procedure

1. Start each case from the steady static state (engine first-call
   initialisation, so no start-up spike biases the fit).
2. March `_aero_coeffs` at the measured time step with measured
   `alpha(t)`, `Re`, chord, and inflow speed.
3. Residuals: `(Cl_model − Cl_meas)/rms(Cl_meas)`, same for `Cd` (and `Cm`
   when present). No smoothing, undocumented resampling, or outlier deletion.
4. Bound-constrained least squares (`scipy.optimize.least_squares`) over the
   parameters selected by `--fit` (default all five), using bounds in §1.
5. Report Jacobian-based covariance and 95 % intervals; calibration fails if the
   Jacobian is rank-deficient or its condition number exceeds 1e10.

## 5. Held-out acceptance criteria (pre-registered)

Calibration may be called **calibrated** only if **all** hold on held-out cases
never used in the fit:

| Criterion | Threshold |
|---|---|
| Held-out cases / samples | ≥ 2 cases and ≥ 50 samples |
| RMSE `Cl` | ≤ 0.08 |
| RMSE `Cd` | ≤ 0.06 |
| RMSE `Cm` (if measured) | ≤ 0.05 |
| `Cl` RMSE improvement vs defaults | ≥ 20 % |
| `Cd` RMSE improvement vs defaults | ≥ 20 % |
| Identifiability | condition number < 1e10 and finite 95 % intervals |
| Not pinned at a bound | each fitted parameter > 0.1 % inside its bounds |

Additionally, the script permits the `calibrated` label only when data are
declared `--provenance measured`. Synthetic data, `sharp-fsi` output, or any
other model output always produce `calibration_claim_allowed = false`.

If any criterion fails, the result is `not_calibrated` with fitted values and
the failing criteria. Thresholds may not be loosened after seeing the held-out
result without a dated amendment and a new held-out set.

## 6. Reporting

Output JSON records: fitted/fixed parameters, bounds, split membership,
per-case reduced frequency, residuals, RMSE for fitted and default parameters,
improvement vs defaults, covariance, 95 % intervals, condition number,
acceptance booleans, data/settings hashes, and a reproducibility stamp.

The fitted parameter file is a **candidate**, not a new default.

## 7. Explicit non-claims

- Current constants are **not calibrated**.
- A successful fit on synthetic data demonstrates tooling only.
- `sharp-fsi` agreement is not calibration or validation.
- A calibrated DS model is not a validated rotor model.
- Intervals are identification intervals from one dataset, not a posterior.
