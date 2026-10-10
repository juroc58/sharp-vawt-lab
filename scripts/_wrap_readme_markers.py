"""One-time: wrap README.md tables in generation markers. Idempotent."""
import re

README = "README.md"
s = open(README).read()

def wrap(name, anchor, transform=None):
    global s
    if f"BEGIN GENERATED: {name}" in s:
        print(f"[skip] {name} already wrapped")
        return
    if anchor not in s:
        print(f"[FAIL] anchor for '{name}' not found verbatim")
        return
    body = transform(anchor) if transform else anchor
    wrapped = (f"<!-- BEGIN GENERATED: {name} -->\n"
               f"{body}\n"
               f"<!-- END GENERATED: {name} -->")
    s = s.replace(anchor, wrapped, 1)
    print(f"[OK]  wrapped {name}")

# headline_table
wrap("headline_table", """| Configuration | Cp | 90 % CI | Reference |
|---|---|---|---|
| **Scaled-up passive (R = 2.26 m, Re = 5.1e5)** | **0.45** | [0.43, 0.46] | ~76 % of Betz |
| **Sharp-inspired CPPC** | **0.27** | [0.25, 0.29] | Bayly-Kentfield 0.37 at 4.6 m |
| Optimised passive (mass-balanced) | 0.44 | [0.42, 0.46] | — |
| Prescribed pitch (ideal actuator) | 0.48 | — | Ham 1979 measured 0.42–0.45 |
| Ham 1979 reproduction | 0.49 | [0.46, 0.51] | matches Ham's method |""")

# aep_steady (the two-row strategy table)
wrap("aep_steady", """| Strategy | AEP | Capacity factor | Load match |
|---|---|---|---|
| **Passive k_load (variable speed)** | **350 kWh/yr** | **16.0 %** | — |
| Fixed-rpm generator | 129 kWh/yr | 5.9 % | 0.37× |""")

# aep_turbulent
wrap("aep_turbulent", """| | AEP | CF |
|---|---|---|
| Steady wind | 281.3 kWh/yr | 12.85 % |
| Turbulent wind (I = 12 %) | 293.7 kWh/yr | 13.41 % |
| **Effect** | **+4.4 %** | **+0.56 pp** |""")

# uq_params
wrap("uq_params", """| Parameter | Low | High | Source of uncertainty |
|---|---|---|---|
| `cd_add` | 0.001 | 0.005 | strut / interference drag |
| `ds_Tf` | 1.5 | 4.5 | separation lag (default 3.0) |
| `ds_Tv` | 3.0 | 9.0 | vortex-lift lag (default 6.0) |
| `ds_Ta` | 0.05 | 0.15 | attached-flow lag (default 0.10) |
| `ds_Kv` | 0.25 | 0.75 | vortex-lift strength (default 0.50) |
| `tau_rev` | 0.05 | 0.20 | induction lag (default 0.10 rev) |
| `c_scale_override` | 0.30 | 0.60 | Adams shift strength |
| `tip_loss_floor_override` | 0.80 | 1.00 | finite-span correction floor |""")

# spearman_table
wrap("spearman_table", """| Anchor | Dominant parameter | ρ | p-value |
|---|---|---|---|
| Ham 1979 reproduction | `tau_rev` (induction lag) | **+0.89** | < 0.001 |
| Sharp-inspired CPPC | `ds_Tf` (separation lag) | **+0.56** | < 0.001 |
| Optimised passive | `tau_rev` | **+0.44** | 0.004 |
| Scale-up R = 2.26 m | `c_scale_override` (Adams shift) | **−0.70** | < 0.001 |""")

open(README, "w").write(s)
print("\nDone. Now run: python3 scripts/build_readme.py")