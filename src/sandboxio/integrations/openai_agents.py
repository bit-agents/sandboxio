"""OpenAI Agents SDK: ``make_code_tool()`` returns a native ``FunctionTool`` (spec/09).

Installed by ``sandboxio[openai-agents]``. The other direction of ADR-0013 — sandboxio
backends *as* a ``SandboxClient`` — is v0.2.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sandboxio.integrations import _common

if TYPE_CHECKING:
    from agents import FunctionTool

    from sandboxio.integrations._common import SandboxSource

__all__ = ["make_code_tool", "make_command_tool"]


def _schema(param: str, description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {param: {"type": "string", "description": description}},
        "required": [param],
        "additionalProperties": False,
    }


def make_code_tool(
    sandbox: SandboxSource,
    *,
    name: str = "run_python",
    description: str = _common.CODE_DESCRIPTION,
    timeout: float | None = None,
) -> FunctionTool:
    """A ``FunctionTool`` running ``run_code`` on the sandbox (or one sandbox per call).

    >>> from sandboxio.testing import FakeBackend
    >>> make_code_tool(FakeBackend().create).name
    'run_python'
    """
    from agents import FunctionTool

    async def on_invoke(_ctx: Any, arguments: str) -> str:
        code = str(json.loads(arguments)["code"])
        return await _common.run_tool(sandbox, lambda sb: sb.run_code(code, timeout=timeout))

    return FunctionTool(
        name=name,
        description=description,
        params_json_schema=_schema("code", _common.CODE_PARAM),
        on_invoke_tool=on_invoke,
    )


def make_command_tool(
    sandbox: SandboxSource,
    *,
    name: str = "run_command",
    description: str = _common.COMMAND_DESCRIPTION,
    timeout: float | None = None,
) -> FunctionTool:
    """A ``FunctionTool`` running ``run`` (through ``sh -c``) on the sandbox."""
    from agents import FunctionTool

    async def on_invoke(_ctx: Any, arguments: str) -> str:
        command = str(json.loads(arguments)["command"])
        return await _common.run_tool(sandbox, lambda sb: sb.run(command, timeout=timeout))

    return FunctionTool(
        name=name,
        description=description,
        params_json_schema=_schema("command", _common.COMMAND_PARAM),
        on_invoke_tool=on_invoke,
    )
