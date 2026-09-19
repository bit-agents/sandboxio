"""Import budget: agents cold-start this on every run (ADR-0012, H8)."""

from __future__ import annotations

import pytest

from _helpers import run_python

BUDGET_MS = 150.0
HARD_CEILING_MS = 200.0
RUNS = 5


def _cumulative_ms() -> float:
    """Cumulative `import sandboxio` time, best of RUNS — the minimum drops scheduler noise."""
    samples: list[float] = []
    for _ in range(RUNS):
        proc = run_python("-X", "importtime", "-c", "import sandboxio")
        assert proc.returncode == 0, proc.stderr
        for line in proc.stderr.splitlines():
            if line.rsplit("|", 1)[-1].strip() == "sandboxio":
                samples.append(int(line.split("|")[1].strip()) / 1000)
                break
    if not samples:
        pytest.fail("no `sandboxio` line in -X importtime output")
    return min(samples)


def test_import_stays_within_budget() -> None:
    elapsed = _cumulative_ms()
    assert elapsed <= HARD_CEILING_MS, f"import took {elapsed:.1f} ms — past the hard ceiling"
    assert elapsed <= BUDGET_MS, (
        f"import took {elapsed:.1f} ms — over the {BUDGET_MS:.0f} ms budget"
    )
