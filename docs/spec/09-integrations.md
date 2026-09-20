# 09 — Integrations

Integrations are the distribution strategy: being the recommended sandbox layer inside a
popular framework is worth more than standalone stars. All integration modules are lazily
imported and dependency-isolated behind extras.

## Framework adapters (`sandboxio.integrations.*`)

Each adapter returns the framework's **native tool object** wrapping `run_code`/`run` on a
provided sandbox or per-call factory.

```python
from sandboxio.integrations.langgraph import make_code_tool        # -> BaseTool
from sandboxio.integrations.crewai import SbxCodeTool
from sandboxio.integrations.pydantic_ai import sandbox_tool

# OpenAI Agents SDK — both directions (ADR-0013)
from sandboxio.integrations.openai_agents import make_code_tool    # sandboxio as a plain tool
from sandboxio.integrations.openai_agents import SbxSandboxClient  # sandboxio backends AS a SandboxClient
```

Rules:

- Under 100 lines each. All logic stays in core; an adapter that needs logic is telling you
  core is missing something.
- Tool descriptions are written **for LLM consumption**: clear, constrained, one obvious way.
- Framework dependencies get loose lower bounds (`langgraph>=0.2`), are tested in the weekly
  CI matrix, and the supported version range is documented.
- An integration MUST NOT weaken a security default. It inherits deny-egress, timeouts and
  caps like any other caller.

Decisions taken for v0.1: the adapters live in core under `sandboxio.integrations.*` with
their framework behind an extra — `sandboxio[langgraph]` (`langchain-core>=0.3`, the tool
type is `langchain_core.tools.BaseTool`) and `sandboxio[openai-agents]` (`openai-agents>=0.1`).
Each ships `make_code_tool()` and `make_command_tool()`, taking either a ready sandbox or a
per-call factory. A `SandboxError` is rendered into the tool's return string — code, fix and
docs URL — rather than raised into the framework, so the model can read what went wrong and
try something else, as it can on the MCP server. `SbxSandboxClient` is v0.2.

| Priority | Integration | Rationale |
|----------|-------------|-----------|
| P0 (v0.1) | LangGraph tool, OpenAI Agents tool, MCP server | largest ecosystems + distribution |
| P1 (v0.2) | Pydantic AI, CrewAI, OpenAI `SandboxClient` adapter | "works with all four" |
| P2 | LlamaIndex, Vercel AI SDK (via MCP), K8s agent-sandbox adapter at ≥beta | follow demand |

## MCP server (`python -m sandboxio.mcp`)

Both an integration and the first server surface
([ADR-0009](../adr/0009-library-first-server-later.md)).

```bash
python -m sandboxio.mcp --backend docker://python:3.12-slim
docker run ghcr.io/<org>/sandboxio-mcp --backend e2b://code-interpreter
```

Tools exposed — deliberately few, code-execution-pattern first:

| Tool | Returns |
|------|---------|
| `run_python(code)` | `{stdout, stderr, exit_code, results}` |
| `run_command(cmd)` | same shape |
| `read_file(path)` / `write_file(path, content)` / `list_files(path)` | file ops |
| `sandbox_info()` | backend, isolation tier, capabilities, policy in effect |

One `run_python` tool instead of many narrow schemas is the point: it is the MCP
code-execution pattern, and it is where the large token reduction comes from.

### Security requirements

Non-negotiable, informed by the LiteLLM CVE chain where the worst RCE lived in an MCP
endpoint:

- The server inherits sandboxio defaults: deny egress, mandatory timeouts, resource caps.
- **No tool ever executes on the host.** Everything routes through the sandbox.
- Configuration — backend DSN, policy — is fixed at process start. There MUST be **no
  runtime config-mutation tool**, and no unauthenticated management or test endpoint.
- The container runs rootless and MUST NOT have a Docker socket reachable from sandboxed
  code.
- Bind to localhost unless explicitly configured otherwise.

Behind `sandboxio[mcp]` (`mcp>=1.2`; built on the SDK's `MCPServer`). One sandbox per
server process, created on the first tool call and killed at shutdown. A `SandboxError`
raised by a tool reaches the model as a tool error carrying the code, the fix and the docs
URL — the SDK hides any other exception behind a generic line. Options: `--backend`,
`--timeout`, `--egress deny|allow`, `--transport stdio|streamable-http`, `--host`, `--port`.

Distribution: publish to the Docker MCP Catalog. Containerized distribution is the launch
centerpiece — it is the multi-language, multi-client story at a fraction of a full server's
attack surface.

Later (v0.2): a `search_docs` tool on the same server, for AI-assistant docs access.
