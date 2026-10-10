import os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_readme_in_sync():
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "build_readme.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, (
        "README.md drifted from scripts/*.json. "
        "Run: python3 scripts/build_readme.py\n" + r.stdout + r.stderr
    )