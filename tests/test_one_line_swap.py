"""The v0.1 promise: swap the DSN and the downstream code runs unchanged (step 5)."""

from __future__ import annotations

import os

import pytest

import sandboxio
from sandboxio import Capability
from sandboxio.protocols import AsyncSandbox

pytestmark = pytest.mark.anyio


async def agent_tool(sb: AsyncSandbox) -> str:
    """Downstream code that knows nothing about which backend it runs on."""
    await sb.files.write("/tmp/sbx-swap-input.txt", "3 4\n")
    res = await sb.run_code(
        "a, b = open('/tmp/sbx-swap-input.txt').read().split()\nprint(int(a) * int(b))"
    )
    res.raise_for_status()
    if Capability.STREAMING in sb.capabilities:
        async with sb.stream(["echo", "streamed"]) as proc:
            chunks = b"".join([c.data async for c in proc])
            assert (await proc.wait()).ok
        assert chunks.strip() == b"streamed"
    return res.stdout.strip()


DSNS = [
    pytest.param("fake://", id="fake"),
    pytest.param("docker://python:3.12-slim", id="docker", marks=pytest.mark.docker),
    pytest.param(
        "e2b://",
        id="e2b",
        marks=[
            pytest.mark.e2b,
            pytest.mark.enable_socket,
            pytest.mark.skipif(not os.environ.get("E2B_API_KEY"), reason="E2B_API_KEY not set"),
        ],
    ),
]


@pytest.mark.parametrize("dsn", DSNS)
async def test_same_code_runs_on_every_backend(dsn: str) -> None:
    if dsn == "fake://":
        # The fake executes nothing, so the arithmetic is scripted the way a user would.
        from sandboxio import registry
        from sandboxio.models import ExecResult
        from sandboxio.testing.fake import FakeBackend

        fake = FakeBackend()
        fake.on_run_code(match="int(a) * int(b)", returns=ExecResult(0, "12\n", ""))
        registry.register("fake", lambda: fake)
    async with await sandboxio.create(dsn, timeout=120) as sb:
        assert await agent_tool(sb) == "12"
