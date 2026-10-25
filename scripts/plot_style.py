"""Shared plotting style for all AEP figures."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import os

import matplotlib.pyplot as plt

# Colour map (consistent across all figures)
COL_PASSIVE_KLOAD = "C0"      # blue - passive CPPC, variable speed
COL_PASSIVE_FIXED = "C2"      # green - passive CPPC, fixed rpm
COL_RIGID = "C7"              # grey - rigid blade baseline
COL_HIGH_BRANCH = "C1"        # orange - high Cp branch
COL_LOW_BRANCH = "C4"         # purple - low Cp branch
COL_WEIBULL = "C3"            # red - Weibull pdf

# Line styles
LS_SOLID = "-"
LS_DASHED = "--"
LS_DOTTED = ":"

# Markers
MK_FIXED = "o"
MK_FREE = "s"
MK_HIGH = "^"
MK_LOW = "v"

# Sizes
FIGSIZE_3PANEL = (15, 4.6)
FIGSIZE_4PANEL = (15, 8)
DPI = 200
FONT_SIZE = 10
FONT_SIZE_TITLE = 12
FONT_SIZE_SUP = 13
LEGEND_FONT_SIZE = 9
GRID_ALPHA = 0.3


def apply_style():
    """Apply consistent matplotlib style."""
    plt.rcParams.update({
        'font.size': FONT_SIZE,
        'axes.titlesize': FONT_SIZE_TITLE,
        'axes.labelsize': FONT_SIZE,
        'xtick.labelsize': FONT_SIZE - 1,
        'ytick.labelsize': FONT_SIZE - 1,
        'legend.fontsize': LEGEND_FONT_SIZE,
        'figure.titlesize': FONT_SIZE_SUP,
        'axes.grid': True,
        'grid.alpha': GRID_ALPHA,
        'grid.linestyle': '-',
        'axes.axisbelow': True,
        'lines.linewidth': 1.6,
        'lines.markersize': 5,
        'savefig.dpi': DPI,
        'savefig.transparent': False,
    })


def create_figure_3panel(**kwargs):
    """Create a 3-panel figure with constrained layout and a dedicated bottom
    legend row (GridSpec height_ratios reserve real space for legends so they
    never overlap axis labels, subplot titles, or neighbouring panels)."""
    fig = plt.figure(figsize=FIGSIZE_3PANEL, constrained_layout=True, **kwargs)
    gs = fig.add_gridspec(2, 3, height_ratios=[1, 0.10], hspace=0.30, wspace=0.20)
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    legend_ax = fig.add_subplot(gs[1, :])
    legend_ax.axis("off")
    fig._legend_ax = legend_ax
    for ax in axes:
        ax.grid(True, alpha=GRID_ALPHA, linestyle="-")
        ax.axhline(0, color="k", lw=0.5)
    return fig, axes


def create_figure_4panel(**kwargs):
    """Create a 2x2 figure with constrained layout and a dedicated bottom
    legend row (GridSpec height_ratios reserve real space for legends)."""
    fig = plt.figure(figsize=FIGSIZE_4PANEL, constrained_layout=True, **kwargs)
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.10], hspace=0.30, wspace=0.20)
    axes = [
        fig.add_subplot(gs[0, 0]),
        fig.add_subplot(gs[0, 1]),
        fig.add_subplot(gs[1, 0]),
        fig.add_subplot(gs[1, 1]),
    ]
    legend_ax = fig.add_subplot(gs[2, :])
    legend_ax.axis("off")
    fig._legend_ax = legend_ax
    for ax in axes:
        ax.grid(True, alpha=GRID_ALPHA, linestyle="-")
        ax.axhline(0, color="k", lw=0.5)
    return fig, axes


def add_weibull_axis(ax, U_grid, pdf, mean_U, k_weibull, color=COL_WEIBULL, label="Weibull pdf"):
    """Add Weibull pdf as secondary y-axis."""
    ax2 = ax.twinx()
    ax2.fill_between(U_grid, 0, pdf, alpha=0.15, color=color, label=label)
    ax2.set_ylabel("pdf [1/m/s]", color=color, fontsize=FONT_SIZE - 1)
    ax2.tick_params(axis='y', labelcolor=color, labelsize=FONT_SIZE - 1)
    ax2.set_ylim(0, ax2.get_ylim()[1] * 1.1)
    # Weibull handle is collected into the shared bottom legend by
    # set_legend_outside; do not draw a competing inside-axes legend here.
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


def annotate_with_arrow(ax, x, y, text, xytext=(10, 10), **kwargs):
    """Add annotation with arrow, avoiding data overlap."""
    default = {
        "arrowprops": {"arrowstyle": "->", "color": 'k', "lw": 1},
        "bbox": {"boxstyle": "round,pad=0.3", "fc": "wheat", "ec": "k", "alpha": 0.9},
        "ha": 'left', "va": 'bottom', "fontsize": FONT_SIZE - 1
    }
    default.update(kwargs)
    ax.annotate(text, xy=(x, y), xytext=xytext, textcoords='offset points', **default)


def finalize_figure(fig, suptitle=None, rect=None):
    """Apply final layout adjustments.

    Constrained layout (enabled at figure creation) handles spacing; do NOT
    call tight_layout here (incompatible with constrained_layout) and do not
    rely on bbox_inches='tight' at save time (that changes the saved bounding
    box rather than reserving real space).
    """
    if suptitle:
        fig.suptitle(suptitle, fontsize=FONT_SIZE_SUP, fontweight='bold')
    return fig


def save_figure(fig, path):
    """Save figure with consistent settings."""
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print(f"  Wrote {path}")


