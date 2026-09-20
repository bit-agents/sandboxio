# Examples

Complete programs, one concept each. Every one of them is executed by CI
([`tests/test_examples.py`](../tests/test_examples.py)) with the Docker and E2B backends
swapped for the in-process fake, so an example that stopped working fails our build rather
than your first attempt.

| Example | Shows | Needs |
|---------|-------|-------|
| [`01_hello_sandbox.py`](01_hello_sandbox.py) | create → `run_code` → `run` → teardown | Docker |
| [`02_swap_backends.py`](02_swap_backends.py) | one function, two providers, one line changed | Docker, `E2B_API_KEY` |
| [`03_stream_and_timeout.py`](03_stream_and_timeout.py) | `stream()`, and `SandboxTimeout` (`SBX_E1302`) stopping a runaway | Docker |
| [`04_egress_denied.py`](04_egress_denied.py) | deny-by-default egress, proven, then the explicit opt-out | Docker |
| [`05_langgraph_agent.py`](05_langgraph_agent.py) | a LangGraph agent whose tool is a sandbox | Docker, `langgraph`, `ANTHROPIC_API_KEY` |
| [`06_openai_agents.py`](06_openai_agents.py) | the same through the OpenAI Agents SDK | Docker, `OPENAI_API_KEY` |
| [`test_my_tool.py`](test_my_tool.py) | testing your agent's tools with `sbx_fake` | nothing |

## Running them

From a clone, with the repository's own environment:

```bash
uv run --extra docker examples/01_hello_sandbox.py
uv run pytest examples/test_my_tool.py
```

The two agent examples run their sandboxio half with no API key and print why they stopped,
so you can see the tool work before you spend a token:

```bash
uv sync --all-extras
uv run examples/05_langgraph_agent.py
```

<!-- TODO(placeholder): once the package is published, each script gets a PEP 723
     `# /// script` header so `uv run https://.../01_hello_sandbox.py` works with no clone
     and no install. It cannot be written until there is a name on PyPI to depend on. -->

Every example assumes a running Docker daemon and the `python:3.12-slim` image. If something
is off, `sandboxio doctor` says what is installed, reachable and missing — without printing
a single secret.

## What they deliberately do not show

- **Per-host allowlists on Docker.** `NetworkPolicy(allow=...)` is refused there with
  `SBX_E1101`, because Docker cannot enforce it and silently ignoring it would be a lie
  about a security control. E2B can; see
  [`docs/spec/05-security-policy.md`](../docs/spec/05-security-policy.md).
- **Tasks rather than concepts.** Image preparation, offline wheelhouses, E2B keys, audit
  sinks, tracing and CI each have a page under [`docs/how-to/`](../docs/how-to/).
