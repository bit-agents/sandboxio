"""The spec/09 gate, so the normative page cannot name a bound the build does not declare.

`docs/spec/` wins over every other document, so a stale bound there is the most
authoritative wrong answer in the repo — and it is a pure string comparison.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "spec" / "09-integrations.md"

# `` `openai-agents>=0.19` `` in prose, and `sandboxio[mcp]` naming an extra.
BOUND = re.compile(r"`([A-Za-z0-9][A-Za-z0-9._-]*)\s*(>=\s*[0-9][^`]*)`")
EXTRA = re.compile(r"`sandboxio\[([a-z0-9,._-]+)\]`")

FIX = (
    "\n\ndocs/spec/ is normative, so it has to match pyproject.toml's "
    "[project.optional-dependencies]. Change whichever is wrong, then regenerate "
    "docs/llms-full.txt with scripts/gen_llms_full.py."
)


def _declared() -> dict[str, list[str]]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    extras: dict[str, list[str]] = pyproject["project"]["optional-dependencies"]
    return extras


def _spec() -> str:
    return SPEC.read_text("utf-8")


def test_bounds_named_in_the_spec_match_pyproject() -> None:
    declared = {
        re.split(r"[><=!~\[]", req, maxsplit=1)[0].strip(): req.strip()
        for reqs in _declared().values()
        for req in reqs
    }
    found = {name: f"{name}{bound}".replace(" ", "") for name, bound in BOUND.findall(_spec())}
    assert found, "the bound pattern matched nothing; spec/09 or this gate has drifted"

    wrong = {
        name: (spelled, declared.get(name, "not declared"))
        for name, spelled in found.items()
        if declared.get(name) != spelled
    }
    assert not wrong, (
        "docs/spec/09-integrations.md names a bound pyproject.toml does not declare:\n"
        + "\n".join(
            f"  {n}: spec says {s!r}, pyproject says {d!r}" for n, (s, d) in wrong.items()
        )
        + FIX
    )


def test_extras_named_in_the_spec_are_declared() -> None:
    named = {e for group in EXTRA.findall(_spec()) for e in group.split(",")}
    assert named, "the extra pattern matched nothing; spec/09 or this gate has drifted"

    undeclared = sorted(named - set(_declared()))
    assert not undeclared, (
        "docs/spec/09-integrations.md promises extras that do not exist: "
        + ", ".join(f"sandboxio[{e}]" for e in undeclared)
        + FIX
    )
