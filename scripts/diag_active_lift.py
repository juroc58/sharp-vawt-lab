"""
Fair comparison of passive vs rigid at the same operating TSR.

Both machines are evaluated at the passive rotor's equilibrium TSR and
the same external load, so that the only difference is whether the
blade rocks.
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
