import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sharp_vawt import create_sim_from_params
from vawt_presets import PRESETS

base = PRESETS["prototype_60cm"].copy()

print("Sweeping Pitch Bearing Friction (mu_c)...")
print(f"{'mu_c':<10} | {'Cp @ 6m/s':<10} | {'Self-Start @ 4m/s'}")
print("-" * 45)

# Sweep from nearly frictionless to heavily sticky
for mu_c in [0.0001, 0.0003, 0.001, 0.005, 0.010, 0.020]:
    params = {**base, "mu_c": mu_c, "U": 6.0, "w0_frac": 0.9}
    
    try:
        res = create_sim_from_params(params).run()
        start_res = create_sim_from_params({**params, "U": 4.0, "w0_frac": 0.1}).run()
        started = "YES" if start_res['tsr_eq'] > 1.8 else "NO"
        print(f"{mu_c:<10.4f} | {res['cp']:<10.3f} | {started}")
    except Exception:
        print(f"{mu_c:<10.4f} | ERROR")