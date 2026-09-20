"""llms.txt points only at pages that exist, and llms-full.txt is regenerated, never edited."""

from __future__ import annotations

import re

from _helpers import REPO_ROOT, run_python

DOCS = REPO_ROOT / "docs"


def test_llms_txt_links_resolve_and_full_text_is_current() -> None:
    index = (DOCS / "llms.txt").read_text()
    targets = re.findall(r"\]\(([^)]+)\)", index)
    assert len(targets) > 15
    for target in targets:
        assert (DOCS / target).exists(), f"llms.txt points at a missing page: {target}"
    proc = run_python(str(REPO_ROOT / "scripts" / "gen_llms_full.py"), "--check")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_full_text_carries_the_key_pages() -> None:
    full = (DOCS / "llms-full.txt").read_text()
    for name in ("README.md", "docs/quickstart.md", "docs/spec/03-public-api.md"):
        assert f"# FILE: {name}" in full
