# sandboxio

**One secure Python API for running AI-agent code in any sandbox.** Swap Docker ↔ E2B with
one line; no network by default; test your agent tools offline with the built-in fake.

> **Pre-alpha — nothing is released.** The core, the contract suite, `FakeBackend`, the
> Docker and E2B adapters, the CLI and the integrations exist and pass their gates, but the
> public API is not stable and nothing is published to PyPI. What is stable enough to build
> against is the [specification](spec/README.md), which is normative and CI-enforced.

## Run code in a sandbox

```bash
uv add "sandboxio[docker]"   # or "sandboxio[e2b]" — the core has no backend built in
```

```python
import sandboxio

async with await sandboxio.create() as sb:
    res = await sb.run_code("print('hello')")
    print(res.stdout)
```

`create()` with no arguments is local Docker with egress denied, a mandatory timeout and
modest resource caps. The backend is one string away:

```python
import sandboxio

sb = await sandboxio.create("e2b://code-interpreter-v1")   # needs E2B_API_KEY
sb = await sandboxio.create("fake://")                     # tests; executes nothing
```

## Where to go next

| You want | Read |
|----------|------|
| Install to a sandboxed run in five minutes | [Quickstart](quickstart.md) |
| A task guide for your backend | [Docker](how-to/docker.md) · [E2B](how-to/e2b.md) · [Offline testing](how-to/offline-testing.md) |
| To run untrusted code safely | [The security model](explanation/security-model.md) · [Isolation tiers](explanation/isolation-tiers.md) |
| To work out why something fails | [Troubleshooting](how-to/troubleshooting.md) |
| A short answer to a common question | [FAQ](faq.md) |
| The meaning of an `SBX_E` code you just hit | [Error codes](errors/README.md) |
| The normative contract | [Specification](spec/README.md) |
| Why a decision is the way it is | [Decisions](adr/README.md) |
| Rules to paste into a coding assistant | [AGENTS.md snippet](reference/README.md) |

Coding assistants: [`llms.txt`](llms.txt) indexes these pages and
[`llms-full.txt`](llms-full.txt) concatenates them for one-shot context loading.

## About this documentation

Working documentation for **sandboxio**: a framework-agnostic Python sandbox abstraction library
for AI-agent code and tool execution. One async API over Docker, E2B and Modal backends;
ports/adapters; capability discovery; security-first defaults; native escape hatches.

> **Naming:** the project is `sandboxio`; `SBX` is its short code, used for error codes
> (`SBX_E1002`), env vars (`SBX_DEBUG`), the pytest fixture (`sbx_fake`) and the CLI alias.
> Canonical usage is `import sandboxio`, unaliased. See [ADR-0014](adr/0014-project-name.md).

## Layout

| Path | Contents | Normative? |
|------|----------|-----------|
| [`quickstart.md`](quickstart.md) | Tutorial: install to a sandboxed run in five minutes. | no |
| [`how-to/`](how-to/README.md) | Task guides: Docker, E2B, offline testing, audit and tracing, CI, operations, troubleshooting. | no |
| [`explanation/`](explanation/README.md) | Why: the security model, isolation tiers, deny by default, error codes. | no |
| [`faq.md`](faq.md) | Short answers to the questions a newcomer asks first. | no |
| [`errors/`](errors/README.md) | Reference: every error code, generated from the source. | yes |
| [`reference/`](reference/README.md) | Reference: the paste-ready `AGENTS.md` snippet for downstream projects. | no |
| [`llms.txt`](llms.txt) / `llms-full.txt` | Index and full text for coding assistants; the full text is generated. | no |
| [`adr/`](adr/README.md) | Architecture Decision Records. One file per decision, with context and consequences. | yes |
| [`spec/`](spec/README.md) | The normative specification: domain model, ports, public API, errors, security policy, observability, configuration, adapter contract. RFC-2119 language. | **yes** |
| [`build-order.md`](build-order.md) | Sequenced implementation plan with per-step exit criteria. | yes |
| [`open-questions.md`](open-questions.md) | Unresolved decisions. Each graduates into an ADR when settled. | no |
| [`hazards.md`](hazards.md) | What can kill the project, or its users, plus tripwires and responses. | no |
| [`runbook.md`](runbook.md) | How to operate the project: dev setup, CI gates, release, provider-churn response, security advisories. | yes |

## Reading order

**User:** [`quickstart.md`](quickstart.md) → [`examples/`](https://github.com/bit-agents/sandboxio/tree/main/examples) →
the [`how-to/`](how-to/README.md) page for your backend →
[`explanation/security-model.md`](explanation/security-model.md) before running untrusted code.

**New contributor:** `README.md` → [`spec/`](spec/README.md) index → [`build-order.md`](build-order.md) → [`runbook.md`](runbook.md).

**Coding agent:** [`spec/`](spec/README.md) is the contract. Where the spec is silent or marked
`OPEN`, stop and ask — do not invent. [`adr/`](adr/README.md) explains *why*, which matters when a
requirement looks arbitrary.

**Deciding something:** check [`open-questions.md`](open-questions.md) first; if it is not
there and it will outlive the PR, it needs an ADR.

## Precedence

When two documents disagree: [`spec/`](spec/README.md) wins over [`adr/`](adr/README.md).

Both descend from an earlier planning set, which the ADRs' Context sections call *the
input set* or *the input design*. It is not part of this repository and is superseded, not
authoritative: it predates every decision recorded here, and several of its snippets were
wrong.

### Corrections to the original design

Listed because the corrections are load-bearing — each is a requirement that looks
arbitrary until you know what it is fixing.

| Topic | Error | Resolved by |
|-------|-------|-------------|
| Routing config | The routing config was **not valid YAML** — `-> isolated` trailing a flow mapping is a parser error. Verified with a parser, not by eye. | [spec/07](spec/07-configuration.md#routing-file) |
| Fake assertions | `assert ... is NetworkPolicy(egress="deny")` — `is` against a freshly constructed dataclass is always false. Use `==`. | [spec/01](spec/01-domain-model.md#value-objects) |
| Streaming example | The example was `pip install -r requirements.txt`, which cannot run under the default deny-egress policy. | [Q10](open-questions.md#q10--deny-by-default-vs-the-demo) |
| Error taxonomy | `TimeoutError` shadowed the builtin, which on our floor is what `asyncio` raises. | [ADR-0017](adr/0017-timeout-error-naming.md) |
| Streaming signature | `stream() -> AsyncIterator[bytes]` with `**kw` — loses stderr and exit code, and leaks a kwargs black hole. | [ADR-0019](adr/0019-streaming-process-handle.md) |
| Sync `create()` | Auto-detected `create()` returning a different type in sync context. | [ADR-0002](adr/0002-async-first-anyio.md) |
| Isolation tiers | Daytona listed at `CONTAINER` beside the word "verify" — an unearned isolation claim. | [ADR-0018](adr/0018-isolation-tier-ordering.md) |
| Project name | The name `sbx` is unavailable on PyPI. | [ADR-0014](adr/0014-project-name.md) |

Every configuration sample in [`spec/`](spec/README.md) is parse-tested in CI, precisely because the
first one was not.

## Published site

This directory is published at **https://docs.sandboxio.dev** by `mkdocs.yml` and
`.github/workflows/docs.yml` ([ADR-0029](adr/0029-docs-site-mkdocs.md)). This page is the
site's landing page; `docs/` is its root, so a relative link may not leave the directory —
link the repository by URL instead, which `scripts/check_doc_links.py` enforces. Error-code
URLs are API ([ADR-0010](adr/0010-stable-error-codes.md)): a page that moves leaves a
redirect behind.

```bash
make site      # or: uv sync --group docs && uv run mkdocs serve
```

## Licensing

Code is **MIT** ([`LICENSE`](https://github.com/bit-agents/sandboxio/blob/main/LICENSE)). The prose in this directory is **CC BY 4.0**
([`LICENSE-DOCS`](https://github.com/bit-agents/sandboxio/blob/main/LICENSE-DOCS)) — quote and adapt the spec, with credit. Code samples
inside these documents are MIT, not CC BY: anything in a fenced block is code, everything
else is prose ([ADR-0026](adr/0026-docs-license-cc-by.md)).

## Core principles

Each is expanded in an ADR.

1. **Thin core, no LCD.** Never reduce the API to what every backend supports. One-backend
   features go behind `Capability` flags and `.native`. ([ADR-0003](adr/0003-no-lowest-common-denominator.md))
2. **Security is the headline, not an add-on.** No-network default, mandatory timeouts,
   isolation-tier reporting, audit hooks — all in v0.1. ([ADR-0005](adr/0005-secure-by-default.md))
3. **Tiny, auditable core.** Near-zero base dependencies; backend SDKs behind extras, lazily
   imported. ([ADR-0004](adr/0004-thin-core-lazy-adapters.md))
4. **Async-first, sync derived.** ([ADR-0002](adr/0002-async-first-anyio.md))
5. **AI agents are first-class consumers** — at runtime and at dev time.
6. **Absorb provider churn publicly.** Tracking and absorbing upstream breaking changes is
   the moat. Document every absorbed break. ([runbook.md](runbook.md#provider-churn-response))
