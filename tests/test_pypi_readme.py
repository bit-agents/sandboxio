"""No README link reaches PyPI relative, where it renders as a dead link.

The READMEs stay relative on disk — that is the form scripts/check_doc_links.py can
validate — and hatch-fancy-pypi-readme rewrites them for the long description only. This
gate applies the configured substitutions itself, so a link in a shape the patterns miss
fails here rather than on the project page.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from _helpers import REPO_ROOT

PYPROJECTS = [
    REPO_ROOT / "pyproject.toml",
    *sorted(REPO_ROOT.glob("packages/*/pyproject.toml")),
]
LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
ABSOLUTE = ("http://", "https://", "mailto:", "#")


def long_description(pyproject: Path) -> str:
    hook = tomllib.loads(pyproject.read_text(encoding="utf-8"))["tool"]["hatch"]["metadata"][
        "hooks"
    ]["fancy-pypi-readme"]
    text = "".join(
        (pyproject.parent / f["path"]).read_text(encoding="utf-8") for f in hook["fragments"]
    )
    for sub in hook["substitutions"]:
        text = re.sub(sub["pattern"], sub["replacement"], text)
    return text


@pytest.mark.parametrize("pyproject", PYPROJECTS, ids=lambda p: p.parent.name)
def test_the_long_description_carries_no_relative_link(pyproject: Path) -> None:
    dead = [t for t in LINK.findall(long_description(pyproject)) if not t.startswith(ABSOLUTE)]
    assert not dead, f"relative after rewriting, dead on PyPI: {sorted(set(dead))}"


@pytest.mark.parametrize("pyproject", PYPROJECTS, ids=lambda p: p.parent.name)
def test_the_readme_is_dynamic_metadata(pyproject: Path) -> None:
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    assert "readme" in project["dynamic"], "the hook only runs for dynamic readme metadata"
    assert "readme" not in project, "a static readme would ship unrewritten"


@pytest.mark.parametrize("pyproject", PYPROJECTS, ids=lambda p: p.parent.name)
def test_the_rewrite_leaves_the_readme_on_disk_relative(pyproject: Path) -> None:
    text = (pyproject.parent / "README.md").read_text(encoding="utf-8")
    assert [t for t in LINK.findall(text) if not t.startswith(ABSOLUTE)], (
        "no relative link left to rewrite; this gate would pass vacuously"
    )
