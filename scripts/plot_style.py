"""Shared plotting style for all AEP figures."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import os


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
        'savefig.bbox': 'tight',
        'savefig.transparent': False,
    })


def create_figure_3panel(**kwargs):
    """Create a 3-panel figure with shared style."""
    fig, axes = plt.subplots(1, 3, figsize=FIGSIZE_3PANEL, **kwargs)
    for ax in axes:
        ax.grid(True, alpha=GRID_ALPHA, linestyle='-')
        ax.axhline(0, color='k', lw=0.5)
    return fig, axes


def create_figure_4panel(**kwargs):
    """Create a 2x2 figure with shared style."""
    fig, axes = plt.subplots(2, 2, figsize=FIGSIZE_4PANEL, **kwargs)
    axes = axes.flatten()
    for ax in axes:
        ax.grid(True, alpha=GRID_ALPHA, linestyle='-')
        ax.axhline(0, color='k', lw=0.5)
    return fig, axes


def add_weibull_axis(ax, U_grid, pdf, mean_U, k_weibull, color=COL_WEIBULL, label="Weibull pdf"):
    """Add Weibull pdf as secondary y-axis."""
    ax2 = ax.twinx()
    ax2.fill_between(U_grid, 0, pdf, alpha=0.15, color=color, label=label)
    ax2.set_ylabel("pdf [1/m/s]", color=color, fontsize=FONT_SIZE - 1)
    ax2.tick_params(axis='y', labelcolor=color, labelsize=FONT_SIZE - 1)
    ax2.set_ylim(0, ax2.get_ylim()[1] * 1.1)
    # Combine legends
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    if lines1 or lines2:
        ax.legend(lines1 + lines2, labels1 + labels2, fontsize=LEGEND_FONT_SIZE, loc='upper left')
    return ax2


def set_legend_outside(ax, loc='lower center', bbox_to_anchor=(0.5, -0.25), ncol=2):
    """Place legend below the axes."""
    ax.legend(fontsize=LEGEND_FONT_SIZE, loc=loc, bbox_to_anchor=bbox_to_anchor, ncol=ncol, framealpha=0.9)


def annotate_with_arrow(ax, x, y, text, xytext=(10, 10), **kwargs):
    """Add annotation with arrow, avoiding data overlap."""
    default = dict(
        arrowprops=dict(arrowstyle="->", color='k', lw=1),
        bbox=dict(boxstyle="round,pad=0.3", fc="wheat", ec="k", alpha=0.9),
        ha='left', va='bottom', fontsize=FONT_SIZE - 1
    )
    default.update(kwargs)
    ax.annotate(text, xy=(x, y), xytext=xytext, textcoords='offset points', **default)


def finalize_figure(fig, suptitle=None, rect=None):
    """Apply final layout adjustments."""
    if suptitle:
        fig.suptitle(suptitle, fontsize=FONT_SIZE_SUP, fontweight='bold')
    if rect is None:
        rect = [0, 0.08, 1, 0.95] if suptitle else [0, 0.05, 1, 0.98]
    fig.tight_layout(rect=rect)
    return fig


def save_figure(fig, path):
    """Save figure with consistent settings."""
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f"  Wrote {path}")


import os