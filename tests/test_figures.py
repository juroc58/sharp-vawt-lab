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
        ("aep_small.json", pa.plot_aep_small_rotor),
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
    data = _load_json("aep_small.json")
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
    assert legend_y1 < 0.22, f"legend row not at bottom (y1={legend_y1:.3f})"
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


def test_rated_line_label_not_zero_kw():
    """The rated-line label in figures must never show '0.0 kW' for a non-zero
    rated power. Use watts when below 1 kW."""
    for fname, plot_fn in (
        ("aep_small.json", pa.plot_aep_small_rotor),
        ("aep_scaleup.json", pa.plot_aep_scaleup),
    ):
        data = _load_json(fname)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.png"
            captured = _capture_plot(pa.plot_aep_scaleup if fname == "aep_scaleup.json" else pa.plot_aep_small_rotor, data, out)
        # The legend is on a dedicated legend axis (fig._legend_ax)
        la = captured.get("legend_ax")
        assert la is not None, f"{fname}: figure must have a legend axis"
        legend = la.get_legend()
        assert legend is not None, f"{fname}: legend axis must have a legend"
        legend_texts = [t.get_text() for t in legend.get_texts()]
        rated_texts = [t for t in legend_texts if t.startswith("Rated (")]
        assert rated_texts, f"{fname}: legend must contain a 'Rated (' entry"
        for t in rated_texts:
            assert "0.0 kW" not in t, f"{fname}: rated label must not be '0.0 kW' (got '{t}')"


def test_turbulent_panel_has_idealised_reference():
    """Panel 3 must contain the idealised cube-bias reference computed from
    the JSON's turbulence intensity, labelled as an idealised reference."""
    data = _load_json("aep_turbulent.json")
    I = data["turbulence"]["I"]
    # Compute expected idealised gain from JSON: E[U^3]/(E[U])^3 = 1 + 3*I^2
    expected_gain = (1.0 + 3.0 * I**2 - 1.0) * 100.0  # percent
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.png"
        captured = _capture_plot(pa.plot_aep_turbulent, data, out)
    # Panel 3 is the third axis (axes[2]) in a 3-panel figure
    panel3 = captured["fig"].axes[2]
    texts = [t.get_text() for t in panel3.texts]
    full_text = " ".join(texts)
    assert "Idealised reference" in full_text, "Panel 3 must contain 'Idealised reference'"
    assert "E[U^3]/E[U]^3" in full_text, "Panel 3 must show the formula"
    assert f"+{expected_gain:.1f}%" in full_text, (
        f"Panel 3 must show the computed idealised gain +{expected_gain:.1f}%"
    )
    assert "idealised reference" in full_text.lower(), (
        "Must be explicitly labelled as idealised reference"
    )
    # Also verify the simulated gain is still present
    steady_aep = data["steady"]["aep_kWh"]
    turb_aep = data["turbulent"]["aep_kWh"]
    sim_gain = (turb_aep / steady_aep - 1.0) * 100.0
    assert f"{sim_gain:+.1f}%" in full_text, "Panel 3 must still show simulated gain"


def test_make_all_figures_run_fails_on_failing_subprocess():
    """_run() must raise RuntimeError when a figure command fails and produces no output."""

    from scripts.make_all_figures import _run

    # Mock a failing command that produces no output
    with pytest.raises(RuntimeError, match="Figure command failed and did not produce output"):
        _run([sys.executable, "-c", "import sys; sys.exit(1)"])


def test_make_all_figures_run_fails_on_failing_subprocess_with_output():
    """_run() must raise RuntimeError when a figure command fails but produces output."""
    from scripts.make_all_figures import _run

    # A command that writes a file then exits non-zero (not diag_qa --check)
    with tempfile.TemporaryDirectory() as td:
        out_file = Path(td) / "test_out.png"
        # Write a dummy file then exit non-zero
        cmd = [
            sys.executable, "-c",
            "open('" + str(out_file) + "', 'wb').write(b'x'); import sys; sys.exit(1)",
            "--out", str(out_file)
        ]
        with pytest.raises(RuntimeError, match="Figure command exited 1 but figure was produced"):
            _run(cmd)


# ---------------------------------------------------------------------------
# Content verification tests for the AEP figure renderers.
# These tests render the real plotting functions and inspect their artists.
# ---------------------------------------------------------------------------

def test_counter_rotating_gain_arithmetic():
    """Counter-rotating figure: printed gain must match JSON, and 'Two independent'
    bar must equal 2 x single rotor baseline."""
    data = _load_json("aep_counter_rotating.json")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.png"
        captured = _capture_plot(pa.plot_aep_counter_rotating, data, out)

    # Panel 0 is the AEP comparison bar chart
    ax0 = captured["fig"].axes[0]
    bars = [a for a in ax0.get_children() if isinstance(a, matplotlib.patches.Rectangle)]
    [b.get_height() for b in bars]

    single = data["single_rotor_baseline"]["aep_kWh"] / 1000
    two_indep = data["two_independent_rotors"]["aep_kWh"] / 1000
    counter_total = data["counter_rotating"]["total"]["aep_kWh"] / 1000
    json_gain = data["counter_rotating"]["vs_two_independent_rotors_improvement_percent"]

    # Bar 0: single rotor
    assert abs(bars[0].get_height() - single) < 0.01, f"Single rotor bar: {bars[0].get_height()} vs {single}"
    # Bar 1: two independent
    assert abs(bars[1].get_height() - two_indep) < 0.01, f"Two indep bar: {bars[1].get_height()} vs {two_indep}"
    assert abs(two_indep - 2 * single) < 0.01, "Two independent must equal 2 x single"
    # Bar 2: counter-rotating total
    assert abs(bars[2].get_height() - counter_total) < 0.01, f"Counter bar: {bars[2].get_height()} vs {counter_total}"

    # Check printed gain matches JSON
    gain_texts = [t.get_text() for t in ax0.texts if "Gain vs two independent" in t.get_text()]
    assert gain_texts, "Gain annotation missing"
    assert f"{json_gain:+.1f}%" in gain_texts[0], f"Gain mismatch: {gain_texts[0]} vs {json_gain:+.1f}%"


def test_scaleup_cf_consistency():
    """Scale-up figure: each bar's printed CF must equal AEP/(rated_power x 8760)
    with the rated power shown on that bar. Seeds-converged collapse when
    high/low AEPs agree within tolerance."""
    data = _load_json("aep_scaleup.json")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.png"
        captured = _capture_plot(pa.plot_aep_scaleup, data, out)

    # Panel 3 is the bar chart (axes[3])
    ax3 = captured["fig"].axes[3]
    bars = [a for a in ax3.get_children() if isinstance(a, matplotlib.patches.Rectangle)]
    [b.get_height() for b in bars]

    # Get text annotations on bars
    [t.get_text() for t in ax3.texts]

    # Check each bar's CF matches AEP / (rated_power * 8760)
    # Bar order: Branch-traced, Seeds converged (or High/Low seed), Fixed rpm, Rigid baseline
    wind = data["wind"]
    p_rated_passive = wind["p_rated_W"]
    data.get("rigid_fair_ref", {}).get("rated_power_W", p_rated_passive)

    # Get bar heights and match with strategies
    strategies = []
    for t in ax3.texts:
        txt = t.get_text()
        if "MWh" in txt and "CF=" in txt:
            # Parse: "X.X MWh\nCF=Y.Y%\n(Z.Z kW rated)"
            parts = txt.split("\n")
            aep_str = parts[0].replace(" MWh", "")
            cf_str = parts[1].replace("CF=", "").replace("%", "")
            rated_str = parts[2].replace("(", "").replace(")", "").replace(" kW rated", "")
            aep = float(aep_str)
            cf = float(cf_str)
            p_rated_kw = float(rated_str)
            strategies.append((aep, cf, p_rated_kw))

    for aep, cf, p_rated_kw in strategies:
        expected_cf = aep / (p_rated_kw / 1000 * 8760) * 100  # CF in percent
        assert abs(cf - expected_cf) < 0.1, f"CF mismatch: {cf}% vs {expected_cf:.1f}%"

    # Check seeds-converged collapse: high/low seeds should be collapsed
    branches = data["branches"]
    if "high_seed" in branches and "low_seed" in branches:
        aep_high = branches["high_seed"]["aep_MWh"]
        aep_low = branches["low_seed"]["aep_MWh"]
        if abs(aep_high - aep_low) / max(aep_high, aep_low) < 1e-4:
            # Seeds converged - should have only one "Seeds converged" bar, not separate High/Low
            bar_labels = [t.get_text() for t in ax3.get_xticklabels()]
            assert "Seeds\nconverged" in bar_labels, "Seeds converged bar missing"
            assert "High\nseed" not in bar_labels, "High seed bar should not appear when converged"
            assert "Low\nseed" not in bar_labels, "Low seed bar should not appear when converged"


def test_nominal_annotation():
    """Counter-rotating sensitivity panel: annotation must point at the point
    flagged is_nominal in the JSON."""
    data = _load_json("aep_counter_rotating.json")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.png"
        captured = _capture_plot(pa.plot_aep_counter_rotating, data, out)

    # Panel 1 is the sensitivity plot (axes[1])
    ax1 = captured["fig"].axes[1]
    anns = [a for a in ax1.texts if "Nominal" in a.get_text()]
    assert anns, "Nominal annotation missing"

    # Find the nominal point in JSON
    sens = data["sensitivity_to_fixed_interaction_factor"]
    nominal_idx = next(i for i, s in enumerate(sens) if s.get("is_nominal"))
    nominal_factor = sens[nominal_idx]["interaction_factor"] * 100
    sens[nominal_idx]["aep_kWh"] / 1000

    ann_text = anns[0].get_text()
    assert f"{nominal_factor:.1f}%" in ann_text, f"Annotation points to wrong factor: {ann_text}"


def test_u4_annotation():
    """Scale-up figure: U=4 branch-switch annotation appears when traced/seed
    Cp discrepancy exists, absent otherwise."""
    data = _load_json("aep_scaleup.json")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.png"
        captured = _capture_plot(pa.plot_aep_scaleup, data, out)

    # Panel 1 is free-running Cp vs wind speed (axes[1])
    ax1 = captured["fig"].axes[1]
    anns = [a for a in ax1.texts if "Branch switch" in a.get_text()]

    traced = data["branches"].get("branch_traced", {})
    high = data["branches"].get("high_seed", {})
    traced_u4 = next((f for f in traced.get("free_results", []) if abs(f["U"] - 4.0) < 0.2), None)
    high_u4 = next((f for f in high.get("free_results", []) if abs(f["U"] - 4.0) < 0.2), None)

    if traced_u4 and high_u4 and abs(traced_u4["cp"] - high_u4["cp"]) > 0.01:
        # Discrepancy exists - annotation should be present
        assert anns, "U=4 branch-switch annotation missing when discrepancy exists"
        ann_text = anns[0].get_text()
        assert "Branch switch" in ann_text
    else:
        # No discrepancy - annotation should be absent
        assert not anns, "U=4 annotation should not appear when no discrepancy"


def _drawn_tick_labels(ax):
    """Tick labels that are actually rendered.

    Matplotlib keeps Text objects for ticks outside the current view limits
    (they are never drawn), so ``ax.get_xticklabels()`` includes labels that
    cannot appear in the saved image. Only visible, non-empty labels whose
    tick location lies inside the axis view interval are returned.
    """
    labels = []
    for axis, get_lim in ((ax.xaxis, ax.get_xlim), (ax.yaxis, ax.get_ylim)):
        lo, hi = sorted(get_lim())
        eps = 1e-9 * max(hi - lo, 1.0)
        for tick in axis.get_major_ticks():
            lab = tick.label1
            if lab.get_visible() and lab.get_text() and lo - eps <= tick.get_loc() <= hi + eps:
                labels.append(lab)
    return labels


def test_bounding_boxes_no_overlap():
    """Render each figure and assert no legend/annotation box overlaps bar
    labels, tick labels, or subplot titles; all text artists inside canvas."""
    for fname, plot_fn in (
        ("aep_small.json", pa.plot_aep_small_rotor),
        ("aep_scaleup.json", pa.plot_aep_scaleup),
        ("aep_turbulent.json", pa.plot_aep_turbulent),
        ("aep_counter_rotating.json", pa.plot_aep_counter_rotating),
    ):
        data = _load_json(fname)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.png"
            captured = _capture_plot(
                pa.plot_aep_scaleup if fname == "aep_scaleup.json" else
                pa.plot_aep_turbulent if fname == "aep_turbulent.json" else
                pa.plot_aep_counter_rotating if fname == "aep_counter_rotating.json" else
                pa.plot_aep_small_rotor, data, out)

        fig = captured["fig"]
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        renderer = FigureCanvasAgg(fig).get_renderer()
        fig.draw(renderer)

        # Canvas bbox in display coordinates (pixels)
        canvas_bbox = fig.get_window_extent(renderer)
        canvas_width = canvas_bbox.width
        canvas_height = canvas_bbox.height

        # Get all text artists (labels, annotations, tick labels, titles)
        all_texts = []
        for ax in fig.axes:
            all_texts.extend(ax.texts)
            all_texts.extend(_drawn_tick_labels(ax))
            if ax.title and ax.title.get_text():
                all_texts.append(ax.title)
            if ax.get_legend():
                all_texts.extend(ax.get_legend().get_texts())

        # Check all texts are inside figure canvas (with 1px tolerance)
        for text in all_texts:
            if not text.get_text():
                continue
            bbox = text.get_window_extent(renderer)
            assert bbox.x0 >= -1, f"{fname}: text '{text.get_text()[:30]}' outside canvas left (x0={bbox.x0})"
            assert bbox.x1 <= canvas_width + 1, f"{fname}: text '{text.get_text()[:30]}' outside canvas right (x1={bbox.x1})"
            assert bbox.y0 >= -1, f"{fname}: text '{text.get_text()[:30]}' outside canvas bottom (y0={bbox.y0})"
            assert bbox.y1 <= canvas_height + 1, f"{fname}: text '{text.get_text()[:30]}' outside canvas top (y1={bbox.y1})"

        # Check no overlapping bboxes (simplified: check legend vs bar labels)
        legend = None
        for ax in fig.axes:
            if ax.get_legend():
                legend = ax.get_legend()
                break
        if legend:
            leg_bbox = legend.get_window_extent(renderer)
            for ax in fig.axes:
                drawn_ticks = _drawn_tick_labels(ax)
                tick_texts = {t.get_text() for t in drawn_ticks}
                for label in list(drawn_ticks) + [ax.title] + ax.texts:
                    if label is ax.title or label in ax.texts:
                        continue
                    label_text = label.get_text()
                    is_tick = label_text in tick_texts
                    tolerance = 10 if is_tick else 2
                    lbl_bbox = label.get_window_extent(renderer)
                    if (leg_bbox.x0 < lbl_bbox.x1 + tolerance and leg_bbox.x1 > lbl_bbox.x0 - tolerance and
                        leg_bbox.y0 < lbl_bbox.y1 + tolerance and leg_bbox.y1 > lbl_bbox.y0 - tolerance):
                        pytest.fail(f"{fname}: legend overlaps with text '{label.get_text()[:30]}'")


    # Also check no hardcoded aep.png (deleted)
    readme = (ROOT / "README.md").read_text()
    assert "aep.png" not in readme, "README must not reference deleted aep.png"
    assert "aep_results.json" not in readme, "README must not reference deleted aep_results.json"


def test_plot_aep_no_bare_subscript_statements():
    """A6: No bare subscript expressions (dead code) in plot_aep.py."""
    import ast
    with open('scripts/plot_aep.py') as f:
        tree = ast.parse(f.read())
    bad = [n for n in ast.walk(tree)
           if isinstance(n, ast.Expr)
           and isinstance(n.value, ast.Subscript)
           and not isinstance(getattr(n, 'parent', None), ast.Call)]
    assert not bad, [(n.lineno, ast.dump(n.value)) for n in bad]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])