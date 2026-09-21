# sandboxio

**One secure Python API for running AI-agent code in any sandbox.** Swap Docker ↔ E2B with
one line; no network by default; test your agent tools offline with the built-in fake.

[![CI](https://github.com/bit-agents/sandboxio/actions/workflows/ci.yml/badge.svg)](https://github.com/bit-agents/sandboxio/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](docs/adr/0015-python-version-floor.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/bit-agents/sandboxio/badge)](https://scorecard.dev/viewer/?uri=github.com/bit-agents/sandboxio)

<!-- TODO(placeholder): the PyPI version badge needs a published release. -->

> [!WARNING]
> **Pre-alpha. The core, the contract suite, `FakeBackend`, the Docker and E2B adapters, the
> CLI and the integrations exist and pass their gates; nothing is released.**
>
> The public API is not stable, nothing is published to PyPI, and no version is suitable for
> any use. What *is* stable enough to build against is [`docs/spec/`](docs/spec/), which is
> normative and CI-enforced.
>
> Watch the repo if you want the v0.1 announcement. Do not depend on this yet.

## Why this exists

Every sandbox provider ships its own SDK with its own shape, so agent code that runs on one
is rewritten for the next. The framework layers each solve it captively — LangChain's
backends only help inside LangChain. sandboxio is the framework-agnostic substrate
underneath, with the security posture that agent execution actually needs.

- **Security is the headline, not an add-on.** Deny-by-default egress, mandatory timeouts,
  isolation-tier reporting and audit hooks are all in v0.1 — not a later hardening pass.
- **No lowest common denominator.** One-backend features stay reachable through `Capability`
  flags and `.native` instead of being sanded off.
- **Tiny, auditable core.** `anyio` and `typing-extensions` only; every backend SDK sits
  behind an extra and is imported lazily.
- **Offline-testable.** `FakeBackend` and a pytest fixture, so your agent's tools have tests
  that need no Docker, no network and no provider account.
- **Provider churn is absorbed publicly.** Upstream breaking changes are tracked, absorbed
  and written down.

## Quickstart

Every Python block below is executed by CI exactly as written
([`tests/test_readme_examples.py`](tests/test_readme_examples.py)); a copied example that
does not run is a P0 bug. The Docker-backed lines run against the built-in fake in CI, so
they are the same code you would run — only the backend differs.

The commands below are what v0.1 will install. Today the name on PyPI holds a `0.0.0`
placeholder that carries no code, so `uv add sandboxio` does not yet get you a library.
`uvx sandboxio demo` is the documented entry point — never the `sbx` alias, which resolves
to an unrelated PyPI package ([ADR-0014](docs/adr/0014-project-name.md)).

```bash
uv add "sandboxio[docker]"     # from v0.1
uvx sandboxio demo             # create, run, stream, prove egress is denied, tear down
sandboxio doctor               # what is installed, reachable and missing — no secrets printed
```

Run code in a sandbox. `create()` with no arguments is local Docker; nothing leaves the
sandbox unless you say so.

```python
import sandboxio

async with await sandboxio.create() as sb:              # zero-config, local Docker
    res = await sb.run_code("print('hello')")
    print(res.stdout)                                    # hello
    res = await sb.run(["python", "--version"], timeout=30)
    print(res.exit_code, res.stdout.strip())
```

Swap the backend with one line. The code that uses the sandbox does not change.

```python
import sandboxio

async def summarise(sb: sandboxio.protocols.AsyncSandbox) -> str:
    await sb.files.write("/work/input.txt", "3 4\n")
    res = await sb.run_code("a, b = open('/work/input.txt').read().split(); print(int(a) * int(b))")
    res.raise_for_status()                               # ExecutionError on a non-zero exit
    return res.stdout.strip()

async with await sandboxio.create("docker://python:3.12-slim") as sb:
    print(await summarise(sb))
async with await sandboxio.create("e2b://code-interpreter-v1") as sb:   # needs E2B_API_KEY
    print(await summarise(sb))
```

Stream output while a long command runs, and rely on the timeout: a sandbox timeout is
`sandboxio.SandboxTimeout`, never the builtin `TimeoutError`.

```python
import sandboxio

async with await sandboxio.create() as sb:
    async with sb.stream(["sh", "-c", "echo start; sleep 1; echo done"], timeout=30) as proc:
        async for chunk in proc:
            print(chunk.stream, chunk.data.decode(), end="")
        res = await proc.wait()
    try:
        await sb.run(["sleep", "999"], timeout=1)
    except sandboxio.SandboxTimeout as exc:
        print(exc.code)                                  # SBX_E1302 — stable, documented
```

Sync code gets the same surface through `create_sync()`. One sandbox is one portal thread;
use the async API for heavy concurrency.

```python
import sandboxio

with sandboxio.create_sync("docker://python:3.12-slim", timeout=60) as sb:
    print(sb.run_code("print(6 * 7)").stdout)
```

Test your agent's tools offline. `sbx_fake` is a pytest fixture installed with the package;
it executes nothing, records everything, and passes the same contract suite as the real
backends.

```python
import pytest
from sandboxio import ExecResult


@pytest.mark.anyio
async def test_my_tool_reads_the_pandas_version(sbx_fake):
    sbx_fake.on_run_code(match="import pandas", returns=ExecResult(0, "2.2.1\n", ""))
    res = await sbx_fake.sandbox.run_code("import pandas; print(pandas.__version__)")
    assert "2.2.1" in res.stdout
    assert sbx_fake.calls[0].network.egress == "deny"     # the default, recorded
```

Full surface, including capability discovery, `require_isolation`, audit sinks and spans:
[`docs/quickstart.md`](docs/quickstart.md) and the normative
[`docs/spec/03-public-api.md`](docs/spec/03-public-api.md).

## Backends

| Backend | Status | Isolation tier |
|---------|--------|----------------|
| Docker | adapter built, unreleased | `CONTAINER` — [containers share the host kernel](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/) |
| E2B | adapter built, unreleased | `MICROVM` — [Firecracker microVM, its own kernel](https://e2b.dev/security) |
| `FakeBackend` | built, unreleased | n/a — in-process, for tests |
| Modal | planned for v0.1.1 | `GVISOR` — [containerised and virtualised using gVisor](https://modal.com/docs/guide/security) |

Every tier above is the mechanism the provider documents for itself, read on **2026-09-20**.
None of those three pages carries its own revision date, so that is the date it was read, not
a date the provider published; re-verification is a [quarterly item](docs/runbook.md).
What the tiers mean — and why `GVISOR` is defence in depth rather than VM equivalence — is in
[`docs/explanation/isolation-tiers.md`](docs/explanation/isolation-tiers.md).

Third-party adapters are first-class: the adapter contract is
[specified](docs/spec/08-adapter-contract.md) and enforced by a shared contract suite.

## Integrations

- **LangGraph / LangChain** — `sandboxio.integrations.langgraph.make_code_tool()` returns a
  native `BaseTool` (`sandboxio[langgraph]`).
- **OpenAI Agents SDK** — `sandboxio.integrations.openai_agents.make_code_tool()` returns a
  native `FunctionTool` (`sandboxio[openai-agents]`).
- **MCP** — `python -m sandboxio.mcp --backend docker://python:3.12-slim` serves
  `run_python`, `run_command`, file tools and `sandbox_info` (`sandboxio[mcp]`), also as a
  container image.

## Documentation

**[docs.sandboxio.dev](https://docs.sandboxio.dev)** — the Markdown under
[`docs/`](docs/) is its source and stays the source, so nothing below moves. Read it here
or there:

- [`examples/`](examples/) — complete programs, one concept each: hello world, swapping
  backends, streaming, proving egress is denied, agent tools. Each one is executed by CI.
- [`docs/quickstart.md`](docs/quickstart.md) — five minutes from install to a sandboxed run.
- [`docs/how-to/`](docs/how-to/) — Docker images and offline wheelhouses, E2B keys and
  allowlists, offline testing with the fake, audit sinks and tracing, CI, and
  [troubleshooting by symptom](docs/how-to/troubleshooting.md).
- [`docs/explanation/`](docs/explanation/) — [the security model](docs/explanation/security-model.md),
  isolation tiers, deny-by-default, why errors have codes, the
  [version policy](docs/explanation/version-policy.md) and
  [why sandboxio and not something else](docs/explanation/comparisons.md).
- [`docs/faq.md`](docs/faq.md) — the questions a newcomer asks first, answered short.
- [`docs/errors/`](docs/errors/README.md) — every error code, generated from the source.
- [`docs/spec/`](docs/spec/) — the normative specification. This is the contract.
- [`docs/adr/`](docs/adr/) — why each decision was made, including the ones that look arbitrary.
- [`docs/llms.txt`](docs/llms.txt) — for coding assistants; `llms-full.txt` beside it.

## Security

Isolation tiers are reported, not assumed: `CONTAINER` is not a security boundary against
hostile code, and sandboxio says so rather than implying otherwise.

Report vulnerabilities privately — see [`SECURITY.md`](SECURITY.md). A report that a
*declared control did not apply* is the highest-severity class this project has.

The project's own supply-chain posture is scored weekly by
[OpenSSF Scorecard](https://scorecard.dev/viewer/?uri=github.com/bit-agents/sandboxio) and
published — the badge above links to the run that produced it.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md). Contributions need a DCO `Signed-off-by` line;
there is no CLA.

## License

Code is [MIT](LICENSE). Prose in `docs/` is [CC BY 4.0](LICENSE-DOCS); code samples inside
those documents are MIT ([ADR-0026](docs/adr/0026-docs-license-cc-by.md)).
