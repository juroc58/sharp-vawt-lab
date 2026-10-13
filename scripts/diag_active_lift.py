"""
Fair comparison of passive vs rigid at the same operating TSR.

Both machines are evaluated at the passive rotor's equilibrium TSR and
the same external load, so that the only difference is whether the
blade rocks.

Also includes an Active Lift isolation experiment (Section 2):
run prescribed ψ(φ) matching the passive schedule with the pivot at
ar = 0 (pure pitch, no radial CG motion) vs at the real arm (ar > 0,
radial CG motion present). The difference isolates the Coriolis-like
term from ordinary cyclic pitch.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from vawt_core import create_sim_from_params

DESIGN = dict(
    R=0.60, H=0.40, N=3, c=0.14,
    ar=0.50, sp=0.25,
    mb=0.010, xbcg=0.20,
    mc=0.002, dcw=0.30,
    balance=0, bias_deg=0.0,
    cd_add=0.002,
    use_dynamic_stall=True, use_flow_curvature=True,
    use_dmst=True, use_tip_loss=True,
    win_deg=45.0, cb=2e-5, mu_c=3e-4,
    free=True, T_max=30.0, stride=5,
    w0_frac=0.9, k_load=0.0025, tsr=2.0,
)

# -----------------------------------------------------------------------
# Section 1: Original passive vs rigid decomposition
# -----------------------------------------------------------------------
print("=" * 72)
print("SECTION 1: Passive vs rigid decomposition (original)")
print("=" * 72)

# --- A. Passive — find the equilibrium TSR ---
rA = create_sim_from_params({**DESIGN, 'prescribe_pitch': False}).run()
tsr_eq = rA['tsr_eq']
mean_psi_deg = 0.5 * (rA['pitch_min'] + rA['pitch_max'])

print(f"Passive:  Cp = {rA['cp']:+.4f}  TSR_eq = {tsr_eq:.3f}  "
      f"pitch range = [{rA['pitch_min']:+.1f}, {rA['pitch_max']:+.1f}] deg  "
      f"mean = {mean_psi_deg:+.1f} deg")
print()

# --- B. Rigid at the SAME TSR, held at the time-mean pitch ---
rB = create_sim_from_params({
    **DESIGN, 'prescribe_pitch': True,
    'free': False, 'tsr': tsr_eq,
    'pp0_deg': mean_psi_deg,
    'pp1_deg': 0.0, 'pp2_deg': 0.0, 'pp3_deg': 0.0,
    'pp_ph_deg': 0.0,
}).run()
print(f"B. Rigid @ psi={mean_psi_deg:+.1f}  @ TSR={tsr_eq:.2f}  "
      f"Cp = {rB['cp']:+.4f}")

# --- C. Rigid at the SAME TSR, held at psi = 0 ---
rC = create_sim_from_params({
    **DESIGN, 'prescribe_pitch': True,
    'free': False, 'tsr': tsr_eq,
    'pp0_deg': 0.0, 'pp1_deg': 0.0,
    'pp2_deg': 0.0, 'pp3_deg': 0.0,
    'pp_ph_deg': 0.0,
}).run()
print(f"C. Rigid @ psi= 0.0   @ TSR={tsr_eq:.2f}  "
      f"Cp = {rC['cp']:+.4f}")

# --- D. Prescribed-pitch with the passive mean pitch ---
# (verifies that the prescribed scheduler gives ~the same as passive)
print()

b = rB['cp']
c = rC['cp']
a = rA['cp']
print("Decomposition at TSR = {:.2f}:".format(tsr_eq))
print(f"  Cp(A) passive                          = {a:+.4f}")
print(f"  Cp(B) rigid at mean pitch              = {b:+.4f}")
print(f"  Cp(C) rigid at zero pitch              = {c:+.4f}")
print()
print(f"  Dynamic pitch A − B                    = {a - b:+.4f}  "
      f"({100*(a-b)/max(abs(b), 1e-9):+.1f}%)")
print(f"  Mean-pitch offset B − C                = {b - c:+.4f}  "
      f"({100*(b-c)/max(abs(c), 1e-9):+.1f}%)")
print()
if a > b * 1.05:
    print("PASS: passive is >5% better than rigid at the same operating")
    print("      point. Dynamic pitch (and hence any Coriolis / Active Lift")
    print("      contribution) is present in the model.")
elif a > b:
    print("MARGINAL: passive is slightly better than rigid. Dynamic pitch")
    print("          contributes < 5% at this design point.")
else:
    print("FAIL: passive is worse than rigid. The mechanism is not working.")

# -----------------------------------------------------------------------
# Section 2: Active Lift isolation experiment (Coriolis isolation)
# -----------------------------------------------------------------------
print()
print("=" * 72)
print("SECTION 2: Active Lift isolation (Coriolis term isolation)")
print("=" * 72)
print()
print("Method: Run the SAME prescribed pitch schedule ψ(φ) from the passive")
print("run, but with two different pivot configurations:")
print("  1. ar = 0.00  → pure pitch, NO radial CG motion → NO Coriolis")
print("  2. ar = 0.50  → real arm, radial CG motion present → Coriolis ACTIVE")
print("Both use the SAME ψ(φ) schedule extracted from the passive run.")
print("The difference isolates the Coriolis-like term from ordinary")
print("cyclic pitch benefit.")
print()

# Extract the passive pitch schedule ψ(φ) by fitting Fourier coefficients
# to the passive simulation's pitch history
# We use the last revolution of the passive run
outA = rA['out']
th = outA[:, 1]
psi = outA[:, 3]
# Get last revolution
mask = th >= th[-1] - 2*np.pi
phi = np.degrees(th[mask] % (2*np.pi))
psi_deg = np.degrees(psi[mask])

# Fit Fourier series: ψ = pp0 + pp1*cos(φ) + pp2*cos(2φ) + pp3*sin(2φ)
# (using the same convention as the core: pp_ph_deg = 0)
A_mat = np.column_stack([
    np.ones_like(phi),
    np.cos(np.radians(phi)),
    np.cos(2*np.radians(phi)),
    np.sin(2*np.radians(phi)),
])
coeffs, _, _, _ = np.linalg.lstsq(A_mat, psi_deg, rcond=None)
pp0, pp1, pp2, pp3 = coeffs
print(f"Fitted pitch schedule: pp0={pp0:+.2f}°, pp1={pp1:+.2f}°, pp2={pp2:+.2f}°, pp3={pp3:+.2f}°")
print()

# Base config for prescribed pitch with fitted schedule
BASE_FITTED = dict(
    R=DESIGN['R'], H=DESIGN['H'], N=DESIGN['N'], c=DESIGN['c'],
    ar=DESIGN['ar'], sp=DESIGN['sp'],
    mb=DESIGN['mb'], xbcg=DESIGN['xbcg'],
    mc=DESIGN['mc'], dcw=DESIGN['dcw'],
    balance=DESIGN['balance'], bias_deg=DESIGN['bias_deg'],
    cd_add=DESIGN['cd_add'],
    use_dynamic_stall=DESIGN['use_dynamic_stall'],
    use_flow_curvature=DESIGN['use_flow_curvature'],
    use_dmst=DESIGN['use_dmst'],
    use_tip_loss=DESIGN['use_tip_loss'],
    win_deg=DESIGN['win_deg'], cb=DESIGN['cb'], mu_c=DESIGN['mu_c'],
    free=False, T_max=30.0, stride=5,
    k_load=DESIGN['k_load'],
)

# Run 1: ar = 0.00 (pure pitch, NO radial CG motion, NO Coriolis)
r_ar0 = create_sim_from_params({
    **BASE_FITTED,
    'prescribe_pitch': True,
    'tsr': tsr_eq,
    'pp0_deg': pp0, 'pp1_deg': pp1, 'pp2_deg': pp2, 'pp3_deg': pp3,
    'pp_ph_deg': 0.0,
    'ar': 0.00,
}).run()
print(f"D. Prescribed ψ(φ), ar=0.00 (NO Coriolis): Cp = {r_ar0['cp']:+.4f}")

# Run 2: ar = 0.50 (real arm, radial CG motion, Coriolis ACTIVE)
r_ar50 = create_sim_from_params({
    **BASE_FITTED,
    'prescribe_pitch': True,
    'tsr': tsr_eq,
    'pp0_deg': pp0, 'pp1_deg': pp1, 'pp2_deg': pp2, 'pp3_deg': pp3,
    'pp_ph_deg': 0.0,
    'ar': 0.50,
}).run()
print(f"E. Prescribed ψ(φ), ar=0.50 (Coriolis ACTIVE): Cp = {r_ar50['cp']:+.4f}")

# Isolate Coriolis term
coriolis_delta = r_ar50['cp'] - r_ar0['cp']
coriolis_pct = 100 * coriolis_delta / max(abs(r_ar0['cp']), 1e-9)
print()
print("=" * 72)
print("CORIOLIS ISOLATION RESULT:")
print(f"  ΔCp (ar=0.50 - ar=0.00) = {coriolis_delta:+.4f}  ({coriolis_pct:+.1f}%)")
print("  This isolates the Coriolis-like term (radial CG motion)")
print("  from the ordinary cyclic pitch benefit.")
print("=" * 72)
print()

# Compare with original dynamic pitch benefit
original_dynamic = a - b
print(f"Original dynamic pitch benefit (A − B): {original_dynamic:+.4f} ({100*original_dynamic/max(abs(b),1e-9):+.1f}%)")
print(f"Coriolis-isolated benefit:             {coriolis_delta:+.4f} ({coriolis_pct:+.1f}%)")
if abs(original_dynamic) > 1e-6:
    print(f"  Fraction of dynamic pitch due to Coriolis: {100*coriolis_delta/original_dynamic:.1f}%")
