#!/usr/bin/env python3
"""Shared plotting style module for AEP figures."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 3-panel: 15 x 4.6 in  (was 15x4.6)
# 4-panel: 15 x 8   in  (was 15x8)
FIGSIZE_3PANEL = (15.0, 4.6)
FIGSIZE_4PANEL = (15.0, 8.0)

FONT_SIZE = 10
LEGEND_FONT_SIZE = 9
GRID_ALPHA = 0.3

LS_SOLID = "-"
LS_DASHED = "--"
LS_DOTTED = ":"

MK_FIXED = "o"
MK_FREE = "D"
MK_HIGH = "^"
MK_LOW = "v"

COL_PASSIVE_KLOAD = "#1f77b4"
COL_PASSIVE_FIXED = "#ff7f0e"
COL_HIGH_BRANCH = "#2ca02c"
COL_LOW_BRANCH = "#d62728"
COL_RIGID = "#9467bd"
COL_WEIBULL = "#8c564b"

def create_figure_3panel(**kwargs):
    """Create a 3-panel figure with a dedicated top suptitle region and bottom legend row.
    Uses constrained_layout=False with explicit GridSpec layout to reserve space
    for suptitle at top and legend at bottom, preventing overlap with subplot titles."""
    fig = plt.figure(figsize=FIGSIZE_3PANEL, constrained_layout=False, **kwargs)
    # Height ratios: [top_margin, 3 panels, bottom_legend]
    # Top margin (0.08) reserves space for suptitle; bottom (0.22) for legend
    gs = fig.add_gridspec(3, 3, height_ratios=[0.08, 1, 0.22], hspace=0.55, wspace=0.20)
    axes = [fig.add_subplot(gs[1, i]) for i in range(3)]
    legend_ax = fig.add_subplot(gs[2, :])
    legend_ax.axis("off")
    legend_ax.set_xticks([])
    legend_ax.set_yticks([])
    fig._legend_ax = legend_ax
    for ax in axes:
        ax.grid(True, alpha=GRID_ALPHA, linestyle="-")
        ax.axhline(0, color="k", lw=0.5)
    return fig, axes


def create_figure_4panel(**kwargs):
    """Create a 2x2 figure with a dedicated top suptitle region and bottom legend row."""
    fig = plt.figure(figsize=FIGSIZE_4PANEL, constrained_layout=False, **kwargs)
    # Height ratios: [top_margin, 2 rows of panels, bottom_legend]
    gs = fig.add_gridspec(4, 2, height_ratios=[0.06, 1, 1, 0.18], hspace=0.40, wspace=0.20)
    axes = [
        fig.add_subplot(gs[1, 0]),
        fig.add_subplot(gs[1, 1]),
        fig.add_subplot(gs[2, 0]),
        fig.add_subplot(gs[2, 1]),
    ]
    legend_ax = fig.add_subplot(gs[3, :])
    legend_ax.axis("off")
    legend_ax.set_xticks([])
    legend_ax.set_yticks([])
    fig._legend_ax = legend_ax
    for ax in axes:
        ax.grid(True, alpha=GRID_ALPHA, linestyle="-")
        ax.axhline(0, color="k", lw=0.5)
    return fig, axes


def add_weibull_axis(ax, U_grid, pdf, mean_U, k_weibull, color=COL_WEIBULL, label="Weibull pdf"):
    """Add Weibull pdf as secondary y-axis."""
    ax2 = ax.twinx()
    ax2.plot(U_grid, pdf, color=color, lw=1.2, ls=":", label=label)
    ax2.set_ylabel("Weibull pdf", color=color, fontsize=FONT_SIZE - 1)
    ax2.tick_params(axis='y', labelcolor=color, labelsize=FONT_SIZE - 1)
    ax2.set_ylim(bottom=0)
    ax2.set_xlim(auto=False)
    ax2.set_ylim(auto=True)
    return ax2


def set_legend_outside(ax, ncol=2):
    """Draw a single combined legend for all axes into the dedicated bottom
    legend row (GridSpec row reserved for legends).

    Collects handles/labels from every axes in the figure, de-duplicates by
    label, and places one legend in ``fig._legend_ax``.  Called once per panel;
    the last call wins and includes every axis plotted so far, so the final
    figure has exactly one non-overlapping legend below all panels.
    """
    fig = ax.figure
    legend_ax = getattr(fig, "_legend_ax", None)
    if legend_ax is None:
        # Fallback for figures built without the GridSpec legend row.
        ax.legend(fontsize=LEGEND_FONT_SIZE, loc="lower center",
                  bbox_to_anchor=(0.5, -0.30), ncol=ncol, framealpha=0.9)
        return
    legend_ax.clear()
    legend_ax.axis("off")
    handles, labels = [], []
    for a in fig.axes:
        if a is legend_ax:
            continue
        h, l = a.get_legend_handles_labels()
        handles.extend(h)
        labels.extend(l)
    seen = {}
    for h, l in zip(handles, labels):
        if l not in seen:
            seen[l] = h
    if seen:
        legend_ax.legend(
            list(seen.values()), list(seen.keys()),
            loc="center", ncol=ncol, frameon=False,
            fontsize=LEGEND_FONT_SIZE,
        )
    # Hide tick labels on legend axis to prevent overlap with legend
    legend_ax.set_xticks([])
    legend_ax.set_yticks([])


def annotate_with_arrow(ax, x, y, text, xytext=(10, 10), **kwargs):
    """Add annotation with arrow, avoiding data overlap."""
    default = {
        "arrowprops": {"arrowstyle": "->", "color": 'k', "lw": 1},
        "bbox": {"boxstyle": "round,pad=0.3", "fc": "wheat", "ec": "k", "alpha": 0.9},
        "ha": 'left', "va": 'bottom', "fontsize": FONT_SIZE - 1
    }
    default.update(kwargs)
    ax.annotate(text, xy=(x, y), xytext=xytext, **default)


def apply_style():
    """Apply global matplotlib style."""
    plt.rcParams.update({
        "font.size": FONT_SIZE,
        "axes.titlesize": FONT_SIZE + 1,
        "axes.labelsize": FONT_SIZE,
        "xtick.labelsize": FONT_SIZE - 1,
        "ytick.labelsize": FONT_SIZE - 1,
        "legend.fontsize": LEGEND_FONT_SIZE,
        "figure.dpi": 200,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.transparent": False,
    })


def finalize_figure(fig, suptitle="", rect=None):
    """Finalize figure layout and apply suptitle."""
    if suptitle:
        fig.suptitle(suptitle, fontsize=FONT_SIZE + 2, fontweight='bold', y=0.98)
    if rect:
        if isinstance(rect, list):
            # Convert list [left, bottom, right, top] to dict
            rect = {"left": rect[0], "bottom": rect[1], "right": rect[2], "top": rect[3]}
        fig.subplots_adjust(**rect)
    # Do not call tight_layout() - it conflicts with explicit GridSpec layout


def save_figure(fig, out_path):
    """Save figure to disk."""
    fig.savefig(out_path, dpi=200)
    plt.close(fig)