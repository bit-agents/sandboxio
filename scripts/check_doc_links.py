#!/usr/bin/env python3
"""Fail if any relative Markdown link or heading anchor in the repo does not resolve.

The spec is the contract, so a dead link into it is the same class of defect as a
config sample that does not parse. Stdlib only: this runs before the package exists.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__"}

FENCE = re.compile(r"^(```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")
LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
MD_LINK_IN_HEADING = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def strip_fences(text: str) -> str:
    """Blank out fenced code blocks so their contents are never parsed as markup."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line.strip()):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def slugify(heading: str) -> str:
    """Approximate github-slugger: strip markup, drop punctuation, spaces to hyphens."""
    text = MD_LINK_IN_HEADING.sub(r"\1", heading).lower()
    text = re.sub(r"[`*~]", "", text)
    text = "".join(c for c in text if c.isalnum() or c in " -_")
    return text.replace(" ", "-")


def anchors_of(text: str) -> set[str]:
    seen: dict[str, int] = {}
    result: set[str] = set()
    for line in strip_fences(text).splitlines():
        m = HEADING.match(line)
        if not m:
            continue
        base = slugify(m.group(2))
        n = seen.get(base, 0)
        seen[base] = n + 1
        result.add(base if n == 0 else f"{base}-{n}")
    return result


def markdown_files() -> list[Path]:
    return sorted(
        p for p in ROOT.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(ROOT).parts)
    )


def main() -> int:
    anchor_cache: dict[Path, set[str]] = {}
    problems: list[str] = []

    for path in markdown_files():
        body = strip_fences(path.read_text(encoding="utf-8"))
        for lineno, line in enumerate(body.splitlines(), 1):
            for _label, target in LINK.findall(line):
                if target.startswith(("http://", "https://", "mailto:", "#!")):
                    continue
                rel, _, fragment = target.partition("#")
                where = f"{path.relative_to(ROOT)}:{lineno}"

                if not rel:
                    dest = path
                else:
                    dest = (path.parent / rel).resolve()
                    if not dest.exists():
                        problems.append(f"{where}: no such path -> {target}")
                        continue

                if not fragment or dest.is_dir():
                    continue
                if dest.suffix.lower() != ".md":
                    continue
                if dest not in anchor_cache:
                    anchor_cache[dest] = anchors_of(dest.read_text(encoding="utf-8"))
                if fragment not in anchor_cache[dest]:
                    problems.append(f"{where}: no such anchor -> {target}")

    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"\n{len(problems)} broken link(s)", file=sys.stderr)
        return 1

    print(f"{len(markdown_files())} files checked, all links and anchors resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
