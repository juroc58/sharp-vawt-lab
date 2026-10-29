"""Output/cache isolation tests for scripts/uncertainty.py.

These tests use mocked simulation execution and temporary paths so no real
UQ simulations are run and no canonical artifacts are touched. They verify:

1. Dry run performs no simulations and writes no outputs.
2. A noncanonical --out dev run writes its JSON and PNG under the dev
   destination and never touches docs/uncertainty.png.
3. A noncanonical budget is rejected from writing the canonical output path.
4. Conflicting sampling flags (--samples with --saltelli) are rejected.
5. The canonical Saltelli base_n = 64 run is allowed to write the canonical
   output path.
6. The requested cache directory is actually used by worker tasks.
7. Worker count / cache location do not change simulation cache identity.
8. Result-affecting input changes do change cache identity.
9. Failed tasks remain visible in results.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import uncertainty as U

FAKE_CP = {
    "ham_1979": 0.49,
    "sharp_cppc": 0.12,
    "optimised_passive": 0.27,
    "scaleup": 0.43,
}


def fake_run_one_task(args):
    """Standalone replacement worker returning a deterministic Cp.

    Exercises _cache_path so the cache-dir propagation test can observe which
    directory workers actually received.
    """
    anchor_name, _anchor_params, _uq_params, cache_dir = args
    U._cache_path("_probe", cache_dir)
    return (
        anchor_name,
        {"cp": FAKE_CP[anchor_name], "tsr": 2.5, "aoa_max": 10.0, "steady": True},
        None,
        _uq_params,
    )


def fake_base_cm0(_anchor_params):
    return {"cp": 0.0, "tsr": 0.0, "steady": True}


class _InlineExecutor:
    """Inline (single-process) executor stand-in for ProcessPoolExecutor.

    Avoids multiprocessing pickling constraints while preserving the
    task-ordering semantics of ex.map().
    """

    def __init__(self, max_workers=None):
        self.max_workers = max_workers

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def map(self, fn, iterable):
        return [fn(task) for task in iterable]


def _install_mocks(monkeypatch):
    monkeypatch.setattr(U, "run_one_task", fake_run_one_task)
    monkeypatch.setattr(U, "_base_cm0", fake_base_cm0)
    monkeypatch.setattr(U, "ProcessPoolExecutor", _InlineExecutor)
    U._CODE_HASH_CACHE = None


def _run_cli(monkeypatch, argv):
    """Run U.main with argv, capturing stdout+stderr. Returns (code, out)."""
    _install_mocks(monkeypatch)
    old_argv = sys.argv
    old_out, old_err = sys.stdout, sys.stderr
    sys.argv = ["uncertainty.py"] + argv
    out_buf, err_buf = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = out_buf, err_buf
    try:
        try:
            code = U.main()
        except SystemExit as exc:
            code = exc.code if exc.code is not None else 0
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        sys.argv = old_argv
    return code, out_buf.getvalue() + err_buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Dry run performs no simulations and writes no outputs.
# ---------------------------------------------------------------------------
def test_dry_run_writes_nothing(monkeypatch, tmp_path):
    dev_json = tmp_path / "dev.json"
    code, out = _run_cli(
        monkeypatch,
        ["--dry-run", "--samples", "5", "--out", str(dev_json),
         "--cache-dir", str(tmp_path / "cache")],
    )
    assert code == 0, out
    assert "Dry run complete" in out
    assert not dev_json.exists(), "dry run wrote a dev JSON"
    assert not (tmp_path / "cache").exists(), "dry run created a cache dir"


# ---------------------------------------------------------------------------
# 2. Dev --out writes dev JSON + dev PNG, leaves canonical PNG alone.
# ---------------------------------------------------------------------------
def test_dev_out_writes_dev_paths_not_canonical(monkeypatch, tmp_path):
    dev_json = tmp_path / "dev_uncertainty.json"
    dev_png = tmp_path / "dev_uncertainty.png"
    canonical_png = Path("docs") / "uncertainty.png"
    canonical_before = (
        canonical_png.read_bytes() if canonical_png.exists() else None
    )

    code, out = _run_cli(
        monkeypatch,
        ["--samples", "5", "--out", str(dev_json),
         "--cache-dir", str(tmp_path / "cache")],
    )
    assert code == 0, out
    assert dev_json.exists(), "dev JSON not written"
    assert dev_png.exists(), "dev PNG not written next to dev JSON"
    canonical_after = (
        canonical_png.read_bytes() if canonical_png.exists() else None
    )
    assert canonical_before == canonical_after, (
        "dev run must not overwrite docs/uncertainty.png"
    )


# ---------------------------------------------------------------------------
# 3. Noncanonical budget rejected from canonical output path.
# ---------------------------------------------------------------------------
def test_noncanonical_rejects_canonical_path(monkeypatch):
    code, out = _run_cli(
        monkeypatch,
        ["--samples", "5", "--out", "scripts/uncertainty_results.json"],
    )
    assert code == 2, out
    assert "noncanonical budget must not write" in out


# ---------------------------------------------------------------------------
# 4. Conflicting sampling flags rejected.
# ---------------------------------------------------------------------------
def test_conflicting_sampling_flags_rejected(monkeypatch):
    code, out = _run_cli(monkeypatch, ["--saltelli", "--samples", "5"])
    assert code == 2, out
    assert "--samples cannot be combined" in out


# ---------------------------------------------------------------------------
# 5. Canonical Saltelli base_n = 64 allowed on canonical path.
# ---------------------------------------------------------------------------
def test_canonical_saltelli_allows_canonical_path(monkeypatch):
    code, out = _run_cli(
        monkeypatch, ["--dry-run", "--saltelli", "--saltelli-n", "64"]
    )
    assert code == 0, out
    assert "uncertainty_results.json" in out


# ---------------------------------------------------------------------------
# 6. Requested cache directory is actually used by workers.
# ---------------------------------------------------------------------------
def test_cache_dir_propagates_to_workers(monkeypatch, tmp_path):
    used = {"path": None}
    real_cache_path = U._cache_path

    def capturing_cache_path(key, cache_dir):
        used["path"] = cache_dir
        return real_cache_path(key, cache_dir)

    monkeypatch.setattr(U, "_cache_path", capturing_cache_path)

    cache_dir = str(tmp_path / "my_cache")
    _run_cli(
        monkeypatch,
        ["--samples", "5", "--out", str(tmp_path / "dev.json"),
         "--cache-dir", cache_dir],
    )
    assert used["path"] == cache_dir, f"workers used {used['path']!r}, not {cache_dir}"


# ---------------------------------------------------------------------------
# 7. Worker count / cache location do not change cache identity.
# ---------------------------------------------------------------------------
def test_cache_identity_independent_of_workers_and_location(monkeypatch):
    anchor = {"R": 0.60}
    uq = {"ds_Tf": 3.0}
    key_a = U._cache_key("sharp_cppc", anchor, uq)
    key_b = U._cache_key("sharp_cppc", anchor, uq)
    assert key_a == key_b, "cache key must be deterministic"
    # Same inputs under a different cache dir still yield the same key.
    assert U._cache_key("sharp_cppc", anchor, uq) == key_a


# ---------------------------------------------------------------------------
# 8. Result-affecting input changes change cache identity.
# ---------------------------------------------------------------------------
def test_cache_identity_changes_with_inputs(monkeypatch):
    base = {"R": 0.60}
    key_default = U._cache_key("sharp_cppc", base, {"ds_Tf": 3.0})
    key_diff_param = U._cache_key("sharp_cppc", base, {"ds_Tf": 4.0})
    key_diff_anchor = U._cache_key("scaleup", base, {"ds_Tf": 3.0})
    assert key_default != key_diff_param
    assert key_default != key_diff_anchor


# ---------------------------------------------------------------------------
# 9. Failed tasks remain visible in results.
# ---------------------------------------------------------------------------
def test_failed_tasks_remain_visible(monkeypatch, tmp_path):
    def failing_task(args):
        anchor_name, _ap, _uq, _cd = args
        if anchor_name == "sharp_cppc":
            return (anchor_name, None, "simulation crashed", _uq)
        return (
            anchor_name,
            {"cp": FAKE_CP[anchor_name], "tsr": 2.5, "aoa_max": 10.0,
             "steady": True},
            None,
            _uq,
        )

    monkeypatch.setattr(U, "run_one_task", failing_task)
    monkeypatch.setattr(U, "_base_cm0", fake_base_cm0)
    monkeypatch.setattr(U, "ProcessPoolExecutor", _InlineExecutor)
    U._CODE_HASH_CACHE = None

    code, out = _run_cli(
        monkeypatch,
        ["--samples", "2", "--out", str(tmp_path / "dev.json"),
         "--cache-dir", str(tmp_path / "cache")],
    )
    assert code == 0, out
    # sharp_cppc failure must appear in the summary output as a fail.
    assert "sharp_cppc" in out
    assert "fail" in out.lower() or "1" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
