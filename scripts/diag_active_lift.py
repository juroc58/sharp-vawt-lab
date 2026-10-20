"""
Active Lift isolation experiment for the Sharp cycloturbine.

This script isolates the Coriolis-like "Active Lift" term by running the SAME
prescribed pitch schedule ψ(φ) with two pivot configurations:
  1. ar = 0.00  → pure pitch, NO radial CG motion → NO Coriolis
  2. ar = 0.312  → real arm, radial CG motion present → Coriolis ACTIVE

Uses the scale-up passive CPPC design (R=2.72m, AR=10.5), which operates
at a healthy TSR ~2.9 with Cp ~0.38, providing a meaningful operating
point for isolating the Coriolis-like term. The Sharp-inspired design
(R=0.60m, AR=2.86) sits only ~4 % above the finite-span collapse
threshold, so it is not a stable operating point for this diagnostic.

The net pitch-to-rotor energy transfer is measured as the difference
in Cp between the same pitch schedule with and without radial CG motion.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from vawt_core import create_sim_from_params


# Scale-up passive CPPC design (R=2.72m, AR=10.5) - proper operating point
# The Sharp-inspired design at R=0.60m sits just above the collapse
# threshold and is not used here.
DESIGN = dict(
    R=2.7179, H=4.0568, N=3, c=0.3861,
    ar=0.3121, sp=0.2181,
    mb=0.92954, xbcg=0.20,
    mc=2.69306, dcw=-0.1935,
    balance=0, bias_deg=0.0,
    prescribe_pitch=False,
    cd_add=0.002,
    use_dynamic_stall=True, use_flow_curvature=True,
    use_dmst=True, use_tip_loss=True,
    win_deg=45.0, cb=2e-5, mu_c=3e-4,
    free=True, T_max=30.0, stride=5,
    w0_frac=0.9, k_load=4.164352, tsr=2.5,
)

# -----------------------------------------------------------------------
# Section 1: Passive operation at proper operating point
# -----------------------------------------------------------------------
print("=" * 72)
print("SECTION 1: Passive CPPC operation (scale-up design, R=2.72m)")
print("=" * 72)

rA = create_sim_from_params({**DESIGN, 'prescribe_pitch': False}).run()
tsr_eq = rA['tsr_eq']
mean_psi_deg = 0.5 * (rA['pitch_min'] + rA['pitch_max'])

print(f"Passive:  Cp = {rA['cp']:+.4f}  TSR_eq = {tsr_eq:.3f}  "
      f"pitch range = [{rA['pitch_min']:+.1f}, {rA['pitch_max']:+.1f}] deg  "
      f"mean = {mean_psi_deg:+.1f} deg")
print()

# -----------------------------------------------------------------------
# Section 2: Active Lift isolation (Coriolis term isolation)
# -----------------------------------------------------------------------
print()
print("=" * 72)
print("SECTION 2: Active Lift isolation (Coriolis term isolation)")
print("=" * 72)
print()
print("Method: Run the SAME prescribed pitch schedule ψ(φ) from the passive")
print("run, but with two different pivot configurations:")
print("  1. ar = 0.00  → pure pitch, NO radial CG motion → NO Coriolis")
print("  2. ar = 0.312  → real arm, radial CG motion present → Coriolis ACTIVE")
print("Both use the SAME ψ(φ) schedule extracted from the passive run.")
print("The difference isolates the Coriolis-like term from ordinary")
print("cyclic pitch benefit.")
print()

# Extract the passive pitch schedule ψ(φ) by fitting Fourier coefficients
# to the passive simulation's pitch history (last revolution)
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
    **DESIGN,
    'prescribe_pitch': True,
    'tsr': tsr_eq,
    'pp0_deg': pp0, 'pp1_deg': pp1, 'pp2_deg': pp2, 'pp3_deg': pp3,
    'pp_ph_deg': 0.0,
    'ar': 0.00,
}).run()
print(f"D. Prescribed ψ(φ), ar=0.00 (NO Coriolis): Cp = {r_ar0['cp']:+.4f}")

# Run 2: ar = 0.50 (real arm, radial CG motion, Coriolis ACTIVE)
r_ar_real = create_sim_from_params({
    **DESIGN,
    'prescribe_pitch': True,
    'tsr': tsr_eq,
    'pp0_deg': pp0, 'pp1_deg': pp1, 'pp2_deg': pp2, 'pp3_deg': pp3,
    'pp_ph_deg': 0.0,
    'ar': DESIGN['ar'],  # 0.50
}).run()
print(f"E. Prescribed ψ(φ), ar={DESIGN['ar']:.4f} (Coriolis ACTIVE): Cp = {r_ar_real['cp']:+.4f}")

# Isolate Coriolis term
coriolis_delta = r_ar_real['cp'] - r_ar0['cp']
coriolis_pct = 100 * coriolis_delta / max(abs(r_ar0['cp']), 1e-9)
print()
print("=" * 72)
print("CORIOLIS ISOLATION RESULT:")
print(f"  ΔCp (ar=real - ar=0) = {coriolis_delta:+.4f}  ({coriolis_pct:+.1f}%)")
print("  This isolates the Coriolis-like term (radial CG motion)")
print("  from the ordinary cyclic pitch benefit.")
print("=" * 72)
print()

# Compare with original dynamic pitch benefit
# Run rigid at mean pitch for comparison
rB = create_sim_from_params({
    **DESIGN, 'prescribe_pitch': True,
    'free': False, 'tsr': tsr_eq,
    'pp0_deg': mean_psi_deg,
    'pp1_deg': 0.0, 'pp2_deg': 0.0, 'pp3_deg': 0.0,
    'pp_ph_deg': 0.0,
}).run()
original_dynamic = rA['cp'] - rB['cp']
print(f"Original dynamic pitch benefit (A − B): {original_dynamic:+.4f} ({100*original_dynamic/max(abs(rB['cp']),1e-9):+.1f}%)")
print(f"Coriolis-isolated benefit:             {coriolis_delta:+.4f} ({coriolis_pct:+.1f}%)")
if abs(original_dynamic) > 1e-6:
    print(f"  Fraction of dynamic pitch due to Coriolis: {100*coriolis_delta/original_dynamic:.1f}%")
