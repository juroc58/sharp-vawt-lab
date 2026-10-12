"""Tests for the pitch-torque sign check (scripts/diag_qa.py).

The review point was that the old diagnostic printed a "sign ok?" column
that could never fail. These tests pin the pass/fail logic itself with
synthetic histories, so a regression in the sign convention (derivation.md
eq. 2.6) fails the suite without needing a full simulation.
"""
import pytest
import numpy as np

from scripts.diag_qa import evaluate_restoring


STALL = 15.0


def _history(alpha, qa):
    return np.asarray(alpha, float), np.asarray(qa, float)


class TestEvaluateRestoring:

    def test_restoring_signs_pass(self):
        """Qa < 0 at +stall, Qa > 0 at -stall -> restoring -> pass."""
        alpha, qa = _history([-15.0, -8.0, 0.0, 8.0, 15.0],
                             [+0.05, +0.02, 0.0, -0.02, -0.05])
        rep = evaluate_restoring(alpha, qa, STALL)
        assert rep["passed"] is True
        assert rep["extreme_ok"] is True
        assert rep["frac_ok"] is True

    def test_anti_restoring_signs_fail(self):
        """Sign reversed (the historical bug) -> must fail."""
        alpha, qa = _history([-15.0, -8.0, 0.0, 8.0, 15.0],
                             [-0.05, -0.02, 0.0, +0.02, +0.05])
        rep = evaluate_restoring(alpha, qa, STALL)
        assert rep["passed"] is False
        assert rep["extreme_ok"] is False

    def test_no_stall_visit_fails(self):
        """If the blade never approaches stall, there is nothing to
        verify -> the check must not vacuously pass."""
        alpha, qa = _history([-5.0, 0.0, 5.0], [0.0, 0.0, 0.0])
        rep = evaluate_restoring(alpha, qa, STALL)
        assert rep["extreme_ok"] is False
        assert rep["passed"] is False
        assert rep["checks"] == []

    def test_low_restoring_fraction_fails(self):
        """Extremes are fine but most of the band is anti-restoring."""
        # +stall and -stall endpoints are restoring, but the interior
        # points in the band are not -> fraction below threshold.
        alpha, qa = _history([-15.0, -12.0, -10.0, 0.0, 10.0, 12.0, 15.0],
                             [+0.05, -0.03, -0.03, 0.0, +0.03, +0.03, -0.05])
        rep = evaluate_restoring(alpha, qa, STALL)
        assert rep["extreme_ok"] is True
        assert rep["frac_ok"] is False
        assert rep["passed"] is False

    def test_unsteady_run_fails(self):
        """A non-steady run must not report a pass even if signs look ok."""
        alpha, qa = _history([-15.0, 0.0, 15.0], [+0.05, 0.0, -0.05])
        rep = evaluate_restoring(alpha, qa, STALL, steady=False)
        assert rep["passed"] is False


@pytest.mark.slow
class TestLiveDiagnostic:
    """End-to-end: a design that reaches stall must pass the QA check."""

    def test_sharp_passive_case_passes(self):
        # Use the R=0.6 design that reaches stall to verify the QA check works
        stall_design = dict(
            R=0.60, H=0.40, N=3, c=0.1176,
            ar=0.50, sp=0.25,
            mb=0.010, xbcg=0.20,
            mc=0.004, dcw=-0.10,
            balance=0, bias_deg=0.0,
            prescribe_pitch=False,
            cd_add=0.002,
            use_dynamic_stall=True,
            use_flow_curvature=True,
            use_dmst=True,
            use_tip_loss=True,
            win_deg=45.0, cb=2e-5, mu_c=3e-4,
            free=True, T_max=12.0, stride=5,
            w0_frac=0.9, k_load=0.0015, tsr=2.14,
        )
        from scripts.diag_qa import restoring_report
        rep, _out, _sim = restoring_report(stall_design)
        assert rep["passed"] is True, rep
        assert rep["extreme_ok"] is True