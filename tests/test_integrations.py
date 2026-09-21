"""Framework adapters return native tool objects and change no security default (spec/09)."""

from __future__ import annotations

import json
from importlib.util import find_spec

import pytest

from _helpers import REPO_ROOT
from sandboxio.errors import ExecutionTimeout
from sandboxio.integrations import _common
from sandboxio.models import ExecResult, RichOutput
from sandboxio.testing.fake import FakeBackend

pytestmark = pytest.mark.anyio

# Per test, never module-wide: a module-level skip took the two framework-free tests with it,
# so a run with one framework missing reported success having checked nothing.
needs_langchain = pytest.mark.skipif(
    find_spec("langchain_core") is None, reason="langchain-core not installed"
)
needs_agents = pytest.mark.skipif(
    find_spec("agents") is None, reason="openai-agents not installed"
)


def test_adapters_stay_under_100_lines() -> None:
    for name in ("langgraph.py", "openai_agents.py"):
        path = REPO_ROOT / "src" / "sandboxio" / "integrations" / name
        code = [line for line in path.read_text().splitlines() if line.strip()]
        assert len(code) <= 100, (
            f"{name} has {len(code)} non-blank lines; logic belongs in core"
        )


def test_render_is_written_for_the_model() -> None:
    assert _common.render(ExecResult(0, "hi\n", "")) == "hi"
    assert _common.render(ExecResult(0, "", "")) == "(no output)"
    out = _common.render(ExecResult(2, "", "boom\n", results=(RichOutput("text/plain", "7"),)))
    assert out == "[stderr]\nboom\n7\n[exit code 2]"
    assert "no network" in _common.CODE_DESCRIPTION


@needs_langchain
async def test_langgraph_tool_is_a_basetool_running_run_code() -> None:
    from langchain_core.tools import BaseTool

    from sandboxio.integrations.langgraph import make_code_tool, make_command_tool

    fake = FakeBackend()
    async with await fake.create() as sb:
        tool = make_code_tool(sb)
        assert isinstance(tool, BaseTool)
        assert tool.name == "run_python"
        assert tool.args_schema is not None
        assert await tool.ainvoke({"code": "print('hi from langgraph')"}) == "hi from langgraph"
        command = make_command_tool(sb, timeout=5)
        assert await command.ainvoke({"command": "echo shell"}) == "shell"
        assert fake.calls[-1].timeout == 5


@needs_langchain
async def test_langgraph_factory_form_creates_one_sandbox_per_call_and_tears_it_down() -> None:
    from sandboxio.integrations.langgraph import make_code_tool

    fake = FakeBackend()
    tool = make_code_tool(fake.create)
    assert await tool.ainvoke({"code": "print(1)"}) == "1"
    assert fake.live_sandboxes() == 0
    assert fake.calls[0].op == "create" and fake.calls[0].network is not None
    assert fake.calls[0].network.egress == "deny", "an integration never weakens a default"


@needs_agents
async def test_openai_agents_tool_is_a_functiontool_running_run_code() -> None:
    from agents import FunctionTool
    from agents.tool_context import ToolContext

    from sandboxio.integrations.openai_agents import make_code_tool, make_command_tool

    fake = FakeBackend()
    tool = make_code_tool(fake.create)
    assert isinstance(tool, FunctionTool)
    assert tool.name == "run_python"
    assert tool.params_json_schema["required"] == ["code"]
    args = json.dumps({"code": "print('hi from agents')"})
    ctx: ToolContext[None] = ToolContext(
        context=None, tool_name=tool.name, tool_call_id="call-1", tool_arguments=args
    )
    out = await tool.on_invoke_tool(ctx, args)
    assert out == "hi from agents"
    assert fake.live_sandboxes() == 0
    command = make_command_tool(fake.create)
    assert await command.on_invoke_tool(ctx, json.dumps({"command": "echo shell"})) == "shell"


@needs_langchain
async def test_tool_output_reports_a_denied_egress_instead_of_hiding_it() -> None:
    from sandboxio.integrations.langgraph import make_code_tool

    fake = FakeBackend()
    tool = make_code_tool(fake.create)
    out = await tool.ainvoke(
        {"code": "import urllib.request\nurllib.request.urlopen('http://x')"}
    )
    assert "egress denied" in out and "[exit code 1]" in out


def test_integrations_are_not_imported_by_import_sandboxio() -> None:
    from _helpers import run_python

    proc = run_python(
        "-c",
        "import sys, sandboxio; print(any(m.startswith('sandboxio.integrations') "
        "or m in ('langchain_core', 'agents', 'mcp') for m in sys.modules))",
    )
    assert proc.stdout.strip() == "False"


def test_render_error_gives_the_model_the_code_the_fix_and_the_docs() -> None:
    exc = ExecutionTimeout("run exceeded 30s in sandbox sb-1")
    lines = _common.render_error(exc).split("\n")
    assert lines[0] == "[SBX_E1302] run exceeded 30s in sandbox sb-1"
    assert lines[1].startswith("Fix: ") and lines[2].startswith("Docs: ")


@pytest.mark.parametrize(
    "module",
    [
        pytest.param("langgraph", marks=needs_langchain),
        pytest.param("openai_agents", marks=needs_agents),
    ],
)
async def test_a_sandbox_error_reaches_the_model_as_text_not_as_a_crash(module: str) -> None:
    """spec/09: all three integrations answer a SandboxError the same way."""
    import importlib

    fake = FakeBackend()
    fake.on_run_code("slow", returns=ExecutionTimeout("run_code exceeded 30s in sandbox sb-1"))
    make = importlib.import_module(f"sandboxio.integrations.{module}").make_code_tool
    async with await fake.create() as sb:
        tool = make(sb)
        out = await (
            tool.ainvoke({"code": "slow"})
            if module == "langgraph"
            else tool.on_invoke_tool(None, json.dumps({"code": "slow"}))
        )
    assert out.startswith("[SBX_E1302] ")
    assert "Fix: " in out and "Docs: " in out
