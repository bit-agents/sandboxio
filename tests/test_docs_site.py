"""The published site keeps the URLs the library prints (ADR-0010, ADR-0029)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from _helpers import REPO_ROOT
from sandboxio.errors import DOCS_ERRORS_URL, catalog

pytestmark = [
    pytest.mark.docs,
    pytest.mark.skipif(
        importlib.util.find_spec("mkdocs") is None,
        reason="needs `uv sync --group docs`",
    ),
]


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("site")
    proc = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict", "--site-dir", str(out)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return out


def test_every_error_code_has_a_stable_url(site: Path) -> None:
    missing = [
        e.code for e in catalog() if not (site / "errors" / e.code / "index.html").is_file()
    ]
    assert not missing, f"codes with no page at {DOCS_ERRORS_URL}/<code>: {missing}"


def test_the_entry_points_are_where_the_docs_promise(site: Path) -> None:
    for page in ("index.html", "errors/index.html", "llms.txt", "llms-full.txt"):
        assert (site / page).is_file(), page


def test_the_custom_domain_ships_with_the_site(site: Path) -> None:
    assert (site / "CNAME").read_text().strip() == "docs.sandboxio.dev"
