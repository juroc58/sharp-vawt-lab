# Calibration Plan for Passive CPPC VAWT

## Purpose

This document describes the measurement protocol and calibration procedure for validating the passive centrifugal-pendulum pitch control (CPPC) VAWT model against experimental data. The goal is to calibrate the five key model parameters:

1. `tau_rev` - induction lag time constant
2. `ds_Tf` - dynamic stall separation lag
3. `tip_loss_multiplier` - finite-span correction multiplier
4. `cm_scale` - pitching moment scale factor
4. `cd_add` - parasitic drag coefficient

## Required Measurements

### Minimum Measurement Set

The following measurements are required at a single wind speed (U = 6 m/s):

1. **Rotor speed vs. time** - High-frequency (≥100 Hz) rotor angular velocity ω(t) for at least 10 revolutions after transients decay
2. **Blade pitch angle vs. azimuth** - Blade pitch angle ψ(φ) over at least one full revolution, measured at ≥100 points per revolution
3. **Wind speed** - Free-stream velocity U measured simultaneously with rotor data
3. **Rotor geometry** - Complete geometric parameters (R, c, H, N, ar, sp, mb, mc, dcw, bias)

### Optional Enhanced Measurements

For more comprehensive calibration:

1. **Torque vs. azimuth** - Aerodynamic torque Q(φ) over one revolution
2. **Multiple wind speeds** - Repeat at U = 4, 6, 8, 10 m/s
3. **Multiple geometries** - Test at least two different rotor geometries (e.g., different AR, solidity)

## Measurement Protocol

### Test Setup

1. **Rotor mounting** - Rigidly mount rotor on low-friction bearings with torque sensor
2. **Wind tunnel** - Use low-turbulence wind tunnel (I < 1%) or atmospheric boundary layer facility
3. **Instrumentation** - Encoder for rotor position, potentiometer/encoder for blade pitch, pitot tube for wind speed
4. **Data acquisition** - Synchronized sampling at ≥100 Hz for all channels

### Test Procedure

1. **Geometry verification** - Measure and record all geometric parameters
2. **Zero calibration** - Zero all sensors with rotor locked
3. **Wind-on transient** - Start wind tunnel, record rotor spin-up from rest
4. **Steady-state recording** - After transients decay (≥10 revolutions), record ≥5 revolutions of data
4. **Wind-off decay** - Shut off wind, record rotor decay to validate inertia/damping
5. **Repeat** - Repeat steps 3-4 at each target wind speed

### Data Format

Save measurements as CSV with the following columns:

```csv
time_s,azimuth_deg,omega_radps,blade1_pitch_deg,blade2_pitch_deg,blade3_pitch_deg,wind_mps,torque_nm
```

For multi-speed tests, include a column for `wind_mps` setpoint.

### File Naming Convention

```
measured_{geometry_name}_{U}mps_{YYYYMMDD}.csv
```

Example: `measured_scaleup_6mps_20261024.csv`

### Data Template

A template CSV is provided at `data/measured_template.csv` with header only.

## Calibration Procedure

### Parameters to Calibrate

| Parameter | Physical Meaning | Nominal Range | Calibration Target |
|-----------|-----------------|---------------|-------------------|
| `tau_rev` | Induction lag (rev) | 0.05 - 0.20 | Rotor speed transient |
| `ds_Tf` | Separation lag (convective times) | 1.5 - 4.5 | Pitch angle history |
| `tip_loss_multiplier` | Finite-span correction | 0.85 - 1.15 | Steady-state rotor speed |
| `cm_scale` | Pitching moment scale | 0.0 - 1.0 | Pitch angle history |
| `cd_add` | Parasitic drag | 0.001 - 0.005 | Rotor speed / torque |

### Calibration Method

1. **Define objective function** - Weighted sum of squared errors between measured and simulated:
   - Rotor speed history (transient and steady-state)
   - Blade pitch angle vs. azimuth
   - Aerodynamic torque (if measured)

2. **Optimization** - Use bounded least-squares (e.g., `scipy.optimize.least_squares`) with bounds from table above

3. **Uncertainty quantification** - Bootstrap resampling of measurement data to estimate parameter confidence intervals

### Validation

After calibration, validate against held-out data (different wind speed or geometry):
- Predict steady-state rotor speed at new U
- Compare pitch angle history
- Compare power coefficient Cp

### Reporting

Report calibrated parameters with 95% confidence intervals:
```
Parameter    Calibrated Value    95% CI           Units
tau_rev      0.123               [0.110, 0.136]   rev
ds_Tf        2.84                [2.45, 3.23]     convective times
tip_loss_mult 1.02               [0.98, 1.06]     -
cm_scale     0.87                [0.79, 0.95]     -
cd_add       0.0032              [0.0021, 0.0043] -
```

## TODO: Real Measurements

- [ ] Acquire wind-tunnel data for scale-up geometry at U = 6 m/s
- [ ] Acquire wind-tunnel data for sharp-inspired geometry at U = 6 m/s  
- [ ] Acquire multi-speed data for scale-up geometry
- [ ] Acquire blade pitch angle history (encoder on pitch axis)
- [ ] Acquire aerodynamic torque data (torque sensor on shaft)

## Using the Calibration Script

Once measurement data is available, run:

```bash
python scripts/calibrate_passive.py \
    --data data/measured_scaleup_6mps_20261024.csv \
    --geometry scaleup \
    --bounds tau_rev:0.05,0.2 ds_Tf:1.5,4.5 tip_loss_multiplier:0.85,1.15 cm_scale:0,1 cd_add:0.001,0.005
```

The script will output calibrated parameters, confidence intervals, and validation plots.