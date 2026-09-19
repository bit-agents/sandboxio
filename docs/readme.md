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
| [`input/`](input/) | Original design and planning set. **Frozen source material** — the reasoning, market analysis and intent behind everything else. Not edited. | no |
| [`adr/`](adr/) | Architecture Decision Records. One file per decision, with context and consequences. | yes |
| [`spec/`](spec/) | The normative specification: domain model, ports, public API, errors, security policy, observability, configuration, adapter contract. RFC-2119 language. | **yes** |
| [`build-order.md`](build-order.md) | Sequenced implementation plan with per-step exit criteria. | yes |
| [`open-questions.md`](open-questions.md) | Unresolved decisions. Each graduates into an ADR when settled. | no |
| [`hazards.md`](hazards.md) | What can kill the project, or its users, plus tripwires and responses. | no |
| [`runbook.md`](runbook.md) | How to operate the project: dev setup, CI gates, release, provider-churn response, security advisories. | yes |

## Reading order

**New contributor:** `readme.md` → [`spec/`](spec/) index → [`build-order.md`](build-order.md) → [`runbook.md`](runbook.md).

**Coding agent:** [`spec/`](spec/) is the contract. Where the spec is silent or marked
`OPEN`, stop and ask — do not invent. [`adr/`](adr/) explains *why*, which matters when a
requirement looks arbitrary.

**Deciding something:** check [`open-questions.md`](open-questions.md) first; if it is not
there and it will outlive the PR, it needs an ADR.

## Precedence

When two documents disagree: [`spec/`](spec/) wins over [`adr/`](adr/) wins over
[`input/`](input/). `input/` is history, not instruction — it predates every decision made
since, and several of its snippets are wrong.

### Known errors in `input/`

`input/` is frozen, so these are **not** fixed in place. They are listed here because the
set is fed to coding agents as context, and a wrong snippet gets copied forward.

| Where | Error | Resolved by |
|-------|-------|-------------|
| `07-server-mode-and-routing.md` | The routing config is **not valid YAML** — `-> isolated` trailing a flow mapping is a parser error. Verified with a parser, not by eye. | [spec/07](spec/07-configuration.md#routing-file) |
| `08-testing-strategy.md` | `assert ... is NetworkPolicy(egress="deny")` — `is` against a freshly constructed dataclass is always false. Use `==`. | [spec/01](spec/01-domain-model.md#value-objects) |
| `04-api-design.md` | The streaming example is `pip install -r requirements.txt`, which cannot run under the default deny-egress policy. | [Q10](open-questions.md#q10--deny-by-default-vs-the-demo) |
| `04-api-design.md` | `TimeoutError` shadows the builtin, which on our floor is what `asyncio` raises. | [ADR-0017](adr/0017-timeout-error-naming.md) |
| `03`, `04` | `stream() -> AsyncIterator[bytes]` with `**kw` — loses stderr and exit code, and leaks a kwargs black hole. | [ADR-0019](adr/0019-streaming-process-handle.md) |
| `03-architecture.md` | Auto-detected `create()` returning a different type in sync context. | [ADR-0002](adr/0002-async-first-anyio.md) |
| `02`, `05` | Daytona listed at `CONTAINER` beside the word "verify" — an unearned isolation claim. | [ADR-0018](adr/0018-isolation-tier-ordering.md) |
| all | The name `sbx` is unavailable on PyPI. | [ADR-0014](adr/0014-project-name.md) |

Every configuration sample in [`spec/`](spec/) is parse-tested in CI, precisely because the
first one was not.

## Core principles

Condensed from [`input/README.md`](input/README.md); each is expanded in an ADR.

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
