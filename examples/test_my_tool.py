"""Test an agent tool with no Docker, no network and no provider account.

Run: uv run pytest examples/test_my_tool.py

`sbx_fake` is a pytest fixture installed with the package. The fake executes nothing,
records every call, and passes the same contract suite the real backends do.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sandboxio import ExecResult, ExecutionError

if TYPE_CHECKING:
    from sandboxio.protocols import AsyncSandbox
    from sandboxio.testing import FakeBackend


async def pandas_version(sb: AsyncSandbox) -> str:
    """The tool under test: your code, typed against the protocol, not against a backend."""
    res = await sb.run_code("import pandas; print(pandas.__version__)")
    res.raise_for_status()
    return res.stdout.strip()


@pytest.mark.anyio
async def test_the_tool_reads_the_version(sbx_fake: FakeBackend) -> None:
    sbx_fake.on_run_code(match="import pandas", returns=ExecResult(0, "2.2.1\n", ""))

    assert await pandas_version(sbx_fake.sandbox) == "2.2.1"

    assert sbx_fake.calls[-1].op == "run_code"
    assert sbx_fake.calls[0].network is not None
    assert sbx_fake.calls[0].network.egress == "deny"  # the default, as recorded


@pytest.mark.anyio
async def test_the_tool_raises_when_the_import_fails(sbx_fake: FakeBackend) -> None:
    sbx_fake.on_run_code(
        match="import pandas",
        returns=ExecResult(1, "", "ModuleNotFoundError: No module named 'pandas'\n"),
    )

    with pytest.raises(ExecutionError) as caught:
        await pandas_version(sbx_fake.sandbox)

    assert caught.value.code == "SBX_E1301"
    assert "ModuleNotFoundError" in caught.value.result.stderr
