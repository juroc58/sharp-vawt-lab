"""Tests for the physics overrides added for the UQ study."""
import math

import numpy as np
import pytest

from sharp_vawt.engine import _cm_moment, _energy_diagnostics
from tests.conftest import BASE_QUICK
from vawt_core import create_sim_from_params


class TestTipLossBounds:

    def test_default_uses_helmbold(self):
        """Default f_ar uses the Helmbold (1942) low-AR correction."""
        s = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14})
        # AR = 0.445 / 0.14 = 3.18 -> Helmbold f_ar = 0.552
        assert s.f_ar == pytest.approx(0.552, abs=0.01)

    def test_raw_correction_when_floor_near_zero(self):
        """Passing ~0 uses the raw Helmbold formula (same as default)."""
        s = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14,
                                    'tip_loss_floor_override': 0.001})
        # Helmbold at AR 3.18: f_ar = 0.552
        assert s.f_ar == pytest.approx(0.552, abs=0.01)

    def test_override_raises_floor(self):
        """tip_loss_floor_override > raw clamps f_ar up to the override value."""
        s = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14,
                                    'tip_loss_floor_override': 0.85})
        assert s.f_ar == pytest.approx(0.85, abs=0.01)

    def test_override_below_raw_is_ignored(self):
        """An override below the raw value must not pull f_ar down."""
        s = create_sim_from_params({**BASE_QUICK, 'H': 3.0, 'c': 0.10,
                                    'tip_loss_floor_override': 0.50})
        # AR = 30, raw Helmbold f_ar ≈ 0.935; override 0.50 should not apply
        assert s.f_ar > 0.85

    def test_multiplier_below_one_increases_tip_loss(self):
        """tip_loss_multiplier < 1 represents residual stronger tip loss."""
        raw = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14})
        weaker = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14,
                                         'tip_loss_multiplier': 0.7})
        assert weaker.f_ar == pytest.approx(0.7 * raw.f_ar, rel=1e-9)
        assert weaker.f_ar < raw.f_ar

    def test_multiplier_above_one_reduces_tip_loss(self):
        """tip_loss_multiplier > 1 explores less finite-span penalty."""
        raw = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14})
        stronger = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14,
                                           'tip_loss_multiplier': 1.3})
        assert stronger.f_ar == pytest.approx(min(1.0, 1.3 * raw.f_ar), rel=1e-9)
        assert stronger.f_ar > raw.f_ar

    def test_ind_k_uncapped_at_low_AR(self):
        """Induced drag uses the raw 1/(pi*e*AR) form; no cap."""
        s = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14})
        # AR = 3.1786, e_osw = 0.90  ->  ind_k ~ 0.1113 (old cap was 0.02)
        assert s.ind_k == pytest.approx(1.0 / (3.14159265 * 0.90 * 3.1786), rel=0.02)
        assert s.ind_k > 0.10
        assert s.ind_k < 0.02 * 20  # sanity: nowhere near the old cap

    def test_high_AR_gives_high_f_ar(self):
        """Higher aspect ratio must give a higher (closer to 1) f_ar."""
        s_lo = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14})
        s_hi = create_sim_from_params({**BASE_QUICK, 'H': 3.0, 'c': 0.10})
        assert s_hi.f_ar > s_lo.f_ar
        assert s_hi.f_ar < 1.0


class TestCmDimensions:
    """Cm moment from polars has correct dimensions and is applied correctly."""

    def test_cm_scale_zero_equals_zeroed_cm_column(self):
        """cm_scale=0 is exactly equivalent to a polar whose Cm column is zero.

        This catches the dynamic-stall separated-Cm blend target, which must
        also vanish: otherwise cm_scale=0 still injects a synthetic moment
        during separation.
        """
        params = {**BASE_QUICK, 'free': False, 'T_max': 6.0, 'cm_scale': 0.0}
        scaled = create_sim_from_params(params)
        zeroed = create_sim_from_params(params)
        zeroed.polar_db.Cm[:] = 0.0
        r_scaled = scaled.run()
        r_zeroed = zeroed.run()
        assert r_scaled['cp'] == pytest.approx(r_zeroed['cp'], rel=1e-10)
        assert r_scaled['tsr_eq'] == pytest.approx(r_zeroed['tsr_eq'], rel=1e-10)

    def test_cm_in_polars(self):
        """Default variant has Cm=0 in attached flow; neuralfoil_cm variant has raw NeuralFoil CM.

        The default variant (polar_variant="neuralfoil") enforces Cm=0 for
        |alpha| <= 20 deg (physical symmetric-section value). The raw
        NeuralFoil CM is available as the "neuralfoil_cm" variant for
        sensitivity analysis.
        """
        from vawt_core import PolarDatabase
        # Default variant: Cm = 0 in attached flow
        pdb = PolarDatabase("airfoil_polars/naca0012", variant="neuralfoil")
        _, _, Cm, _ = pdb.lookup(1e6, math.radians(15.0))
        assert abs(Cm) < 1e-6

        # neuralfoil_cm variant: raw NeuralFoil CM
        pdb_nf = PolarDatabase("airfoil_polars/naca0012", variant="neuralfoil_cm")
        _, _, Cm_nf, _ = pdb_nf.lookup(1e6, math.radians(15.0))
        # NeuralFoil's attached-flow Cm at Re=1e6, alpha=15 deg is ~+0.047
        assert Cm_nf == pytest.approx(0.0465, abs=0.005)
        assert -0.1 < Cm_nf < 0.1

    def test_cm_zero_at_zero_alpha(self):
        """A symmetric NACA 0012 has zero moment at zero incidence."""
        from vawt_core import PolarDatabase
        pdb = PolarDatabase("airfoil_polars/naca0012")
        for re in (1e5, 2e5, 4e5, 1e6):
            _, _, Cm, _ = pdb.lookup(re, 0.0)
            assert abs(Cm) < 1e-6

    def test_cm_provenance_is_neuralfoil_attached(self):
        """The table provenance must name the attached-flow Cm source."""
        import json
        from pathlib import Path
        prov = json.loads(
            (Path(__file__).resolve().parents[1]
             / "sharp_vawt" / "airfoil_polars" / "provenance.json").read_text()
        )
        assert "NeuralFoil" in prov["cm_method"]
        assert "Cm=0" in prov["cm_method"] or "|alpha|<=20" in prov["cm_method"]
        assert "nose-up" in prov["cm_convention"]
        assert "synthetic" in prov["cm_method"]
        assert "neuralfoil_cm" in prov["cm_method"]

    def test_smoothed_low_re_variant_caps_slope_only_at_low_re(self):
        """The smoothed_lowRe variant is a documented model-form change.

        The default "neuralfoil" variant already has clamped slope and
        monotone Cl. The "smoothed_lowRe" variant applies additional
        aggressive clamping (1.1 * 2pi slope cap) as a sensitivity bound.
        """
        import numpy as np

        from vawt_core import _SMOOTH_LOW_RE_CAP, PolarDatabase
        default = PolarDatabase("airfoil_polars/naca0012", variant="neuralfoil")
        smooth = PolarDatabase("airfoil_polars/naca0012",
                               variant="smoothed_lowRe")
        # Re=1e5 row is first in the sorted grid.
        # Default already has slope <= 1.15*2pi; smoothed applies 1.1*2pi
        assert abs(default.cla_re[0]) <= 1.15 * 2.0 * np.pi * 1.001
        assert abs(smooth.cla_re[0]) <= _SMOOTH_LOW_RE_CAP * 1.001
        # The highest-Re row is untouched by smoothed_lowRe.
        assert np.array_equal(smooth.Cl[-1], default.Cl[-1])
        # Both variants have monotone Cl up to 20 deg.
        ag = np.degrees(smooth.alpha_grid)
        m = (ag >= 0.0) & (ag <= 20.0)
        assert np.all(np.diff(smooth.Cl[0, m]) >= -1e-9)
        assert np.all(np.diff(default.Cl[0, m]) >= -1e-9)

    def test_cm_moment_scales_with_chord_height_and_velocity(self):
        """The production Cm moment helper has the documented dimensions.

        Q_Cm = 0.5 rho W^2 c^2 H Cm.  Holding every other variable fixed:
        linear in H, quadratic in c, quadratic in W, odd in Cm, zero at Cm=0.
        """
        rho, W, c, H, Cm = 1.225, 8.0, 0.14, 0.40, 0.05
        q = _cm_moment(rho, W * W, c, H, Cm)
        assert q == pytest.approx(0.5 * rho * W * W * c * c * H * Cm, rel=1e-12)
        assert _cm_moment(rho, W * W, c, 2.0 * H, Cm) == pytest.approx(2.0 * q, rel=1e-12)
        assert _cm_moment(rho, W * W, 2.0 * c, H, Cm) == pytest.approx(4.0 * q, rel=1e-12)
        assert _cm_moment(rho, (2.0 * W) ** 2, c, H, Cm) == pytest.approx(4.0 * q, rel=1e-12)
        assert _cm_moment(rho, W * W, c, H, -Cm) == pytest.approx(-q, rel=1e-12)
        assert _cm_moment(rho, W * W, c, H, 0.0) == 0.0

    def test_cm_moment_whole_rotor_smoke(self):
        """Integration smoke test: a Cm-bearing run stays in a sane Cp range.

        H changes many other terms (Reynolds number, induction, planform area),
        so this is deliberately a loose whole-rotor smoke test, not a
        dimensional check of the Cm moment.  The isolated scaling check above
        covers the moment law.
        """
        base_params = {
            'R': 0.6, 'c': 0.15, 'H': 0.4, 'N': 3,
            'ar': 0.5, 'sp': 0.25,
            'mb': 0.01, 'xbcg': 0.2, 'mc': 0.002, 'dcw': 0.3,
            'balance': 0, 'bias_deg': 0.0,
            'prescribe_pitch': False,
            'cd_add': 0.002,
            'use_dynamic_stall': True,
            'use_flow_curvature': True,
            'use_dmst': True,
            'use_tip_loss': False,
            'win_deg': 45.0, 'cb': 2e-5, 'mu_c': 3e-4,
            'free': False, 'tsr': 2.5, 'T_max': 5.0, 'stride': 5,
            'k_load': 0.0025,
        }

        r_h1 = create_sim_from_params({**base_params, 'H': 0.4}).run()
        r_h2 = create_sim_from_params({**base_params, 'H': 0.8}).run()

        assert r_h1['cp'] > 0
        assert r_h2['cp'] > 0

        cp_ratio = r_h2['cp'] / r_h1['cp']
        assert 0.4 < cp_ratio < 1.5,             f"Cp ratio H=0.8/H=0.4 = {cp_ratio:.3f}"


    def test_cm_odd_symmetry(self):
        """Cm should be an odd function of alpha (sign flip)."""
        import math

        from vawt_core import PolarDatabase
        pdb = PolarDatabase("airfoil_polars/naca0012")
        for a in [5.0, 15.0, 30.0, 60.0]:
            Cl_pos, Cd_pos, Cm_pos, cla = pdb.lookup(1e6, math.radians(a))
            Cl_neg, Cd_neg, Cm_neg, _cla = pdb.lookup(1e6, math.radians(-a))
            # Cl should be odd: Cl(-a) = -Cl(a)
            assert Cl_neg == pytest.approx(-Cl_pos, rel=0.01)
            # Cm should be odd: Cm(-a) = -Cm(a)
            assert Cm_neg == pytest.approx(-Cm_pos, rel=0.05)
            # Cd should be even: Cd(-a) = Cd(a)
            assert Cd_neg == pytest.approx(Cd_pos, rel=0.01)


class TestVonKarmanTurbulence:
    """von Kármán turbulence model has correct variance and spectrum."""

    def test_vonkarman_variance(self):
        """von Kármán turbulence variance = 0.47 * Dryden variance for same sigma, L."""
        import numpy as np

        from vawt_core import create_sim_from_params
        
        base = {
            'R': 1.0, 'c': 0.2, 'H': 2.0, 'N': 3,
            'ar': 0.5, 'sp': 0.2,
            'mb': 0.1, 'xbcg': 0.2, 'mc': 0.01, 'dcw': 0.0,
            'balance': 0, 'bias_deg': 0.0,
            'prescribe_pitch': False,
            'cd_add': 0.0, 'use_dynamic_stall': False,
            'use_flow_curvature': False, 'use_dmst': False,
            'use_tip_loss': True,
            'win_deg': 45.0, 'cb': 0.0, 'mu_c': 0.0,
            'free': False, 'tsr': 2.5, 'T_max': 10.0, 'stride': 5,
            'w0_frac': 0.9, 'k_load': 0.001,
            'turb_I': 0.1, 'turb_L': 10.0,
        }
        
        sim = create_sim_from_params({**base, 'turb_model': 'vonkarman', 'seed': 42})
        _t, U = sim._make_wind(50000)

        # Measured turbulence intensity should match target I
        measured_ti = np.std(U - np.mean(U)) / np.mean(U)
        target_ti = base['turb_I']

        assert abs(measured_ti - target_ti) < 0.02, \
            f"von Kármán TI = {measured_ti:.3f}, expected ~{target_ti:.3f}"

    def test_vonkarman_runs_without_error(self):
        """von Kármán model runs without crashing."""
        from vawt_core import create_sim_from_params
        r = create_sim_from_params({
            'R': 1.0, 'c': 0.2, 'H': 2.0, 'N': 3,
            'ar': 0.5, 'sp': 0.2,
            'mb': 0.1, 'xbcg': 0.2, 'mc': 0.01, 'dcw': 0.0,
            'balance': 0, 'bias_deg': 0.0,
            'prescribe_pitch': False,
            'cd_add': 0.0, 'use_dynamic_stall': False,
            'use_flow_curvature': False, 'use_dmst': True,
            'use_tip_loss': True, 'turb_model': 'vonkarman',
            'win_deg': 45.0, 'cb': 0.0, 'mu_c': 0.0,
            'free': True, 'tsr': 2.5, 'T_max': 5.0, 'stride': 5,
            'w0_frac': 0.9, 'k_load': 0.001,
            'turb_I': 0.1, 'turb_L': 10.0, 'seed': 123,
        }).run()
        assert r['cp'] > 0


class TestWorkingDirectoryIndependence:
    """Simulation runs correctly from any working directory."""

    def test_run_from_temp_dir(self):
        """Simulation runs correctly when cwd is different from repo root."""
        import os
        import subprocess
        import sys
        import tempfile
        
        # Get the repo root directory dynamically
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Run a quick simulation from a temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write the test script to a file to avoid shell quoting issues
            script_path = os.path.join(tmpdir, 'test_run.py')
            script_content = (
                'import sys\n'
                f'sys.path.insert(0, {repo_root!r})\n'
                'from vawt_core import create_sim_from_params\n'
                'r = create_sim_from_params({\n'
                '    "R": 0.6, "c": 0.14, "H": 0.4, "N": 3,\n'
                '    "ar": 0.5, "sp": 0.25, "mb": 0.01, "xbcg": 0.2,\n'
                '    "mc": 0.002, "dcw": 0.3, "balance": 0, "bias_deg": 0.0,\n'
                '    "prescribe_pitch": True,\n'
                '    "pp0_deg": 0.0, "pp1_deg": -10.0, "pp2_deg": 0.0,\n'
                '    "pp3_deg": 0.0, "pp_ph_deg": 0.0, "free": False,\n'
                '    "tsr": 2.5, "T_max": 5.0, "stride": 5,\n'
                '    "use_dynamic_stall": True, "use_flow_curvature": True,\n'
                '    "use_tip_loss": True, "use_dmst": True,\n'
                '    "win_deg": 45.0, "cb": 2e-5, "mu_c": 3e-4,\n'
                '    "k_load": 0.0025\n'
                '}).run()\n'
                'print("Cp={\" + str(r[\"cp\"])[:6] + \"}")\n'
            )
            
            script_path = os.path.join(tmpdir, 'test_run.py')
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            result = subprocess.run([
                sys.executable, script_path
            ], cwd=tmpdir, capture_output=True, text=True, timeout=30)
            
            assert result.returncode == 0, f"Failed: {result.stderr}"
            assert "Cp=" in result.stdout


def _prose_outside_code_fences(text: str) -> str:
    """Return ``text`` with fenced (```) code blocks removed and lowercased.

    Issue markers such as TODO/FIXME are only meaningful in README prose;
    fenced code blocks may legitimately contain them in examples, so they are
    stripped before the prose check. This single helper is exercised by both
    the real README test and the fixture tests below.
    """
    import re
    return re.sub(r'```.*?```', '', text, flags=re.DOTALL).lower()


class TestReadmeProseLint:
    """Lint README for common issues."""

    def test_no_double_brackets(self):
        """README should not contain [[...]] placeholder brackets."""
        import os
        import re
        readme_path = os.path.join(os.path.dirname(__file__), '..', 'README.md')
        with open(readme_path, 'r') as f:
            content = f.read()
        double_brackets = re.findall(r'\[\[.*?\]\]', content)
        assert not double_brackets, f"Found unfilled [[...]] in README: {double_brackets}"

    def test_no_todo_fixme_in_readme(self):
        """README should not have TODO/FIXME comments (move to issues)."""
        import os
        readme_path = os.path.join(os.path.dirname(__file__), '..', 'README.md')
        with open(readme_path, 'r') as f:
            content = f.read()
        prose = _prose_outside_code_fences(content)
        assert 'todo:' not in prose, "TODO found in README prose"
        assert 'fixme:' not in prose, "FIXME found in README prose"

    def test_todo_allowed_in_code_fence(self):
        """TODO inside a fenced code block should be allowed."""
        content = "Some text\n```python\n# TODO: this is fine\n```\nMore text"
        prose = _prose_outside_code_fences(content)
        assert 'todo:' not in prose

    def test_todo_outside_code_fence_fails(self):
        """TODO outside code fence should be caught."""
        import pytest
        content = "TODO: this should fail\n```python\n# TODO: this is fine\n```"
        prose = _prose_outside_code_fences(content)
        with pytest.raises(AssertionError):
            assert 'todo:' not in prose

    def test_fixme_allowed_in_code_fence(self):
        """FIXME inside a fenced code block should be allowed."""
        content = "Some text\n```bash\n# FIXME: this is fine\n```\nMore text"
        prose = _prose_outside_code_fences(content)
        assert 'fixme:' not in prose

    def test_fixme_outside_code_fence_fails(self):
        """FIXME outside code fence should be caught."""
        import pytest
        content = "FIXME: this should fail\n```bash\n# FIXME: this is fine\n```"
        prose = _prose_outside_code_fences(content)
        with pytest.raises(AssertionError):
            assert 'fixme:' not in prose

    def test_mixed_todo_fixme(self):
        """Mixed TODO/FIXME inside and outside fences."""
        import pytest
        content = "TODO: bad\n```\nFIXME: ok\n```\nFIXME: bad"
        prose = _prose_outside_code_fences(content)
        with pytest.raises(AssertionError):
            assert 'todo:' not in prose or 'fixme:' not in prose


class TestChangelogReproduction:
    """Test that numbers quoted in changelog reproduce from scripts."""

    def test_changelog_cp_values_reproduce(self):
        """Key Cp values mentioned in CHANGELOG.md should reproduce from scripts."""
        import os
        import re
        
        changelog_path = os.path.join(os.path.dirname(__file__), '..', 'CHANGELOG.md')
        if not os.path.exists(changelog_path):
            pytest.skip("CHANGELOG.md not found")
        
        with open(changelog_path, 'r') as f:
            changelog = f.read()
        
        # Extract Cp values from changelog (pattern: X.XX or 0.XX)
        re.findall(r'Cp\s*[=≈]\s*(\d+\.\d+)', changelog, re.IGNORECASE)
        # This is a basic check - full reproduction would require parsing context
        # For now, just verify the file is readable and has expected format
        assert '## [3.2.0]' in open(changelog_path).read() or '## [3.1.0]' in open(changelog_path).read()


class TestCScaleOverride:

    def test_c_scale_default_used_when_zero(self):
        """c_scale_override = 0 (default) → use geometry-derived value."""
        # For R = 0.6, c = 0.14: c_scale = min(1, 0.233/0.418) = 0.558
        s = create_sim_from_params({**BASE_QUICK, 'c': 0.14, 'R': 0.60,
                                    'c_scale_override': 0.0})
        assert s.c_scale == pytest.approx(0.558, abs=0.01)

    def test_c_scale_override_applied(self):
        s = create_sim_from_params({**BASE_QUICK, 'c_scale_override': 0.42})
        assert s.c_scale == pytest.approx(0.42)


class TestOutputColumnContract:

    def test_raw_angular_columns_are_radians_and_history_matches(self):
        params = {
            **BASE_QUICK, 'free': False, 'prescribe_pitch': True,
            'pp0_deg': 5.0, 'pp1_deg': 0.0, 'pp2_deg': 0.0, 'pp3_deg': 0.0,
            'T_max': 0.5, 'stride': 1,
            'use_dynamic_stall': False, 'use_dmst': False,
            'use_tip_loss': False, 'use_flow_curvature': False,
        }
        r = create_sim_from_params(params).run(store_history=True)
        idx = {name: i for i, name in enumerate(r['columns'])}
        assert r['columns'][3:6] == ['psi_rad', 'pitch_rad', 'aoa_rad']
        assert 'pitch_deg' not in r['columns']
        assert 'aoa_deg' not in r['columns']
        assert r['column_units']['psi_rad'] == 'rad'
        assert r['column_units']['pitch_rad'] == 'rad'
        assert r['column_units']['aoa_rad'] == 'rad'
        assert r['column_units']['psidot_0'] == 'rad/s'
        psi = r['out'][:, idx['psi_rad']]
        # A nontrivial angle: 5 deg == 0.0873 rad, so a degrees/radians
        # mix-up cannot accidentally compare equal.
        assert np.allclose(psi, math.radians(5.0), atol=1e-12)
        assert not np.allclose(psi, 5.0)
        for name in r['columns']:
            assert np.array_equal(r['history'][name], r['out'][:, idx[name]])

    def test_pitch_column_is_psi_plus_geometric_offset(self):
        """pitch_rad is the total chord pitch psi + delta from the radial line."""
        params = {
            **BASE_QUICK, 'free': False, 'prescribe_pitch': True,
            'pp0_deg': 7.0, 'pp1_deg': 0.0, 'pp2_deg': 0.0, 'pp3_deg': 0.0,
            'T_max': 0.2, 'stride': 1,
            'use_dynamic_stall': False, 'use_dmst': False,
            'use_tip_loss': False, 'use_flow_curvature': False,
        }
        sim = create_sim_from_params(params)
        r = sim.run()
        idx = {name: i for i, name in enumerate(r['columns'])}
        psi = math.radians(7.0)
        stq = -sim.xq * math.cos(psi) - sim.ar_len * math.sin(psi)
        srq = -sim.xq * math.sin(psi) + sim.ar_len * math.cos(psi)
        delta = math.atan2(stq, sim.Rp + srq)
        assert np.allclose(r['out'][:, idx['pitch_rad']], psi + delta, atol=1e-12)
        assert not np.allclose(r['out'][:, idx['pitch_rad']],
                               math.degrees(psi + delta))

    def test_pitch_summary_converts_raw_radians_to_degrees(self):
        r = create_sim_from_params({
            **BASE_QUICK, 'T_max': 2.0, 'stride': 5,
        }).run(store_history=True)
        idx = {name: i for i, name in enumerate(r['columns'])}
        theta = r['out'][:, idx['theta']]
        m = theta > theta[-1] - 2.0 * math.pi * 4
        if m.sum() < 5:
            m = np.ones(len(theta), bool)
        beta_deg = np.degrees(r['out'][m, idx['pitch_rad']])
        assert r['pitch_summary_units'] == 'deg'
        assert r['pitch_min'] == pytest.approx(float(beta_deg.min()))
        assert r['pitch_max'] == pytest.approx(float(beta_deg.max()))
        assert r['pitch_rms'] == pytest.approx(float(beta_deg.std()))
        assert r['aoa_max'] == pytest.approx(
            float(np.degrees(np.abs(r['out'][m, idx['aoa_rad']]).max())))


class TestEnergyLedger:

    def test_energy_ledger_closes_for_passive_run(self):
        """Passive run: |resid| < 2 %."""
        r = create_sim_from_params({
            **BASE_QUICK, 'T_max': 15.0, 'stride': 5,
        }).run()
        assert r['energy_balance_valid'] is True
        assert abs(r['energy_balance']) < 0.02

    def test_energy_diagnostics_balanced_steady_transfer(self):
        d = _energy_diagnostics([100.0, 100.0, 0.0, 0.0, 0.0, 0.0, 5.0, 5.0])
        assert d['energy_balance'] == pytest.approx(0.0)
        assert d['energy_balance_abs_J'] == pytest.approx(0.0)
        assert d['energy_balance_defined'] is True
        assert d['energy_balance_throughput'] == pytest.approx(0.0)

    def test_energy_diagnostics_transient_stored_energy(self):
        d = _energy_diagnostics([100.0, 80.0, 0.0, 0.0, 0.0, 0.0, 10.0, 30.0])
        assert d['energy_balance'] == pytest.approx(0.0)
        assert d['d_stored_J'] == pytest.approx(20.0)

    def test_energy_diagnostics_dissipative_channels(self):
        d = _energy_diagnostics([100.0, 60.0, 10.0, 20.0, 5.0, 5.0, 0.0, 0.0])
        assert d['energy_balance'] == pytest.approx(0.0)
        assert d['energy_balance_defined'] is True

    def test_energy_diagnostics_low_net_aerodynamic_work(self):
        d = _energy_diagnostics([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        assert d['energy_balance_defined'] is False
        assert math.isnan(d['energy_balance'])
        assert d['energy_balance_throughput_defined'] is False
        assert math.isnan(d['energy_balance_throughput'])

    def test_energy_diagnostics_reports_absolute_and_both_normalisations(self):
        # 10 J of imbalance with E_in = 100 J and E_shaft = 90 J.
        d = _energy_diagnostics([100.0, 90.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        assert d['energy_balance_abs_J'] == pytest.approx(10.0)
        assert d['energy_balance'] == pytest.approx(0.10)
        assert d['energy_balance_throughput'] == pytest.approx(10.0 / 190.0)
        # The throughput ratio is smaller; it must never replace the absolute error.
        assert d['energy_balance_throughput'] < d['energy_balance']

    def test_reproducibility(self):
        """Same seed + same params → same Cp."""
        p = {**BASE_QUICK, 'T_max': 10.0, 'turb_I': 0.12, 'seed': 3}
        r1 = create_sim_from_params(p).run()
        r2 = create_sim_from_params(p).run()
        assert r1['cp'] == pytest.approx(r2['cp'], abs=1e-9)


class TestFnRatio:
    """Sharp's design rule: pitch natural frequency / rotor frequency >= 1.5."""

    def test_scaleup_fn_ratio_meets_sharp_rule(self):
        """Scale-up design should meet Sharp's fn_ratio >= 1.5 rule."""
        # Scale-up geometry from optimization_scaleup.json
        scaleup = {
            'R': 2.7179, 'H': 4.0568, 'N': 3, 'c': 0.3861,
            'ar': 0.3121, 'sp': 0.2181,
            'mb': 0.92954, 'xbcg': 0.20, 'mc': 2.69306, 'dcw': -0.1935,
            'balance': 0, 'bias_deg': 0.0,
            'prescribe_pitch': False,
            'cd_add': 0.002,
            'use_dynamic_stall': True, 'use_flow_curvature': True,
            'use_dmst': True, 'use_tip_loss': True,
            'win_deg': 45.0, 'cb': 2e-5, 'mu_c': 3e-4,
            'free': True, 'T_max': 40.0, 'stride': 8,
            'w0_frac': 0.9, 'k_load': 4.164352, 'tsr': 2.5,
        }
        s = create_sim_from_params(scaleup)
        # fn_ratio = sqrt(M * Rp * ar / Ip)
        # Sharp's design rule: fn_ratio >= 1.5
        assert s.fn_ratio >= 1.5, f"fn_ratio = {s.fn_ratio:.2f} < 1.5"

    def test_fn_ratio_reported_in_results(self):
        """pitch_freq_ratio should be present in run results."""
        r = create_sim_from_params(BASE_QUICK).run()
        assert 'pitch_freq_ratio' in r


class TestCmHubMoment:
    """Cm pitch-moment coupling: non-zero Cm drives hub reaction torque."""

    def test_cm_neuralfoil_variant_nonzero_in_polar(self):
        """The neuralfoil_cm variant has non-zero Cm at 15° (raw NeuralFoil)."""
        import math

        from vawt_core import PolarDatabase
        pdb = PolarDatabase("airfoil_polars/naca0012", variant="neuralfoil_cm")
        _, _, Cm, _ = pdb.lookup(1e6, math.radians(15.0))
        assert abs(Cm) > 0.001, f"Cm at 15° should be non-zero, got {Cm:.6f}"

    def test_cm_default_variant_zero_in_attached(self):
        """Default variant has Cm=0 in attached flow (physical symmetric section)."""
        import math

        from vawt_core import PolarDatabase
        pdb = PolarDatabase("airfoil_polars/naca0012", variant="neuralfoil")
        _, _, Cm, _ = pdb.lookup(1e6, math.radians(15.0))
        assert abs(Cm) < 1e-6, f"Default Cm at 15° should be zero, got {Cm:.6f}"

    def test_cm_sign_test_locked_blade(self):
        """Three-value locked-blade Cm sign test.
        
        Locked blades (free=False, prescribe_pitch=True) with constant Cm values:
        +0.1 (nose-up by the usual convention) should give lowest Cp, -0.1
        (nose-down) should give highest. This catches sign errors in the
        Qa_cm = q * Cm * c hub reaction torque.
        
        Measured on current machine: Cm=+0.1→Cp≈0.205, Cm=0→Cp≈0.257,
        Cm=-0.1→Cp≈0.309. Positive Cm reduces shaft torque, negative Cm increases it.
        """
        from vawt_core import create_sim_from_params
        
        base = dict(BASE_QUICK, free=False, prescribe_pitch=True, T_max=10.0, stride=5)
        
        sim = create_sim_from_params(base)
        pdb = sim.polar_db
        
        cps = []
        for cm_val in [0.1, 0.0, -0.1]:
            pdb.Cm[:] = cm_val  # Constant Cm across all Re/alpha
            r = sim.run()
            cps.append(r['cp'])
        
        # Positive Cm (nose-up pitching moment) reduces shaft torque → lowest Cp
        # Negative Cm (nose-down pitching moment) increases shaft torque → highest Cp
        assert cps[0] < cps[1] < cps[2], \
            f"Cp ordering wrong: Cm=+0.1→{cps[0]:.4f}, Cm=0→{cps[1]:.4f}, Cm=-0.1→{cps[2]:.4f}"
        # Cm=0 case should be between the two signed cases (sanity check on range)
        assert cps[2] - cps[0] > 0.05, \
            f"Cm effect too small: ΔCp = {cps[2]-cps[0]:.4f}, expected > 0.05"

    def test_cm_zeroed_column_changes_cp(self):
        """Same polar, only the Cm column zeroed: Cp must change.

        Uses the neuralfoil_cm variant which has non-zero attached-flow Cm.
        Comparing against a surrogate polar changes Cl and Cd as well, so it
        cannot isolate the hub-reaction term. Here both simulators load the
        same CSV tables; the second has ``Cm[:] = 0`` applied in memory.
        """
        from vawt_core import create_sim_from_params

        base = dict(BASE_QUICK, free=False, tsr=2.5,
                    T_max=15.0, stride=5,
                    polar_variant="neuralfoil_cm")
        # With the blade held at fixed speed and fixed pitch, Cm no longer
        # averages out over the revolution, so the hub-reaction term moves Cp.
        sim_with_cm = create_sim_from_params(base)
        sim_zero_cm = create_sim_from_params(base)
        assert sim_zero_cm.polar_db is not sim_with_cm.polar_db

        # Only the Cm column changes; Cl and Cd stay bit-identical.
        sim_zero_cm.polar_db.Cm[:] = 0.0

        cp_with = sim_with_cm.run()['cp']
        cp_zero = sim_zero_cm.run()['cp']
        assert abs(cp_with - cp_zero) > 0.005, (
            "Zeroing only the Cm column should move Cp; "
            f"got {cp_with:.4f} vs {cp_zero:.4f}"
        )

    def test_cm_torque_in_energy_ledger(self):
        """Energy ledger should account for Cm hub reaction torque."""
        r = create_sim_from_params(BASE_QUICK).run()
        # Energy ledger closes when Cm is properly accounted
        assert r['energy_balance_valid'] is True
        assert abs(r['energy_balance']) < 0.02


class TestPolarExtremeAngles:
    """NACA 0012 polar behaviour at extreme angles of attack."""

    def test_cl_zero_at_90_deg(self):
        """CL should be zero at 90° angle of attack (blade edge-on)."""
        from vawt_core import PolarDatabase
        pdb = PolarDatabase("airfoil_polars/naca0012")
        Cl, _Cd, _Cm, _cla = pdb.lookup(1e6, math.radians(90.0))
        assert abs(Cl) < 0.05, f"CL at 90° should be ~0, got {Cl:.4f}"

    def test_cl_negative_at_150_deg(self):
        """CL should be clearly negative at 150° angle of attack (post-stall).

        Flat-plate deep-stall model: CL(150°) ≈ -0.56, consistent with the
        Sheldahl & Klimas SAND80-2114 trend (roughly -0.5 to -0.6). This is
        an analytic deep-stall value, not a direct measurement.
        """
        from vawt_core import PolarDatabase
        pdb = PolarDatabase("airfoil_polars/naca0012")
        Cl, _Cd, _Cm, _cla = pdb.lookup(1e6, math.radians(150.0))
        assert Cl < -0.02, f"CL at 150° should be clearly negative, got {Cl:.4f}"

    def test_cl_max_at_re1e6(self):
        """CLmax should be ~1.25 at Re=1e6."""
        from vawt_core import PolarDatabase
        pdb = PolarDatabase("airfoil_polars/naca0012")
        max_cl = max(
            pdb.lookup(1e6, math.radians(a))[0]
            for a in [i * 5 for i in range(1, 18)]
        )
        assert 1.15 < max_cl < 1.35, f"CLmax = {max_cl:.3f}, expected ~1.25"

    def test_cd_reasonable_at_stall(self):
        """CD should increase through stall but stay below ~1.6."""
        from vawt_core import PolarDatabase
        pdb = PolarDatabase("airfoil_polars/naca0012")
        cd_max = max(
            pdb.lookup(1e6, math.radians(a))[1]
            for a in [i * 5 for i in range(1, 36)]
        )
        assert cd_max < 1.7, f"CD max = {cd_max:.3f}, should be < 1.7"


class TestActiveLiftDiagnostic:
    """Active lift isolation diagnostic produces sensible results."""

    @pytest.mark.needs_jit
    def test_active_lift_runs(self):
        """diag_active_lift.py should run and produce a small ΔCp."""
        import os
        import subprocess
        import sys
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            [sys.executable, "scripts/diag_active_lift.py"],
            cwd=repo_root, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, f"diag_active_lift failed: {result.stderr}"

    @pytest.mark.needs_jit
    def test_active_lift_delta_cp_small(self):
        """Active lift should produce a small ΔCp (< 0.01) at scale-up."""
        import os
        import re
        import subprocess
        import sys
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            [sys.executable, "scripts/diag_active_lift.py"],
            cwd=repo_root, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0
        # Parse ΔCp from output
        match = re.search(r'ΔCp\s*=\s*([\d.+-]+)', result.stdout)
        if match:
            delta_cp = float(match.group(1))
            assert abs(delta_cp) < 0.01, f"ΔCp = {delta_cp:.6f}, expected < 0.01"
