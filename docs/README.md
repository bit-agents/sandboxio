# sandboxio — Project Documentation

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
| [`how-to/`](how-to/) | Task guides: Docker, E2B, offline testing, audit and tracing, CI, operations. | no |
| [`explanation/`](explanation/) | Why: isolation tiers, deny by default, error codes. | no |
| [`errors/`](errors/README.md) | Reference: every error code, generated from the source. | yes |
| [`reference/`](reference/) | Reference: the paste-ready `AGENTS.md` snippet for downstream projects. | no |
| [`llms.txt`](llms.txt) / `llms-full.txt` | Index and full text for coding assistants; the full text is generated. | no |
| [`adr/`](adr/) | Architecture Decision Records. One file per decision, with context and consequences. | yes |
| [`spec/`](spec/) | The normative specification: domain model, ports, public API, errors, security policy, observability, configuration, adapter contract. RFC-2119 language. | **yes** |
| [`build-order.md`](build-order.md) | Sequenced implementation plan with per-step exit criteria. | yes |
| [`open-questions.md`](open-questions.md) | Unresolved decisions. Each graduates into an ADR when settled. | no |
| [`hazards.md`](hazards.md) | What can kill the project, or its users, plus tripwires and responses. | no |
| [`runbook.md`](runbook.md) | How to operate the project: dev setup, CI gates, release, provider-churn response, security advisories. | yes |

## Reading order

**User:** [`quickstart.md`](quickstart.md) → [`examples/`](../examples/) →
the [`how-to/`](how-to/) page for your backend →
[`explanation/isolation-tiers.md`](explanation/isolation-tiers.md) before running untrusted code.

**New contributor:** `README.md` → [`spec/`](spec/) index → [`build-order.md`](build-order.md) → [`runbook.md`](runbook.md).

**Coding agent:** [`spec/`](spec/) is the contract. Where the spec is silent or marked
`OPEN`, stop and ask — do not invent. [`adr/`](adr/) explains *why*, which matters when a
requirement looks arbitrary.

**Deciding something:** check [`open-questions.md`](open-questions.md) first; if it is not
there and it will outlive the PR, it needs an ADR.

## Precedence

When two documents disagree: [`spec/`](spec/) wins over [`adr/`](adr/).

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

Every configuration sample in [`spec/`](spec/) is parse-tested in CI, precisely because the
first one was not.

## Licensing

Code is **MIT** ([`LICENSE`](../LICENSE)). The prose in this directory is **CC BY 4.0**
([`LICENSE-DOCS`](../LICENSE-DOCS)) — quote and adapt the spec, with credit. Code samples
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
