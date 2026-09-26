"""The DSN gate, so published prose cannot name an E2B template that does not exist.

`e2b://code-interpreter` sat in the normative spec while the adapter, the shipped MCP image
and every how-to said `code-interpreter-v1`, so a reader copying from the most authoritative
page got a template E2B does not serve. Which of the two is right is a string comparison.
"""

from __future__ import annotations

import re
from pathlib import Path

from _helpers import REPO_ROOT

# Read, not imported: a documentation gate should not need the provider SDK installed.
BACKEND = REPO_ROOT / "packages" / "sandboxio-e2b" / "src" / "sandboxio_e2b" / "_backend.py"
DEFAULT = re.compile(r'^DEFAULT_TEMPLATE = "([^"]+)"', re.MULTILINE)

# E2B's stock template wherever it is named. A placeholder that names nothing upstream —
# `e2b://my-template` in the MCP image's README — is left alone.
STOCK = re.compile(r"e2b://(code-interpreter[A-Za-z0-9._-]*)")

ROOTS = ("docs", "docker", "examples", "packages", "src")
SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".txt"}

# docs/adr/ records what was decided on a date and is immutable once Accepted
# (docs/adr/README.md); docs/llms-full.txt is generated from the pages beside it.
SKIP = ("docs/adr/", "docs/llms-full.txt")


def default_template() -> str:
    found = DEFAULT.search(BACKEND.read_text(encoding="utf-8"))
    assert found, "sandboxio_e2b no longer defines DEFAULT_TEMPLATE; this gate lost its anchor"
    return found.group(1)


def pages() -> list[Path]:
    files = sorted(REPO_ROOT.glob("*.md"))
    for root in ROOTS:
        files += sorted(
            p
            for p in (REPO_ROOT / root).rglob("*")
            if p.is_file() and (p.suffix in SUFFIXES or p.name == "Dockerfile")
        )
    return [f for f in files if not str(f.relative_to(REPO_ROOT)).startswith(SKIP)]


def test_every_named_e2b_template_is_the_one_the_adapter_uses() -> None:
    template = default_template()
    wrong = [
        f"{page.relative_to(REPO_ROOT)}:{line}: e2b://{named}"
        for page in pages()
        for line, text in enumerate(page.read_text(encoding="utf-8").splitlines(), start=1)
        for named in STOCK.findall(text)
        if named != template
    ]
    assert not wrong, (
        f"these name an E2B template that is not {template!r}, the one sandboxio_e2b "
        f"creates by default:\n" + "\n".join(f"  {w}" for w in wrong)
    )
