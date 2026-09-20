"""LangGraph / LangChain: ``make_code_tool()`` returns a native ``BaseTool`` (spec/09).

Installed by ``sandboxio[langgraph]`` (``langchain-core>=0.3``); the sandbox inherits every
security default — deny egress, the timeout, the caps — because nothing here can change them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sandboxio.integrations import _common

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from sandboxio.integrations._common import SandboxSource

__all__ = ["make_code_tool", "make_command_tool"]


def make_code_tool(
    sandbox: SandboxSource,
    *,
    name: str = "run_python",
    description: str = _common.CODE_DESCRIPTION,
    timeout: float | None = None,
) -> BaseTool:
    """A LangChain tool running ``run_code`` on the sandbox (or one sandbox per call).

    >>> from sandboxio.testing import FakeBackend
    >>> tool = make_code_tool(FakeBackend().create)   # one fake sandbox per call
    >>> tool.name
    'run_python'
    """
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    class RunPython(BaseModel):
        code: str = Field(description=_common.CODE_PARAM)

    async def run_python(code: str) -> str:
        return await _common.run_tool(sandbox, lambda sb: sb.run_code(code, timeout=timeout))

    return StructuredTool.from_function(
        coroutine=run_python, name=name, description=description, args_schema=RunPython
    )


def make_command_tool(
    sandbox: SandboxSource,
    *,
    name: str = "run_command",
    description: str = _common.COMMAND_DESCRIPTION,
    timeout: float | None = None,
) -> BaseTool:
    """A LangChain tool running ``run`` (through ``sh -c``) on the sandbox."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    class RunCommand(BaseModel):
        command: str = Field(description=_common.COMMAND_PARAM)

    async def run_command(command: str) -> str:
        return await _common.run_tool(sandbox, lambda sb: sb.run(command, timeout=timeout))

    return StructuredTool.from_function(
        coroutine=run_command, name=name, description=description, args_schema=RunCommand
    )
