# How to use sandboxio from LangGraph, the OpenAI Agents SDK and MCP

Each integration returns the framework's **native** tool object wrapping `run_code` or
`run` on a sandbox you provide. The tool descriptions are written for the model: one obvious
way, the limits stated. No integration can weaken a default — deny egress, the timeout and
the caps come from the sandbox you hand it ([spec/09](../spec/09-integrations.md)).

Two ways to hand over a sandbox:

- a **ready sandbox** — reused across calls; you own its lifetime;
- a **factory** such as `backend.create` or `functools.partial(sandboxio.create, "e2b://")`
  — one fresh sandbox per tool call, torn down when the call ends.

## LangGraph / LangChain

```bash
uv add "sandboxio[docker,langgraph]"
```

```python
import sandboxio
from sandboxio.integrations.langgraph import make_code_tool

async with await sandboxio.create("docker://python:3.12-slim") as sb:
    run_python = make_code_tool(sb)                 # a langchain_core BaseTool
    print(await run_python.ainvoke({"code": "print(2 ** 10)"}))
    # graph = create_react_agent(model, tools=[run_python])
```

`make_command_tool(sb)` wraps `run` the same way. Both take `name=`, `description=` and
`timeout=` overrides.

## OpenAI Agents SDK

```bash
uv add "sandboxio[e2b,openai-agents]"
```

```python
import functools

import sandboxio
from sandboxio.integrations.openai_agents import make_code_tool

run_python = make_code_tool(functools.partial(sandboxio.create, "e2b://"))   # FunctionTool
# agent = Agent(name="analyst", instructions="...", tools=[run_python])
```

sandboxio backends *as* an OpenAI `SandboxClient` is planned for v0.2
([ADR-0013](../adr/0013-complement-openai-sandboxclient.md)).

## MCP server

```bash
uv add "sandboxio[mcp,docker]"
python -m sandboxio.mcp --backend docker://python:3.12-slim
```

One sandbox per server process, created on the first tool call and killed at shutdown.
Tools: `run_python(code)`, `run_command(cmd)`, `read_file(path)`, `write_file(path, content)`,
`list_files(path)`, `sandbox_info()`. One `run_python` tool instead of many narrow schemas is
the point — it is the MCP code-execution pattern.

Claude Desktop, Cursor and most clients take this shape:

```json
{
  "mcpServers": {
    "sandboxio": {
      "command": "uvx",
      "args": ["--from", "sandboxio[mcp,docker]", "python", "-m", "sandboxio.mcp",
               "--backend", "docker://python:3.12-slim"]
    }
  }
}
```

Options are fixed for the process: `--backend`, `--timeout`, `--egress deny|allow`,
`--transport stdio|streamable-http`, `--host` (localhost unless you say otherwise), `--port`.
There is deliberately **no** tool that changes them at runtime, and no tool ever executes on
the host: every call routes through the sandbox.

### As a container

```bash
docker build -f docker/mcp/Dockerfile -t sandboxio-mcp .
docker run -i --rm -e E2B_API_KEY sandboxio-mcp --backend e2b://code-interpreter-v1
```

The image is rootless, mounts no Docker socket, and defaults to the E2B backend because a
sandbox provider inside the container must be a cloud one. Catalog metadata lives in
[`docker/mcp/`](../../docker/mcp/README.md).
