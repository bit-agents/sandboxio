from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_python(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a clean, isolated child interpreter from the repo root."""
    return subprocess.run(
        [sys.executable, "-I", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )


def stdout_of(*args: str) -> str:
    proc = run_python(*args)
    if proc.returncode != 0:
        raise AssertionError(f"child interpreter failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout
