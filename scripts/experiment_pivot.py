import os
import sys

# This block fixes the import path so it works from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sharp_vawt import create_sim_from_params
from vawt_presets import PRESETS

# Start with the optimized 1/3 scale prototype
base = PRESETS["prototype_1_3"].copy()

# We use balance=1. This tells the physics engine:
# "Keep the counterweight mass (mc) fixed, but solve for the new 
# counterweight offset (dcw) so the blade stays statically balanced."
base["balance"] = 1
base["mc"] = 0.1243 # Keep the 124g weight

print("Experimenting with Pivot Position (sp) and Counterweight Offset (dcw)...")
print(f"{'Pivot (sp)':<10} | {'New dcw':<10} | {'Cp @ 6m/s':<10} | {'RPM @ 6m/s':<10} | {'Self-Start @ 4m/s'}")
print("-" * 75)

# Sweep pivot from 15% to 35% of chord
for sp in [0.15, 0.20, 0.216, 0.25, 0.30, 0.35]:
    params = {**base, "sp": sp, "U": 6.0, "w0_frac": 0.9}
    
    try:
        # Create the simulation object
        sim_obj = create_sim_from_params(params)
        
        # The engine solves for dcw in __init__ when balance=1
        solved_dcw = sim_obj.dcw
        
        # Run at normal speed
        res = sim_obj.run()
        
        # Test startup
        start_sim = create_sim_from_params({**params, "U": 4.0, "w0_frac": 0.1})
        start_res = start_sim.run()
        startup_status = "YES" if start_res['tsr_eq'] > 1.8 else "NO"
        
        print(f"{sp:<10.3f} | {solved_dcw:<10.3f} | {res['cp']:<10.3f} | {res['rpm']:<10.1f} | {startup_status}")
        
    except Exception as e:
        print(f"{sp:<10.3f} | ERROR: {e}")