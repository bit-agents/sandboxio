"""Release plumbing that a compromised upstream could otherwise walk through.

Supply-chain compromise of sandboxio itself is in the threat model (spec/05); the publish
job holds `id-token: write`, so a re-tagged third-party action would run with it.
"""

from __future__ import annotations

import re

import pytest

from _helpers import REPO_ROOT

WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)", re.MULTILINE)
PINNED = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def test_workflows_exist() -> None:
    assert WORKFLOWS, "no workflows found; this gate would pass vacuously"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_commit_sha(path: object) -> None:
    from pathlib import Path

    assert isinstance(path, Path)
    unpinned = [
        ref
        for ref in USES.findall(path.read_text())
        if not ref.startswith("./") and not PINNED.match(ref)
    ]
    assert not unpinned, (
        f"{path.name} uses a mutable ref: {unpinned}. Pin to a 40-char commit SHA with the "
        f"version in a trailing comment — a re-tagged action runs with the job's permissions."
    )


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_pin_records_the_version_it_came_from(path: object) -> None:
    """A bare SHA nobody can read is a pin nobody will ever update."""
    from pathlib import Path

    assert isinstance(path, Path)
    for line in path.read_text().splitlines():
        if "uses:" in line and "@" in line and not line.strip().startswith("#"):
            comment = line.split("uses:", 1)[1]
            assert "#" in comment, f"{path.name}: unlabelled pin: {line.strip()}"


def test_elevated_permissions_stay_in_the_publish_job() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert text.index("permissions:\n  contents: read") < text.index("id-token: write")
    assert "attestations: write" in text
