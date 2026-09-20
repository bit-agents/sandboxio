"""Every script in examples/ is executed, with `docker`/`e2b` resolving to FakeBackend.

Same bar as the README blocks (test_readme_examples.py): an example that no longer runs
fails CI instead of a stranger's first attempt. The halves that need a model provider are
behind a credential check and print why they stopped; this gate keeps the key unset so the
sandboxio half is what runs. `examples/test_my_tool.py` is collected by pytest directly.
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import importlib.util
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import cast

import anyio
import pytest

from _helpers import REPO_ROOT
from sandboxio import registry
from sandboxio.testing.fake import FakeBackend

EXAMPLES = sorted(
    p for p in (REPO_ROOT / "examples").glob("*.py") if not p.name.startswith("test_")
)
# Frameworks an example imports at module level, installed by `uv sync --all-extras`.
NEEDS: dict[str, str] = {
    "05_langgraph_agent.py": "langchain_core",
    "06_openai_agents.py": "agents",
}


def test_the_examples_are_discovered() -> None:
    assert len(EXAMPLES) >= 4, "example discovery broke — it found almost nothing"


def test_every_example_is_documented() -> None:
    index = (REPO_ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    missing = [p.name for p in EXAMPLES if p.name not in index]
    assert not missing, f"undocumented examples: {missing}"


@pytest.fixture
def fakes_as_providers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`docker` and `e2b` resolve to fakes; no example knows the difference."""
    registry._reset()
    registry.register("docker", lambda: FakeBackend())
    registry.register("e2b", lambda: FakeBackend())
    monkeypatch.setenv("E2B_API_KEY", "not-a-real-key")  # the fake never reads it
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    yield
    registry._reset()


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"sbx_example_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.name for p in EXAMPLES])
def test_example_runs(
    path: Path,
    fakes_as_providers: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if path.name in NEEDS:
        pytest.importorskip(NEEDS[path.name], reason=f"{path.name} needs the framework")

    module = _load(path)
    entry = getattr(module, "main", None)
    assert callable(entry), f"{path.name} must define an async main()"

    anyio.run(cast("Callable[[], Awaitable[None]]", entry))

    out, err = capsys.readouterr()
    assert out.strip(), f"{path.name} printed nothing"
    assert err == "", f"{path.name} wrote to stderr:\n{err}"
    assert "Traceback" not in out
