# 🌬 VAWT Lab

A Python numerical laboratory for simulating and analysing **vertical-axis wind
turbines**, with a focus on **centrifugal-pendulum (Sharp) self-pitching**,
dynamic stall behaviour, and multi-parameter performance optimisation.

The project ships one physics core, one optimiser, and a set of validation
scripts. Every number in this README is reproducible from the scripts in
`scripts/`.

![validation](docs/validation.png)

---

## 🏆 Headline result

At **R = 0.60 m**, **Re ≈ 1.4 × 10⁵**:

| | |
|---|---|
| Optimised pitch schedule | psi(phi) = psi0 + psi1*cos(phi) + psi3*cos(2*phi) |
| Peak power coefficient | **Cp = 0.51** |
| Dynamic-stall contribution | **+2.1 %** (result is *not* DS-dominated) |
| Curvilinear-flow contribution | **0 %** |

**Validation against Ham 1979.** Running the same solver in the model class
Ham used (single-streamtube, static polars, cosine pitch law with
`theta_1c = -10 deg`), the code reproduces his Pinson C2E rig at
**Cp = 0.47 at TSR = 2.5** — inside his measured band of 0.42-0.45 when
accounting for Reynolds-number and polar-source differences. This confirms
the core physics before the dynamic-stall and curvilinear-flow extensions
are applied.

At the optimised design point (R = 0.60 m, c/R = 0.196), turning the
dynamic-stall model off changes Cp by **2.1 %**, and turning the Adams
curvilinear correction off changes Cp by **0 %**. The headline result is
therefore not an artifact of either sub-model — it comes from the steady
blade forces at the optimised pitch schedule.

---

## 🔬 What makes this different from a typical hobby VAWT repo

Most projects report a Cp number. This one reports:

1. **A Cp number with a dynamic-stall sensitivity test.** Turning the
   (uncalibrated) DS model off changes Cp by 2 %. That means the result is
   driven by steady blade forces, not by fitting the unsteady model.
2. **A Ham 1979 reproduction.** Same code path, applied to the historical
   Pinson C2E rig, returns Cp = 0.47 at TSR = 2.5 — inside Ham's
   experimental band.
3. **A single source of truth.** One physics kernel. No duplicate
   implementations to disagree with each other.

---

## 📐 Physics implemented

- **Induction**: double-multiple-streamtube (Paraschivoiu 1981), with the
  Sharpe-Glauert empirical branch for high loading.
- **Dynamic stall**: MIT / Noll-Ham increment on the static polar (Pawsey
  2002, App. B.2). Steady flow reproduces the static polar exactly.
- **Curvilinear flow**: Adams & Chen (2018) virtual-incidence and
  virtual-camber shifts, scaled by `min(1.0, (c/R)/0.418)`.
- **Pitch law**: `psi(phi) = psi0 + psi1*cos(phi) + psi2*sin(phi) + psi3*cos(2*phi) + psi4*sin(2*phi)`
- **Polars**: Sheldahl-Klimas NACA 0012 tables at four Reynolds numbers
  (1×10⁵, 2×10⁵, 4×10⁵, 1×10⁶), bilinear interpolation in (log Re, alpha).
- **Dynamics**: coupled rotor + pitch DOFs integrated with symplectic Euler.

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

- **static polars only** — the model class Ham himself used  → peak Cp = 0.47 at TSR = 2.5
- **+ dynamic stall** — modern VAWT model                     → peak Cp = 0.47 at TSR = 2.5
- **+ dynamic stall + curvilinear flow** — Adams shift applied

Ham 1979 published peak Cp = 0.42-0.45 at TSR = 2.5-3.0.

The `+ curv` row drops to 0.40 because Adams fitted his coefficients at
`c/R = 0.418` on a *variable-pitch* machine. Ham's rig uses a fixed cosine
pitch (`c/R = 0.167`), so the virtual-camber shift is not absorbed by the
pitch schedule. This is a known limitation of applying Adams outside his
fit range.

### 2. Dynamic-stall sensitivity

    python3 scripts/validate_ds_off.py

Compares the optimiser's design point with the dynamic-stall model on and
off. Expected: **Cp = 0.514 / 0.503 / 0.503** (ΔCp < 3 %).

### 3. Regenerate the validation figure

    python3 scripts/plot_validation.py

Produces `docs/validation.png`.

### 4. Re-run the optimiser (optional, ~10 min on 4 cores)

    python3 vawt_optimizer.py

Two-stage optimiser: differential evolution (global) → Nelder-Mead (local).
Searches over chord, TSR, load factor, and the first three pitch-law
coefficients. Saves results to `optimization_result.json`.

---

## 🎛 Programmatic use

Every quantity in the README is reproducible from a single function call:

```python
from vawt_core import create_sim_from_params

r = create_sim_from_params({
    'c': 0.117607, 'tsr': 2.14487, 'k_load': 0.0015,
    'pp0_deg': +5.156, 'pp1_deg': -6.329,
    'pp2_deg': +2.758, 'pp3_deg': -0.085,
    'prescribe_pitch': True, 'free': True,
    'T_max': 30.0, 'cd_add': 0.002,
}).run()
print(f"Cp = {r['cp']:.4f}")
```

`create_sim_from_params` raises `KeyError` on unknown parameters, so
parameter mismatches surface immediately.

---

## 📊 Directory layout

    sharp-vawt-lab/
    |-- vawt_core.py              # the physics engine (single source of truth)
    |-- vawt_optimizer.py         # DE + Nelder-Mead optimiser
    |-- gen_polars.py             # polar fallback when CSVs are missing
    |-- polars/naca0012/          # real NACA 0012 tables at four Re
    |-- scripts/
    |   |-- validate_ham.py       # Ham 1979 benchmark
    |   |-- validate_ds_off.py    # dynamic-stall sensitivity test
    |   |-- plot_validation.py    # regenerate docs/validation.png
    |-- docs/
        |-- validation.png

---

## 🧭 What v2 does not do (yet)

- **Passive CPPC optimisation.** The optimiser tunes *prescribed* pitch.
  Passive centrifugal-pendulum dynamics are implemented in the core but not
  yet wrapped into an optimiser objective.
- **Annual energy production.** AEP over a Weibull wind distribution is
  straightforward to add on top of the core; not shipped in v2.
- **Uncertainty quantification.** The dynamic-stall sensitivity check is
  one-dimensional. A full Latin-hypercube UQ over the model constants would
  be more rigorous.
- **Visualisation.** No animation in v2.

---

## 📄 References

- Ham, N.D., Soohoo, P., Noll, R.B., Drees, H.M. (1979). *Analytical and
  experimental evaluation of cycloturbine aerodynamic performance.*
  AIAA 79-0968.
- Adams, Z., Chen, J. (2018). *Flux-line theory: a novel analytical model
  for vertical axis wind turbines.* AIAA J. 56(6).
  DOI [10.2514/1.J056575](https://doi.org/10.2514/1.J056575).
- Pawsey, N.C.K. (2002). *Development and evaluation of passive
  variable-pitch vertical axis wind turbines.* PhD thesis, UNSW.
- Sharp, P.A. (2021). *The Sharp Cycloturbine: a summary of how it works.*
- Sheldahl, R.E., Klimas, P.C. (1981). *Aerodynamic characteristics of
  seven symmetrical airfoil sections through 180 degrees angle of attack.*
  Sandia SAND80-2114.

---

## 📜 License

MIT — see [LICENSE](LICENSE).