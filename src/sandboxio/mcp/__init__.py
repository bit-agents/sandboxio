"""The MCP server (spec/09): ``python -m sandboxio.mcp --backend docker://python:3.12-slim``.

One sandbox per server process, created on the first tool call and killed at shutdown.
The backend DSN and policy are fixed at start; there is no tool that changes them, and no
tool ever executes on the host. Installed by ``sandboxio[mcp]``; binds localhost unless
``--host`` says otherwise.
"""

from __future__ import annotations

import argparse
import functools
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, TypeVar

import anyio

import sandboxio
from sandboxio.errors import SandboxError
from sandboxio.models import Capability, NetworkPolicy

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence

    from mcp.server.mcpserver import MCPServer

    from sandboxio.protocols import AsyncSandbox

__all__ = ["build_server", "main"]

DEFAULT_BACKEND = "docker://python:3.12-slim"
DEFAULT_TIMEOUT = 300.0
INSTRUCTIONS = (
    "Code and commands run inside an isolated sandbox with no network access, a fixed "
    "time limit and no access to this machine. Use run_python for computation; print() "
    "what you need to see. Files under /work persist for the session."
)


class _Session:
    """Owns the one sandbox. Creation is lazy so `list_tools` never provisions anything."""

    def __init__(self, dsn: str, *, timeout: float, egress: str) -> None:
        self.dsn = dsn
        self.timeout = timeout
        self.network = NetworkPolicy(egress="allow" if egress == "allow" else "deny")
        self._sandbox: AsyncSandbox | None = None
        self._lock = anyio.Lock()

    async def sandbox(self) -> AsyncSandbox:
        async with self._lock:
            if self._sandbox is None:
                self._sandbox = await sandboxio.create(
                    self.dsn,
                    timeout=self.timeout,
                    network=self.network,
                    metadata={"sandboxio_mcp": "1"},
                )
            return self._sandbox

    async def close(self) -> None:
        sb, self._sandbox = self._sandbox, None
        if sb is not None:
            await sb.__aexit__(None, None, None)


_F = TypeVar("_F", bound="Callable[..., Awaitable[Any]]")


def _tool(fn: _F) -> _F:
    """A ``SandboxError`` reaches the model with its code, fix and docs URL, not as a crash.

    The MCP server forwards only ``ToolError`` messages; anything else is logged server-side
    and replaced by a generic line. The message is already redacted (spec/06).
    """
    from mcp.server.mcpserver.exceptions import ToolError

    @functools.wraps(fn)
    async def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except SandboxError as exc:
            raise ToolError(str(exc)) from exc

    return guarded  # type: ignore[return-value]


def _result(res: sandboxio.ExecResult) -> dict[str, Any]:
    return {
        "stdout": res.stdout,
        "stderr": res.stderr,
        "exit_code": res.exit_code,
        "results": [{"mime_type": r.mime_type, "data": r.data} for r in res.results or ()],
    }


def build_server(
    backend: str = DEFAULT_BACKEND, *, timeout: float = DEFAULT_TIMEOUT, egress: str = "deny"
) -> MCPServer:
    """The configured server: run_python, run_command, read/write/list files, sandbox_info.

    >>> server = build_server("fake://")
    >>> sorted(t.name for t in anyio.run(server.list_tools))[:2]
    ['list_files', 'read_file']
    """
    from mcp.server.mcpserver import MCPServer

    session = _Session(backend, timeout=timeout, egress=egress)

    @asynccontextmanager
    async def lifespan(_server: MCPServer[None]) -> AsyncGenerator[None]:
        try:
            yield
        finally:
            await session.close()

    server: MCPServer[None] = MCPServer(
        "sandboxio", instructions=INSTRUCTIONS, version=sandboxio.__version__, lifespan=lifespan
    )

    @server.tool(
        description="Run Python code in the sandbox; returns stdout, stderr, exit_code."
    )
    @_tool
    async def run_python(code: str) -> dict[str, Any]:
        sb = await session.sandbox()
        return _result(await sb.run_code(code))

    @server.tool(description="Run one shell command in the sandbox; same shape as run_python.")
    @_tool
    async def run_command(cmd: str) -> dict[str, Any]:
        sb = await session.sandbox()
        return _result(await sb.run(cmd))

    @server.tool(description="Read a file from the sandbox filesystem as text.")
    @_tool
    async def read_file(path: str) -> str:
        sb = await session.sandbox()
        return (await sb.files.read(path)).decode(errors="replace")

    @server.tool(description="Write text to a file in the sandbox filesystem.")
    @_tool
    async def write_file(path: str, content: str) -> str:
        sb = await session.sandbox()
        await sb.files.write(path, content)
        return f"wrote {len(content.encode())} bytes to {path}"

    @server.tool(description="List a directory in the sandbox filesystem.")
    @_tool
    async def list_files(path: str = "/work") -> list[dict[str, Any]]:
        sb = await session.sandbox()
        entries = await sb.files.ls(path)
        return [{"path": e.path, "size": e.size, "is_dir": e.is_dir} for e in entries]

    @server.tool(description="Backend, isolation tier, capabilities and the policy in effect.")
    @_tool
    async def sandbox_info() -> dict[str, Any]:
        sb = await session.sandbox()
        return {
            "backend": session.dsn,
            "sandbox_id": sb.id,
            "isolation": sb.isolation.value,
            "capabilities": [c.name for c in Capability if c in sb.capabilities],
            "network": {"egress": session.network.egress, "allow": list(session.network.allow)},
            "timeout_s": session.timeout,
        }

    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sandboxio.mcp", description="Serve one sandbox over MCP."
    )
    parser.add_argument("--backend", default=DEFAULT_BACKEND, metavar="DSN")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, metavar="SECONDS")
    parser.add_argument(
        "--egress", choices=["deny", "allow"], default="deny", help="fixed for the process"
    )
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP only; localhost by default")
    parser.add_argument("--port", type=int, default=8000, help="HTTP only")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m sandboxio.mcp``."""
    args = build_parser().parse_args(argv)
    server = build_server(args.backend, timeout=args.timeout, egress=args.egress)
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)
    return 0
