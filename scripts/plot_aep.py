#!/usr/bin/env python3
"""Plotting module for AEP figures.

Reads JSON results from compute_aep_small.py, compute_aep_scaleup.py,
compute_aep_turbulent.py, and compute_aep_counter_rotating.py
and generates publication-quality figures using shared style.

Usage:
    python3 scripts/plot_aep.py --json scripts/aep_small.json --out docs/aep_small.png --type small
    python3 scripts/plot_aep.py --json scripts/aep_scaleup.json --out docs/aep_scaleup.png --type scaleup
    python3 scripts/plot_aep.py --json scripts/aep_turbulent.json --out docs/aep_turbulent.png --type turbulent
    python3 scripts/plot_aep.py --json scripts/aep_counter_rotating.json --out docs/aep_counter_rotating.png --type counter
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, _ROOT)

from plot_style import (
    COL_HIGH_BRANCH,
    COL_LOW_BRANCH,
    COL_PASSIVE_FIXED,
    COL_PASSIVE_KLOAD,
    COL_RIGID,
    FONT_SIZE,
    GRID_ALPHA,
    LS_DASHED,
    LS_DOTTED,
    LS_SOLID,
    MK_FIXED,
    MK_FREE,
    MK_HIGH,
    MK_LOW,
    add_weibull_axis,
    annotate_with_arrow,
    apply_style,
    create_figure_3panel,
    create_figure_4panel,
    finalize_figure,
    save_figure,
    set_legend_outside,
)


def load_json(path: str) -> dict[str, Any]:
    with open(path) as fh:
        return json.load(fh)


def _fmt_rated(p_watts: float) -> str:
    """Format rated power with sensible units: watts below 1 kW, kW otherwise."""
    if p_watts < 1000:
        return f"Rated ({p_watts:.1f} W)"
    return f"Rated ({p_watts/1000:.1f} kW)"


def weibull_pdf(U, U_mean, k):
    lam = U_mean / math.gamma(1.0 + 1.0 / k)
    return (k / lam) * (U / lam) ** (k - 1.0) * np.exp(-(U / lam) ** k)


def plot_aep_small_rotor(data: dict[str, Any], out_path: str):
    """Plot AEP for the small-rotor (R=0.60 m) from aep_small.json."""
    apply_style()
    fig, axes = create_figure_3panel()

    geo = data['geometry']
    wind = data['wind']
    res_p = data['results']['passive_k_load']
    R = geo['R']
    H = geo.get('H')
    if H is None:
        raise ValueError(
            f"geometry in {out_path} is missing 'H'; regenerate the JSON with "
            f"authoritative geometry metadata so figure titles reflect the true "
            f"machine design instead of a preset from a different design."
        )
    # Authoritative title from JSON geometry (never fall back to a preset from
    # a different design).
    title = fr"AEP — Passive CPPC, $R = {R:.2f}$ m, $H = {H:.2f}$ m"

    tsrs = np.array(res_p['tsr'])
    cp_tsr = np.array(res_p['cp_tsr'])
    free = res_p.get('free_results', [])

    # Build power curves from Cp data
    U_grid = np.linspace(wind['cut_in'], wind['cut_out'], 200)
    A = 2.0 * R * H
    p_rated = wind['p_rated_W']

    # Reconstruct Cp vs U for branch-traced
    if free:
        U_free = np.array([f['U'] for f in free])
        cp_free = np.array([f['cp'] for f in free])
        cp_passive = np.interp(U_grid, U_free, cp_free)
    else:
        cp_passive = np.zeros_like(U_grid)

    # Fixed-rpm Cp from tsr sweep
    # Use nanargmax to handle NaN values in cp_tsr
    valid_cp_tsr = cp_tsr[~np.isnan(cp_tsr)]
    if len(valid_cp_tsr) > 0:
        idx_best = int(np.nanargmax(cp_tsr))
    else:
        idx_best = 0
    tsr_design = float(tsrs[idx_best])
    tsr_fixed = np.clip(tsr_design * wind['mean_U'] / U_grid, tsrs[0], tsrs[-1])
    cp_fixed = np.interp(tsr_fixed, tsrs, cp_tsr)

    # Panel 1: Cp vs TSR (fixed rpm) with both branches
    ax = axes[0]
    ax.plot(tsrs, cp_tsr, LS_SOLID, color=COL_PASSIVE_KLOAD, lw=1.8,
            marker=MK_FIXED, label="Passive CPPC (fixed rpm, 3-phase mean)")
    if 'cp_tsr_lo' in res_p and 'cp_tsr_hi' in res_p:
        lo = np.array(res_p['cp_tsr_lo'])
        hi = np.array(res_p['cp_tsr_hi'])
        spread = hi - lo
        mask = spread > 0.03
        if np.any(mask):
            ax.fill_between(tsrs[mask], lo[mask], hi[mask],
                            color=COL_PASSIVE_KLOAD, alpha=0.15,
                            label="Phase spread > 3% (bistable)")
    if free:
        fr_tsr = np.array([f['tsr_eq'] for f in free])
        fr_cp = np.array([f['cp'] for f in free])
        ax.scatter(fr_tsr, fr_cp, color=COL_HIGH_BRANCH, marker=MK_FREE, s=40,
                   zorder=3, label="Free-running equilibria", edgecolor='k', lw=0.5)
    ax.set_xlabel(r"Tip-speed ratio $\lambda$")
    ax.set_ylabel(r"Power coefficient $C_p$")
    ax.set_title("Cp vs TSR at fixed rpm")
    ax.set_ylim(bottom=0)
    set_legend_outside(ax)

    # Panel 2: Free-running Cp vs wind speed
    ax = axes[1]
    if free:
        Us = np.array([f['U'] for f in free])
        cps = np.array([f['cp'] for f in free])
        ax.plot(Us, cps, LS_SOLID, color=COL_PASSIVE_KLOAD, lw=1.6,
                marker=MK_FREE, label="Passive CPPC (branch-traced)")
    ax.set_xlabel(r"Wind speed $U$ [m/s]")
    ax.set_ylabel(r"Cp at equilibrium")
    ax.set_title("Free-running Cp vs wind speed")
    ax.set_ylim(bottom=0)
    ax.axvline(wind['cut_in'], color='k', ls=':', lw=1, alpha=0.5)
    ax.axvline(wind['rated_wind_speed'], color='k', ls=':', lw=1, alpha=0.5)
    set_legend_outside(ax)

    # Panel 3: Power curve with Weibull
    ax = axes[2]
    U_grid = np.linspace(wind['cut_in'], wind['cut_out'], 200)
    P_passive = np.minimum(0.5 * 1.225 * A * U_grid ** 3 * np.clip(cp_passive, 0, 0.593) * 0.90, p_rated)
    P_fixed = np.minimum(0.5 * 1.225 * A * U_grid ** 3 * np.clip(cp_fixed, 0, 0.593) * 0.90, p_rated)

    ax.plot(U_grid, P_passive, LS_SOLID, color=COL_PASSIVE_KLOAD, lw=2.0,
            label="Passive CPPC, $k_{load}$ (var. speed)")
    ax.plot(U_grid, P_fixed, LS_DASHED, color=COL_PASSIVE_FIXED, lw=1.8,
            label="Passive CPPC, fixed rpm")
    ax.set_xlabel(r"Wind speed $U$ [m/s]")
    ax.set_ylabel(r"Electrical power [W]")
    ax.set_title("Power curve")
    ax.set_xlim(wind['cut_in'], wind['cut_out'])
    ax.set_ylim(bottom=-0.02)
    pdf = weibull_pdf(U_grid, wind['mean_U'], wind['k_weibull'])
    add_weibull_axis(ax, U_grid, pdf, wind['mean_U'], wind['k_weibull'])
    ax.axhline(wind['p_rated_W'], color='k', ls=':', lw=1, alpha=0.7,
               label=_fmt_rated(wind['p_rated_W']))
    ax.axvline(wind['cut_in'], color='k', ls=':', lw=1, alpha=0.5)
    ax.axvline(wind['rated_wind_speed'], color='k', ls=':', lw=1, alpha=0.5)
    set_legend_outside(ax, ncol=2)

    title = fr"AEP — Passive CPPC, $R = {R:.2f}$ m, $H = {H:.2f}$ m"
    finalize_figure(fig, suptitle=title)
    save_figure(fig, out_path)


def plot_aep_scaleup(data: dict[str, Any], out_path: str):
    """Plot AEP for the scale-up (R=2.72 m) from aep_scaleup.json."""
    apply_style()
    fig, axes = create_figure_4panel()

    geo = data['geometry']
    wind = data['wind']
    res_p = data['results']['passive_k_load']
    res_f = data['results']['passive_fixed_rpm']
    branches = data.get('branches', {})
    rigid = data.get('rigid_fair_ref')

    R = geo['R']
    H = geo.get('H')
    if H is None:
        raise ValueError(
            "geometry in aep_scaleup.json is missing 'H'; regenerate the JSON "
            "with authoritative geometry metadata."
        )
    tsrs = np.array(res_p['tsr'])
    cp_tsr = np.array(res_p['cp_tsr'])
    free = res_p.get('free_results', [])

    high_branch = branches.get('high_seed', {})
    low_branch = branches.get('low_seed', {})
    traced_branch = branches.get('branch_traced', {})

    # Build power curves from Cp data
    U_grid = np.linspace(wind['cut_in'], wind['cut_out'], 200)
    A = 2.0 * R * H
    RHO = 1.225
    ETA = 0.90
    p_rated = wind['p_rated_W']

    # Reconstruct Cp vs U for branch-traced
    if free:
        U_free = np.array([f['U'] for f in free])
        cp_free = np.array([f['cp'] for f in free])
        cp_passive = np.interp(U_grid, U_free, cp_free)
    else:
        cp_passive = np.zeros_like(U_grid)

    # Fixed-rpm Cp from tsr sweep
    # Use nanargmax to handle NaN values in cp_tsr
    valid_cp_tsr = cp_tsr[~np.isnan(cp_tsr)]
    if len(valid_cp_tsr) > 0:
        idx_best = int(np.nanargmax(cp_tsr))
    else:
        idx_best = 0
    tsr_design = float(tsrs[idx_best])
    tsr_fixed = np.clip(tsr_design * wind['mean_U'] / U_grid, tsrs[0], tsrs[-1])
    cp_fixed = np.interp(tsr_fixed, tsrs, cp_tsr)

    P_passive = np.minimum(0.5 * RHO * A * U_grid ** 3 * np.clip(cp_passive, 0, 0.593) * ETA, p_rated)
    P_fixed = np.minimum(0.5 * RHO * A * U_grid ** 3 * np.clip(cp_fixed, 0, 0.593) * ETA, p_rated)

    # For high/low branches
    if high_branch and 'free_results' in high_branch:
        hfr = high_branch['free_results']
        if hfr:
            Uh = np.array([f['U'] for f in hfr])
            cph = np.array([f['cp'] for f in hfr])
            np.interp(U_grid, Uh, cph)
    if low_branch and 'free_results' in low_branch:
        lfr = low_branch['free_results']
        if lfr:
            Ul = np.array([f['U'] for f in lfr])
            cpl = np.array([f['cp'] for f in lfr])
            np.interp(U_grid, Ul, cpl)

    # Panel 1: Cp vs TSR (fixed rpm) with both branches
    ax = axes[0]
    ax.plot(tsrs, cp_tsr, LS_SOLID, color=COL_PASSIVE_KLOAD, lw=1.8,
            marker=MK_FIXED, label="Passive CPPC (fixed rpm, 3-phase mean)")
    if 'cp_tsr_lo' in res_p and 'cp_tsr_hi' in res_p:
        lo = np.array(res_p['cp_tsr_lo'])
        hi = np.array(res_p['cp_tsr_hi'])
        spread = hi - lo
        mask = spread > 0.03
        if np.any(mask):
            ax.fill_between(tsrs[mask], lo[mask], hi[mask],
                            color=COL_PASSIVE_KLOAD, alpha=0.15,
                            label="Phase spread > 3% (bistable)")
    if free:
        fr_tsr = np.array([f['tsr_eq'] for f in free])
        fr_cp = np.array([f['cp'] for f in free])
        ax.scatter(fr_tsr, fr_cp, color=COL_HIGH_BRANCH, marker=MK_FREE, s=40,
                   zorder=3, label="Free-running (branch-traced)", edgecolor='k', lw=0.5)
    ax.set_xlabel(r"Tip-speed ratio $\lambda$")
    ax.set_ylabel(r"Power coefficient $C_p$")
    ax.set_title("Cp vs TSR at fixed rpm")
    ax.set_ylim(bottom=0)
    set_legend_outside(ax)

    # Panel 2: Free-running Cp vs wind speed - ALL branches
    ax = axes[1]
    if free:
        Us = np.array([f['U'] for f in free])
        cps = np.array([f['cp'] for f in free])
        ax.plot(Us, cps, LS_SOLID, color=COL_HIGH_BRANCH, lw=1.8,
                marker=MK_FREE, label="Branch-traced (continuation)")
    if high_branch and 'free_results' in high_branch:
        hfr = high_branch['free_results']
        if hfr:
            Uh = np.array([f['U'] for f in hfr])
            cph = np.array([f['cp'] for f in hfr])
            ax.plot(Uh, cph, LS_DASHED, color=COL_HIGH_BRANCH, lw=1.2,
                    marker=MK_HIGH, ms=4, label="High seed ($w_0=1.20$)")
    if low_branch and 'free_results' in low_branch:
        lfr = low_branch['free_results']
        if lfr:
            Ul = np.array([f['U'] for f in lfr])
            cpl = np.array([f['cp'] for f in lfr])
            ax.plot(Ul, cpl, LS_DOTTED, color=COL_LOW_BRANCH, lw=1.2,
                    marker=MK_LOW, ms=4, label="Low seed ($w_0=0.20$)")
    # Annotate branch switching at U=4 only when traced branch differs from seeds
    if free and len(Us) > 0:
        u4_idx = np.argmin(np.abs(Us - 4.0))
        if abs(Us[u4_idx] - 4.0) < 0.2 and len(cps) > u4_idx:
            traced_cp = cps[u4_idx]
            seed_diff = 0.0
            if high_branch and 'free_results' in high_branch and high_branch['free_results']:
                hfr = high_branch['free_results']
                uh_idx = np.argmin(np.abs(Uh - 4.0))
                if abs(Uh[uh_idx] - 4.0) < 0.2:
                    seed_diff = max(seed_diff, abs(traced_cp - cph[uh_idx]))
            if low_branch and 'free_results' in low_branch and low_branch['free_results']:
                lfr = low_branch['free_results']
                ul_idx = np.argmin(np.abs(Ul - 4.0))
                if abs(Ul[ul_idx] - 4.0) < 0.2:
                    seed_diff = max(seed_diff, abs(traced_cp - cpl[ul_idx]))
            if seed_diff > 0.01:
                ax.annotate('Branch switch:\ntraced → lower equil.\nseeds → upper equil.',
                            xy=(Us[u4_idx], cps[u4_idx]), xytext=(Us[u4_idx]+1.5, cps[u4_idx]+0.05),
                            fontsize=FONT_SIZE - 2, ha='left', va='bottom',
                            arrowprops={'arrowstyle': '->', 'color': 'k', 'lw': 1},
                            bbox={'boxstyle': 'round,pad=0.3', 'fc': 'yellow', 'ec': 'k', 'alpha': 0.9})
    # Branch envelope: only show when high/low seeds are distinct
    if (high_branch and low_branch and
        'free_results' in high_branch and 'free_results' in low_branch):
        hfr = high_branch['free_results']
        lfr = low_branch['free_results']
        if hfr and lfr:
            Uh = np.array([f['U'] for f in hfr])
            cph = np.array([f['cp'] for f in hfr])
            Ul = np.array([f['U'] for f in lfr])
            cpl = np.array([f['cp'] for f in lfr])
            if len(Uh) == len(Ul) and np.allclose(Uh, Ul):
                # Check if high/low are actually distinct
                if np.any(np.abs(cph - cpl) > 1e-4):
                    ax.fill_between(Uh, cpl, cph, color='gray', alpha=0.15,
                                    label="Branch envelope")
                else:
                    # Seeds converged - no envelope needed
                    pass
    ax.set_xlabel(r"Wind speed $U$ [m/s]")
    ax.set_ylabel(r"Cp at equilibrium")
    ax.set_title("Free-running Cp vs wind speed (all branches)")
    ax.set_ylim(bottom=0)
    ax.axvline(wind['cut_in'], color='k', ls=':', lw=1, alpha=0.5)
    ax.axvline(wind['rated_wind_speed'], color='k', ls=':', lw=1, alpha=0.5)
    set_legend_outside(ax, ncol=3)

    # Panel 3: Power curve with Weibull
    ax = axes[2]
    ax.plot(U_grid, P_passive / 1000, LS_SOLID, color=COL_PASSIVE_KLOAD, lw=2.0,
            label="Passive CPPC, $k_{load}$ (var. speed)")
    ax.plot(U_grid, P_fixed / 1000, LS_DASHED, color=COL_PASSIVE_FIXED, lw=1.8,
            label="Passive CPPC, fixed rpm")
    ax.set_xlabel(r"Wind speed $U$ [m/s]")
    ax.set_ylabel(r"Electrical power [kW]")
    ax.set_title("Power curve")
    ax.set_xlim(wind['cut_in'], wind['cut_out'])
    ax.set_ylim(bottom=0)
    pdf = weibull_pdf(U_grid, wind['mean_U'], wind['k_weibull'])
    add_weibull_axis(ax, U_grid, pdf, wind['mean_U'], wind['k_weibull'])
    ax.axhline(wind['p_rated_W'] / 1000, color='k', ls=':', lw=1, alpha=0.7,
               label=_fmt_rated(wind['p_rated_W']))
    ax.axvline(wind['cut_in'], color='k', ls=':', lw=1, alpha=0.5)
    ax.axvline(wind['rated_wind_speed'], color='k', ls=':', lw=1, alpha=0.5)
    set_legend_outside(ax, ncol=3)

    # Panel 4: AEP bar chart
    ax = axes[3]
    strategies = []
    aep_vals = []
    aep_low = []
    aep_high = []
    cf_vals = []
    rated_powers = []

    # Check if high/low seeds are effectively identical (within 0.01%)
    seeds_identical = False
    if high_branch and low_branch:
        aep_high_val = high_branch.get('aep_MWh', 0)
        aep_low_val = low_branch.get('aep_MWh', 0)
        if aep_high_val > 0 and abs(aep_high_val - aep_low_val) / aep_high_val < 1e-4:
            seeds_identical = True

    if traced_branch:
        strategies.append("Branch-\ntraced")
        aep_vals.append(traced_branch.get('aep_MWh', 0))
        cf_vals.append(traced_branch.get('cf', 0) * 100)
        aep_low.append(traced_branch.get('aep_MWh', 0))
        aep_high.append(traced_branch.get('aep_MWh', 0))
        rated_powers.append(wind.get('p_rated_W', 0) / 1000)

    if seeds_identical and high_branch:
        # Collapse identical high/low seeds into one "Seeds converged" bar
        strategies.append("Seeds\nconverged")
        aep_vals.append(high_branch.get('aep_MWh', 0))
        cf_vals.append(high_branch.get('cf', 0) * 100)
        aep_low.append(high_branch.get('aep_MWh', 0))
        aep_high.append(high_branch.get('aep_MWh', 0))
        rated_powers.append(wind.get('p_rated_W', 0) / 1000)
    else:
        if high_branch:
            strategies.append("High\nseed")
            aep_vals.append(high_branch.get('aep_MWh', 0))
            cf_vals.append(high_branch.get('cf', 0) * 100)
            aep_low.append(high_branch.get('aep_MWh', 0))
            aep_high.append(high_branch.get('aep_MWh', 0))
            rated_powers.append(wind.get('p_rated_W', 0) / 1000)
        if low_branch:
            strategies.append("Low\nseed")
            aep_vals.append(low_branch.get('aep_MWh', 0))
            cf_vals.append(low_branch.get('cf', 0) * 100)
            aep_low.append(low_branch.get('aep_MWh', 0))
            aep_high.append(low_branch.get('aep_MWh', 0))
            rated_powers.append(wind.get('p_rated_W', 0) / 1000)

    strategies.append("Fixed\nrpm")
    aep_vals.append(res_f.get('aep_MWh', 0))
    cf_vals.append(res_f.get('cf', 0) * 100)
    aep_low.append(res_f.get('aep_MWh', 0))
    aep_high.append(res_f.get('aep_MWh', 0))
    rated_powers.append(wind.get('p_rated_W', 0) / 1000)
    if rigid and rigid.get('aep_MWh') is not None:
        strategies.append("Rigid\nbaseline")
        aep_vals.append(rigid['aep_MWh'])
        cf_vals.append(rigid['cf'] * 100)
        aep_low.append(rigid['aep_MWh'])
        aep_high.append(rigid['aep_MWh'])
        rated_powers.append(rigid.get('rated_power_W', 0) / 1000)
    else:
        rated_powers = [wind.get('p_rated_W', 0) / 1000] * len(strategies)

    x = np.arange(len(strategies))
    colors = [COL_HIGH_BRANCH, COL_HIGH_BRANCH, COL_LOW_BRANCH, COL_PASSIVE_FIXED]
    if rigid and rigid.get('aep_MWh') is not None:
        colors.append(COL_RIGID)
    else:
        colors = colors[:len(strategies)]

    bars = ax.bar(x, aep_vals, color=colors[:len(strategies)], alpha=0.7,
                  edgecolor='k', lw=0.5, width=0.6)
    if len(aep_low) == len(aep_high) == len(aep_vals):
        yerr_low = np.array(aep_vals) - np.array(aep_low)
        yerr_high = np.array(aep_high) - np.array(aep_vals)
        if np.any(yerr_low > 0) or np.any(yerr_high > 0):
            ax.errorbar(x, aep_vals, yerr=[yerr_low, yerr_high],
                        fmt='none', color='k', capsize=4, lw=1)

    for i, (bar, aep, cf, p_rated) in enumerate(zip(bars, aep_vals, cf_vals, rated_powers)):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f"{aep:.1f} MWh\nCF={cf:.1f}%\n({p_rated:.1f} kW rated)",
                ha='center', va='bottom',
                fontsize=FONT_SIZE - 2, fontweight='bold')

    if rigid and rigid.get('aep_MWh') is not None and len(aep_vals) > 0:
        rigid_aep = rigid['aep_MWh']
        for i, aep in enumerate(aep_vals):
            if i < len(strategies) - 1 and rigid_aep > 0:
                gain = (aep / rigid_aep - 1.0) * 100
                ax.text(i, aep / 2, f"{gain:+.1f}%", ha='center', va='center',
                        fontsize=FONT_SIZE - 1, color='k', fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(strategies, fontsize=FONT_SIZE - 1)
    ax.set_ylabel("AEP [MWh/yr]")
    ax.set_title("AEP and capacity factor per strategy")
    ax.set_ylim(bottom=0, top=max(aep_vals) * 1.3 if aep_vals else 1)
    ax.grid(True, alpha=GRID_ALPHA, axis='y')

    title = fr"AEP — Passive CPPC, $R = {geo['R']:.2f}$ m, $H = {geo['H']:.2f}$ m"
    finalize_figure(fig, suptitle=title, rect=[0.06, 0.05, 0.93, 0.95])
    save_figure(fig, out_path)


def plot_aep_turbulent(data: dict[str, Any], out_path: str):
    apply_style()
    fig, axes = create_figure_3panel()
    _ax1, _ax2, _ax3 = axes

    steady = data['steady']
    turbulent = data['turbulent']
    pws = data.get('per_wind_speed', [])
    if not pws:
        raise ValueError(
            "aep_turbulent.json is missing per_wind_speed data. Regenerate with "
            "scripts/compute_aep_turbulent.py (current version stores per-wind-"
            "speed dicts with Cp_steady, Cp_turb_mean, Cp_turb_std). Do not plot "
            "empty arrays."
        )
    # per_wind_speed rows carry both steady and turbulent results at each U.
    U_s = np.array([d['U'] for d in pws])
    cp_s = np.array([d['Cp_steady'] for d in pws])
    U_t = np.array([d['U'] for d in pws])
    cp_t = np.array([d['Cp_turb_mean'] for d in pws])
    cp_t_std = np.array([d['Cp_turb_std'] for d in pws])

    ax = axes[0]
    ax.plot(U_s, cp_s, LS_SOLID, color=COL_PASSIVE_KLOAD, lw=1.8, marker=MK_FIXED,
            label="Steady wind")
    ax.errorbar(U_t, cp_t, yerr=cp_t_std, fmt='o', color=COL_HIGH_BRANCH,
                label=r"Turbulent (mean $\pm$ std)", capsize=3, lw=1.5)
    ax.set_xlabel(r"Wind speed $U$ [m/s]")
    ax.set_ylabel(r"Power coefficient $C_p$")
    ax.set_title("Cp vs wind speed")
    ax.set_ylim(bottom=0)
    set_legend_outside(ax)

    # Panel 2: AEP bar chart
    ax = axes[1]
    strategies = ["Steady", "Turbulent"]
    aep_vals = [steady['aep_kWh'] / 1000, turbulent['aep_kWh'] / 1000]
    cf_vals = [steady['cf'] * 100, turbulent['cf'] * 100]
    gain = (aep_vals[1] / aep_vals[0] - 1.0) * 100 if aep_vals[0] > 0 else 0

    x = np.arange(len(strategies))
    bars = ax.bar(x, aep_vals, color=[COL_PASSIVE_KLOAD, COL_HIGH_BRANCH],
                  alpha=0.7, edgecolor='k', lw=0.5, width=0.6)
    for i, (bar, aep, cf) in enumerate(zip(bars, aep_vals, cf_vals)):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                f"{aep:.1f} MWh\nCF={cf:.2f}%", ha='center', va='bottom',
                fontsize=FONT_SIZE - 1, fontweight='bold')
    ax.text(0.5, max(aep_vals) * 0.35, f"Turbulence effect:\n{gain:+.1f}%",
            ha='center', va='center', fontsize=FONT_SIZE,
            bbox={'boxstyle': "round,pad=0.4", 'fc': "wheat", 'ec': "k", 'alpha': 0.9})

    ax.set_xticks(x)
    ax.set_xticklabels(strategies)
    ax.set_ylabel("AEP [MWh/yr]")
    ax.set_title("AEP comparison")
    ax.set_ylim(bottom=0, top=max(aep_vals) * 1.3)
    ax.grid(True, alpha=GRID_ALPHA, axis='y')

    # Panel 3: Turbulence effect explanation (conditional on the actual results)
    ax = axes[2]
    # Idealised cube-bias reference: E[U^3]/(E[U])^3 for Gaussian turbulence
    # Under Gaussian assumption: E[U^3]/(E[U])^3 = 1 + 3*I^2 (no clipping, no limits)
    I = data['turbulence']['I']
    idealised_gain = (1.0 + 3.0 * I**2 - 1.0) * 100.0  # percent
    ax.text(0.5, 0.5,
            f"Turbulence effect: {gain:+.1f}% on AEP "
            f"({('gain' if gain >= 0 else 'loss')}).\n"
            f"Idealised reference (E[U^3]/E[U]^3, I={I:.2f}, no clipping/limits): "
            f"+{idealised_gain:.1f}%.\n"
            "Possible mechanisms (not established causation):\n"
            "1. Cube bias: E[U^3] > (E[U])^3 (Jensen)\n"
            "2. Cp(U) convexity: E[Cp(U)] > Cp(E[U])\n"
            "Vertical bars: seed-to-seed std (temporal variability), "
            "not a confidence interval.",
            ha='center', va='center', transform=ax.transAxes, fontsize=FONT_SIZE)
    ax.set_title("Turbulence effect (conditional on results)")
    ax.axis('off')

    title = f"AEP - Turbulent Wind (I = {data['turbulence']['I']*100:.0f}%, L = {data['turbulence']['L_m']:.0f} m)"
    finalize_figure(fig, suptitle=title)
    save_figure(fig, out_path)


def plot_aep_counter_rotating(data: dict[str, Any], out_path: str):
    apply_style()
    # Guard: refuse to render if speculative flags are absent from the data.
    config = data.get("configuration", {})
    if not config.get("speculative_scenario", False):
        raise ValueError(
            "aep_counter_rotating.json is missing 'speculative_scenario=True'; "
            "regenerate with scripts/compute_aep_counter_rotating.py"
        )
    if not config.get("not_a_validated_array_prediction", False):
        raise ValueError(
            "aep_counter_rotating.json is missing 'not_a_validated_array_prediction=True'; "
            "regenerate with scripts/compute_aep_counter_rotating.py"
        )
    fig, axes = create_figure_3panel()
    _ax1, _ax2, _ax3 = axes

    single = data['single_rotor_baseline']
    two_indep = data.get('two_independent_rotors', {})
    counter = data['counter_rotating']
    sensitivity = data.get('sensitivity_to_fixed_interaction_factor', [])

    # Panel 1: AEP comparison
    ax = axes[0]
    strategies = ["Single rotor", "Two\nindependent", "Counter-\nrotating"]
    aep_vals = [
        single['aep_kWh'] / 1000,
        two_indep.get('aep_kWh', 2 * single['aep_kWh']) / 1000,
        counter['total']['aep_kWh'] / 1000
    ]
    cf_vals = [single['capacity_factor'] * 100,
               two_indep.get('capacity_factor', single['capacity_factor']) * 100,
               counter['total']['capacity_factor'] * 100]

    x = np.arange(len(strategies))
    colors = [COL_PASSIVE_KLOAD, COL_PASSIVE_FIXED, COL_HIGH_BRANCH]
    bars = ax.bar(x, aep_vals, color=colors, alpha=0.7, edgecolor='k', lw=0.5, width=0.55)
    for i, (bar, aep, cf) in enumerate(zip(bars, aep_vals, cf_vals)):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f"{aep:.1f} MWh\nCF={cf:.1f}%", ha='center', va='bottom',
                fontsize=FONT_SIZE - 1, fontweight='bold')

    gain_vs_two = counter.get('vs_two_independent_rotors_improvement_percent', 0)
    # Place gain annotation at top of figure with offset to avoid bar labels
    y_top = max(aep_vals) * 1.15
    ax.text(0.5, y_top, f"Gain vs two independent:\n{gain_vs_two:+.1f}%",
            ha='center', va='bottom', fontsize=FONT_SIZE,
            bbox={'boxstyle': "round,pad=0.4", 'fc': "wheat", 'ec': "k", 'alpha': 0.9},
            transform=ax.get_yaxis_transform())

    ax.set_xticks(x)
    ax.set_xticklabels(strategies, fontsize=FONT_SIZE - 1)
    ax.set_ylabel("AEP [MWh/yr]")
    ax.set_title("AEP comparison")
    ax.set_ylim(bottom=0, top=max(aep_vals) * 1.35)
    ax.grid(True, alpha=GRID_ALPHA, axis='y')

    # Panel 2: Sensitivity to interaction factor
    ax = axes[1]
    if sensitivity:
        factors = [s['interaction_factor'] * 100 for s in sensitivity]
        aeps = [s['aep_kWh'] / 1000 for s in sensitivity]
        ax.plot(factors, aeps, LS_SOLID, color=COL_HIGH_BRANCH, lw=2.0, marker='o')
        ax.set_xlabel("Downstream interaction factor [%]")
        ax.set_ylabel("Total AEP [MWh/yr]")
        ax.set_title("Sensitivity to interaction factor")
        ax.grid(True, alpha=GRID_ALPHA)
        # Find the nominal model point (explicitly marked in sensitivity data)
        nominal_idx = next((i for i, s in enumerate(sensitivity) if s.get('is_nominal')), None)
        if nominal_idx is not None:
            annotate_with_arrow(ax, factors[nominal_idx], aeps[nominal_idx],
                                f"Nominal model\n(factor = {factors[nominal_idx]:.1f}%)",
                                xytext=(25, -15))
        else:
            # Fallback: annotate the point closest to the mean interaction factor
            mean_f = data['configuration'].get('interaction_factor_mean', 0) * 100
            nominal_idx = min(range(len(factors)), key=lambda i: abs(factors[i] - mean_f))
            annotate_with_arrow(ax, factors[nominal_idx], aep[nominal_idx],
                                f"Nearest evaluated\n(factor = {factors[nominal_idx]:.1f}%)",
                                xytext=(25, -15))

    # Panel 3: Model caveat
    ax = axes[2]
    ax.text(0.5, 0.5,
            "SPECULATIVE SCENARIO.\n"
            "Interaction model: heuristic momentum/wake/channeling.\n"
            "2D BEM cannot resolve 3D wake at 0.37D spacing.\n"
            f"Gain over two independent rotors: {gain_vs_two:+.1f}%\n"
            "NOT A VALIDATED ARRAY PREDICTION.",
            ha='center', va='center', transform=ax.transAxes, fontsize=FONT_SIZE)
    ax.set_title("Model caveat")
    ax.axis('off')

    title = "AEP - Counter-Rotating Pair (speculative, 0.37D spacing)"
    finalize_figure(fig, suptitle=title, rect=[0.06, 0.05, 0.98, 0.93])
    save_figure(fig, out_path)


def main():
    parser = argparse.ArgumentParser(description="Generate AEP plots from JSON results.")
    parser.add_argument("--json", required=True, help="Input JSON file")
    parser.add_argument("--out", required=True, help="Output PNG file")
    parser.add_argument("--type", choices=["auto", "small", "scaleup", "turbulent", "counter"],
                        default="auto", help="Plot type (auto-detect from JSON)")
    args = parser.parse_args()

    data = load_json(args.json)

    if args.type == "auto":
        if 'branches' in data:
            plot_type = "scaleup"
        elif 'turbulence' in data:
            plot_type = "turbulent"
        elif 'counter_rotating' in data:
            plot_type = "counter"
        else:
            plot_type = "small"
    else:
        plot_type = args.type

    if plot_type == "small":
        plot_aep_small_rotor(data, args.out)
    elif plot_type == "scaleup":
        plot_aep_scaleup(data, args.out)
    elif plot_type == "turbulent":
        plot_aep_turbulent(data, args.out)
    elif plot_type == "counter":
        plot_aep_counter_rotating(data, args.out)
    else:
        raise ValueError(f"Unknown plot type: {plot_type}")


if __name__ == "__main__":
    main()
