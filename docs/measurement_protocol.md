# Prototype Measurement Protocol

## Equipment

- **Rotor**: 1/3 scale Sharp cycloturbine prototype (R = 0.906 m, H = 1.353 m, N = 3 blades)
- **Generator**: Hoverboard motor (rectified)
- **Electrical**: 12 V battery, dump load
- **Wind measurement**: Anemometer at hub height

## Logging

- Sample rate: 1 Hz
- Output format: `data/measured_template.csv` with columns
  `Time, Wind_Speed_m_s, Wind_Direction_deg, RPM, DC_Voltage_V, DC_Current_A, Power_W`

## Data Cleaning

- Reject rows where wind direction changes > 30° in 10 seconds
  (indicates turbulence / non-representative inflow)

## Validation Steps

1. Load the prototype preset:

   ```python
   from sharp_vawt import create_sim_from_params
   from vawt_presets import PRESETS

   sim = create_sim_from_params(PRESETS["prototype_1_3"])
   result = sim.run()
   print(f"Model Cp at TSR 2.5: {result['cp']:.4f}")
   ```

2. Compare the model Cp against the measured power coefficient:

   $$
   C_{p,\text{measured}} = \frac{P_{\text{measured}}}{\frac{1}{2} \rho U^3 A}
   $$

   where $A = 2 R H$ is the swept area, $\rho = 1.225$ kg/m³, and $U$ is the
   measured wind speed.

3. Confirm the measured Cp is within the model's predicted band for the same
   TSR. If the measured Cp deviates by more than ~10 %, investigate:
   - Wind-direction filtering (see Data Cleaning)
   - Anemometer calibration at hub height
   - Generator/dump-load efficiency
   - Rotor alignment and blade pitch setting
