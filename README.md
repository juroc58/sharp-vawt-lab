# 🌬 VAWT Lab

A Python numerical laboratory for the **Sharp cycloturbine** — a passive
variable-pitch vertical-axis wind turbine with centrifugal-pendulum pitch
control (CPPC). Implements a lag-based dynamic-stall increment on the static
polar (loosely after the Noll–Ham formulation), Adams (2018) curvilinear
corrections, double-multiple-streamtube induction, and the full Lagrangian
coupling between rotor and pitch dynamics.

The project ships one physics core and a set of validation scripts. Every
number in this README is reproducible from the scripts in `scripts/`, except
where a paragraph explicitly cites an external study (those numbers are
quoted, not reproduced here).

**Related external work.** A companion project,
[`juroc58/sharp-fsi`](https://github.com/juroc58/sharp-fsi), is a from-scratch
2-D discrete-vortex + fluid-structure-interaction code for the same blade
section. It shares this project's geometry, mass properties and pitch
equation, so it is a **model-class cross-check, not an independent
validation**: it can catch implementation errors in the 2-D aerodynamics, but
it cannot validate those shared assumptions. Its comparison report is not
vendored in this archive, so no agreement figure is reproduced here.

![validation](docs/validation.png)

![ham curve](docs/ham_curve.png)

---

## 🏆 Headline results

### Small-rotor regime (R = 0.60 m, Re ≈ 1.4 × 10⁵, σ ≈ 0.11)

<!-- BEGIN GENERATED: headline_table_small -->
| Configuration | Cp | 90 % CI | Reference |
|---|---|---|---|
| **Sharp-inspired CPPC** | **0.10** | [0.003, 0.17] | scenario range, not precision (see note) |
| Optimised passive (mass-balanced) | **0.23** | [0.052, 0.29] | fixed optimiser point |
| Prescribed pitch (ideal actuator) | 0.50 | — | upper bound |
| Ham 1979 reproduction | **0.49** | [0.46, 0.51] | fixed design point |
<!-- END GENERATED: headline_table_small -->

**Read the Sharp-inspired interval as two branches, not a precision bar.**
The nominal design point (finite-span multiplier 1.0) gives Cp = 0.104;
below a multiplier of about 0.78 the same rotor collapses to Cp ≈ 0.003
(0.0039 at 0.75, 0.0030 at 0.70). The UQ samples put 16 % of this
distribution on the collapsed branch, which is why the 90 % interval
reaches 0.003. `scripts/scan_tip_loss.py` reproduces the scan. The
optimised-passive distribution has a smaller collapsed tail (2 %); the
scale-up has none.

### Scale-up regime (R = 2.72 m, Re ≈ 5.1 × 10⁵)

<!-- BEGIN GENERATED: headline_table_large -->
| Configuration | Cp | 90 % CI | Reference |
|---|---|---|---|
| **Scaled-up passive (R = 2.72 m)** | **0.37** | [0.30, 0.42] | ~62 % of Betz |
<!-- END GENERATED: headline_table_large -->

The confidence intervals come from Saltelli sampling over eleven
uncalibrated inputs (`scripts/uncertainty.py`). All Sharp-machine
numbers use the generalized Prandtl finite-span correction; the Ham
reproduction is run without one and without the curvature correction, using
double-multiple-streamtube induction and Ham's cosine pitch law. See the
[Uncertainty](#-uncertainty) section for the parameter ranges and histograms.

**Convention.** The headline Cp for each machine is the **UQ mean with
tip loss ON**. Ham is the exception: his model class has no tip loss, so
the reproduction is run without one. Deterministic design-point values
quoted in the body text are labelled as such; the table gives the UQ mean
over eleven uncertain inputs. The UQ study is a scenario analysis, not
a calibrated error bar: the finite-span multiplier alone spans ±30 %, and
both small-rotor distributions cross a collapse threshold (see below).

For Ham, the body text quotes a peak of 0.470 from
`scripts/plot_ham_curve.py` (static polars, TSR = 2.5). The headline table
quotes the UQ mean 0.49 [0.46, 0.51], essentially the same point: the
anchor uses Ham's model class (DS off, no curvature, no tip loss) and
samples the induction-lag and strut-drag constants.

### Sharp-inspired CPPC

This design follows Sharp's **mechanism** (centrifugal-pendulum pitch
control) but not his **geometry**. It uses a light counterweight 0.30
chords ahead of the leading edge; Sharp's published range is 0.5–1.0.
At R = 0.60 m, with the finite-span correction on and the UQ spread
over eleven uncalibrated inputs, the anchor (c = 0.14 m, m_c = 0.002 kg,
d_cw = 0.30c) reaches **0.10 [0.003, 0.17]**.

**The mechanism fails inside Sharp's own parameter range.** With a
Sharp-like counterweight mass (m_c = 0.008 kg) and `balance = 0` so the
offset is actually applied, every offset at or ahead of the pivot
collapses: Cp = 0.0113 at 0.1 chords, 0.0082 at 0.3, 0.0063 at 0.5 and
0.0028 at 0.8, with the blade against the stops 16–36 % of each
revolution. Offsets from 0 to −0.4 chords run (Cp 0.13–0.24), best at
−0.3 chords. The baseline where `balance = 1` solves the counterweight
position from the equilibrium (d_cw = −0.31, behind the pivot) also runs
cleanly: Cp = 0.23, TSR = 2.14, no stops. That is not Sharp's CPPC
regime. The light-counterweight anchor (m_c = 0.002 kg) survives at
Cp = 0.10, but it sits near the collapse threshold; the Sharp-like mass
pushes the offset designs over it.

`scripts/passive_sharp.py` sweeps counterweight mass and offset. The
offset sweep is meaningful only with `balance = 0` (the default
`balance = 1` solves d_cw from the equilibrium and would ignore the swept
value); the script now sets this explicitly.

The mechanism is still auto-regulating at the anchor design point: as load
increases, pitch range grows and TSR falls, keeping the blade's angle
of attack near stall. A diagnostic confirms the aerodynamic pitch
torque has the correct sign (nose-in when α → +stall, nose-out when
α → −stall), which is the stabilising property Sharp's CPPC mechanism
relies on. Note that the blade does still reach stall at high wind
speeds — see the AEP section below.

### Optimised passive

A joint optimisation over chord, counterweight mass and position, load factor,
and pivot geometry found a configuration with a small arm ratio and a
relatively heavy counterweight. On the current polars its fixed design
point evaluates to Cp = 0.28;
the UQ mean over eleven inputs is **0.23 [0.05, 0.29]**. The optimised
arm ratio is **ar = 0.260**, which sits at the lower bound of the ar range
rather than on the upper bound; the UQ spread is **0.24**, dominated by the
finite-span multiplier (S₁ = 0.81), and 2 % of samples fall on the collapsed
branch. The optimiser snapshot in `scripts/optimization_passive.json`
predates the polar revision and was not re-run, so 0.28 should be read as
"the stored design point on the new polars", not as a fresh optimum.

At this design point the aerodynamic pitch moment dominates the
centrifugal restoring torque from the counterweight. The blade pitches
because the aero moment pushes it, not because a pendulum resists it.
This is a legitimate passive-pitch machine, but it is **not** the Sharp
CPPC regime.

### Scaled-up passive design

Extending the joint optimiser to radius R ∈ [0.6, 3.0] m now finds
**R = 2.72 m** (chord 0.386 m, AR 10.5). With the finite-span correction
enabled *inside the optimiser*, the optimum sits at **H/R = 1.49**, i.e.
H/D = 0.75. The fixed design point evaluates to Cp = 0.39 on the current
polars; the UQ mean is **0.37 [0.30, 0.42]** (62 % of the Betz limit).
The optimiser snapshot in `scripts/optimization_scaleup.json` (Cp = 0.43)
predates the polar revision and was not re-run.

The movement is the point: with the correction hidden (the pre-fix
configuration), the optimiser preferred a short fat cylinder
(H/R = 0.5, AR = 3.2). Once the aspect-ratio cost is visible, it
prefers a tall thin one (H/R = 1.5, AR = 10.5). Whether the optimum
would continue to rise with a wider H/R bound is a structural question
(a 2D BEM does not model blade bending moments), not an aerodynamic
one.

### Prescribed pitch (upper bound)

For reference, running the same rotor with an ideal actuator commanding
ψ(φ) directly reaches 0.50 -- the same class of machine as Ham's
cam-driven Pinson C2E. This is not achievable with a passive Sharp mechanism.

---

### ⚠ Important: Two different geometries compared

**aep.png (left panel)** and **validation.png** show Cp(TSR) curves for **two different geometries**:

| Panel | Geometry | R | H | c | AR | Mode |
|-------|----------|---|---|---|-----|-------|
| **aep.png (left)** | Scale-up passive CPPC | 2.72 m | 4.06 m | 0.386 m | 10.5 | Passive CPPC, fixed rpm |
| **validation.png** | Model design scaled to R = 1.83 m (not Ham's rig) | 1.83 m | 1.22 m | 0.359 m | 3.4 | Prescribed pitch, no tip loss |

The **aep.png left panel** shows our scale-up passive CPPC design (R=2.72m, AR=10.5) with free pitch.
The **validation.png** panel is this project's prescribed-pitch design point
scaled rigidly to R = 1.83 m (c and H scale with R). It is a **scaled**
comparison, not a like-for-like Ham geometry: H/R = 0.667 here versus 0.749
on Ham's rig. The exact Ham geometry (R = 1.83 m, H = 1.37 m, c = 0.305 m,
AR 4.5) is the subject of `ham_curve.png` and `scripts/validate_ham.py`.

These are **different machines** -- do not directly compare their Cp values.

---

## 🌀 Active Lift

Sharp (2021) describes a secondary mechanism — "Active Lift" — in which the
blade unit's CG moving radially inward on the upwind pass and outward on the
downwind pass produces a Coriolis torque on the rotor. He estimates it
contributes about **10 %** to torque at his scale.

### What `diag_active_lift.py` measures

The diagnostic script runs the same prescribed pitch schedule at two pivot
configurations: with the arm at its real radial position (`ar` = 0.312) and
with `ar` = 0 (pure pitch, no radial CG motion). The difference isolates the
Coriolis contribution from the ordinary cyclic-pitch benefit.

**Result:** The Coriolis contribution at the scale-up design is
**ΔCp = +0.0069 (+1.8 %)**. It is 64 % of the +2.8 % dynamic-pitch benefit
but only 1.8 % of Cp, because the baseline prescribed-pitch schedule
already captures most of the cyclic-pitch gain. The diagnostic script
reports the measured values each time it runs.

**The diagnostic does not measure Sharp's original CPPC machine** (R = 0.60 m,
AR = 2.86). That geometry runs only at a low TSR (≈ 1.38) with the raw
finite-span correction and collapses below a multiplier of about 0.78, so
the scale-up design (R = 2.72 m, AR = 10.5) is used to get a clean,
healthy free-running operating point.

**Sharp's own estimate of +10 %** is about five times larger than this
model's **1.8 %**. The Coriolis term is a real but secondary contribution
here, not a primary mechanism.

## 📈 Annual energy production

![aep](docs/aep.png)

Power curves integrated against a Weibull wind distribution (k = 2.0,
mean U = 6 m/s, cut-in 3 m/s, cut-out 25 m/s). See
`scripts/compute_aep.py` and `scripts/compute_aep_rigid_fair.py`.

### CPPC vs a fair rigid baseline

The comparison that matters is against a **fixed-pitch rigid blade at its
own optimal pitch and load**, not a blade locked at zero pitch inheriting
the passive machine's load. `scripts/compute_aep_rigid_fair.py` runs that
comparison at both design points:

| Geometry | AR | Passive CPPC | Best rigid | Gain |
|---|---|---|---|---|
| **Sharp-inspired (R = 0.60 m)** | 2.86 | **162.6 kWh/yr** | none (does not spin) | **n/a** |
| **Scale-up (R = 2.72 m)** | 10.5 | **17,266 kWh/yr** | 14,450 kWh/yr | **+19.5 %** |

Sharp's published claim is **25–30 % more energy than a fixed-blade
rotor**. The model gives **+19.5 %** at the scale-up geometry, where a
rigid blade actually works. This is the closest agreement with Sharp in
the repo, and it required the fair baseline to surface.

The two rows describe different regimes. At AR 2.86 no fixed-pitch
configuration produces a steady rotation at all: uncapped induced drag
(Cd_i ≈ 0.11 at this AR) kills fixed-pitch operation, so the CPPC
mechanism is the difference between a working machine and a dead one, not
an efficiency gain. At AR 10.5, a rigid blade at ψ₀ = +5°, k_load = 4.0
reaches Cp = 0.32 with no pitching at all; the passive CPPC machine
reaches 0.38.

**Caveat.** Both geometries were optimised *for* CPPC. The comparison is
fair in the sense of "same rotor, same wind, only the pitch mechanism
differs" — it is not a claim that rigid VAWTs are useless at other
geometries. A rotor designed from scratch for fixed-pitch operation would
likely do better than 14 450 kWh/yr at AR 10.5.

The two scale-up AEP values quoted in this README (17,266 kWh/yr here and
16,843 kWh/yr in the fixed-rpm table below) come from slightly different
setups: the rigid comparison sweeps the k_load grid and picks 4.0 with
`T_max = 30 s`, while the steady table uses the stored operating point
k_load = 4.164 with `T_max = 25 s`. The 2.5 % difference is the
evaluation setup, not a physics change.

### Fixed-rpm penalty

For the scale-up design (R = 2.72 m, peak Cp ≈ 0.39):

<!-- BEGIN GENERATED: aep_steady -->
| Strategy | AEP | Capacity factor |
|---|---|---|
| **Passive k_load (variable speed)** | **16843 kWh/yr** | **12.8 %** |
| Fixed-rpm generator | 11838 kWh/yr | 9.0 % |
<!-- END GENERATED: aep_steady -->

The passive machine produces **1.42× more energy** than the same rotor on
a fixed-rpm generator because the k_load·ω² torque tracks the wind's
power curve: the rotor speed adjusts so the tip-speed ratio stays near
its optimum at every wind speed. A fixed-speed generator drifts far from
the design point as the wind varies and only operates near peak
efficiency in a narrow window around its design wind speed.

This is the physical claim Sharp's paper makes for CPPC. The passive
mechanism adapts to wind speed without any external control.

## 📊 Uncertainty

![uncertainty](docs/uncertainty.png)

Eleven uncertain inputs are sampled: ten model constants that come from the
source papers but were not fitted to this specific machine, plus the
finite-span multiplier (a model-form uncertainty, not a constant). Saltelli
sampling (N = 64, 1536 runs per anchor) propagates that uncertainty through
each headline case and yields first-order (S₁) and total-order (Sₜ) Sobol
indices:

<!-- BEGIN GENERATED: uq_params -->
| Parameter | Low | High | Source of uncertainty |
|---|---|---|---|
| `cd_add` | 0.001 | 0.005 | strut / interference drag |
| `ds_Tf` | 1.5 | 4.5 | separation lag (default 3.0) |
| `ds_Tv` | 3.0 | 9.0 | vortex-lift lag (default 6.0) |
| `ds_Ta` | 0.05 | 0.15 | attached-flow lag (default 0.10) |
| `ds_Kv` | 0.25 | 0.75 | vortex-lift strength (default 0.50) |
| `tau_rev` | 0.05 | 0.20 | induction lag (default 0.10 rev) |
| `e_osw` | 0.85 | 0.95 | Oswald efficiency for finite-span |
| `c_scale_override` | 0.30 | 0.60 | Adams shift strength |
| `tip_loss_multiplier` | 0.70 | 1.30 | multiplier on generalized Prandtl f_ar (<1 = low-AR under-correction, >1 = less tip loss) |
| `ds_Knc` | 0.5 | 1.5 | apparent-mass lift multiplier (k_nc) |
| `arm_cd` | 0.5 | 1.5 | arm drag coefficient multiplier (Geometry) |
<!-- END GENERATED: uq_params -->

The 90 % confidence width is **0.047 Cp** for Ham, **0.123** for the
scale-up, **0.169** for Sharp-inspired CPPC and **0.242** for optimised
passive. These are much wider than the intervals quoted in v3.3.0 because
the old Saltelli sampler double-scaled its inputs (see CHANGELOG); the
ranges below are the honest ones.

**The finite-span multiplier dominates the three tip-loss anchors.** Its
first-order Sobol index is 0.58 for Sharp-inspired CPPC, 0.81 for
optimised passive and 0.83 for the scale-up (total-order 0.78 / 0.92 /
0.88). Ham is the exception: its model class has tip loss off, so
`tau_rev` dominates there. This is a model-form uncertainty, not a fitted
constant: the raw generalized Prandtl factor is multiplied by a value in
[0.70, 1.30], which covers both the residual low-AR under-correction
(< 1) and less tip loss (> 1). At AR 10.5 the raw factor is already 0.86,
so applying a ±30 % band there is conservative; the scale-up Sobol row
should be read that way.

**The small-rotor distributions cross a collapse threshold.** Below a
multiplier of about 0.78 the Sharp-inspired rotor cannot sustain rotation:
`scripts/scan_tip_loss.py` gives Cp = 0.104 at 1.00, 0.069 at 0.80,
0.0039 at 0.75 and 0.0030 at 0.70. The UQ samples put **16 % of the
Sharp-inspired distribution and 2 % of the optimised-passive distribution
on that collapsed branch** (Cp < 0.02). The 90 % interval [0.003, 0.17] is
therefore a **scenario range** — "runs at ~0.15 with little tip loss,
collapses to ~0.003 with strong tip loss" — not a precision estimate. The
scale-up (AR 10.5) has no collapsed samples; its minimum is 0.273.

`tau_rev` (induction lag) dominates Ham's uncertainty (S₁ = 0.86), with
`cd_add` second (S₁ = 0.17). Ham's raw samples span 0.451–0.512, wider
than the old README claimed (0.464–0.474); the 90 % interval is
[0.459, 0.506].

Every sample in all four anchors produced a finite, positive Cp, so no
outlier was excluded (`n_fail = 0`). The lowest Sharp-inspired sample is
0.0018, not a negative or NaN result.

To reproduce: `python3 scripts/uncertainty.py --saltelli --saltelli-n 64
--saltelli-second-order` (~20 min on 4 cores; the result is cached in
`.uq_cache/` so an interrupted run resumes).

## 🌪️ Turbulent-wind sensitivity

![aep_turbulent](docs/aep_turbulent.png)

10 realisations per wind speed, turbulence intensity I = 12 %,
length scale L = 30 m (von Kármán spectrum with √0.47 variance scaling). See
`scripts/compute_aep_turbulent.py`.

<!-- BEGIN GENERATED: aep_turbulent -->
| | AEP | CF |
|---|---|---|
| Steady wind | 16965.7 kWh/yr | 12.91 % |
| Turbulent wind (I = 12 %) | 18226.7 kWh/yr | 13.87 % |
| **Effect** | **+7.4 %** | **+0.96 pp** |
<!-- END GENERATED: aep_turbulent -->

### Why turbulence gives a gain, not a loss

The AEP is `∫ P(U) · pdf(U) dU`. Two convex nonlinearities in that
integral produce a mean power above the power at the mean wind speed:

1. **Cube-bias.** For any fluctuating signal, `E[U³] > (E[U])³`
   (Jensen's inequality applied to `x³`). At I = 12 %, this alone
   contributes `3·I² ≈ +4.3 %` — independent of any physics.
2. **Cp(U) convexity.** The steady Cp rises with wind speed (Reynolds
   effect), so turbulence samples a convex range and
   `E[Cp(U)] > Cp(E[U])`. In the model this contributes the remaining
   ~3 percentage points of the +7.4 % net effect.

Both effects are captured by the model because it uses polars
across four Reynolds numbers (synthetic — see `airfoil_polars/README.md`).

### Caveat

The 2D BEM captures the mathematical gain plus the inertial and
induction losses, but not 3D wake-turbulence interaction or high-
frequency dynamic-stall hysteresis. Real turbines typically lose
2–8 % of the perfect-turbine gain to these effects, so the realistic
net effect is probably within ±3 % of the steady-wind AEP. The result
should be read as **"the CPPC mechanism is robust under turbulence"**
rather than "turbulence improves the machine."

### Which parameter drives the spread?

Saltelli Sobol sensitivity indices (N = 64, 1536 runs per anchor) for each
anchor. Runs in ~20 min on 4 cores (`scripts/uncertainty.py --saltelli
--saltelli-n 64 --saltelli-second-order`).

<!-- BEGIN GENERATED: uq_sobol -->
| Anchor | Dominant S₁ parameter | S₁ | Total-order Sₜ |
|---|---|---|---|
| Ham 1979 reproduction | `tau_rev` | **+0.86** | +0.84 |
| Sharp-inspired CPPC | `tip_loss_multiplier` | **+0.58** | +0.77 |
| Optimised passive | `tip_loss_multiplier` | **+0.81** | +0.92 |
| Scale-up R = 2.72 m | `tip_loss_multiplier` | **+0.83** | +0.88 |
<!-- END GENERATED: uq_sobol -->

**The finite-span multiplier drives the three tip-loss anchors.** Direct
runs at the nominal parameters (`scripts/scan_tip_loss.py`):

| Multiplier | 0.70 | 0.75 | 0.80 | 0.90 | 1.00 | 1.20 | 1.30 |
|---|---|---|---|---|---|---|---|
| Cp, Sharp-inspired | 0.003 | 0.004 | 0.069 | 0.089 | 0.104 | 0.164 | 0.174 |
| Cp, scale-up | 0.302 | 0.322 | 0.340 | 0.370 | 0.393 | 0.423 | 0.423 |

The Sharp-inspired branch is discontinuous between 0.75 and 0.80; the
scale-up is smooth because its raw factor is already high. That is why the
small-rotor UQ is a scenario range while the scale-up UQ behaves like a
normal parameter interval.

**Physical reading:**

- **`ham_1979`**: prescribed pitch bypasses the dynamic-stall model, so the
  surviving uncertainty is the wake/induction relaxation (`tau_rev`,
  S₁ = 0.86) plus `cd_add` (0.17). This is the cleanest single-parameter
  result.
- **`sharp_cppc`**: multiplier S₁ = 0.58 (total-order 0.78), with `ds_Tf`
  (0.08) and `ds_Knc` (0.06) minor; the bimodal output inflates the
  total-order index.
- **`optimised_passive`**: multiplier S₁ = 0.81 (total-order 0.92), then
  `cd_add` (0.10) and `ds_Tf` (0.09).
- **`scaleup`**: multiplier S₁ = 0.83 (total-order 0.88), then
  `c_scale_override` (0.06), `cd_add` (0.04) and `tau_rev` (0.04). Unlike
  the v3.3.0 result, the scale-up is not dominated by the Adams shift: the
  wider multiplier band overwhelms it.

**Actionable conclusion.** The single most valuable measurement is a
low-aspect-ratio finite-span/tip-loss calibration for the actual rotor
geometry; it would replace the ±30 % multiplier band that dominates every
anchor. A strut-drag measurement (`cd_add`) and a wake-induction relaxation
measurement (`tau_rev`) are the next most useful.

## 🔬 What this project does differently

Most VAWT hobby repos report a Cp number. This one reports **four**, with the
mechanism of each spelled out, plus a validation against the primary
literature:

1. **Ham 1979 reproduction (partial).** The same solver, run in the
   model class Ham used (double-multiple-streamtube induction, static
   polars, no curvature correction, cosine pitch
   law with θ₁c = −10°), peaks at **Cp = 0.470 at TSR = 2.5** (a single
   deterministic run; the UQ mean in the headline table is 0.49
   [0.46, 0.51]) — about 8 % above his measured band of 0.42–0.45. The
   **shape** of the curve does not match: the model over-predicts by
   ~0.03 at TSR 2, is closest around the peak, over-predicts the
   high-TSR tail (0.22 vs 0.12 at TSR 4), and with the Adams curvature
   correction active it under-predicts at TSR 3+ (see
   `docs/ham_curve.png`). The peak reproduction is consistent with
   running without a finite-span correction; the shape is a residual
   limitation of the model class, not something the peak number captures.
2. **Dynamic-stall sensitivity depends on the regime.** At the
   prescribed-pitch design point, turning the (uncalibrated) DS model off
   changes Cp by **≈1.8 %**; the `scripts/validate_ds_off.py` tolerance is
   4 %. For the **passive** machine the dependence is much larger:
   Cp drops from ~0.18 to ~0.03 when DS is disabled (~80 %), because the
   passive rotor operates close to static stall. The UQ study samples the
   DS constants for that reason; it is not a cosmetic correction.
3. **Pitch-torque sign check.** `scripts/diag_qa.py` reconstructs the aero
   pitch torque from the pitch equation and **exits non-zero** if it is not
   restoring at the stall extremes — the physical requirement for Sharp's
   "blades do not stall" claim. The pass/fail logic is pinned by
   `tests/test_diag_qa.py` with synthetic histories, so a sign regression
   fails the suite.
4. **Sharp-inspired parameter sweep.** The counterweight mass and offset
   are swept through Sharp's design range, showing where his mechanism works
   and where the mass ratio becomes unstable.

---

## 📐 Physics implemented

A full derivation of every equation in `vawt_core.py`, with source-paper
references, is in [`docs/derivation.md`](docs/derivation.md).


- **Induction**: double-multiple-streamtube (Paraschivoiu 1981), with the
  Sharpe-Glauert empirical branch for high loading.
- **Dynamic stall**: lag-based increment on the static polar, loosely after
  the Noll–Ham formulation (Pawsey 2002, App. B.2); the implementation is
  not the MIT model. Steady flow reproduces the static polar exactly.
- **Curvilinear flow**: Adams & Chen (2018) virtual-incidence and
  virtual-camber shifts, scaled by `min(1.0, (c/R)/0.418)`.
- **Pitch dynamics**: coupled rotor + pitch DOF integrated with symplectic
  Euler. Sharp's centrifugal-pendulum restoring torque is computed from the
  blade unit's CG position relative to the pitch pivot.
- **Pitch law** (prescribed mode): `ψ(φ) = pp0 + pp1·cos(φ + ph) + pp2·cos 2(φ + ph) + pp3·sin 2(φ + ph)` with `ph` = `pp_ph_deg`. There is no sin φ term and no fourth harmonic.
- **Polars**: NACA 0012 tables at four Reynolds numbers
  (1×10⁵, 2×10⁵, 4×10⁵, 1×10⁶). Attached-flow Cl/Cd come from
  NeuralFoil 0.3.3 (XFOIL-trained); deep stall is a flat-plate model
  anchored to Sheldahl–Klimas trends. Cm is a synthetic Abbott &
  von Doenhoff trend, not measured. Bilinear interpolation in (log Re, α).
  See `airfoil_polars/README.md` and `airfoil_polars/provenance.json`.
- **Energy ledger**: closes to within a few percent for passive runs;
  disabled in prescribed mode because the pitch actuator work is external.
- **Pitch-moment coupling**: the blade pitching moment `Cm(α, Re)` from the
  polar contributes a hub reaction torque `Qa = c̄·Cm·½ρU²c` that enters the
  rotational energy balance as `Tsum += Tk − Qa`. The Cm table is a smooth
  synthetic trend (near zero attached, about −0.05 through the stall band),
  not measured data; it crosses zero at α = 90° and 180°.
- **Turbulence synthesis**: von Kármán spectrum with FFT-based phase
  randomisation. Wind speed standard deviation is `σU = I · U` (turbulence
  intensity times mean wind speed), and the spectrum integral matches the
  target variance exactly (verified numerically). Length scale `L = 30 m`
  is used for the AEP turbulence study; different length scales change the
  temporal correlation but not the marginal distribution.

---

## 📦 Install

    git clone https://github.com/juroc58/sharp-vawt-lab.git
    cd sharp-vawt-lab
    python3 -m venv vawt-env
    source vawt-env/bin/activate
    pip install -r requirements.txt          # runtime only
    pip install -r requirements-dev.txt      # + test tools (pytest, timeout)

---

## ⚡ Quick start

### 0. Run the test suite

    pip install -r requirements-dev.txt
    pytest                      # full suite (fast + slow validation)
    pytest -m "not slow"        # fast only, for local iteration
    pytest --cov                # with coverage (kernel is numba-jitted)

`tests/` pins the solver with golden-Cp regression cases
(`tests/test_regression.py`), a pitch-torque sign check, the Ham/DS
verdict logic, and factory validation. The validation scripts below also
exit non-zero on failure, so they can be wired into CI directly.

### 1. Validate against Ham 1979

    python3 scripts/validate_ham.py

Runs the Pinson C2E rig (R = 1.83 m, c = 0.305 m, c/R = 0.167) through three
model configurations:

- **static polars only** — Ham's model class  → peak Cp = 0.470 at TSR = 2.5
- **+ dynamic stall** — modern VAWT model     → peak Cp = 0.480 at TSR = 2.5
- **+ dynamic stall + curvilinear flow** — Adams shift applied → 0.405

These are single deterministic runs. The headline table's Ham UQ mean of
0.49 samples the eleven uncertain model inputs about this point.

Ham 1979 published peak Cp = 0.42–0.45 at TSR = 2.5–3.0. The `+ curv` row
drops to 0.40 because Adams fitted his coefficients at c/R = 0.418 on a
variable-pitch machine; Ham's rig uses a fixed cosine pitch at c/R = 0.167,
so the virtual-camber shift is not absorbed by the pitch schedule. This is a
documented limitation of applying Adams outside his fit range.

### 2. Dynamic-stall sensitivity

    python3 scripts/validate_ds_off.py

Compares the prescribed-pitch design point with the dynamic-stall model on
and off. Measured: **ΔCp ≈ 1.8 %** (the script's tolerance is 3 %; the test
allows 4 %), confirming the prescribed result is not a DS artifact. The
passive machine is very different (~80 %); see the Uncertainty section.

### 3. Passive CPPC parameter sweeps

    python3 scripts/passive_sweeps.py

Reproduces the Sharp-inspired counterweight sweep and the k_load sweep
behind the operating points discussed above.

### 4. Pitch-torque sign diagnostic

    python3 scripts/diag_qa.py

Reconstructs the aerodynamic pitch torque from the passive simulation and
verifies it has the correct sign (nose-in at +stall, nose-out at −stall),
exiting non-zero on failure. This is the physical evidence that the CPPC
mechanism is behaving as Sharp describes.

### 5. Regenerate the validation figure

    python3 scripts/plot_validation.py

Produces `docs/validation.png`.

### 6. Optimise passive hardware (optional, ~15 min on 4 cores)

    python3 scripts/optimize_passive.py

Two-stage DE + Nelder-Mead search over chord, load, counterweight mass and
position, arm ratio, pivot position, and pitch bias. Writes
`scripts/optimization_passive.json`.

### 7. Optimise prescribed pitch (reference)

    python3 scripts/optimize_actuator.py

Same optimiser structure but with a prescribed Fourier pitch law. Produces
the ideal-actuator upper bound of 0.50. Included for comparison only.

---

## 🎛 Programmatic use

Every quantity in the README is reproducible from a single function call:

```python
from vawt_core import create_sim_from_params

# Sharp-inspired CPPC design point
r = create_sim_from_params({
    'R': 0.60, 'H': 0.40, 'N': 3, 'c': 0.14,
    'ar': 0.50, 'sp': 0.25,
    'mb': 0.010, 'xbcg': 0.20,
    'mc': 0.002, 'dcw': 0.30,
    'balance': 0, 'bias_deg': 0.0,
    'prescribe_pitch': False,
    'cd_add': 0.002,
    'use_dynamic_stall': True, 'use_flow_curvature': True, 'use_dmst': True,
    'win_deg': 45.0, 'cb': 2e-5, 'mu_c': 3e-4,
    'free': True, 'T_max': 40.0,
    'k_load': 0.0025, 'tsr': 2.14,
}).run()
print(f"Cp = {r['cp']:.4f}   TSR_eq = {r['tsr_eq']:.2f}   "
      f"pitch = [{r['pitch_min']:+.1f}, {r['pitch_max']:+.1f}] deg")

```

`create_sim_from_params` raises `KeyError` on unknown parameters, so
parameter mismatches surface immediately.

---

## 📊 Directory layout

```text
sharp-vawt-lab/
|-- vawt_core.py                 # physics engine (single source of truth)
|-- pyproject.toml               # packaging + pytest config
|-- airfoil_polars/naca0012/             # synthetic NACA 0012 polars; see airfoil_polars/README.md
|-- scripts/
|   |-- build_readme.py          # regenerate README numeric blocks
|   |-- validate_ham.py          # Ham 1979 benchmark
|   |-- validate_ds_off.py       # dynamic-stall sensitivity
|   |-- plot_validation.py       # regenerate docs/validation.png
|   |-- plot_ham_curve.py        # regenerate docs/ham_curve.png
|   |-- passive_sweeps.py        # Sharp counterweight and load sweeps
|   |-- passive_sharp.py         # single passive run at design point
|   |-- diag_qa.py               # pitch-torque sign verification (pass/fail)
|   |-- diag_active_lift.py      # passive / rigid / zero-pitch decomposition
|   |-- compute_aep.py           # AEP, passive vs fixed-rpm
|   |-- compute_aep_rigid_fair.py# fair rigid-blade AEP baseline
|   |-- compute_aep_turbulent.py # turbulent-wind AEP
|   |-- uncertainty.py           # LHS over eight uncalibrated constants
|   |-- spearman_sensitivity.py  # rank-correlation sensitivity
|   |-- optimize_passive.py      # DE + NM over passive hardware
|   |-- optimize_actuator.py     # DE + NM over prescribed pitch (reference)
|   |-- optimize_scaleup.py      # joint R + hardware optimisation
|   |-- render_animation.py      # MP4 visualization
|-- tests/                       # pytest suite (fast + slow markers)
|   |-- test_regression.py       # golden-Cp regression cases
|   |-- test_diag_qa.py          # pitch-torque sign check
|   |-- test_validation.py       # Ham + DS verdict logic
|   |-- test_physics.py          # tip-loss / c_scale / ledger
|   |-- test_factory.py          # key validation, removed-key guards
|   |-- test_geometry.py         # geometry + mass balance
|   |-- test_readme_numbers.py   # README vs scripts/*.json drift
|   |-- regenerate_golden.py     # helper to refresh golden Cp
|-- docs/                        # figures + derivation.md
|-- README.md
```

## 🧭 What this project does not model

    3D flow. No tip vortices, no spanwise flow, no tower shadow.
  A generalized Prandtl finite-span factor is available via
  `use_tip_loss=True`; it reduces lift by about 40 % at AR 2.9 and 15 %
  at AR 10.5. The optimisation results are 2D upper bounds. At the
  current scale-up optimum (AR 10.5) the raw factor is f_ar ≈ 0.86, so
  the correction barely moves Cp; it matters most at low aspect ratio,
  where it moved the optimum away from a short, fat rotor (AR ≈ 3).

    Active Lift (detail). The Coriolis contribution from the blade unit's
    radial CG motion is present in the model via the relative-motion
    term in the blade's air velocity. The current diagnostic isolates it
    at the scale-up point (+1.8 % of Cp; see the Active Lift section).
    Earlier versions of this README quoted a +7 % figure from a
    rocking-velocity-suppression experiment and a +0.0002 Cp net-energy
    figure from an integral of the Lagrangian `sumL` term; both are
    retracted and no script currently produces them. The specific
    L-shaped bellcrank geometry of Sharp's later machines is not modelled
    separately.

Pitching moment (Cm ≠ 0). The polar tables include a smooth synthetic Cm
trend based on Abbott & von Doenhoff behaviour, not measured values. The
passive CPPC mechanism relies on the centre-of-pressure shift in stall,
which in reality is driven by the pitching moment coefficient Cm. The
model uses that trend through stall, but it cannot claim to reproduce a
measured centre-of-pressure excursion. See `airfoil_polars/README.md`
for the full provenance.

Flux-line optimal pitch. Adams's inverse method for computing the
maximum-power pitch schedule from first principles is not implemented. The
prescribed-pitch optimiser searches a Fourier parametrisation instead.


Uncertainty interactions. The Saltelli study (N=64, second-order) computes
full Sobol S1/ST/S2 indices including parameter interactions. See `scripts/uncertainty_results.json` and the Uncertainty section.

Model-form uncertainty. The model combines literature sources developed
for different machines and flight regimes (lag-based Noll–Ham-style
dynamic stall, Adams curvilinear flow, DMS induction, generalized Prandtl
finite-span). The component models each have their own validation ranges,
and the combined 2D BEM prediction error from structural mismatches
between them — i.e., model-form uncertainty — is not separately
quantified. This is the dominant uncertainty for absolute Cp predictions
and is not captured by the parameter-level UQ study, which only propagates
parameter ranges through a fixed model structure.

Finite-span correction. The correction uses the generalized Prandtl form
f_ar = 1/(1 + 1.8/(e*AR)) (k=1.8), with no default floor. The formula is
an empirical fit to low-AR wind-turbine data; the classical Prandtl form
with k=2.0 under-corrects at low AR. The UQ study multiplies f_ar by
`tip_loss_multiplier` in [0.70, 1.30] to cover both the residual
low-AR under-correction (multiplier < 1) and less tip loss (> 1). See
`vawt_core.py`, `docs/derivation.md`, and `scripts/scan_tip_loss.py`.

## 📄 References

- Ham, N.D., Soohoo, P., Noll, R.B., Drees, H.M. (1979). Analytical and experimental evaluation of cycloturbine aerodynamic performance. AIAA 79-0968.
- Adams, Z., Chen, J. (2018). Flux-line theory: a novel analytical model for vertical axis wind turbines. AIAA J. 56(6). DOI 10.2514/1.J056575.
- Pawsey, N.C.K. (2002). Development and evaluation of passive variable-pitch vertical axis wind turbines. PhD thesis, UNSW.
- Sharp, P.A. (2021). The Sharp Cycloturbine: a summary of how it works.
- Sheldahl, R.E., Klimas, P.C. (1981). Aerodynamic characteristics of seven symmetrical airfoil sections through 180 degrees angle of attack. Sandia SAND80-2114. *(Anchors the deep-stall trend; the attached-flow Cl/Cd in this repo come from NeuralFoil, not from digitised SAND tables.)*
- Bayly, D., Kentfield, J. (1981). A vertical axis cyclogiro type wind-turbine with freely-hinged blades. Proc. Intersociety Energy Conversion Conference.

## 📖 How to cite

If you use this software, please cite it as:

    @software{sharp_vawt_lab_2026,
      author       = {juroc58},
      title        = {sharp-vawt-lab: a 2D BEM solver for the Sharp cycloturbine},
      version      = {3.3.1},
      year         = {2026},
      url          = {https://github.com/juroc58/sharp-vawt-lab},
      license      = {MIT},
    }

A machine-readable citation is available in [`CITATION.cff`](CITATION.cff)
(`citation-cff` / `cffconvert` can convert it to BibTeX, EndNote, etc.).

## 📜 License

MIT — see LICENSE.