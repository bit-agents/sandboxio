# AGENTS.md

Context for coding agents working in this repository. Humans: read
[CONTRIBUTING.md](CONTRIBUTING.md) first — it is shorter and says the same things.

## What this is

sandboxio is one secure Python API for running AI-agent code in any sandbox (Docker, E2B,
Modal, and an in-process fake). It is a library, not a framework and not a service.

**The specification exists and is normative.** [`docs/spec/`](docs/spec/) is written in
RFC-2119 language and wins over every other document, including this one. Where the spec is
silent or marked `OPEN (Qn)`, **stop and ask** — do not guess. Unresolved items live in
[`docs/open-questions.md`](docs/open-questions.md).

Read before writing code:

| You are touching | Read |
|------------------|------|
| types, value objects, tiers | [spec/01](docs/spec/01-domain-model.md) |
| an adapter's interface | [spec/02](docs/spec/02-ports.md), [spec/08](docs/spec/08-adapter-contract.md) |
| anything in `sandboxio.*` | [spec/03](docs/spec/03-public-api.md) |
| errors, codes, hints | [spec/04](docs/spec/04-errors.md) |
| defaults, network, secrets | [spec/05](docs/spec/05-security-policy.md) |
| logging, spans, audit | [spec/06](docs/spec/06-observability.md) |
| DSNs, config, routing | [spec/07](docs/spec/07-configuration.md) |
| the CLI | [spec/10](docs/spec/10-cli.md) |

Why a decision is the way it is: [`docs/adr/`](docs/adr/). What is being built next, in
order: [`docs/build-order.md`](docs/build-order.md).

## Pinned decisions

These are settled. Do not re-derive them, and do not "improve" them in passing.

| Decision | Value | Source |
|----------|-------|--------|
| Name / short code | `sandboxio` / `SBX` | [ADR-0014](docs/adr/0014-project-name.md) |
| Import | `import sandboxio`, never aliased in docs | [ADR-0014](docs/adr/0014-project-name.md) |
| Python floor | `>=3.11`; develop on 3.14 | [ADR-0015](docs/adr/0015-python-version-floor.md) |
| License | MIT (code), CC BY 4.0 (`docs/` prose), DCO, no CLA | [ADR-0016](docs/adr/0016-license-mit.md), [ADR-0026](docs/adr/0026-docs-license-cc-by.md) |
| Base dependencies | `anyio` + `typing-extensions`, nothing else | [ADR-0004](docs/adr/0004-thin-core-lazy-adapters.md) |
| Async model | async-first on anyio; the sync facade is a thin wrapper | [ADR-0002](docs/adr/0002-async-first-anyio.md), [ADR-0022](docs/adr/0022-sync-facade.md) |
| Error codes | `SBX_E1002`-style, stable, semver-covered | [ADR-0010](docs/adr/0010-stable-error-codes.md) |
| Env vars | `SBX_`-prefixed (`SBX_DEBUG`) | [ADR-0014](docs/adr/0014-project-name.md) |
| Entry-point group | `sandboxio.backends` | [ADR-0004](docs/adr/0004-thin-core-lazy-adapters.md) |
| Timeout error | `SandboxTimeout`, never the builtin | [ADR-0017](docs/adr/0017-timeout-error-naming.md) |
| v0.1 backends | Docker + E2B + Fake; Modal is v0.1.1 | [ADR-0025](docs/adr/0025-v01-scope-cut.md) |

`from __future__ import annotations` is required in every module; ruff enforces it. The
floor is 3.11, so no PEP 695 type-parameter syntax and no t-strings — CI proves this, your
local 3.14 interpreter does not.

## Rules that CI enforces

A red gate is never worked around. If a gate is wrong, change the gate in its own PR.

- **No eager imports.** `import sandboxio` must not pull in an adapter, a provider SDK or
  any third-party package beyond the two base dependencies. `tests/test_import_hygiene.py`
  fails on anything else, and the import budget is 150 ms
  ([ADR-0004](docs/adr/0004-thin-core-lazy-adapters.md), [ADR-0012](docs/adr/0012-no-telemetry-no-import-side-effects.md)).
- **No import side effects.** No sockets, no logging configuration, no printing, no global
  mutable state, no telemetry — ever, not even opt-out.
- **Strict typing.** pyright strict and mypy strict both pass; `py.typed` ships.
- **Every doc sample is machine-checked.** YAML and JSON samples parse, Python samples
  compile, every relative link and anchor resolves.
- **A capability you declare, you implement.** Declaring a `Capability` an adapter does not
  honour is the one unforgivable bug ([ADR-0007](docs/adr/0007-contract-suite-as-spec.md)).
- **Never widen the API to the lowest common denominator.** One-backend features go behind
  `Capability` flags and `.native` ([ADR-0003](docs/adr/0003-no-lowest-common-denominator.md)).

## Commands

```bash
uv sync                       # dev environment; 3.14 by default
uv run pytest                 # unit + gates; no Docker, no network
uv run ruff check . && uv run ruff format --check .
uv run mypy && uv run pyright
```

Everything CI runs is in these four lines. Run them before proposing a change.

## Working style here

- **Commit subjects follow Conventional Commits** and every commit is signed off (`git commit -s`).
- **A bug fix arrives with the test that would have caught it.** If the contract suite
  should have caught it, the test goes in the suite.
- **A decision that outlives the PR needs an ADR**, not a comment. Copy
  [`docs/adr/0000-template.md`](docs/adr/0000-template.md).
- **Do not invent security claims.** Isolation tiers are only published with a dated link
  to the provider's own documentation ([ADR-0006](docs/adr/0006-isolation-tiers-first-class.md)).
- A plausible-looking patch you cannot defend in review is worse than no patch. This is a
  security-adjacent project and the issue queue has to stay survivable.
