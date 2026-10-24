# Prototype data protocol

Status: **no measured prototype data exist in this repository.** The directories
below are an empty, pre-registered container. Their presence is not evidence of
validation.

See `docs/prototype_validation_plan.md` for the full protocol (instrumentation,
test matrix, exclusions, frozen inputs, acceptance criteria).

## Directory layout

```
data/prototype/
  raw/         immutable sensor exports, calibration certificates, operator notes
  processed/   schema-validated CSVs written by scripts/import_prototype_data.py
  metadata/    geometry, instrumentation and frozen model settings (JSON)
  results/     comparisons written by scripts/compare_prototype.py
```

Do not hand-edit files in `raw/`. Do not silently delete excluded rows: keep
them in `processed/` with `accepted=false` and a non-empty `exclusion_reason`.

## Raw input CSV schema

One row per steady-state averaging window (or per start-up test). Times are UTC,
ISO 8601. Units are fixed; do not add unit suffixes to values.

| Column | Unit | Required | Meaning |
|---|---|---|---|
| `run_id` | — | yes | unique; stable across files |
| `date_utc` | ISO 8601 | yes | start of the averaging window |
| `operator` | — | yes | initials / name |
| `rotor_id` | — | yes | pre-assigned physical rotor identifier |
| `geometry_id` | — | yes | must match `metadata/geometry_<id>.json` |
| `wind_speed_mps` | m/s | yes | hub-height corrected mean |
| `wind_speed_uncertainty_mps` | m/s | yes | combined standard uncertainty |
| `rpm` | rev/min | yes | mean shaft speed |
| `rpm_uncertainty` | rev/min | yes | combined standard uncertainty |
| `electrical_power_W` | W | yes | mean electrical output |
| `electrical_power_uncertainty_W` | W | yes | combined standard uncertainty |
| `load_ohms` | ohm | yes | applied resistive load (or `nan` for MPPT) |
| `generator_model` | — | yes | make/model/serial |
| `drivetrain_efficiency_assumption` | — | yes | number in (0, 1] used to infer shaft power |
| `torque_Nm` | N·m | no | direct torque measurement; leave empty if unavailable |
| `torque_uncertainty_Nm` | N·m | no | required if `torque_Nm` is present |
| `air_density_kgm3` | kg/m³ | yes | from temperature/pressure/humidity |
| `temperature_C` | °C | yes | ambient |
| `pressure_hPa` | hPa | yes | ambient |
| `humidity_percent` | % | yes | relative humidity |
| `notes` | — | no | free text (quote if it contains commas) |
| `exclusion_reason` | — | no | pre-registered reason code/text; if present the row is `accepted=false` |

Derived columns added by the importer:

`shaft_power_W`, `torque_source` (`measured` / `inferred`), `tip_speed_mps`,
`tsr`, `cp`, `accepted` (boolean), and propagated uncertainties for each derived
quantity.

## Metadata files

- `metadata/geometry_<id>.json` — measured geometry. Template:
  `metadata/geometry_template.json`.
- `metadata/frozen_model_settings.json` — model inputs locked before measured
  power curves are inspected. Template:
  `metadata/frozen_model_settings.template.json`.
- `metadata/instrumentation.json` — sensor models, ranges, calibration dates.

## Commands

```bash
python3 scripts/import_prototype_data.py \
    --input data/prototype/raw/campaign_2026_11.csv \
    --geometry data/prototype/metadata/geometry_R0p6.json \
    --out data/prototype/processed/campaign_2026_11_processed.csv

python3 scripts/compare_prototype.py \
    --data data/prototype/processed/campaign_2026_11_processed.csv \
    --geometry data/prototype/metadata/geometry_R0p6.json \
    --settings data/prototype/metadata/frozen_model_settings.json \
    --out data/prototype/results/comparison_2026_11.json
```

The comparison reports one of `not_yet_available`, `discrepancy`, or
`validation_criteria_met`. Only the last may be described as validation, and
only for the tested envelope.
