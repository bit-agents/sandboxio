# Open Questions

Gaps, contradictions and unmade decisions found in `docs/input/`. Worked through one at a
time; each resolved item gets a `Decision:` line and, where it shapes the codebase, an ADR
in `docs/adr/`.

**Status legend:** `OPEN` · `DECIDED` · `DEFERRED` (revisit at a named trigger)

**Priority legend:** `P0` blocks commit one · `P1` blocks v0.1 core · `P2` blocks v0.1 ship

| # | Question | Priority | Status |
|---|----------|----------|--------|
| [Q1](#q1--project-name) | Project name | P0 | **DECIDED** |
| [Q2](#q2--python-version-floor) | Python version floor | P0 | **DECIDED** |
| [Q3](#q3--license) | License | P0 | **DECIDED** |
| [Q4](#q4--timeouterror-shadows-the-builtin) | `TimeoutError` shadows the builtin | P1 | **DECIDED** |
| [Q5](#q5--isolationtier-needs-ordering) | `IsolationTier` needs ordering | P1 | **DECIDED** |
| [Q6](#q6--stream-loses-stderr-and-exit-code) | `stream()` loses stderr and exit code | P1 | **DECIDED** |
| [Q7](#q7--cancellation-semantics) | Cancellation semantics | P1 | **DECIDED** |
| [Q8](#q8--sync-facade-mechanism) | Sync facade mechanism | P1 | **DECIDED** |
| [Q9](#q9--one-event-three-sinks-audit--otel--meter) | Audit / OTel / Meter overlap | P1 | **DECIDED** |
| [Q10](#q10--deny-by-default-vs-the-demo) | Deny-by-default vs. the demo | P2 | **DECIDED** |
| [Q11](#q11--stateful_code-on-docker) | `STATEFUL_CODE` on Docker | P2 | **DECIDED** |
| [Q12](#q12--v01-scope-cut) | v0.1 scope cut | P2 | **DECIDED** |
| [Q13](#q13--doc-bug-is-on-a-dataclass) | Doc bug: `is` on a dataclass | P2 | **DECIDED** |

---

## Q1 — Project name

**Priority:** P0 · **Status:** DECIDED · **Source:** `docs/input/README.md`

The working name was load-bearing across module paths, DSN handling, the entry-point group,
error codes, env vars, the CLI, docs URLs and the third-party package convention — and it
is taken on PyPI by a dormant 2020 flashcards package. PEP 541 transfer is slow and
uncertain, so it was treated as unavailable.

**Decision:** the project is **`sandboxio`**, with **`SBX`** as its short code for error
codes, env vars, the pytest fixture and the CLI alias. Canonical usage is `import
sandboxio`, unaliased. Full rationale, the candidate sweep and the surface-by-surface table
are in [ADR-0014](adr/0014-project-name.md).

---

## Q2 — Python version floor

**Priority:** P0 · **Status:** DECIDED · **Source:** `docs/input/03-architecture.md`, `04-api-design.md`

Never stated in the input set. A floor is an adoption gate: the whole target ecosystem
(`e2b`, `modal`, `langgraph`, `openai-agents`, `pydantic-ai`, `crewai`, `typer`, `anyio`)
sits at `>=3.10`, and download share shows a 3.13 floor would exclude roughly three
quarters of it, a 3.14 floor ~94%. `crewai` additionally caps at `<3.14`.

**Decision:** `requires-python = ">=3.11"`, CI matrix 3.11-3.14, development and default CI
on **3.14**, `from __future__ import annotations` repo-wide, no upper cap. Data and
rationale in [ADR-0015](adr/0015-python-version-floor.md).

---

## Q3 — License

**Priority:** P0 · **Status:** DECIDED · **Source:** not covered in `docs/input/`

Positioning is self-hostable and enterprise-supply-chain friendly, and the market doc cites
Daytona's license changes as a risk, yet no license was chosen. The surrounding ecosystem is
overwhelmingly permissive (`anyio`, `pydantic`, `langgraph`, `e2b`, `openai-agents` all MIT).

**Decision:** **MIT** for the library, **DCO** for contributions, and the Phase-2
`sandboxio-server` license deliberately left open until that package exists. Rationale and
the Apache-2.0 trade-off in [ADR-0016](adr/0016-license-mit.md).

---

## Q4 — `TimeoutError` shadows the builtin

**Priority:** P1 · **Status:** DECIDED · **Source:** `docs/input/04-api-design.md`

The input taxonomy named the class `TimeoutError`, shadowing the builtin — which, on our
3.11 floor, is what `asyncio` and `anyio` raise. The decisive fact: builtin `TimeoutError`
is an `OSError` subclass, so inheriting it would let `except OSError` swallow sandbox
timeouts and would attach dead `errno`/`strerror` attributes. Prior art is split (httpx no,
aiohttp yes, redis-py and urllib3 shadow the name).

**Decision:** no sandboxio exception inherits from a builtin and no name shadows one.
Canonical `SandboxTimeout` as a catch-all base, with `ExecutionTimeout` (`SBX_E1302`,
unchanged meaning) and `CreateTimeout` (`SBX_E1203`) carrying the codes, plus a new
`SandboxGone` (`SBX_E1204`) for a sandbox whose lifetime ended mid-use — a gap the original
catalog had no error for. No `TimeoutError` alias. Full rationale in
[ADR-0017](adr/0017-timeout-error-naming.md).

---

## Q5 — `IsolationTier` needs ordering

**Priority:** P1 · **Status:** DECIDED · **Source:** `docs/input/05-security.md`

`require_isolation=MICROVM` implies a comparison a plain `Enum` does not provide, and
`CONTAINER < GVISOR < MICROVM` is not self-evidently a legitimate total order. Kubernetes
`RuntimeClass`, which we already borrow as a mental model, deliberately does not rank its
handlers. The discriminator was what happens when a stronger tier is added later: a
set-based `require_isolation={MICROVM}` would reject a future `CONFIDENTIAL_VM` backend.

**Decision:** plain `Enum` with string values plus an explicit rank map spaced by 10, rich
comparisons derived from the rank, no arithmetic, and `tier.satisfies(minimum)` as the
taught form. The rank orders **escape resistance only**, not general security. Adds
`UNKNOWN` as the default for any adapter that does not declare a tier — it satisfies no
requirement, and creating on one warns. Rationale in
[ADR-0018](adr/0018-isolation-tier-ordering.md).

---

## Q6 — `stream()` loses stderr and exit code

**Priority:** P1 · **Status:** DECIDED · **Source:** `docs/input/03-architecture.md`, `04-api-design.md`

`AsyncIterator[bytes]` loses stdout/stderr separation and the exit code, and carries a
`**kwargs` black hole. The decisive constraint was cleanup: breaking out of an `async for`
does not close the iterator, so an abandoned bare iterator leaks a billing remote process.

**Decision:** `stream()` is a plain, non-awaitable factory returning a **`Process`** async
context manager that iterates `OutputChunk(stream, data)` and terminates in
`await proc.wait()`. Ordering is guaranteed within each stream, not between them.
`ExecResult` gains `streamed: bool`, and when set, `stdout`/`stderr` are empty by
construction. `stream_code` is deferred until a second backend supports it. Rationale and
the rejected alternatives in [ADR-0019](adr/0019-streaming-process-handle.md).

---

## Q7 — Cancellation semantics

**Priority:** P1 · **Status:** DECIDED · **Source:** not covered in `docs/input/`

Undefined in the input set, and behind the most expensive failure mode in the project.
Under structured concurrency a `finally: await sb.kill()` is decorative — it is cancelled at
its first checkpoint — so a cancelled agent run leaks a billing cloud sandbox.

**Decision:** shielded teardown in a bounded `anyio.move_on_after(TEARDOWN_GRACE,
shield=True)` scope, default 5 s, overridable by `SBX_TEARDOWN_GRACE`. Cancellation kills
the remote process; detach-on-cancel is deferred. Only the id-known window of `create()` is
shielded, never the whole call. Cancellation always propagates as cancellation, never
wrapped in a `SandboxError`. Grace expiry emits `OrphanedSandboxWarning`; `sandboxio reap`
is the operator backstop. A background reaper task was rejected as unowned global state.
The mandatory `create(timeout=...)` is the guaranteed backstop. Rationale in
[ADR-0020](adr/0020-cancellation-semantics.md).

---

## Q8 — Sync facade mechanism

**Priority:** P1 · **Status:** DECIDED · **Source:** `docs/input/03-architecture.md`

"Generated via an anyio blocking portal" was ambiguous between build-time codegen and a
runtime wrapper. The point that collapsed the option space: **codegen does not avoid the
portal** — `unasync`-style generation works only when the emitted sync code calls sync
libraries, and our adapters are async-only. Codegen decides where the delegating wrapper
lives, not whether one exists.

**Decision:** hand-written thin delegation (~30 members) with a **CI-enforced parity test**
that introspects the async protocols and matches signatures — which removes the drift
objection without a codegen pipeline. The portal is **per-sandbox**, started by
`create_sync()` and stopped on exit; N sync sandboxes means N threads, documented. Sync
streaming is offered with its per-chunk thread round-trip cost stated. Supersedes the
runtime-proxy lean in ADR-0002. Rationale in [ADR-0022](adr/0022-sync-facade.md).

---

## Q9 — One event, three sinks (Audit / OTel / Meter)

**Priority:** P1 · **Status:** DECIDED · **Source:** `docs/input/05-security.md`, `06-integrations.md`, `04-api-design.md`

Three surfaces carried overlapping fields and would have drifted, forcing the
secret-redaction rule to be implemented per sink. Two things the original question missed:
the sub-question of whether `cost_usd` is knowable at all, and that a *slow* audit sink is a
subtler problem than a failing one.

**Decision:** one `_OperationRecord` opened at start and closed at completion, redacted once
at close, rendered three ways; the OTel span starts at open so long executions are visible
while running. **No inline `cost_usd`** — both SDKs were inspected and the data does not
exist at execution time (E2B has no cost surface; Modal's billing is post-hoc, account-level
and daily-resolution). Cost ships instead as capability-gated post-hoc reconciliation by
`metadata` label. Audit sinks are async, must return promptly, are awaited inline under
`SBX_AUDIT_TIMEOUT`, and failure policy is configurable (`warn` default, `fail` available).
Evidence and rationale in [ADR-0021](adr/0021-observability-record.md).

---

## Q10 — Deny-by-default vs. the demo

**Priority:** P2 · **Status:** DECIDED · **Source:** `docs/input/05-security.md` vs `04-api-design.md`, `09-dx-playbook.md`

Half the premise was a misreading: `network_mode: none` governs the *sandbox's* egress, while
`docker pull` runs on the *host* daemon. The demo was never in conflict with the default. The
real constraint is harder — **Docker Engine has no per-host egress filtering** (verified
against the CLI: `--network` accepts only `none | bridge | host | container | <custom>`), so
Docker cannot honour `NetworkPolicy(allow=(...))` at all.

**Decision:** Docker raises `CapabilityNotSupported` for a non-empty `allow` rather than
silently granting bridge access; allowlists are an E2B/Modal capability. Dependencies reach a
deny-egress sandbox by **image prep** or an **offline wheelhouse**. A mutable install-then-lock
setup window is rejected — it is unimplementable on Docker and makes the policy in effect
time-varying in the audit record. The demo's under-60 s budget is restated as measured warm.
Rationale in [ADR-0023](adr/0023-docker-network-and-dependencies.md).

---

## Q11 — `STATEFUL_CODE` on Docker

**Priority:** P2 · **Status:** DECIDED · **Source:** `docs/input/08-testing-strategy.md`, `03-architecture.md`

`run_code(context_id=...)` needs a persistent interpreter, which Docker does not provide.
Baking an exec server or Jupyter kernel into an image fails on a point that outweighs
convenience: users bring arbitrary images, and `docker://python:3.12-slim` is the documented
zero-config path.

**Decision:** Docker declares `STATEFUL_CODE` **off** in v0.1 and raises
`CapabilityNotSupported`; stateless `run_code` is fully supported and `results` stays `None`,
never synthesised. A runtime-injected bootstrap — upload a script, `docker exec` it, frame a
protocol over stdin, needing only Python in the image — is recorded as the **intended path**,
revisited after the E2B adapter reveals what stateful contexts and rich outputs really need.
Purpose-built-image approaches are rejected outright. Rationale in
[ADR-0024](adr/0024-stateful-code-on-docker.md).

---

## Q12 — v0.1 scope cut

**Priority:** P2 · **Status:** DECIDED · **Source:** `docs/input/10-roadmap.md`

Three real adapters plus the suite, CI matrix, MCP server, two framework adapters, OTel,
audit, CLI and full docs is not an eight-week scope. What slips under pressure is
documentation and test depth — the two things the differentiation rests on.

**Decision:** v0.1 ships **Docker + E2B + Fake**; **Modal moves to v0.1.1**. Two backends
carry the one-line-swap narrative as well as three, and Docker↔E2B is the widest gap in the
set, so it stresses the abstraction hardest. One framework adapter (LangGraph) in v0.1;
"works with all four" becomes a v0.2 claim. Rationale in
[ADR-0025](adr/0025-v01-scope-cut.md).

---

## Q13 — Doc bug: `is` on a dataclass

**Priority:** P2 · **Status:** DECIDED · **Source:** `docs/input/08-testing-strategy.md`

`assert sbx_fake.calls[0].network is NetworkPolicy(egress="deny")` is always false. Minor
alone, but `input/` is fed to coding agents, so the bug propagates into generated tests.
Q13 also called for a sweep of the other snippets for the same class of error.

**Decision:** value objects are frozen dataclasses compared with `==`
([spec/01](spec/01-domain-model.md#value-objects)); the corrected snippet is in
[spec/08](spec/08-adapter-contract.md#fakebackend). The sweep was done and found a worse
one — the routing config in `input/07` **is not valid YAML** and was copied verbatim into
the spec before a parser caught it. Fixed in [spec/07](spec/07-configuration.md#routing-file),
which now also restructures `default_class` as a top-level mandatory key rather than a
pseudo-route. All findings are listed as
[known errors in `input/`](readme.md#known-errors-in-input); `input/` stays frozen. Every
config sample in `spec/` is now parse-tested in CI.
