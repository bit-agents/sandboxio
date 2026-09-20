"""What every framework adapter shares: the LLM-facing description and result rendering."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from sandboxio.models import ExecResult
    from sandboxio.protocols import AsyncSandbox

# A ready sandbox (reused across calls; the caller owns its lifetime), or a zero-argument
# factory awaited per call (one sandbox per tool call, torn down after it).
SandboxSource: TypeAlias = "AsyncSandbox | Callable[[], Awaitable[AsyncSandbox]]"

CODE_DESCRIPTION = (
    "Run Python code in an isolated sandbox and return what it printed. Use print() for "
    "anything you need to see. The sandbox has no network access unless the operator "
    "allowed it, a fixed time limit, and only the packages already installed in it. Files "
    "written under /work persist for the life of the sandbox. Do not attempt to install "
    "packages or reach the internet; the attempt fails and the output tells you so."
)
COMMAND_DESCRIPTION = (
    "Run one shell command in an isolated sandbox and return its output. Same limits as "
    "the Python tool: no network unless allowed, a fixed time limit, no host access."
)
CODE_PARAM = "Complete Python source to execute. Output is what it prints."
COMMAND_PARAM = "The command line to run through sh -c inside the sandbox."


@asynccontextmanager
async def use(source: SandboxSource) -> AsyncGenerator[AsyncSandbox]:
    """Yield a sandbox from either form of ``SandboxSource``."""
    if callable(source):
        async with await source() as sb:
            yield sb
    else:
        yield source


def render(result: ExecResult) -> str:
    """What the model reads back: stdout, then stderr and the exit code only when relevant."""
    parts = [result.stdout.rstrip("\n")] if result.stdout.strip() else []
    if result.stderr.strip():
        parts.append(f"[stderr]\n{result.stderr.rstrip()}")
    for output in result.results or ():
        if output.mime_type == "text/plain" and output.data.strip():
            parts.append(output.data.rstrip())
    if not result.ok:
        parts.append(f"[exit code {result.exit_code}]")
    return "\n".join(parts) if parts else "(no output)"
