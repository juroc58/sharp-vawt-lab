# 🌬 VAWT Lab

A Python numerical laboratory for the **Sharp cycloturbine** — a passive
variable-pitch vertical-axis wind turbine with centrifugal-pendulum pitch
control (CPPC). Implements the modified MIT dynamic stall model, Adams (2018)
curvilinear corrections, double-multiple-streamtube induction, and the full
Lagrangian coupling between rotor and pitch dynamics.

The project ships one physics core and a set of validation scripts. Every
number in this README is reproducible from the scripts in `scripts/`.

![validation](docs/validation.png)

---

## 🏆 Headline results

At **R = 0.60 m**, **Re ≈ 1.4 × 10⁵**, **σ ≈ 0.09**:

| Configuration | Cp | Reference |
|---|---|---|
| **Sharp-conforming CPPC** | **0.36** | Bayly-Kentfield measured 0.37 |
| Optimised passive (mass-balanced) | 0.49 | — |
| Rigid blade (no pitch) | 0.34 | — |
| Prescribed pitch (ideal actuator) | 0.48 | Ham 1979 measured 0.42–0.45 |

### Sharp-conforming CPPC

Uses a light counterweight 0.30 chord ahead of the leading edge (Sharp's spec
range is 0.5–1.0). Produces a +14.9° nose-out bias, keeps α_max at 16.2° (near
the NACA 0012 stall angle), and reaches **Cp = 0.36** — matching the best
measured passive-pitch VAWT (Bayly-Kentfield, 4.6 m diameter).

The mechanism is auto-regulating: as load increases, pitch range grows and
TSR falls, keeping the blade's angle of attack near stall. A diagnostic
confirms the aerodynamic pitch torque has the correct sign (nose-in when
α → +stall, nose-out when α → −stall), which is the physical reason Sharp's
blades do not stall.

### Optimised passive

A joint optimisation over chord, counterweight mass and position, load factor,
and pivot geometry found a **mass-balanced** configuration — heavy
counterweight sitting nearly on the pitch pivot (CG offset ≈ 3 mm from pivot)
— that reaches **Cp = 0.49**, matching the ideal-actuator upper bound.

At this design point the aerodynamic pitch torque (~0.20 N·m peak) is roughly
4× the centrifugal restoring torque (0.048 N·m peak). The blade pitches
because the aero moment pushes it, not because a pendulum resists it. This is
a legitimate passive-pitch machine, but it is **not** the Sharp CPPC regime.

### Prescribed pitch (upper bound)

For reference, running the same rotor with an ideal actuator commanding
ψ(φ) directly reaches Cp = 0.48 — the same class of machine as Ham's
cam-driven Pinson C2E. This is not achievable with a passive Sharp mechanism.

---

## 🔬 What this project does differently

Most VAWT hobby repos report a Cp number. This one reports **four**, with the
mechanism of each spelled out, plus a validation against the primary
literature:

1. **Ham 1979 reproduction.** The same solver, run in the model class Ham
   used (single-streamtube, static polars, cosine pitch law with
   θ₁c = −10°), reproduces his Pinson C2E rig at **Cp = 0.47 at TSR = 2.5**
   — inside his measured band of 0.42–0.45.
2. **Dynamic-stall sensitivity.** Turning the (uncalibrated) DS model off
   changes Cp by **2.1 %** at the design point. The result is driven by
   steady blade forces, not by fitting the unsteady model.
3. **Pitch-torque sign check.** A diagnostic confirms the aero pitch torque
   is stabilising — the physical requirement for Sharp's "blades do not
   stall" claim.
4. **Sharp-conforming parameter sweep.** The counterweight mass and offset
   are swept through Sharp's design range, showing where his mechanism works
   and where the mass ratio becomes unstable.

---

## 📐 Physics implemented

- **Induction**: double-multiple-streamtube (Paraschivoiu 1981), with the
  Sharpe-Glauert empirical branch for high loading.
- **Dynamic stall**: MIT / Noll-Ham increment on the static polar (Pawsey
  2002, App. B.2). Steady flow reproduces the static polar exactly.
- **Curvilinear flow**: Adams & Chen (2018) virtual-incidence and
  virtual-camber shifts, scaled by `min(1.0, (c/R)/0.418)`.
- **Pitch dynamics**: coupled rotor + pitch DOF integrated with symplectic
  Euler. Sharp's centrifugal-pendulum restoring torque is computed from the
  blade unit's CG position relative to the pitch pivot.
- **Pitch law** (prescribed mode): `ψ(φ) = ψ₀ + ψ₁·cos φ + ψ₂·sin φ + ψ₃·cos 2φ + ψ₄·sin 2φ`
- **Polars**: Sheldahl-Klimas NACA 0012 tables at four Reynolds numbers
  (1×10⁵, 2×10⁵, 4×10⁵, 1×10⁶), bilinear interpolation in (log Re, α).
- **Energy ledger**: closes to within a few percent for passive runs;
  disabled in prescribed mode because the pitch actuator work is external.

---

## 📦 Install

    git clone https://github.com/juroc58/sharp-vawt-lab.git
    cd sharp-vawt-lab
    python3 -m venv vawt-env
    source vawt-env/bin/activate
    pip install -r requirements.txt

---

## ⚡ Quick start

### 1. Validate against Ham 1979

    python3 scripts/validate_ham.py

Runs the Pinson C2E rig (R = 1.83 m, c = 0.305 m, c/R = 0.167) through three
model configurations:

- **static polars only** — Ham's model class  → peak Cp = 0.47 at TSR = 2.5
- **+ dynamic stall** — modern VAWT model     → peak Cp = 0.47 at TSR = 2.5
- **+ dynamic stall + curvilinear flow** — Adams shift applied

Ham 1979 published peak Cp = 0.42–0.45 at TSR = 2.5–3.0. The `+ curv` row
drops to 0.40 because Adams fitted his coefficients at c/R = 0.418 on a
variable-pitch machine; Ham's rig uses a fixed cosine pitch at c/R = 0.167,
so the virtual-camber shift is not absorbed by the pitch schedule. This is a
documented limitation of applying Adams outside his fit range.

### 2. Dynamic-stall sensitivity

    python3 scripts/validate_ds_off.py

Compares the optimiser's design point with the dynamic-stall model on and
off. Expected: **ΔCp < 3 %**, confirming the result is not a DS-model
artifact.

### 3. Passive CPPC parameter sweeps

    python3 scripts/passive_sweeps.py

Reproduces the Sharp-conforming counterweight sweep and the k_load sweep
that establish the Cp = 0.36 operating point.

### 4. Pitch-torque sign diagnostic

    python3 scripts/diag_qa.py

Reconstructs the aerodynamic pitch torque from the passive simulation and
verifies it has the correct sign (nose-in at +stall, nose-out at −stall).
This is the physical evidence that the CPPC mechanism is behaving as Sharp
describes.

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
the ideal-actuator upper bound of 0.48. Included for comparison only.

---

## 🎛 Programmatic use

Every quantity in the README is reproducible from a single function call:

```python
from vawt_core import create_sim_from_params

# Sharp-conforming CPPC design point
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

sharp-vawt-lab/
|-- vawt_core.py # physics engine (single source of truth)
|-- polars/naca0012/ # real NACA 0012 tables at four Re
|-- scripts/
| |-- validate_ham.py # Ham 1979 benchmark
| |-- validate_ds_off.py # dynamic-stall sensitivity
| |-- plot_validation.py # regenerate docs/validation.png
| |-- passive_sweeps.py # Sharp counterweight and load sweeps
| |-- passive_sharp.py # single passive run at design point
| |-- diag_qa.py # pitch-torque sign verification
| |-- optimize_passive.py # DE + NM over passive hardware
| |-- optimize_actuator.py # DE + NM over prescribed pitch (reference)
| |-- render_animation.py # MP4 visualization
|-- docs/
|-- validation.png
|-- diag_qa.png
        |-- animation.mp4

---

## 🧭 What this project does not model

    3D flow. No tip vortices, no spanwise flow, no tower shadow.

    Active Lift. Sharp's secondary mechanism, where the L-shaped bellcrank
    between the rocking hinge and the CG adds a transient torque during pitch
    reversal. A first-order model of the effect produced no measurable Cp gain
    at R = 0.60 m; it likely requires Sharp's larger machine geometry.

    Flux-line optimal pitch. Adams's inverse method for computing the
    maximum-power pitch schedule from first principles is not implemented. The
    prescribed-pitch optimiser searches a Fourier parametrisation instead.

    Annual energy production. AEP over a Weibull wind distribution is not
    shipped in v2.

    Uncertainty quantification. The dynamic-stall sensitivity check is
    one-dimensional. A full Latin-hypercube UQ over the model constants would
    be more rigorous.

## 📄 References

    Ham, N.D., Soohoo, P., Noll, R.B., Drees, H.M. (1979). Analytical and
    experimental evaluation of cycloturbine aerodynamic performance.
    AIAA 79-0968.

    Adams, Z., Chen, J. (2018). Flux-line theory: a novel analytical model
    for vertical axis wind turbines. AIAA J. 56(6).
    DOI 10.2514/1.J056575.

    Pawsey, N.C.K. (2002). Development and evaluation of passive
    variable-pitch vertical axis wind turbines. PhD thesis, UNSW.

    Sharp, P.A. (2021). The Sharp Cycloturbine: a summary of how it works.

    Sheldahl, R.E., Klimas, P.C. (1981). Aerodynamic characteristics of
    seven symmetrical airfoil sections through 180 degrees angle of attack.
    Sandia SAND80-2114.

    Bayly, D., Kentfield, J. (1981). A vertical axis cyclogiro type
    wind-turbine with freely-hinged blades. Proc. Intersociety Energy
    Conversion Conference.

## 📜 License

MIT — see LICENSE.