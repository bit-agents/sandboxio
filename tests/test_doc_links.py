from __future__ import annotations

from _helpers import REPO_ROOT, run_python


def test_every_relative_link_and_anchor_resolves() -> None:
    proc = run_python(str(REPO_ROOT / "scripts" / "check_doc_links.py"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
