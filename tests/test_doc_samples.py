"""Every machine-readable sample in the docs is parsed, never eyeballed.

The input design set shipped a routing config that was not valid YAML (spec/07).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import yaml

from _helpers import REPO_ROOT

SKIP_MARKER = "<!-- doc-sample: skip -->"
FENCE = re.compile(r"^(?P<indent>\s*)(?P<ticks>```+|~~~+)(?P<info>.*)$")
PARSED_LANGS = {"yaml", "yml", "json", "python", "py"}


class Sample(str):
    """A fenced block, carrying its location so pytest ids point at the source line."""

    lang: str
    where: str

    def __new__(cls, text: str, lang: str, where: str) -> Sample:
        self = super().__new__(cls, text)
        self.lang, self.where = lang, where
        return self


def _markdown_files() -> list[Path]:
    return sorted(
        p for p in REPO_ROOT.rglob("*.md") if ".git" not in p.parts and ".venv" not in p.parts
    )


def _samples() -> list[Sample]:
    found: list[Sample] = []
    for path in _markdown_files():
        rel = path.relative_to(REPO_ROOT)
        lines = path.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            opening = FENCE.match(lines[i])
            if not opening:
                i += 1
                continue
            indent, ticks = opening["indent"], opening["ticks"]
            lang = opening["info"].strip().split()[0].lower() if opening["info"].strip() else ""
            start, i = i, i + 1
            body: list[str] = []
            while i < len(lines) and not (
                lines[i].startswith(indent + ticks)
                and not lines[i][len(indent + ticks) :].strip()
            ):
                body.append(lines[i][len(indent) :])
                i += 1
            i += 1
            skipped = start > 0 and SKIP_MARKER in lines[start - 1]
            if lang in PARSED_LANGS and not skipped:
                found.append(Sample("\n".join(body), lang, f"{rel}:{start + 1}"))
    return found


SAMPLES = _samples()


def test_the_docs_actually_contain_samples() -> None:
    assert len(SAMPLES) > 20, "sample extraction broke — it found almost nothing"


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.where)
def test_sample_parses(sample: Sample) -> None:
    if sample.lang in {"yaml", "yml"}:
        yaml.safe_load(sample)
    elif sample.lang == "json":
        json.loads(sample)
    else:
        # Docs show real call sites, so top-level await has to be legal here.
        compile(sample, sample.where, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
