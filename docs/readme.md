# sbx — Project Documentation

Working documentation for **sbx**: a framework-agnostic Python sandbox abstraction library
for AI-agent code and tool execution. One async API over Docker, E2B and Modal backends;
ports/adapters; capability discovery; security-first defaults; native escape hatches.

> The name `sbx` is not yet settled — see [Q1](open-questions.md#q1--project-name).

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
since and contains at least one known copy-forward bug
([Q13](open-questions.md#q13--doc-bug-is-on-a-dataclass)).

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
