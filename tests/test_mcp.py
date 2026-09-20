"""The MCP server (spec/09): few tools, nothing on the host, config fixed at start."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from _helpers import REPO_ROOT
from sandboxio import registry
from sandboxio.testing.fake import FakeBackend

pytestmark = pytest.mark.anyio

mcp = pytest.importorskip("mcp")

EXPECTED_TOOLS = {
    "run_python",
    "run_command",
    "read_file",
    "write_file",
    "list_files",
    "sandbox_info",
}


@pytest.fixture
def fake() -> Iterator[FakeBackend]:
    registry._reset()
    fake = FakeBackend()
    registry.register("fake", lambda: fake)
    yield fake
    registry._reset()


def _structured(result: Any) -> Any:
    return result.structured_content


async def test_exactly_the_specified_tools_and_listing_provisions_nothing(
    fake: FakeBackend,
) -> None:
    from sandboxio.mcp import build_server

    server = build_server("fake://")
    assert {t.name for t in await server.list_tools()} == EXPECTED_TOOLS
    assert fake.live_sandboxes() == 0, "listing tools must not create a sandbox"


async def test_tools_route_through_one_sandbox_and_return_the_spec_shape(
    fake: FakeBackend,
) -> None:
    from sandboxio.mcp import build_server

    server = build_server("fake://", timeout=42)
    out = _structured(await server.call_tool("run_python", {"code": "print(6 * 7)"}))
    assert out == {"stdout": "42\n", "stderr": "", "exit_code": 0, "results": []}
    out = _structured(await server.call_tool("run_command", {"cmd": "echo hi"}))
    assert out["stdout"] == "hi\n" and out["exit_code"] == 0
    await server.call_tool("write_file", {"path": "/work/a.txt", "content": "payload"})
    read = await server.call_tool("read_file", {"path": "/work/a.txt"})
    assert _structured(read) == {"result": "payload"}
    listed = _structured(await server.call_tool("list_files", {"path": "/work"}))
    assert listed == {"result": [{"path": "/work/a.txt", "size": 7, "is_dir": False}]}
    info = _structured(await server.call_tool("sandbox_info", {}))
    assert info["backend"] == "fake://" and info["isolation"] == "container"
    assert info["network"] == {"egress": "deny", "allow": []} and info["timeout_s"] == 42
    assert "RUN_CODE" in info["capabilities"]
    assert fake.live_sandboxes() == 1, "one sandbox per server process"
    assert fake.calls[0].network is not None and fake.calls[0].network.egress == "deny"


async def test_sandbox_errors_become_tool_errors_the_model_can_read(
    fake: FakeBackend,
) -> None:
    """Only ToolError messages reach the model; a raw exception is hidden as a crash."""
    from mcp.server.mcpserver.exceptions import ToolError

    from sandboxio.errors import PathNotFound
    from sandboxio.mcp import build_server

    server = build_server("fake://")
    with pytest.raises(ToolError) as info:
        await server.call_tool("read_file", {"path": "/nope"})
    assert "SBX_E1701" in str(info.value) and "Fix:" in str(info.value)
    causes: list[BaseException] = []
    exc: BaseException | None = info.value
    while exc is not None:
        causes.append(exc)
        exc = exc.__cause__
    assert any(isinstance(c, PathNotFound) for c in causes), "the original error stays chained"


def test_no_tool_touches_the_host_and_no_config_mutation_tool_exists() -> None:
    source = (REPO_ROOT / "src" / "sandboxio" / "mcp" / "__init__.py").read_text()
    for forbidden in ("subprocess", "os.system", "os.popen", "exec(", "eval("):
        assert forbidden not in source, f"{forbidden!r} in the MCP server"
    tool_names = set(re.findall(r"async def (\w+)\(", source))
    assert not any(n.startswith(("set_", "configure", "update_")) for n in tool_names)
    assert '"127.0.0.1"' in source, "binds localhost unless told otherwise"


async def test_stdio_end_to_end_with_a_real_client() -> None:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-I", "-m", "sandboxio.mcp", "--backend", "fake://"],
        cwd=str(REPO_ROOT),
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        assert {t.name for t in tools.tools} == EXPECTED_TOOLS
        result = await session.call_tool("run_python", {"code": "print('over stdio')"})
        assert _structured(result)["stdout"] == "over stdio\n"
        failed = await session.call_tool("read_file", {"path": "/nope"})
        assert failed.is_error, "a sandbox error reaches the model as an error result"
        text = str(failed.content[0].text)  # type: ignore[union-attr]
        assert "SBX_E1701" in text and "Fix:" in text, "code and fix reach the model"
