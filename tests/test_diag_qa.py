"""Tests for the Qa sign diagnostic (scripts/diag_qa.py)."""
from __future__ import annotations

import numpy as np
import pytest

# Import the pure evaluation function (no simulation dependency)
from scripts.diag_qa import evaluate_restoring


def test_restoring_pass_correct_signs():
    """A case with correct restoring signs should pass."""
    # Need enough samples in the fraction band (|alpha| > 0.5 * |alpha|_max)
    # |alpha|_max = 10, band = |alpha| > 5, need >= 5 samples
    alpha = np.array([10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 0.0,
                      -6.0, -7.0, -8.0, -9.0, -10.0])
    qa = np.array([-2.0, -1.8, -1.6, -1.4, -1.2, -1.0, 0.0,
                   1.0, 1.2, 1.4, 1.6, 2.0])
    stall = 16.0

    report = evaluate_restoring(alpha, qa, stall)
    assert report["passed"] is True
    assert report["extreme_ok"] is True
    assert report["frac_ok"] is True
    assert report["fraction"] == 1.0


def test_restoring_fail_wrong_sign_at_positive_alpha():
    """Wrong sign at positive alpha should fail the extreme check."""
    alpha = np.array([12.0, 10.0, 8.0, 6.0, 4.0, 2.0, 0.0,
                      -2.0, -4.0, -6.0, -8.0, -10.0, -12.0])
    qa = np.array([2.0, 1.5, 1.0, 0.5, 0.2, 0.1, 0.0,
                   -0.1, -0.2, -0.5, -1.0, -1.5, -2.0])  # wrong sign at positive
    stall = 16.0

    report = evaluate_restoring(alpha, qa, stall)
    assert report["passed"] is False
    assert report["extreme_ok"] is False
    for label, ok, _ in report["checks"]:
        if "max" in label:
            assert ok is False


def test_restoring_fail_wrong_sign_at_negative_alpha():
    """Wrong sign at negative alpha should fail the extreme check."""
    alpha = np.array([12.0, 10.0, 8.0, 6.0, 4.0, 2.0, 0.0,
                      -2.0, -4.0, -6.0, -8.0, -10.0, -12.0])
    qa = np.array([-2.0, -1.5, -1.0, -0.5, -0.2, -0.1, 0.0,
                   -0.1, -0.2, -0.5, -1.0, -1.5, -2.0])  # wrong sign at negative
    stall = 16.0

    report = evaluate_restoring(alpha, qa, stall)
    assert report["passed"] is False
    assert report["extreme_ok"] is False
    for label, ok, _ in report["checks"]:
        if "min" in label:
            assert ok is False


def test_restoring_fail_low_fraction():
    """Restoring fraction below threshold should fail."""
    alpha = np.linspace(-10, 10, 21)
    # First half: correct (negative Qa for positive alpha, positive Qa for negative alpha)
    # Second half: wrong signs
    qa = np.concatenate([
        -alpha[:11],  # correct: opposite sign
        alpha[11:]    # wrong: same sign
    ])
    stall = 16.0

    report = evaluate_restoring(alpha, qa, stall)
    assert report["passed"] is False
    assert report["frac_ok"] is not True
    assert report["fraction"] < 0.70


def test_restoring_insufficient_samples():
    """Too few samples in band should make fraction check NaN and fail."""
    # |alpha|_max = 1.0, band = |alpha| > 0.5, only 4 samples in band (< 5)
    alpha = np.array([1.0, 0.5, 0.0, -0.5, -1.0])
    qa = np.array([-0.2, -0.1, 0.0, 0.1, 0.2])
    stall = 16.0

    report = evaluate_restoring(alpha, qa, stall)
    assert np.isnan(report["fraction"]) or report["n_band"] < 5
    assert report["frac_ok"] is not True
    assert report["passed"] is False


def test_restoring_no_checks_when_flat():
    """When alpha is flat (no variation), no extreme checks run."""
    alpha = np.array([0.0, 0.0, 0.0])
    qa = np.array([0.0, 0.0, 0.0])
    stall = 16.0

    report = evaluate_restoring(alpha, qa, stall)
    assert len(report["checks"]) == 0
    assert not report["extreme_ok"]
    assert not report["frac_ok"]
    assert not report["passed"]


def test_restoring_thresholds_use_achieved_alpha_max():
    """Thresholds should be based on achieved |alpha|_max, not stall angle."""
    # Cycle reaches only 8 deg, stall is 16 deg
    # Old code: 0.8 * 16 = 12.8 deg threshold (never reached)
    # New code: 0.75 * 8 = 6 deg threshold (reached at 8 deg)
    alpha = np.array([8.0, 4.0, 0.0, -4.0, -8.0])
    qa = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    stall = 16.0

    report = evaluate_restoring(alpha, qa, stall)
    # Should evaluate extreme checks since 8 > 0.75 * 8 = 6
    assert len(report["checks"]) == 2
    assert report["extreme_ok"] is True
    # Fraction band: |alpha| > 0.5 * 8 = 4 -> samples with |alpha| > 4
    # That's 8.0 and -8.0 = 2 samples (need >= 5)
    assert report["n_band"] == 2
    # With only 2 samples, fraction is NaN (< MIN_SAMPLES=5)
    assert np.isnan(report["fraction"])
    assert not report["frac_ok"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])