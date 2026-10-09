# Physics derivation of `vawt_core.py`

This document walks through every physics module in the SHARP cycloturbine
core, gives the governing equations as they appear in the source, and
references the paper each equation is taken from. It is intended for a
reader who has never seen the code before and wants to verify that the
implementation matches the published literature.

**Notation.** All quantities are in SI units unless noted. Vector
components are given in the rotating blade frame: $\hat{t}$ is the
tangential direction (positive in the direction of blade motion), $\hat{r}$
is the outward radial direction, and $\hat{z}$ is the rotor axis. Blade
azimuth $\varphi$ is measured from $+x$ (wind direction), so the upwind
half of the rotor is $\cos\varphi < 0$.

---

## 0. Sign conventions

- Pitch angle $\psi > 0$ means the blade is rocked **nose-out** (leading
  edge away from the hub). The code uses this throughout.
- Angle of attack $\alpha$ is positive when the relative flow arrives from
  the outer face of the blade (upwind pass). It is negative on the
  downwind pass.
- Rotor angular velocity $\omega > 0$ means counter-clockwise viewed from
  above.
- Azimuth $\varphi = \pi$ is upwind (blade moving perpendicular to the
  wind, inward); $\varphi = 0$ is downwind.

These conventions match Sharp (2021) Fig. 2 and Pawsey (2002) Fig. 1.2.
Ham (1979) uses $\psi = 0$ at upwind, which is a 90° phase shift from this
code. All test scripts that reproduce Ham's results apply the shift
explicitly.

---

## 1. Rotor geometry and the pitch degree of freedom

Each blade rocks about a pivot located at distance $a_r$ from the support-arm
root, and at a chordwise position $s_p$ from the leading edge. The pivot
radius from the rotor axis is

$$
R_p = R - a_r
\tag{1.1}
$$

The quarter-chord point is offset from the pivot by

$$
x_q = 0.25 c - s_p
\tag{1.2}
$$

in the chord direction, and the mid-chord by $x_m = 0.5c - s_p$. The blade-unit
centre of mass (blade + counterweight) is at chordwise offset

$$
x_g = \frac{m_b x_b + m_c x_{cw}}{m_b + m_c}
\tag{1.3}
$$

where $x_b$ is the blade CG relative to the pivot and $x_{cw}$ is the
counterweight CG. This $x_g$ is the parameter that controls the entire
passive mechanism: **the equilibrium bias angle is $\arctan(|x_g|/a_r)$**.
Sharp (2021) targets a "few degrees" of bias, which requires
$|x_g| \lesssim 0.1 a_r$.

The blade-unit moment of inertia about the pivot is

$$
I_p = m_b\!\left(\frac{c^2}{12} + x_b^2 + a_r^2\right)
      + m_c\!\left(x_{cw}^2 + a_r^2\right)
\tag{1.4}
$$

Equations (1.1)–(1.4) are computed once in `CycloturbineSim._resolve_balance`
at object construction.

---

## 2. Blade kinematics — the velocity triangle

At instant $t$, blade $k$ (with $k = 0, 1, \dots, N-1$) is at azimuth

$$
\varphi_k = \theta + \frac{2\pi k}{N}
\tag{2.1}
$$

where $\theta$ is the rotor angle (time integral of $\omega$). The blade's
quarter-chord point moves in the rotor frame with tangential and radial
offsets from the pivot given by

$$
s_t = -x_q \cos\psi_k - a_r \sin\psi_k, \qquad
s_r = -x_q \sin\psi_k + a_r \cos\psi_k
\tag{2.2}
$$

The tangential and radial components of the quarter-chord velocity are

$$
v_t = \omega R_p + (\omega - \dot\psi_k)\, s_r, \qquad
v_r = -(\omega - \dot\psi_k)\, s_t
\tag{2.3}
$$

where the term $(\omega - \dot\psi_k)$ is the blade's *rocking-frame* angular
rate — the difference between the rotor rate and the blade's own pitch rate.

The apparent wind components in the blade frame are then

$$
u_1 = U_f \sin\varphi_k + v_t, \qquad
u_2 = U_f \cos\varphi_k - v_r
\tag{2.4}
$$

where $U_f$ is the local induced velocity (Section 5). The relative speed and
inflow angle are

$$
W = \sqrt{u_1^2 + u_2^2}, \qquad
\varphi_f = \mathrm{atan2}(u_2, u_1)
\tag{2.5}
$$

and the angle of attack is

$$
\alpha = \mathrm{wrap}(\varphi_f + \psi_k)
\tag{2.6}
$$

with $\mathrm{wrap}(a) = \mathrm{atan2}(\sin a, \cos a)$ to keep
$\alpha \in (-\pi, \pi]$.

Equation (2.6) is the sign convention at the heart of the code. The `+`
sign is required by the definition of $s_t, s_r$ in (2.2). Getting this
sign wrong changes the direction of the aerodynamic pitch moment by 180°
and destroys the passive mechanism. This bug was present in early versions
of the code and cost significant debugging time (see Section 12).

---

## 3. Static polar database

The polar lookup is bilinear on $(\log \mathrm{Re}, \alpha)$. Given a query
$(\log \mathrm{Re}, \alpha)$, the code finds the bracketing indices
$(j_0, j_1)$ in the Re grid and $(i_0, i_1)$ in the angle grid, computes
interpolation weights $w_r, w_a$, and returns

$$
C_L = \sum_{a \in \{0,1\}} \sum_{r \in \{0,1\}}
      C_{L,\,j_r i_a}\, (1 - w_a)^{1-a}\, w_a^{a}\,
                        (1 - w_r)^{1-r}\, w_r^{r}
\tag{3.1}
$$

and similarly for $C_D$. The Reynolds number at each blade station is

$$
\mathrm{Re} = \frac{W c}{\nu}
\tag{3.2}
$$

with $\nu = 1.5\times 10^{-5}$ m²/s (air at sea level, 15 °C).

The database source is the Sheldahl & Klimas (1981) report SAND80-2114,
tabulated for NACA 0012 at four Reynolds numbers
($10^5, 2\times10^5, 4\times10^5, 10^6$), spanning $\alpha \in [-180°, 180°]$.

---

## 4. Adams (2018) curvilinear flow corrections

In curvilinear flow the blade sees a chordwise velocity gradient that
differs from a wind-tunnel test. Adams & Chen (2018) model this as a
virtual-incidence shift plus virtual-camber lift and drag increments. The
effectiveness parameter is

$$
\psi_{\text{eff}} = \frac{\lambda^2}{1 + \lambda^2}, \qquad
\lambda = \frac{\omega R}{U_f}
\tag{4.1}
$$

The Adams corrections (his Table 2) are applied to the input angle and
output coefficients:

$$
\alpha_{\text{eff}} = \alpha + \psi_{\text{eff}}\,\Delta\alpha_{vi}\, s_c
\tag{4.2}
$$

$$
\Delta C_L = \psi_{\text{eff}}\,\Delta C_{L,vc}\, s_c, \qquad
\Delta C_D = \psi_{\text{eff}}\,\Delta C_{D,cf}\, s_c
\tag{4.3}
$$

with literature values

$$
\Delta\alpha_{vi} = -0.0742~\text{rad},\quad
\Delta C_{L,vc} = -0.402,\quad
\Delta C_{D,cf} = +0.0156
\tag{4.4}
$$

The scale factor $s_c = \min(1,\, (c/R)/0.418)$ accounts for the fact that
Adams fitted his coefficients at $c/r = 0.418$. For the R = 0.60 m machine
with $c = 0.14$ m, $s_c = 0.56$; for the Ham 1979 rig with $c/r = 0.167$,
$s_c = 0.40$. The cap at 1.0 prevents extrapolation beyond Adams's fit
range for high-solidity rotors. This cap was added after discovering that
the uncapped version over-corrected the Ham geometry and drove the Cp
negative (see Section 12).

---

## 5. Double-multiple-streamtube induction

The rotor disk is divided into $n_b = 180$ azimuthal streamtube bins. Each
blade updates the induction factor of the bin it crosses. The upwind half
of the rotor uses the freestream directly; the downwind half uses the
decelerated wake from the corresponding upwind bin.

**Upwind pass** ($\cos\varphi_k < 0$):
$$
U_{\text{ch}} = U_\infty, \qquad
U_f = U_\infty (1 - a_k)
\tag{5.1}
$$

**Downwind pass** ($\cos\varphi_k > 0$):
$$
U_{\text{ch}} = \max\!\left(0.05\, U_\infty,\,
                          U_\infty (1 - 2\,a_{\text{tab}})\right), \qquad
U_f = U_{\text{ch}} (1 - a_k)
\tag{5.2}
$$

Here $a_{\text{tab}}$ is the induction factor in the corresponding upwind
bin, and $a_k$ is the current blade's own induction.

The thrust coefficient estimated from blade forces is

$$
C_T = \frac{4 N F_x}{4\pi\rho R H \max(|\cos\varphi|, 0.1)\, U_{\text{ch}}^2}
\tag{5.3}
$$

where $F_x$ is the streamwise force on the blade. The target induction
factor is obtained from the momentum balance:

$$
a_{\text{tgt}} = \begin{cases}
0 & C_T \le 0\\
\frac{1}{2}\!\left(1 - \sqrt{1 - C_T}\right) & C_T \le 0.879\\
1 - \dfrac{1.816 - C_T}{4(\sqrt{1.816} - 1)} & C_T > 0.879
\end{cases}
\tag{5.4}
$$

The third branch is the Sharpe / Glauert empirical fit for heavily-loaded
rotor operation (Pawsey 2002 §5.3, based on the correction proposed by
Sharpe 1990). The transition at $C_T = 0.879$ is continuous.

The induction factor is relaxed toward its target with a first-order lag:

$$
a_k^{n+1} = a_k^n + \min\!\left(1,
             \frac{\Delta t\, \omega}{2\pi\, \tau_{\text{rev}}}\right)
             \left(a_{\text{tgt}} - a_k^n\right)
\tag{5.5}
$$

where $\tau_{\text{rev}} = 0.1$ revolutions is the induction relaxation
time (Paraschivoiu 1981 uses a similar value). This models the finite time
required for the wake to adjust to a change in blade loading.

---

## 6. MIT dynamic-stall increment

The dynamic-stall model follows the modified MIT formulation (Pawsey 2002
App. B.2, Noll & Ham 1982), but is written as an **increment on the static
polar** so that in steady flow the output exactly reproduces the static
coefficients.

Three physical state variables (plus two bookkeeping values) are
carried per blade:

- $\alpha_{\text{lag}}$ — the attached-flow-lagged angle (a low-pass filter
  on the geometric angle)
- $f$ — the separation parameter ($f=1$ fully attached, $f=0$ fully separated)
- $v$ — the vortex-lift contribution

The Kirchhoff separation function is

$$
f_{\text{static}}(\alpha) = 1 - \left(\frac{C_L(\alpha)}{C_{L,\max}}\right)^2
\tag{6.1}
$$

The lagged angle evolves as

$$
\dot\alpha_{\text{lag}} = \frac{\alpha - \alpha_{\text{lag}}}{\tau_\alpha},
\qquad \tau_\alpha = T_\alpha \frac{c}{W}
\tag{6.2}
$$

The separation parameter lags toward its static value:

$$
\dot f = \frac{f_{\text{static}}(\alpha_{\text{lag}}) - f}{\tau_f},
\qquad \tau_f = T_f \frac{c}{W}
\tag{6.3}
$$

The vortex lift is driven by the rate of change of $f$:

$$
\dot v =
\begin{cases}
\dfrac{v_{\mathrm{target}} - v}{\tau_v} & \dot f < 0 \;\;(\text{separation growing})\\
-\dfrac{v}{\tau_{\mathrm{conv}}} & \text{otherwise}
\end{cases}
\tag{6.4}
$$

with $v_{\text{target}} = \mathrm{sign}(\alpha)\,(1-f)\,|C_L(\alpha_{\text{lag}})|$
and $\tau_v = T_v c / W$, $\tau_{\text{conv}} = 15 c / W$.

The lift and drag are reconstructed from the separation parameter:

$$
C_L = C_L(\alpha_{\text{lag}})
      + (f - f_{\text{static}}(\alpha_{\text{lag}}))
        \left(C_{L,\text{att}} - C_{L,\text{sep}}\right)
\tag{6.5}
$$

$$
C_D = C_D(\alpha_{\text{lag}})
      + (f_{\text{static}} - f) \left(C_{D,\text{sep}} - C_D(\alpha_{\text{lag}})\right)
\tag{6.6}
$$

with $C_{L,\text{sep}} = \sin 2\alpha$ (flat-plate), $C_{D,\text{sep}} = 1.98\sin^2\alpha$.
In steady flow $f = f_{\text{static}}$ and the increment vanishes, so
$C_L = C_L(\alpha)$ exactly.

Finally the vortex lift is added:

$$
C_L \mathrel{+}= v, \qquad
C_D \mathrel{+}= 0.5\,|v|\,|\sin\alpha|
\tag{6.7}
$$

Time constants used: $T_f = 3.0$, $T_v = 6.0$, $T_\alpha = 0.1$ (all in
convective time units $c/W$). These are literature-typical values, **not
fitted to data** for the SHARP geometry.

The apparent-mass lift (Theodorsen) is added once by the caller:

$$
C_{L,nc} = \frac{\pi}{2}\,\frac{c}{W}\,\dot\alpha
\tag{6.8}
$$

---

## 7. Blade forces and aerodynamic pitch moment

With the coefficients computed, the blade-element forces per spanwise
station are:

$$
F_t = q\, C_L \sin\varphi_f - q\, C_D \cos\varphi_f
\tag{7.1}
$$

$$
F_r = q\, C_L \cos\varphi_f + q\, C_D \sin\varphi_f
\tag{7.2}
$$

where $q = \tfrac12 \rho W^2 c\,H$ is the dynamic pressure times the
element area. The apparent-mass forces act at the mid-chord:

$$
F_{t,nc} = q\, C_{L,nc} \sin\varphi_f, \qquad
F_{r,nc} = q\, C_{L,nc} \cos\varphi_f
\tag{7.3}
$$

The aerodynamic torque about the rotor axis and the aerodynamic pitch
moment about the pivot are

$$
T_{\text{aero}} = (R_p + s_{r,c})\,F_t - s_{t,c}\,F_r
\tag{7.4}
$$

$$
Q_{\text{aero}} = s_{t,c}\,F_r - s_{r,c}\,F_t
\tag{7.5}
$$

where $(s_{t,c}, s_{r,c})$ is the offset of the centre of pressure from the
pivot. The centre of pressure moves aft in stall:

$$
x_{\text{cp}} = \left(0.25 + 0.25\,(1 - f)\right) c - s_p
\tag{7.6}
$$

In attached flow $f = 1$ and the CoP is at the quarter-chord (the pivot
location), so $Q_{\text{aero}} = 0$. In stall the CoP moves to mid-chord
and $Q_{\text{aero}}$ becomes a strong nose-down moment. **This is the
physical mechanism that stabilises Sharp's blades near stall** — the
aerodynamic pitch moment grows rapidly as $\alpha$ approaches stall,
pushing the blade back below the stall angle before the lift collapses.
The sign check in `scripts/diag_qa.py` verifies this behaviour on every
build.

---

## 8. Sharp CPPC pitch dynamics

The pitch DOF is coupled to the rotor DOF through the Lagrangian. Let
$x_g$ be the blade-unit CG offset from the pivot (§1). The centrifugal
force acting on the CG projects onto the pitch axis as

$$
M_{\text{cf}} = -M \omega^2 R_p\,(x_g \cos\psi + a_r \sin\psi)
\tag{8.1}
$$

This is the Sharp (2021) restoring torque. It grows with $\omega^2$ and
with the CG offset. The $a_r \sin\psi$ term is the dominant restoring
contribution for small $x_g$; the $x_g \cos\psi$ term provides the
equilibrium bias that fixes the blade's neutral pitch angle. When
$x_g = 0$ the mechanism has no bias but still has a restoring torque
proportional to $a_r \sin\psi$; when $x_g$ is large the blade locks
against the stop before it can reach equilibrium.

The total pitch torque is the sum of aerodynamic, centrifugal,
damping, friction, spring, and hard-stop contributions:

$$
Q_{\text{tot}} = Q_{\text{aero}}
                  - c_b\dot\psi - k_c\psi - Q_{\text{fric}}
                  + Q_{\text{stop}}
\tag{8.2}
$$

Note: $Q_{\text{tot}}$ here contains the aerodynamic and dissipative
torques only. The centrifugal restoring term $M_{\text{cf}}$ from
eq. (8.1) is added separately in the generalized force $X_k$ (eq. 8.6).

The friction torque depends on the centrifugal load on the pivot
bearing:

$$
Q_{\text{fric}} = \mu_c\, M\,\omega^2 (R_p + s_r)\, r_b\,\tanh(\dot\psi/\epsilon)
\tag{8.3}
$$

with $\epsilon = 0.5$ rad/s smoothing the sign function near zero.
The stop torque is

$$
Q_{\text{stop}} = \begin{cases}
-k_s(\psi - \psi_{\text{lim}}) - c_s\dot\psi & \psi > \psi_{\text{lim}}\\
-k_s(\psi + \psi_{\text{lim}}) - c_s\dot\psi & \psi < -\psi_{\text{lim}}\\
0 & \text{otherwise}
\end{cases}
\tag{8.4}
$$

The pitch equation is written in a form that includes the rotor
angular acceleration:

$$
\ddot\psi_k = \frac{(I_p + M R_p s_r)\,\dot\omega + X_k}{I_p}
\tag{8.5}
$$

where the generalized force $X_k$ contains all the torque terms in (8.2)
plus the centrifugal coupling:

$$
X_k = M R_p s_t \omega^2 + Q_{\text{tot}}
\tag{8.6}
$$

Equation (8.5) is the correct Lagrange form. It reduces to
$\ddot\psi = Q_{\text{tot}}/I_p$ when the rotor is at constant speed,
and to a coupled response when the rotor accelerates.

---

## 9. Rotor dynamics

The rotor is driven by the total blade torque and slowed by the external
load. The effective rotor inertia includes the blades' own translational
inertia and their coupling to the pitch DOF:

$$
J_{\text{eff}} = J_{\text{hub}} + \sum_k M R_p^2
                  \left(1 - \frac{M s_{r,k}^2}{I_p}\right)
\tag{9.1}
$$

The rotor angular acceleration is

$$
\dot\omega = \frac{T_{\text{sum}} - k_{\text{load}}\omega^2
              - Q_{\text{arm}} - \Sigma_L}{J_{\text{eff}}}
\tag{9.2}
$$

where $T_{\text{sum}}$ is the sum of blade torques, $k_{\text{load}}\omega^2$
is the external load (a natural match for a water-pumping or resistive load),
$Q_{\text{arm}} = k_{\text{arm}}\omega^2$ is the support-arm drag torque, and

$$
\Sigma_L = \sum_k \left[ M R_p s_{t,k} \dot\psi_k (2\omega - \dot\psi_k)
           - \left(1 + \frac{M R_p s_{r,k}}{I_p}\right) X_k \right]
\tag{9.3}
$$

is the coupling term. In prescribed-pitch mode $\Sigma_L$ is set to zero,
because the actuator work is external and not part of the rotor's
angular momentum budget.

---

## 10. Energy ledger

Six energy channels are tracked by the code for diagnostic audit:

| Channel | Expression | Meaning |
|---|---|---|
| `E_in` | $\int \sum_k (T_k \omega + Q_k \dot\psi_k)\,dt$ | aerodynamic power into the rotor + pitch DOFs |
| `E_shaft` | $\int Q_{\text{shaft}}\,\omega\,dt$ | useful mechanical output to load |
| `E_arm` | $\int Q_{\text{arm}}\,\omega\,dt$ | strut drag losses |
| `E_vis` | $\int c_b \dot\psi^2\,dt$ | pivot viscous damping |
| `E_cou` | $\int Q_{\text{fric}}\,\dot\psi\,dt$ | pivot Coulomb friction |
| `E_stop` | $\int c_s \dot\psi^2\,dt$ | hard-stop damping |

The residual is

$$
\text{resid} = \frac{E_{\text{in}} - (E_{\text{shaft}} + E_{\text{arm}}
                + E_{\text{vis}} + E_{\text{cou}} + E_{\text{stop}}
                + \Delta E_{\text{kin}})}{|E_{\text{in}}|}
\tag{10.1}
$$

with $\Delta E_{\text{kin}}$ the change in kinetic plus elastic energy of the
coupled rotor + pitch system between $t=0$ and $t=T$. In passive mode the
residual is a genuine diagnostic and should be below 2 %; in prescribed-pitch
mode the actuator work is unaccounted for and the residual is not meaningful.

---

## 11. Numerical integration

The scheme is semi-implicit (symplectic) Euler:

$$
\begin{aligned}
\dot\psi_k^{n+1} &= \dot\psi_k^n + \ddot\psi_k^n\,\Delta t\\
\psi_k^{n+1} &= \psi_k^n + \dot\psi_k^{n+1}\,\Delta t\\
\omega^{n+1} &= \omega^n + \dot\omega^n\,\Delta t\\
\theta^{n+1} &= \theta^n + \omega^{n+1}\,\Delta t
\end{aligned}
\tag{11.1}
$$

Note the position update uses the *updated* velocity — this is the
symplectic structure that conserves a nearby Hamiltonian for the
unforced system.

Typical time step: $\Delta t = 2\times10^{-4}$ s. The rotor turns through
about 0.4° per step at the design speed. Convergence studies show that
halving $\Delta t$ changes Cp by less than 0.5 %.

---

## 12. Summary of approximations

The following approximations are **intentional** and documented as
limitations in the README:

1. **Two-dimensional flow.** No tip vortices, no spanwise flow, no 3D
   wake structure. The tip-loss correction is a bounded finite-span
   reduction capped at 15 %; the true 3D loss at H/c = 3 is around 15–25 %.

2. **No flow curvature expansion.** Flux-line theory predicts the flow
   to accelerate through the rotor in a way that a 2D DMS model misses.
   The Adams correction partially compensates but is not a substitute.

3. **No Active Lift.** Sharp's secondary mechanism (the L-shaped
   bellcrank between the rocking hinge and the CG) is not modelled. A
   first-order term was tested and gave a null result at R = 0.6 m.

4. **Uncalibrated dynamic-stall constants.** $T_f, T_v, T_\alpha$ are
   literature-typical values from Pawsey's thesis, not fitted to data.
   The uncertainty study shows they contribute 3–4 % to Cp spread.

5. **No stall-cell effects.** At low aspect ratio, stall cells can
   occupy part of the span, reducing effective lift further. Not modelled.

6. **Simple atmospheric turbulence.** The `turb_I` implementation is a
   first-order AR(1) process with a single length scale, not a full
   Dryden or von Kármán spectrum.

Additional known-good behaviours:

- The dynamic-stall increment is designed so that steady flow reproduces
  the static polar exactly. Turning `use_dynamic_stall=False` at a fixed
  point changes Cp by 2.1 % — a good sign the DS model is not being
  exploited by the optimiser.
- The Adams curvature cap $s_c \le 1$ was added after discovering that
  the uncapped version over-corrected at high chord-to-radius ratio and
  drove the Ham 1979 reproduction Cp negative.
- The pitch-sign convention in Eq. (2.6) is critical. An early version
  used $-\psi$ instead of $+\psi$; this reversed the direction of the
  aerodynamic pitch moment and destroyed the passive mechanism. The
  `scripts/diag_qa.py` test verifies the correct sign on every build.

---

## References

- Ham, N.D., Soohoo, P., Noll, R.B., Drees, H.M. (1979). *Analytical and
  experimental evaluation of cycloturbine aerodynamic performance.* AIAA
  79-0968.
- Adams, Z., Chen, J. (2018). *Flux-line theory: a novel analytical model
  for vertical axis wind turbines.* AIAA J. 56(6).
- Pawsey, N.C.K. (2002). *Development and evaluation of passive
  variable-pitch vertical axis wind turbines.* PhD thesis, UNSW.
- Sharp, P.A. (2021). *The Sharp Cycloturbine: a summary of how it works.*
- Sheldahl, R.E., Klimas, P.C. (1981). *Aerodynamic characteristics of
  seven symmetrical airfoil sections through 180 degrees angle of attack.*
  Sandia SAND80-2114.
- Paraschivoiu, I. (1981). *Aerodynamic loads and performance of the
  Darrieus rotor.* J. Energy 6(6).
- Leishman, J.G. (2002). *Principles of Helicopter Aerodynamics.*
  Cambridge University Press.
