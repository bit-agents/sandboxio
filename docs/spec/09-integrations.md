# 09 — Integrations

Integrations are the distribution strategy: being the recommended sandbox layer inside a
popular framework is worth more than standalone stars. All integration modules are lazily
imported and dependency-isolated behind extras.

## Framework adapters (`sbx.integrations.*`)

Each adapter returns the framework's **native tool object** wrapping `run_code`/`run` on a
provided sandbox or per-call factory.

```python
from sbx.integrations.langgraph import make_code_tool        # -> BaseTool
from sbx.integrations.crewai import SbxCodeTool
from sbx.integrations.pydantic_ai import sandbox_tool

# OpenAI Agents SDK — both directions (ADR-0013)
from sbx.integrations.openai_agents import make_code_tool    # sbx as a plain tool
from sbx.integrations.openai_agents import SbxSandboxClient  # sbx backends AS a SandboxClient
```

Rules:

- Under 100 lines each. All logic stays in core; an adapter that needs logic is telling you
  core is missing something.
- Tool descriptions are written **for LLM consumption**: clear, constrained, one obvious way.
- Framework dependencies get loose lower bounds (`langgraph>=0.2`), are tested in the weekly
  CI matrix, and the supported version range is documented.
- An integration MUST NOT weaken a security default. It inherits deny-egress, timeouts and
  caps like any other caller.

| Priority | Integration | Rationale |
|----------|-------------|-----------|
| P0 (v0.1) | LangGraph tool, OpenAI Agents tool, MCP server | largest ecosystems + distribution |
| P1 (v0.2) | Pydantic AI, CrewAI, OpenAI `SandboxClient` adapter | "works with all four" |
| P2 | LlamaIndex, Vercel AI SDK (via MCP), K8s agent-sandbox adapter at ≥beta | follow demand |

## MCP server (`python -m sbx.mcp`)

Both an integration and the first server surface
([ADR-0009](../adr/0009-library-first-server-later.md)).

```bash
python -m sbx.mcp --backend docker://python:3.12-slim
docker run ghcr.io/<org>/sbx-mcp --backend e2b://code-interpreter
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

- The server inherits sbx defaults: deny egress, mandatory timeouts, resource caps.
- **No tool ever executes on the host.** Everything routes through the sandbox.
- Configuration — backend DSN, policy — is fixed at process start. There MUST be **no
  runtime config-mutation tool**, and no unauthenticated management or test endpoint.
- The container runs rootless and MUST NOT have a Docker socket reachable from sandboxed
  code.
- Bind to localhost unless explicitly configured otherwise.

Distribution: publish to the Docker MCP Catalog. Containerized distribution is the launch
centerpiece — it is the multi-language, multi-client story at a fraction of a full server's
attack surface.

Later (v0.2): a `search_docs` tool on the same server, for AI-assistant docs access.
