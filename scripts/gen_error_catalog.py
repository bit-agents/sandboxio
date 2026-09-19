#!/usr/bin/env python3
"""Render docs/errors/ from the catalog in sandboxio.errors, or --check that it is current.

Codes, hints and pages cannot drift because the pages are never hand-written (spec/04).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sandboxio.errors import CatalogEntry, catalog

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "errors"
STAMP = (
    "<!-- Generated from src/sandboxio/errors.py by scripts/gen_error_catalog.py. "
    "Do not edit by hand. -->"
)


def render_page(entry: CatalogEntry) -> str:
    parents = ", ".join(f"`{b}`" for b in entry.bases)
    lines = [
        f"# {entry.code} — `{entry.name}`",
        "",
        entry.summary,
        "",
        "**Fix**",
        "",
        "```text",
        entry.hint,
        "```",
        "",
        f"**Class:** `sandboxio.errors.{entry.name}` · **Inherits:** {parents}",
        "",
        f"Stable URL: <{entry.url}>. Codes are semver-covered API; this code will not be",
        "renamed or repurposed ([ADR-0010](../adr/0010-stable-error-codes.md)).",
        "",
        "[← All error codes](README.md)",
        "",
        STAMP,
        "",
    ]
    return "\n".join(lines)


def render_index(entries: tuple[CatalogEntry, ...]) -> str:
    rows = [f"| [{e.code}]({e.code}.md) | `{e.name}` | {e.summary} |" for e in entries]
    lines = [
        "# Error codes",
        "",
        "Every sandboxio exception carries one of these codes, a hint with the exact fix, and",
        "a link to its page here. Codes are stable across releases",
        "([spec/04](../spec/04-errors.md), [ADR-0010](../adr/0010-stable-error-codes.md)).",
        "",
        "| Code | Class | Meaning |",
        "|------|-------|---------|",
        *rows,
        "",
        STAMP,
        "",
    ]
    return "\n".join(lines)


def expected_files() -> dict[Path, str]:
    entries = catalog()
    files = {OUT / f"{e.code}.md": render_page(e) for e in entries}
    files[OUT / "README.md"] = render_index(entries)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if docs/errors/ is stale")
    args = parser.parse_args()

    expected = expected_files()
    if not args.check:
        OUT.mkdir(parents=True, exist_ok=True)
        for stale in OUT.glob("*.md"):
            if stale not in expected:
                stale.unlink()
        for path, text in expected.items():
            path.write_text(text, encoding="utf-8")
        print(f"wrote {len(expected)} files to {OUT.relative_to(ROOT)}")
        return 0

    problems = [
        f"stale or missing: {p.relative_to(ROOT)}"
        for p, text in expected.items()
        if not p.exists() or p.read_text(encoding="utf-8") != text
    ]
    problems += [
        f"page without a code: {p.relative_to(ROOT)}"
        for p in OUT.glob("*.md")
        if p not in expected
    ]
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print("\nrun: uv run python scripts/gen_error_catalog.py", file=sys.stderr)
        return 1
    print(f"{len(expected)} error pages current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
