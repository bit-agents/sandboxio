# Quickstart

Five minutes from a clean machine to code running in a sandbox that cannot reach the
network. You need Python 3.11+ and, for the Docker backend, a running Docker daemon.
Everything here also runs against the in-process fake, which needs neither.

## 1. Prove the install works

```bash
uvx sandboxio demo
```

The demo creates a sandbox, runs code, streams output, tries to reach the network from
inside — and reports that the attempt was denied — then tears the sandbox down. The first
run pulls the `python:3.12-slim` image (about 130 MB, on the host, outside the sandbox's
network policy). With the image pulled, the demo's own five steps take about two and a
half seconds; `uvx` resolving and installing the package on a cold cache puts the whole
command nearer six. If Docker is not installed, the demo prints the exact install command
and exits `1`.

When something is off, ask the doctor. It prints credential variable *names*, never values,
and makes no provider API call:

```bash
sandboxio doctor
sandboxio doctor --json     # paste-friendly, for bug reports
```

## 2. Add it to a project

```bash
uv add "sandboxio[docker]"   # or "sandboxio[e2b]" — the core has no backend built in
```

The base package depends on `anyio` and `typing-extensions` only. Every backend SDK lives
behind an extra and is imported the first time that backend is used.

## 3. Run code

```python
import sandboxio

async with await sandboxio.create() as sb:
    res = await sb.run_code("print('hello')")
    print(res.stdout)
```

`create()` with no arguments is local Docker with the defaults every backend applies:

| Default | Value | Change it with |
|---------|-------|----------------|
| Network | egress denied | `network=NetworkPolicy(egress="allow")` or an allowlist on E2B |
| Timeout | 300 s for the sandbox and every call | `timeout=` on `create()`, `run()`, `run_code()`, `stream()` |
| Resources | modest CPU and memory caps | `resources=Resources(memory_mb=2048)` |
| Labels | none | `metadata={"tenant_id": ..., "session_id": ...}` |

`timeout=None` on a call means "inherit the sandbox timeout", never "unbounded";
`timeout=None` on `create()` is refused.

## 4. Swap the backend

```python
import sandboxio

sb = await sandboxio.create("docker://python:3.12-slim")
sb = await sandboxio.create("e2b://code-interpreter-v1")      # needs E2B_API_KEY
sb = await sandboxio.create("fake://")                        # tests; executes nothing
```

The DSN is `<backend>://[<template>][?timeout=<seconds>]` and nothing else — no secrets,
no policy. Production code SHOULD prefer typed configuration
([spec/07](spec/07-configuration.md#typed-configuration)).

Make a deployment fail closed rather than silently downgrade:

```python
import sandboxio
from sandboxio import IsolationTier

sb = await sandboxio.create("e2b://", require_isolation=IsolationTier.MICROVM)
```

If the resolved backend is weaker, `create()` raises `ConfigurationError` before anything is
provisioned. `CONTAINER` (Docker) is not a boundary against hostile code; read
[isolation tiers](explanation/isolation-tiers.md) before choosing.

## 5. Use the whole surface

```python
import sandboxio
from sandboxio import Capability

async with await sandboxio.create() as sb:
    await sb.files.write("/work/data.csv", "a,b\n1,2\n")
    await sb.files.upload("local.txt", "/work/local.txt")
    print(await sb.files.ls("/work"))

    async with sb.stream(["pytest", "-q"], timeout=300) as proc:   # `async with` is required
        async for chunk in proc:
            print(chunk.stream, chunk.data.decode(), end="")
        res = await proc.wait()

    if Capability.STATEFUL_CODE in sb.capabilities:              # E2B and the fake, not Docker
        await sb.run_code("x = 41", context_id="session-1")
        print((await sb.run_code("print(x + 1)", context_id="session-1")).stdout)

    sb.native   # the provider's own object — outside the semver contract
```

Capabilities are discovered per sandbox, never inferred from the backend name. Calling
something the backend does not declare raises `CapabilityNotSupported` naming the backends
that do.

## 6. Handle errors by code

```python
import sandboxio

try:
    async with await sandboxio.create("e2b://") as sb:
        await sb.run("sleep 999", timeout=5)
except sandboxio.SandboxTimeout as exc:      # not the builtin TimeoutError
    print(exc.code, exc.hint)                 # SBX_E1302, and the fix
except sandboxio.SandboxError as exc:
    print(exc)                                # [code] message / Fix: ... / Docs: ...
```

Every exception carries a stable code, a hint holding the exact fix, and a docs URL
([error reference](errors/README.md), [why codes](explanation/error-codes.md)).

## 7. Test without a sandbox

```python
import pytest
from sandboxio import ExecResult


@pytest.mark.anyio
async def test_tool(sbx_fake):
    sbx_fake.on_run_code(match="import pandas", returns=ExecResult(0, "2.2.1\n", ""))
    res = await sbx_fake.sandbox.run_code("import pandas; print(pandas.__version__)")
    assert "2.2.1" in res.stdout
```

The fixture is installed with the package. More in
[offline testing](how-to/offline-testing.md).

## Where next

- [`examples/`](https://github.com/bit-agents/sandboxio/blob/main/examples/README.md): the same ground as complete programs you can run —
  one concept each, every one executed by CI.
- [Docker how-to](how-to/docker.md): images with dependencies, offline wheelhouses, the reaper.
- [E2B how-to](how-to/e2b.md): API key, allowlists, stateful contexts, rich outputs.
- [Audit and tracing](how-to/observability.md): sinks, OTel spans, redaction.
- [CI](how-to/ci.md): a copy-paste GitHub Actions workflow.
- [Integrations](how-to/integrations.md): LangGraph, OpenAI Agents SDK, MCP.
- [Operations](how-to/operations.md): `doctor`, `reap`, the `SBX_*` switches.
- Coding assistant in your repo? Paste [the AGENTS.md snippet](reference/agents-snippet.md).
