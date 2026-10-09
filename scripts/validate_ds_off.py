"""
Dynamic-stall sensitivity test.

The most important robustness check: is the optimised Cp real, or is the
model exploiting the (uncalibrated) dynamic-stall increment?
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vawt_core import create_sim_from_params

DESIGN = dict(
    c=0.117607, tsr=2.14487, k_load=0.00149992,
    pp0_deg=+5.15612, pp1_deg=-6.32883,
    pp2_deg=+2.75837, pp3_deg=-0.0845207,
    cd_add=0.002,
    use_flow_curvature=True,   # ← add this
    free=True, T_max=30.0, stride=5,
    prescribe_pitch=True, w0_frac=0.9,
)

cases = [
    ("full model",           dict()),
    ("no dynamic stall",     dict(use_dynamic_stall=False)),
    ("no DS, no curvature",  dict(use_dynamic_stall=False,
                                  use_flow_curvature=False)),
]

print("Dynamic-stall sensitivity - optimiser design point")
print("=" * 60)
print(f"{'case':<25} {'Cp':>9} {'alpha_max':>12}")
print("-" * 60)

for label, override in cases:
    r = create_sim_from_params({**DESIGN, **override}).run()
    print(f"{label:<25} {r['cp']:>9.4f} {r['aoa_max']:>12.2f}")

print()
print("If delta Cp < 5%: result is NOT dynamic-stall dominated -> publishable.")
