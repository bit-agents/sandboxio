"""The placeholder inventory, so an unfilled marker cannot reach a release unnoticed.

A new `{{PLACEHOLDER}}` or `TODO(placeholder)` fails here; filling one fails here too,
until its row is deleted. Neither can land unnoticed.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".claude", "dist", "htmlcov"}
SUFFIXES = {".md", ".txt", ".py", ".yaml", ".yml", ".toml", ".cfg"}

# Upper-case only: `{{sandboxio.debug}}` in the MCP catalog entry is Docker's own template
# syntax, not ours.
PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")

# Every unfilled placeholder in the tree. Delete a row when it is filled.
EXPECTED: dict[str, int] = {
    "{{DOCS_URL}}": 2,  # blocked on the docs site being deployed, not on the domain
    "{{INSTALL}}": 4,  # nothing is published to PyPI yet
}

# Files still carrying a `TODO(placeholder)` marker.
EXPECTED_TODO = {
    "README.md",
    "docs/llms-full.txt",
    "docs/quickstart.md",
    "examples/README.md",
}


SELF = Path(__file__).resolve()


def _files() -> list[Path]:
    # This file spells the markers out, so it cannot be its own subject.
    return [
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and p.suffix in SUFFIXES
        and p.resolve() != SELF
        and not SKIP_DIRS & set(p.relative_to(ROOT).parts)
    ]


def test_placeholder_inventory_is_unchanged() -> None:
    markers = (m for p in _files() for m in PLACEHOLDER.findall(p.read_text("utf-8")))
    found = dict(Counter(markers))
    assert found == EXPECTED, f"the inventory moved; fill it or update EXPECTED. Found {found}"


def test_todo_placeholder_markers_are_unchanged() -> None:
    found = {
        str(p.relative_to(ROOT))
        for p in _files()
        if "TODO(placeholder)" in p.read_text("utf-8")
    }
    assert found == EXPECTED_TODO, f"TODO(placeholder) markers moved. Found {sorted(found)}"
