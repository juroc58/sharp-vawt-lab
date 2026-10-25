"""Figure freshness, manifest coverage, and speculative-label tests."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import plot_aep as pa

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MANIFEST = DOCS / "figure_manifest.json"


def test_manifest_exists_and_covers_required_figures():
    assert MANIFEST.is_file(), "run scripts/make_all_figures.py"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest.get("schema") == 1
    figs = manifest.get("figures", {})
    from scripts.check_figures import REQUIRED
    missing = REQUIRED - set(figs)
    assert not missing, f"manifest missing: {sorted(missing)}"


def test_figures_match_manifest_and_sources():
    from scripts.check_figures import check
    problems = check()
    assert not problems, "\n".join(problems)


def test_figures_are_not_empty():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for name, rec in manifest["figures"].items():
        assert (DOCS / name).stat().st_size > 1000, f"{name} is suspiciously small"
        assert rec["bytes"] == (DOCS / name).stat().st_size


def test_counter_rotating_figure_is_labelled_speculative():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    labels = set(manifest["figures"]["aep_counter_rotating.png"].get("labels", []))
    assert {"SPECULATIVE SCENARIO", "NOT A VALIDATED ARRAY PREDICTION"} <= labels
    source = (ROOT / "scripts" / "plot_aep.py").read_text(encoding="utf-8")
    assert "SPECULATIVE SCENARIO" in source
    assert "NOT A VALIDATED ARRAY PREDICTION" in source


def test_manifest_is_cwd_independent():
    import os
    import subprocess
    import sys
    script = ROOT / "scripts" / "check_figures.py"
    result = subprocess.run(  # noqa: PLW1510 - returncode checked explicitly below
        [sys.executable, str(script)],
        cwd=os.path.dirname(str(ROOT)),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Content / layout tests for the AEP figure renderer.
# ---------------------------------------------------------------------------
def _load_json(name):
    return json.loads((ROOT / "scripts" / name).read_text())


def _capture_plot(plot_fn, data, out_path):
    """Call a plot function, capturing the Figure before save_figure closes it."""
    captured = {}

    def _capture_save(fig, path):
        captured["fig"] = fig
        fig.canvas.draw()
        st = getattr(fig, "_suptitle", None)
        captured["title"] = st.get_text() if st is not None else ""
        renderer = fig.canvas.get_renderer()
        captured["axes_positions"] = [
            (a.get_position(), a.get_window_extent(renderer)) for a in fig.axes
        ]
        la = getattr(fig, "_legend_ax", None)
        captured["legend_ax"] = la
        captured["legend_ax_pos"] = la.get_position() if la is not None else None
        captured["legend_ax_lines"] = len(la.get_lines()) if la is not None else None
        data_axes = [a for a in fig.axes if a is not la]
        captured["panel1_lines"] = [
            (line.get_label(), line.get_xdata().copy(), line.get_ydata().copy())
            for line in data_axes[0].get_lines()
        ] if data_axes else []
        orig_save(fig, path)  # closes fig

    orig_save = pa.save_figure
    pa.save_figure = _capture_save
    try:
        plot_fn(data, str(out_path))
    finally:
        pa.save_figure = orig_save
    return captured


def test_aep_titles_match_geometry():
    """Figure titles must come from authoritative JSON geometry, never a preset
    from a different design."""
    for fname, plot_fn in (
        ("aep_results.json", pa.plot_aep_small_rotor),
        ("aep_scaleup.json", pa.plot_aep_scaleup),
    ):
        data = _load_json(fname)
        geo = data["geometry"]
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.png"
            captured = _capture_plot(plot_fn, data, out)
        title = captured["title"]
        assert f"{geo['R']:.2f}" in title, title
        assert f"{geo['H']:.2f}" in title, title
        assert "Small-Rotor" not in title, title


def test_turbulent_panel_has_nonempty_finite_data():
    """Panel 1 must plot non-empty, finite Cp values that agree with JSON."""
    data = _load_json("aep_turbulent.json")
    pws = data["per_wind_speed"]
    assert len(pws) > 0
    for row in pws:
        assert np.isfinite(row["Cp_steady"])
        assert np.isfinite(row["Cp_turb_mean"])
        assert np.isfinite(row["Cp_turb_std"])
    expected_U = np.array([d["U"] for d in pws])
    expected_cp = np.array([d["Cp_steady"] for d in pws])
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.png"
        captured = _capture_plot(pa.plot_aep_turbulent, data, out)
    lines = captured["panel1_lines"]
    steady_lines = [l for l in lines if "Steady" in l[0]]
    assert len(steady_lines) >= 1, "panel 1 must plot the steady curve"
    _label, xs, ys = steady_lines[0]
    assert len(xs) == len(pws), (len(xs), len(pws))
    assert np.all(np.isfinite(xs)) and np.all(np.isfinite(ys))
    np.testing.assert_allclose(xs, expected_U)
    np.testing.assert_allclose(ys, expected_cp)


def test_missing_per_wind_speed_raises():
    """Missing per_wind_speed must raise explicitly, not plot empty arrays."""
    data = _load_json("aep_turbulent.json")
    bad = {k: v for k, v in data.items() if k != "per_wind_speed"}
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.png"
        with pytest.raises(ValueError, match="per_wind_speed"):
            pa.plot_aep_turbulent(bad, str(out))


def test_legend_row_reserved_and_no_tight_layout():
    """A dedicated GridSpec legend row must exist (empty of data lines), and
    saving must not rely on bbox_inches='tight'."""
    data = _load_json("aep_results.json")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.png"
        captured = _capture_plot(pa.plot_aep_small_rotor, data, out)
    la = captured["legend_ax"]
    assert la is not None, "no dedicated legend row"
    assert captured["legend_ax_lines"] == 0, "legend row must not carry data lines"
    # Legend row sits at the bottom of the figure; data axes extend above it.
    legend_y1 = captured["legend_ax_pos"].y1
    data_y1 = [pos.y1 for pos, _ in captured["axes_positions"]]
    assert data_y1, "no data axes"
    assert legend_y1 < 0.2, f"legend row not at bottom (y1={legend_y1:.3f})"
    assert max(data_y1) > legend_y1 + 0.05, "no data extends above legend row"
    # save_figure must not rely on bbox_inches='tight' (check only its body).
    source = (ROOT / "scripts" / "plot_style.py").read_text()
    savefig_body = source[source.index("def save_figure"):]
    assert "bbox_inches" not in savefig_body


def test_turbulent_variability_label_describes_std():
    """The turbulent variability label must describe the stored statistic
    (seed-to-seed std), not a confidence interval."""
    source = (ROOT / "scripts" / "plot_aep.py").read_text()
    assert "std" in source.lower(), "variability should be described as std"
    assert "not a confidence interval" in source.lower(), (
        "should explicitly disclaim confidence-interval interpretation"
    )
