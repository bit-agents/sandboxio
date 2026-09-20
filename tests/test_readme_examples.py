"""Every Python block in the README runs verbatim (build-order Step 6 exit criterion).

Blocks that say Docker or E2B run against ``FakeBackend`` registered under those names via
``sandboxio.register`` — the same code path a user takes, minus the provider. Blocks that
define ``test_`` functions run through pytester with the ``sbx_fake`` plugin. Bash blocks
are documentation of shell commands and are not executed here.
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import ast
import inspect
import re
from collections.abc import Iterator
from typing import Any

import anyio
import pytest

from _helpers import REPO_ROOT
from sandboxio import registry
from sandboxio.testing.fake import FakeBackend

README = REPO_ROOT / "README.md"
FENCE = re.compile(r"^```(\w*)\s*$")
SKIP_MARKER = "<!-- doc-sample: skip -->"


def _python_blocks() -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    lines = README.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m or m.group(1) not in {"python", "py"}:
            i += 1
            continue
        start = i
        body: list[str] = []
        i += 1
        while i < len(lines) and lines[i] != "```":
            body.append(lines[i])
            i += 1
        i += 1
        if start > 0 and SKIP_MARKER in lines[start - 1]:
            continue
        blocks.append((f"README.md:{start + 1}", "\n".join(body) + "\n"))
    return blocks


BLOCKS = _python_blocks()


def test_the_readme_has_examples() -> None:
    assert len(BLOCKS) >= 4, "README example extraction broke"


@pytest.fixture
def fakes_as_providers() -> Iterator[None]:
    """`docker` and `e2b` resolve to fakes; the example code never knows."""
    registry._reset()
    registry.register("docker", lambda: FakeBackend())
    registry.register("e2b", lambda: FakeBackend())
    yield
    registry._reset()


def _is_pytest_block(source: str) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.parse(source).body
    )


@pytest.mark.parametrize(("where", "source"), BLOCKS, ids=[w for w, _ in BLOCKS])
def test_readme_example_runs_verbatim(
    where: str,
    source: str,
    fakes_as_providers: None,
    pytester: pytest.Pytester,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if _is_pytest_block(source):
        pytester.makepyfile(test_readme_example=source)
        expected = sum(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith("test_")
            for n in ast.parse(source).body
        )
        result = pytester.runpytest_inprocess("-q", "-p", "no:cacheprovider")
        result.assert_outcomes(passed=expected)
        return

    code = compile(source, where, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    namespace: dict[str, Any] = {"__name__": "__readme__"}
    if code.co_flags & inspect.CO_COROUTINE:

        async def run() -> None:
            await eval(code, namespace)

        anyio.run(run)
    else:
        exec(code, namespace)
    out, err = capsys.readouterr()
    assert err == "", f"{where} wrote to stderr:\n{err}"
    assert "Traceback" not in out
