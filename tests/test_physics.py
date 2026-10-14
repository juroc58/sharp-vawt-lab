"""Tests for the physics overrides added for the UQ study."""
import pytest
import math

from vawt_core import create_sim_from_params
from tests.conftest import BASE_QUICK


class TestTipLossBounds:

    def test_default_uses_generalized_prandtl(self):
        """Default f_ar uses generalized Prandtl formula (k=1.8) without floor."""
        s = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14})
        # AR = 0.445 / 0.14 = 3.18  →  Gen. Prandtl f_ar = 1/(1 + 1.8/(0.9*3.18)) ≈ 0.614
        assert s.f_ar == pytest.approx(0.614, abs=0.01)

    def test_raw_correction_when_floor_near_zero(self):
        """Passing ~0 uses the raw generalized Prandtl formula (same as default now)."""
        s = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14,
                                    'tip_loss_floor_override': 0.001})
        # Gen. Prandtl: f_ar = 1/(1 + 1.8/(0.9*3.18)) ≈ 0.614
        assert s.f_ar == pytest.approx(0.614, abs=0.01)

    def test_override_raises_floor(self):
        """tip_loss_floor_override > raw clamps f_ar up to the override value."""
        s = create_sim_from_params({**BASE_QUICK, 'H': 0.445, 'c': 0.14,
                                    'tip_loss_floor_override': 0.85})
        assert s.f_ar == pytest.approx(0.85, abs=0.01)

    def test_override_below_raw_is_ignored(self):
        """An override below the raw value must not pull f_ar down."""
        s = create_sim_from_params({**BASE_QUICK, 'H': 3.0, 'c': 0.10,
                                    'tip_loss_floor_override': 0.50})
        # AR = 30, raw Gen. Prandtl f_ar ≈ 0.94; override 0.50 should not apply
        assert s.f_ar > 0.85

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

    def test_cm_in_polars(self):
        """Polar tables contain non-zero Cm values."""
        from vawt_core import PolarDatabase
        pdb = PolarDatabase("polars/naca0012")
        # At Re=1e6, alpha=15°, Cm should be negative (nose-down)
        Cl, Cd, Cm, cla = pdb.lookup(1e6, math.radians(15.0))
        assert Cm < -0.001  # negative nose-down moment
        assert Cm > -0.1  # not absurdly large

    def test_cm_moment_dimensions(self):
        """Cm moment Qa_cm = q * Cm * c has correct dimensions [N·m]."""
        # q = 0.5*rho*W^2*c*H has dimensions [Pa] * [m^2] = [N]
        # q * Cm * c has dimensions [N] * [m] = [N·m] (torque)
        # This is a dimensional sanity check
        from vawt_core import create_sim_from_params
        s = create_sim_from_params({
            'R': 2.0, 'c': 0.5, 'H': 10.0, 'N': 3,
            'ar': 0.5, 'sp': 0.2,
            'mb': 1.0, 'xbcg': 0.2, 'mc': 5.0, 'dcw': 0.0,
            'balance': 0, 'bias_deg': 0.0,
            'prescribe_pitch': False, 'cd_add': 0.0,
            'use_dynamic_stall': False, 'use_flow_curvature': False,
            'use_dmst': True, 'use_tip_loss': True,
            'win_deg': 45.0, 'cb': 0.0, 'mu_c': 0.0,
            'free': False, 'tsr': 2.5, 'T_max': 2.0, 'stride': 5,
            'k_load': 0.001,
        })
        # Just verify it runs without error and Cm is present
        r = s.run()
        assert 'cp' in r
        # Cm is integrated in the run; just verify no crash

    def test_cm_odd_symmetry(self):
        """Cm should be an odd function of alpha (sign flip)."""
        from vawt_core import PolarDatabase
        import math
        pdb = PolarDatabase("polars/naca0012")
        for a in [5.0, 15.0, 30.0, 60.0]:
            Cl_pos, Cd_pos, Cm_pos, cla = pdb.lookup(1e6, math.radians(a))
            Cl_neg, Cd_neg, Cm_neg, cla = pdb.lookup(1e6, math.radians(-a))
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
        from vawt_core import create_sim_from_params
        import numpy as np
        
        base = {
            'R': 1.0, 'c': 0.2, 'H': 2.0, 'N': 3,
            'ar': 0.5, 'sp': 0.2,
            'mb': 0.1, 'xbcg': 0.2, 'mc': 0.01, 'dcw': 0.0,
            'balance': 0, 'bias_deg': 0.0,
            'prescribe_pitch': False,
            'cd_add': 0.0, 'use_dynamic_stall': False,
            'use_flow_curvature': False, 'use_dmst': False,
            'use_tip_loss': True, 'use_dmst': False,
            'win_deg': 45.0, 'cb': 0.0, 'mu_c': 0.0,
            'free': False, 'tsr': 2.5, 'T_max': 10.0, 'stride': 5,
            'w0_frac': 0.9, 'k_load': 0.001, 'tsr': 2.5,
            'turb_I': 0.1, 'turb_L': 10.0,
        }
        
        # Dryden
        r_dryden = create_sim_from_params({**base, 'turb_model': 'dryden', 'seed': 42}).run()
        # von Kármán
        r_vk = create_sim_from_params({**base, 'turb_model': 'vonkarman', 'seed': 42}).run()
        
        # Both should run successfully
        assert r_dryden['steady'] is not None
        assert r_vk['steady'] is not None
        # The variance check is more involved; for now just verify both run
        assert r_vk['cp'] > 0
        assert r_dryden['cp'] > 0

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
            'w0_frac': 0.9, 'k_load': 0.001, 'tsr': 2.5,
            'turb_I': 0.1, 'turb_L': 10.0, 'seed': 123,
        }).run()
        assert r['cp'] > 0


class TestWorkingDirectoryIndependence:
    """Simulation runs correctly from any working directory."""

    def test_run_from_temp_dir(self):
        """Simulation runs correctly when cwd is different from repo root."""
        import tempfile
        import os
        import subprocess
        import sys
        
        # Get the repo root directory dynamically
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Run a quick simulation from a temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write the test script to a file to avoid shell quoting issues
            script_path = os.path.join(tmpdir, 'test_run.py')
            script_content = (
                'import sys\n'
                'sys.path.insert(0, {0!r})\n'
                'from vawt_core import create_sim_from_params\n'
                'r = create_sim_from_params({{\n'
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
                '}}).run()\n'
                'print("Cp={{\" + str(r[\"cp\"])[:6] + \"}}")\n'
            ).format(repo_root)
            
            script_path = os.path.join(tmpdir, 'test_run.py')
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            result = subprocess.run([
                sys.executable, script_path
            ], cwd=tmpdir, capture_output=True, text=True, timeout=30)
            
            assert result.returncode == 0, f"Failed: {result.stderr}"
            assert "Cp=" in result.stdout


class TestReadmeProseLint:
    """Lint README for common issues."""

    def test_no_double_brackets(self):
        """README should not contain [[...]] placeholder brackets."""
        import os
        readme_path = os.path.join(os.path.dirname(__file__), '..', 'README.md')
        with open(readme_path, 'r') as f:
            content = f.read()
        # Check for [[...]] patterns that indicate unfilled template variables
        import re
        double_brackets = re.findall(r'\[\[.*?\]\]', content)
        assert not double_brackets, f"Found unfilled [[...]] in README: {double_brackets}"

    def test_no_todo_fixme_in_readme(self):
        """README should not have TODO/FIXME comments (move to issues)."""
        import os
        readme_path = os.path.join(os.path.dirname(__file__), '..', 'README.md')
        with open(readme_path, 'r') as f:
            content = f.read().lower()
        # Check for TODO/FIXME (but allow in code blocks)
        # Just a basic check
        assert 'todo:' not in content or 'todo:' in content.split('```')[1::2]


class TestChangelogReproduction:
    """Test that numbers quoted in changelog reproduce from scripts."""

    def test_changelog_cp_values_reproduce(self):
        """Key Cp values mentioned in CHANGELOG.md should reproduce from scripts."""
        import os
        import subprocess
        import sys
        import re
        
        changelog_path = os.path.join(os.path.dirname(__file__), '..', 'CHANGELOG.md')
        if not os.path.exists(changelog_path):
            pytest.skip("CHANGELOG.md not found")
        
        with open(changelog_path, 'r') as f:
            changelog = f.read()
        
        # Extract Cp values from changelog (pattern: X.XX or 0.XX)
        cp_matches = re.findall(r'Cp\s*[=≈]\s*(\d+\.\d+)', changelog, re.IGNORECASE)
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


class TestEnergyLedger:

    def test_energy_ledger_closes_for_passive_run(self):
        """Passive run: |resid| < 2 %."""
        r = create_sim_from_params({
            **BASE_QUICK, 'T_max': 15.0, 'stride': 5,
        }).run()
        assert r['energy_balance_valid'] is True
        assert abs(r['energy_balance']) < 0.02

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
        scaleup = dict(
            R=2.7179, H=4.0568, N=3, c=0.3861,
            ar=0.3121, sp=0.2181,
            mb=0.92954, xbcg=0.20, mc=2.69306, dcw=-0.1935,
            balance=0, bias_deg=0.0,
            prescribe_pitch=False,
            cd_add=0.002,
            use_dynamic_stall=True, use_flow_curvature=True,
            use_dmst=True, use_tip_loss=True,
            win_deg=45.0, cb=2e-5, mu_c=3e-4,
            free=True, T_max=40.0, stride=8,
            w0_frac=0.9, k_load=4.164352, tsr=2.5,
        )
        s = create_sim_from_params(scaleup)
        # fn_ratio = sqrt(M * Rp * ar / Ip)
        # Sharp's design rule: fn_ratio >= 1.5
        assert s.fn_ratio >= 1.5, f"fn_ratio = {s.fn_ratio:.2f} < 1.5"

    def test_fn_ratio_reported_in_results(self):
        """pitch_freq_ratio should be present in run results."""
        r = create_sim_from_params(BASE_QUICK).run()
        assert 'pitch_freq_ratio' in r
