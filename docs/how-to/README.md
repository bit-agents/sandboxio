# How-to guides

Task guides: each one solves a single problem end to end and assumes you have already run
the [quickstart](../quickstart.md).

| Guide | Covers |
|-------|--------|
| [Docker](docker.md) | Images with dependencies, offline wheelhouses, the reaper, why allowlists are refused |
| [E2B](e2b.md) | API key, egress allowlists, stateful contexts, rich outputs |
| [Offline testing](offline-testing.md) | The `sbx_fake` fixture, scripting results, resolving DSNs to the fake |
| [Audit and tracing](observability.md) | Sinks, OTel spans, redaction |
| [CI](ci.md) | A workflow that runs the fake on pull requests and Docker on main |
| [Integrations](integrations.md) | LangGraph, OpenAI Agents, the MCP server |
| [Operations](operations.md) | `sandboxio doctor`, `sandboxio reap`, `SBX_*` variables, exit codes |
