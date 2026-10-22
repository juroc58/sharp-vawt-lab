#!/usr/bin/env python3
"""Plotting module for AEP figures.

Reads JSON results from compute_aep.py and compute_aep_scaleup.py
and generates publication-quality figures using shared style.

Usage:
    python3 scripts/plot_aep.py --json scripts/aep_results.json --out docs/aep.png
    python3 scripts/plot_aep.py --json scripts/aep_scaleup.json --out docs/aep_scaleup.png --scaleup
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Dict, Any, List, Tuple

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, _ROOT)

from plot_style import (
    apply_style, create_figure_3panel, create_figure_4panel,
    COL_PASSIVE_KLOAD, COL_PASSIVE_FIXED, COL_RIGID,
    COL_HIGH_BRANCH, COL_LOW_BRANCH, COL_WEIBULL,
    LS_SOLID, LS_DASHED, LS_DOTTED,
    MK_FIXED, MK_FREE, MK_HIGH, MK_LOW,
    add_weibull_axis, set_legend_outside, annotate_with_arrow,
    finalize_figure, save_figure,
    FONT_SIZE, GRID_ALPHA,
)

from vawt_presets import PRESETS


def load_json(path: str) -> Dict[str, Any]:
    with open(path) as fh:
        return json.load(fh)


def weibull_pdf(U, U_mean, k):
    lam = U_mean / math.gamma(1.0 + 1.0 / k)
    return (k / lam) * (U / lam) ** (k - 1.0) * np.exp(-(U / lam) ** k)


def plot_aep_small_rotor(data: Dict[str, Any], out_path: str):
    """Plot AEP for the small-rotor (R=0.60 m) from aep_results.json."""
    apply_style()
    fig, axes = create_figure_3panel()

    geo = data['geometry']
    wind = data['wind']
    res_p = data['results']['passive_k_load']
    res_f = data['results']['passive_fixed_rpm']
    rigid = data.get('rigid_fair_ref')

    R = geo['R']
    preset = PRESETS.get('sharp_cppc', {})
    H = preset.get('H', 0.40)

    tsrs = np.array(res_p['tsr'])
    cp_tsr = np.array(res_p['cp_tsr'])
    free = res_p.get('free_results', [])

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
    idx_best = int(np.argmax(cp_tsr))
    tsr_design = float(tsrs[idx_best])
    tsr_fixed = np.clip(tsr_design * wind['mean_U'] / U_grid, tsrs[0], tsrs[-1])
    cp_fixed = np.interp(tsr_fixed, tsrs, cp_tsr)

    P_passive = np.minimum(0.5 * 1.225 * A * U_grid ** 3 * np.clip(cp_passive, 0, 0.593) * 0.90, p_rated)
    P_fixed = np.minimum(0.5 * 1.225 * A * U_grid ** 3 * np.clip(cp_fixed, 0, 0.593) * 0.90, p_rated)

    # Panel 1: Cp vs TSR (fixed rpm) with both branches
    ax = axes[0]
    ax.plot(tsrs, cp_tsr, LS_SOLID, color=COL_PASSIVE_KLOAD, lw=1.8,
            marker=MK_FIXED, label="Passive CPPC (fixed rpm, phase-averaged)")
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
               label=f"Rated ({wind['p_rated_W']/1000:.1f} kW)")
    ax.axvline(wind['cut_in'], color='k', ls=':', lw=1, alpha=0.5)
    ax.axvline(wind['rated_wind_speed'], color='k', ls=':', lw=1, alpha=0.5)
    set_legend_outside(ax, ncol=2)

    title = fr"AEP - Small-Rotor CPPC, $R = {R:.2f}$ m"
    finalize_figure(fig, suptitle=title)
    save_figure(fig, out_path)


def plot_aep_scaleup(data: Dict[str, Any], out_path: str):
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
    H = geo.get('H', PRESETS['scaleup']['H'])
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
    idx_best = int(np.argmax(cp_tsr))
    tsr_design = float(tsrs[idx_best])
    tsr_fixed = np.clip(tsr_design * wind['mean_U'] / U_grid, tsrs[0], tsrs[-1])
    cp_fixed = np.interp(tsr_fixed, tsrs, cp_tsr)

    P_passive = np.minimum(0.5 * RHO * A * U_grid ** 3 * np.clip(cp_passive, 0, 0.593) * ETA, p_rated)
    P_fixed = np.minimum(0.5 * RHO * A * U_grid ** 3 * np.clip(cp_fixed, 0, 0.593) * ETA, p_rated)

    # For high/low branches
    cp_high = cp_passive
    cp_low = cp_passive
    if high_branch and 'free_results' in high_branch:
        hfr = high_branch['free_results']
        if hfr:
            Uh = np.array([f['U'] for f in hfr])
            cph = np.array([f['cp'] for f in hfr])
            cp_high = np.interp(U_grid, Uh, cph)
    if low_branch and 'free_results' in low_branch:
        lfr = low_branch['free_results']
        if lfr:
            Ul = np.array([f['U'] for f in lfr])
            cpl = np.array([f['cp'] for f in lfr])
            cp_low = np.interp(U_grid, Ul, cpl)

    P_high = np.minimum(0.5 * RHO * A * U_grid ** 3 * np.clip(cp_high, 0, 0.593) * ETA, p_rated)
    P_low = np.minimum(0.5 * RHO * A * U_grid ** 3 * np.clip(cp_low, 0, 0.593) * ETA, p_rated)

    # Panel 1: Cp vs TSR (fixed rpm) with both branches
    ax = axes[0]
    ax.plot(tsrs, cp_tsr, LS_SOLID, color=COL_PASSIVE_KLOAD, lw=1.8,
            marker=MK_FIXED, label="Passive CPPC (fixed rpm, phase-averaged)")
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
                ax.fill_between(Uh, cpl, cph, color='gray', alpha=0.15,
                                label="Branch envelope")
    ax.set_xlabel(r"Wind speed $U$ [m/s]")
    ax.set_ylabel(r"Cp at equilibrium")
    ax.set_title("Free-running Cp vs wind speed (all branches)")
    ax.set_ylim(bottom=0)
    ax.axvline(wind['cut_in'], color='k', ls=':', lw=1, alpha=0.5)
    ax.axvline(wind['rated_wind_speed'], color='k', ls=':', lw=1, alpha=0.5)
    set_legend_outside(ax, ncol=2)

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
               label=f"Rated ({wind['p_rated_W']/1000:.1f} kW)")
    ax.axvline(wind['cut_in'], color='k', ls=':', lw=1, alpha=0.5)
    ax.axvline(wind['rated_wind_speed'], color='k', ls=':', lw=1, alpha=0.5)
    set_legend_outside(ax, ncol=2)

    # Panel 4: AEP bar chart
    ax = axes[3]
    strategies = []
    aep_vals = []
    aep_low = []
    aep_high = []
    cf_vals = []

    if traced_branch:
        strategies.append("Branch-\ntraced")
        aep_vals.append(traced_branch.get('aep_MWh', 0))
        cf_vals.append(traced_branch.get('cf', 0) * 100)
        aep_low.append(traced_branch.get('aep_MWh', 0))
        aep_high.append(traced_branch.get('aep_MWh', 0))
    if high_branch:
        strategies.append("High\nseed")
        aep_vals.append(high_branch.get('aep_MWh', 0))
        cf_vals.append(high_branch.get('cf', 0) * 100)
        aep_low.append(high_branch.get('aep_MWh', 0))
        aep_high.append(high_branch.get('aep_MWh', 0))
    if low_branch:
        strategies.append("Low\nseed")
        aep_vals.append(low_branch.get('aep_MWh', 0))
        cf_vals.append(low_branch.get('cf', 0) * 100)
        aep_low.append(low_branch.get('aep_MWh', 0))
        aep_high.append(low_branch.get('aep_MWh', 0))
    strategies.append("Fixed\nrpm")
    aep_vals.append(res_f.get('aep_MWh', 0))
    cf_vals.append(res_f.get('cf', 0) * 100)
    aep_low.append(res_f.get('aep_MWh', 0))
    aep_high.append(res_f.get('aep_MWh', 0))
    if rigid and rigid.get('aep_MWh') is not None:
        strategies.append("Rigid\nbaseline")
        aep_vals.append(rigid['aep_MWh'])
        cf_vals.append(rigid['cf'] * 100)
        aep_low.append(rigid['aep_MWh'])
        aep_high.append(rigid['aep_MWh'])

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

    for i, (bar, aep, cf) in enumerate(zip(bars, aep_vals, cf_vals)):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f"{aep:.1f} MWh\nCF={cf:.1f}%", ha='center', va='bottom',
                fontsize=FONT_SIZE - 1, fontweight='bold')

    if rigid and rigid.get('aep_MWh') is not None and len(aep_vals) > 0:
        rigid_aep = rigid['aep_MWh']
        for i, aep in enumerate(aep_vals):
            if i < len(strategies) - 1 and rigid_aep > 0:
                gain = (aep / rigid_aep - 1.0) * 100
                ax.text(i, aep_vals[i] / 2, f"{gain:+.1f}%", ha='center', va='center',
                        fontsize=FONT_SIZE - 1, color='k', fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(strategies, fontsize=FONT_SIZE - 1)
    ax.set_ylabel("AEP [MWh/yr]")
    ax.set_title("AEP and capacity factor per strategy")
    ax.set_ylim(bottom=0, top=max(aep_vals) * 1.3 if aep_vals else 1)
    ax.grid(True, alpha=GRID_ALPHA, axis='y')

    title = fr"AEP - Scale-Up CPPC, $R = {geo['R']:.2f}$ m, AR $\approx$ {geo.get('AR', H/geo['c']):.1f}"
    finalize_figure(fig, suptitle=title, rect=[0, 0.05, 1, 0.95])
    save_figure(fig, out_path)


def plot_aep_turbulent(data: Dict[str, Any], out_path: str):
    apply_style()
    fig, axes = create_figure_3panel()
    ax1, ax2, ax3 = axes

    wind = data['wind']
    steady = data['steady']
    turbulent = data['turbulent']

    # Panel 1: Cp vs U
    ax = axes[0]
    spd = steady.get('per_wind_speed', [])
    tpd = turbulent.get('per_wind_speed', [])
    U_s = np.array([u for u, _, _, _ in spd])
    cp_s = np.array([cp for _, _, cp, _ in spd])
    U_t = np.array([u for u, _, _, _, _, _ in tpd])
    cp_t = np.array([cp for _, _, _, cp, _, _ in tpd])
    cp_t_std = np.array([std for _, _, _, _, std, _ in tpd])

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
    ax.text(0.5, max(aep_vals) * 0.6, f"Turbulence effect:\n{gain:+.1f}%",
            ha='center', va='center', fontsize=FONT_SIZE,
            bbox=dict(boxstyle="round,pad=0.4", fc="wheat", ec="k", alpha=0.9))

    ax.set_xticks(x)
    ax.set_xticklabels(strategies)
    ax.set_ylabel("AEP [MWh/yr]")
    ax.set_title("AEP comparison")
    ax.set_ylim(bottom=0, top=max(aep_vals) * 1.3)
    ax.grid(True, alpha=GRID_ALPHA, axis='y')

    # Panel 3: Turbulence effect explanation
    ax = axes[2]
    ax.text(0.5, 0.5,
            "Turbulence gives a net gain from:\n"
            "1. Cube bias: E[U^3] > (E[U])^3 (Jensen)\n"
            "2. Cp(U) convexity: E[Cp(U)] > Cp(E[U])\n"
            "Real turbines lose 2-8% to 3D effects",
            ha='center', va='center', transform=ax.transAxes, fontsize=FONT_SIZE)
    ax.set_title("Why turbulence gives a gain")
    ax.axis('off')

    title = f"AEP - Turbulent Wind (I = {data['turbulence']['I']*100:.0f}%, L = {data['turbulence']['L_m']:.0f} m)"
    finalize_figure(fig, suptitle=title)
    save_figure(fig, out_path)


def plot_aep_counter_rotating(data: Dict[str, Any], out_path: str):
    apply_style()
    fig, axes = create_figure_3panel()
    ax1, ax2, ax3 = axes

    single = data['single_rotor_baseline']
    counter = data['counter_rotating']
    sensitivity = data.get('sensitivity_to_fixed_interaction_factor', [])

    # Panel 1: AEP comparison
    ax = axes[0]
    strategies = ["Single rotor", "Two independent", "Counter-rotating"]
    aep_vals = [
        single['aep_kWh'] / 1000,
        (counter['upstream_rotor']['aep_kWh'] + counter['downstream_rotor']['aep_kWh']) / 1000,
        counter['total']['aep_kWh'] / 1000
    ]
    cf_vals = [single['capacity_factor'] * 100,
               (counter['upstream_rotor']['capacity_factor'] + counter['downstream_rotor']['capacity_factor']) / 2 * 100,
               counter['total']['capacity_factor'] * 100]

    x = np.arange(len(strategies))
    colors = [COL_PASSIVE_KLOAD, COL_PASSIVE_FIXED, COL_HIGH_BRANCH]
    bars = ax.bar(x, aep_vals, color=colors, alpha=0.7, edgecolor='k', lw=0.5, width=0.6)
    for i, (bar, aep, cf) in enumerate(zip(bars, aep_vals, cf_vals)):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f"{aep:.1f} MWh\nCF={cf:.1f}%", ha='center', va='bottom',
                fontsize=FONT_SIZE - 1, fontweight='bold')

    gain_vs_two = counter.get('vs_two_independent_rotors_improvement_percent', 0)
    ax.text(0.5, max(aep_vals) * 0.6, f"Gain vs two independent:\n{gain_vs_two:+.1f}%",
            ha='center', va='center', fontsize=FONT_SIZE,
            bbox=dict(boxstyle="round,pad=0.4", fc="wheat", ec="k", alpha=0.9))

    ax.set_xticks(x)
    ax.set_xticklabels(strategies)
    ax.set_ylabel("AEP [MWh/yr]")
    ax.set_title("AEP comparison")
    ax.set_ylim(bottom=0, top=max(aep_vals) * 1.3)
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
        nominal_idx = next((i for i, f in enumerate(factors)
                           if abs(f - data['configuration'].get('interaction_factor_mean', 0)*100) < 1), 0)
        annotate_with_arrow(ax, factors[nominal_idx], aeps[nominal_idx],
                            f"Nominal model\n(factor = {factors[nominal_idx]:.1f}%)")

    # Panel 3: Model caveat
    ax = axes[2]
    ax.text(0.5, 0.5,
            "Counter-rotating pair is a SPECULATIVE SCENARIO.\n"
            "Interaction model: heuristic momentum/wake/channeling.\n"
            "2D BEM cannot resolve 3D wake at 0.37D spacing.\n"
            "Gain over two independent rotors: +2.8%\n"
            "Not a validated array prediction.",
            ha='center', va='center', transform=ax.transAxes, fontsize=FONT_SIZE)
    ax.set_title("Model caveat")
    ax.axis('off')

    title = "AEP - Counter-Rotating Pair (speculative, 0.37D spacing)"
    finalize_figure(fig, suptitle=title)
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
