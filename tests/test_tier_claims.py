"""The tier gate, so a security claim about someone else's kernel cannot go bare.

ADR-0006 requires a dated provider source behind every published tier and H16 requires the
root-on-writable-rootfs disclosure at the top of the Docker pages. Both are prose restating
a decision, which is the class no link checker sees — and two of the places that drifted
are PyPI long descriptions, where nothing else in the repo is visible.
"""

from __future__ import annotations

import re

import pytest

from _helpers import REPO_ROOT

# The canonical dated table. Every other page has to agree with the date it states, so a
# quarterly re-verification (runbook) moves one date and the gate finds the stragglers.
CANONICAL = REPO_ROOT / "README.md"
READ_ON = re.compile(r"read on \*\*(\d{4}-\d{2}-\d{2})\*\*")

# The provider's own description of its mechanism — the only source ADR-0006 accepts.
SOURCES = {
    "CONTAINER": "https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/",
    "GVISOR": "https://modal.com/docs/guide/security",
    "MICROVM": "https://e2b.dev/security",
}

# Keyed by the adapter distribution's suffix, so a new packages/sandboxio-<name>/ forces an
# entry here rather than shipping a tier nobody sourced.
BACKENDS = {"docker": "CONTAINER", "e2b": "MICROVM", "modal": "GVISOR"}

# Pages that publish more than one tier: both canonical tables, and the security page a
# reader is sent to from every one of them.
SURVEYS = {
    "README.md": ("CONTAINER", "GVISOR", "MICROVM"),
    "docs/explanation/isolation-tiers.md": ("CONTAINER", "GVISOR", "MICROVM"),
    "docs/explanation/security-model.md": ("CONTAINER", "MICROVM"),
}

WHITESPACE = re.compile(r"\s+")
H16_ANCHOR = "hazards.md#h16--docker-sandboxes-run-as-root-on-a-writable-rootfs"


def claims() -> list[tuple[str, str]]:
    """Every (page, tier) pair a reader can meet outside the surveys."""
    pairs = []
    for package in sorted(REPO_ROOT.glob("packages/sandboxio-*")):
        name = package.name.removeprefix("sandboxio-")
        assert name in BACKENDS, f"{package.name} ships a tier; name it in BACKENDS"
        pairs.append((f"{package.relative_to(REPO_ROOT)}/README.md", BACKENDS[name]))
        how_to = REPO_ROOT / "docs" / "how-to" / f"{name}.md"
        if how_to.exists():
            pairs.append((f"docs/how-to/{name}.md", BACKENDS[name]))
    pairs += [(page, tier) for page, tiers in SURVEYS.items() for tier in tiers]
    return sorted(pairs)


@pytest.fixture(scope="module")
def read_on() -> str:
    match = READ_ON.search(CANONICAL.read_text(encoding="utf-8"))
    assert match, "README.md no longer dates its tier table; this gate has nothing to hold"
    return match.group(0)


@pytest.mark.parametrize(("page", "tier"), claims(), ids=lambda v: v)
def test_a_published_tier_carries_its_dated_source(page: str, tier: str, read_on: str) -> None:
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    assert tier in text, f"{page} no longer publishes {tier}; drop it from this gate"
    assert SOURCES[tier] in text, (
        f"{page} publishes {tier} without the provider's own description of the mechanism "
        f"({SOURCES[tier]}) — a security claim about someone else's system with nothing "
        f"behind it (ADR-0006, H4)."
    )
    assert read_on in text, (
        f"{page} sources {tier} but does not say when the page was read. Use "
        f"{read_on!r}, the date README.md's table states."
    )


@pytest.mark.parametrize(
    "page", ["packages/sandboxio-docker/README.md", "docs/how-to/docker.md"], ids=lambda v: v
)
def test_the_docker_pages_disclose_root_on_a_writable_rootfs(page: str) -> None:
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    prose = WHITESPACE.sub(" ", text).lower().replace("**", "")
    assert "as root on a writable rootfs" in prose, (
        f"{page} introduces the Docker backend without the disclosure H16 asks for at the "
        f"top: the sandbox runs as root on a writable rootfs. The honest statement is the "
        f"control here — there is no better default to reach for."
    )
    assert H16_ANCHOR in text, f"{page} states the gap but does not link H16 for the why"
