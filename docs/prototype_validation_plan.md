# Prototype validation plan (pre-registered)

Status: **validation not yet available.** No physical rotor has produced measured data for this model.
This document is written *before* data collection so that the comparison cannot be tuned after the fact.
It is a protocol, not evidence.

## 0. What this plan can and cannot establish

A successful comparison would be **validation** in the strict sense: independent measured data,
collected on a physical rotor, compared with model outputs that were frozen before those data were
examined. Agreement would support the model for the tested operating envelope only. It would not
validate other geometries, other Reynolds numbers, array configurations, or long-term site yield.

Until the data exist and the pre-registered acceptance criteria are met, every reference to this work
must say **“prototype validation planned”**, never “validated”.

## 1. Rotor and hardware (fill in before the first run; do not edit during the campaign)

| Item | Value | Notes |
|---|---|---|
| Rotor ID | _(pre-assigned)_ | unique, marked on hardware |
| Geometry ID | _(pre-assigned)_ | must match `data/prototype/metadata/geometry_<id>.json` |
| Blade count `N` | 3 (baseline) | record any change as a new rotor ID |
| Radius `R` [m] | 0.60 (baseline) | tip radius, measured |
| Chord `c` [m] | 0.14 | measured at 3 stations |
| Span `H` [m] | 0.40 | measured |
| Airfoil | NACA 0012 | document any deviation |
| Pivot position `sp/c` | 0.25 | measured from leading edge |
| Arm ratio `ar = arm/c` | 0.50 | measured |
| Counterweight mass `mc` [kg] | 0.002 | weighed |
| Counterweight offset `dcw` | +0.30 | from pivot, sign convention in `docs/derivation.md` |
| Blade mass `mb` [kg] | 0.010 | weighed |
| Blade CG `xbcg/c` | 0.20 | balance measurement |
| Hub inertia `J_hub` [kg m²] | 0.02 | pendulum or CAD estimate |
| Generator | _(model/serial)_ | record |
| Drivetrain | direct or belt; ratio | record |
| Bearing | type, preload | record |
| Rectifier/load | resistor bank and/or MPPT | record exact values |
| Wind machine | type, calibration date | record |

## 2. Instrumentation

| Quantity | Sensor | Range / resolution | Calibration | Uncertainty method |
|---|---|---|---|---|
| Wind speed | cup or sonic anemometer at hub height, **upwind of the rotor by ≥ 5R** | 0–20 m/s, 0.1 m/s | dated certificate | Type B from certificate + Type A from 10 Hz record |
| Wind direction | vane / sonic | ±2° | dated certificate | Type B |
| RPM | optical or Hall sensor on hub | 1–2000 rpm | pulse check | ±1 pulse / window |
| Electrical power | DC voltage + current (or power analyser) | 0–2 kW | shunt/analyser certificate | Type B, combined |
| Torque | inline torque transducer **or** inferred from electrical power and RPM | 0–50 N·m | certificate | see §3 |
| Temperature | shielded RTD | −20–50 °C | certificate | ±0.5 °C |
| Pressure | barometer | 900–1100 hPa | certificate | ±1 hPa |
| Humidity | RH sensor | 0–100 % | certificate | ±3 % |

Wind speed must be corrected to rotor-centre height using the documented shear law and the measured
anemometer height; the correction and its uncertainty must be recorded per run. Do not silently use
the anemometer reading as the rotor inflow.

### 2.1 Torque

Preferred: inline torque transducer between rotor and generator. If no transducer is available, torque
is **inferred** as `Q = P_electrical / (eta_drivetrain * omega)` and the row must set
`torque_inferred = true`, with `torque_uncertainty_Nm` propagated from power, RPM and efficiency
uncertainties. Inferred torque must not be presented as a direct measurement.

## 3. Test matrix and procedure

1. **Start-up tests.** For each wind condition, release the rotor from rest and record the full
   spin-up transient. Repeat 3 times. Report time-to-first-power and whether the rotor settled on the
   working branch.
2. **Load steps.** At each wind speed, apply at least 5 resistive load values spanning the expected
   optimum (e.g. 5, 10, 20, 40, 80 Ω, adjusted to the generator). Hold each load for ≥ 60 s after
   steady state, record 10 Hz for ≥ 30 s.
3. **Wind conditions.** At least 6 nominal wind speeds spanning 4–12 m/s, or the safe range of the rig.
4. **Repetitions.** Minimum 3 independent runs per (wind speed, load) condition, on at least 2
   different days.
5. **Reference condition.** One repeat of the same condition at the start and end of each day to
   detect drift.
6. **Logging.** Raw sensor files, calibration certificates, and operator notes go under
   `data/prototype/raw/`; processed rows under `data/prototype/processed/`; metadata under
   `data/prototype/metadata/`.

## 4. Exclusion rules (fixed before collection)

A run is excluded **only** if one of the following pre-registered conditions holds:

- wind direction outside ±30° of the intended axis for more than 10 % of the averaging window;
- mean wind speed outside the intended bin by more than 0.5 m/s;
- wind-speed standard deviation / mean > 0.25 (non-stationary);
- RPM or power sensor saturation, dropout, or timestamp desynchronisation > 0.5 s;
- visible mechanical fault, loose blade, or changed geometry;
- ambient air density outside 1.05–1.35 kg/m³ and no valid correction applied;
- run shorter than the pre-registered steady-state window.

Excluded rows must remain in the raw archive with an `exclusion_reason`; the processed file must not
silently drop them. The count of exclusions and reasons must be reported.

## 5. Frozen model inputs (locked before examining measured power curves)

The following must be written to `data/prototype/metadata/frozen_model_settings.json` and hashed
**before** the first measured power curve is inspected:

- geometry (all fields),
- polar source (`sharp_vawt/airfoil_polars`, variant name, file hashes),
- dynamic-stall configuration (`use_dynamic_stall`, `ds_Tf`, `ds_Tv`, `ds_Ta`, `ds_Kv`, `ds_Knc`),
- induction model (`use_dmst`, `tau_rev`, `a_fix`),
- tip-loss / finite-span settings (`use_tip_loss`, `tip_loss_multiplier`, `tip_loss_floor_override`,
  `e_osw`, `ind_drag_scale`),
- load model (`k_load` mapping or fixed-RPM/fixed-load policy),
- drivetrain efficiency,
- cut-in / cut-out assumptions,
- code commit hash and stamp schema version.

**Prototype data must not be used to tune polars, DS constants, regression goldens, or any frozen
input during the first comparison.** Any later recalibration uses the held-out protocol in
`docs/dynamic_stall_calibration_plan.md` and must be reported as a separate, post-hoc analysis.

## 6. Model outputs to compare

At each measured condition, run the frozen model with the measured wind speed and the measured load
(or measured RPM, if the generator holds speed) and compare:

1. mean shaft/electrical power [W],
2. mean CP (`P / (0.5 rho A U³)`),
3. mean RPM and tip-speed ratio,
4. where available, torque and its sign/phase behaviour,
5. start-up time to first power (qualitative unless instrumented).

The comparison must report absolute and relative errors per row, bias, RMSE, and coverage of the
uncertainty band. Predictions and measurements must be plotted with error bars, unfiltered.

## 7. Acceptance criteria (pre-registered)

Validation is considered **met** only if all of the following hold on the held-out measured rows:

| Metric | Criterion |
|---|---|
| Mean relative error in Cp | ≤ 15 % |
| RMSE in Cp | ≤ 0.03 absolute |
| Mean relative error in RPM | ≤ 10 % |
| Bias in Cp | ≤ 0.02 absolute |
| Coverage of 90 % model scenario band | ≥ 70 % of points |
| Sign of torque / power in all accepted rows | correct |
| Number of accepted rows per condition | ≥ 3 |

If any criterion fails, the result is reported as a **discrepancy**, not validation. No post-hoc
loosening of these thresholds is permitted without a dated amendment and a new held-out set.

## 8. Uncertainty propagation

- Each measured quantity carries Type A (repeatability) and Type B (calibration) uncertainty.
- Derived quantities (Cp, TSR, torque) use first-order propagation, or Monte Carlo with ≥ 10 000
  draws when non-linear.
- Model uncertainty is reported separately as a scenario range (not a confidence interval). It is
  not added to measurement uncertainty to manufacture agreement.

## 9. Reporting template

`scripts/compare_prototype.py` writes `data/prototype/results/comparison_<date>.json` with:

- `status`: `"not_yet_available"`, `"discrepancy"`, or `"validation_criteria_met"`;
- frozen-settings hash and file hashes;
- per-row measured/predicted values and errors;
- aggregate metrics and acceptance-criteria booleans;
- a plain-language statement of what the comparison does and does not establish.

## 10. Explicit non-claims

This plan does **not** claim:

- that the 2-D BEM model is experimentally validated;
- that agreement with `sharp-fsi` is validation;
- that literature comparisons are validation;
- that uncertainty intervals are validation;
- that counter-rotating array results are predictions of a real array;
- that prototype validation exists before the data and the pre-registered comparison do.
