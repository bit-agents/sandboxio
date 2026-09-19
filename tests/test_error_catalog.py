"""The gate from spec/04: every code has a page, every page a code, and nothing is stale."""

from __future__ import annotations

from _helpers import REPO_ROOT, run_python
from sandboxio.errors import catalog

ERRORS_DIR = REPO_ROOT / "docs" / "errors"


def test_generated_pages_are_current() -> None:
    proc = run_python(str(REPO_ROOT / "scripts" / "gen_error_catalog.py"), "--check")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_code_has_a_page_and_every_page_a_code() -> None:
    pages = {p.stem for p in ERRORS_DIR.glob("SBX_E*.md")}
    assert pages == {e.code for e in catalog()}
    assert (ERRORS_DIR / "README.md").exists()
