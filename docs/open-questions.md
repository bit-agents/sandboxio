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
| [Q8](#q8--sync-facade-mechanism) | Sync facade mechanism | P1 | OPEN |
| [Q9](#q9--one-event-three-sinks-audit--otel--meter) | Audit / OTel / Meter overlap | P1 | OPEN |
| [Q10](#q10--deny-by-default-vs-the-demo) | Deny-by-default vs. the demo | P2 | OPEN |
| [Q11](#q11--stateful_code-on-docker) | `STATEFUL_CODE` on Docker | P2 | OPEN |
| [Q12](#q12--v01-scope-cut) | v0.1 scope cut | P2 | OPEN |
| [Q13](#q13--doc-bug-is-on-a-dataclass) | Doc bug: `is` on a dataclass | P2 | OPEN |

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

**Priority:** P1 · **Status:** OPEN · **Source:** `docs/input/03-architecture.md`

"Sync facade is **generated** via an anyio blocking portal" is ambiguous between build-time
codegen and a runtime wrapper. Affects typing fidelity, wheel contents, traceback quality
and how `sandboxio.create()` behaves when called from a sync context.

**Options**
- Build-time codegen of real `.py` — best typing/IDE, adds a generation step to CI and a
  drift risk.
- Runtime `__getattr__`/portal wrapper + hand-written `.pyi` stubs — simplest, stubs can drift.
- Hand-written thin sync class — most code, zero magic, best tracebacks.

**Also unresolved:** `04` shows both `sandboxio.create_sync(...)` and "auto-detected `sandboxio.create()`
in sync context". Auto-detection returning different types from one name is hostile to typing
and to the "one obvious way" rule.

**Recommendation:** runtime portal wrapper + generated-and-CI-verified stubs; drop
auto-detection, keep `create_sync()` as the single explicit sync entry point.

**Decision:** _pending_

---

## Q9 — One event, three sinks (Audit / OTel / Meter)

**Priority:** P1 · **Status:** OPEN · **Source:** `docs/input/05-security.md`, `06-integrations.md`, `04-api-design.md`

Three observability surfaces carry overlapping fields — `AuditEvent` (backend, isolation,
duration_ms, exit_code, bytes in/out), OTel span attributes (same list), and `Meter`
(duration_ms, cost_usd, backend). Emitted independently they will drift, and the redaction
rule ("secrets never appear in events, logs or spans") then has to be enforced three times.

**Recommendation:** one internal operation record produced per op, with three renderers
(audit sink, OTel span mapper, `ExecResult.meter`) and **one** redaction pass upstream of
all of them. Makes the secret-redaction contract testable once.

**Open sub-question:** is `Meter.cost_usd` actually knowable at execution time for E2B/Modal,
or only post-hoc from billing? If the latter, it is an estimate and must be labelled as one.

**Decision:** _pending_

---

## Q10 — Deny-by-default vs. the demo

**Priority:** P2 · **Status:** OPEN · **Source:** `docs/input/05-security.md` vs `04-api-design.md`, `09-dx-playbook.md`

`NetworkPolicy(egress="deny")` is the v0.1 headline default, and the Docker mapping is
network mode `none`. But the streaming example in `04` is literally
`pip install -r requirements.txt` inside the sandbox, and `09` requires `uvx sandboxio demo` to
work with no account and no config. With egress denied, anything installing packages at
runtime fails.

**Needs deciding**
- Does `sandboxio demo` opt into egress (undermining the default) or run fully offline on a
  pre-baked image?
- Is there a blessed pattern for "install deps then lock down" — two-phase policy, or
  build-time image prep only?
- Replace the misleading `pip install` streaming example with one that works under defaults.

**Recommendation:** demo runs offline on a pre-baked image; document image-prep as the
supported way to get dependencies; keep the streaming example but make it something that
runs under deny (e.g. a long local build/test), with a separate, loud how-to for egress
allowlists.

**Decision:** _pending_

---

## Q11 — `STATEFUL_CODE` on Docker

**Priority:** P2 · **Status:** OPEN · **Source:** `docs/input/08-testing-strategy.md`, `03-architecture.md`

`run_code(code, context_id=...)` implies a persistent interpreter per context. E2B gets this
free from its code-interpreter template; Docker does not — it needs a long-lived kernel in
the container (Jupyter kernel, or a bespoke exec server) plus its own lifecycle, timeouts and
teardown. This is plausibly the single largest piece of Docker-adapter work, and the
capability-honesty test forces an answer rather than a fudge.

**Options**
- Docker declares `STATEFUL_CODE` off in v0.1; `context_id` raises `CapabilityNotSupported`.
- Build a minimal exec-server image shipped with the adapter.
- Embed a Jupyter kernel (heavier image, well-trodden, rich outputs come along).

**Recommendation:** v0.1 Docker declares it off and raises — honest, and keeps the adapter
small. Revisit once the E2B adapter has pinned down what rich outputs and stateful contexts
actually need to look like.

**Decision:** _pending_

---

## Q12 — v0.1 scope cut

**Priority:** P2 · **Status:** OPEN · **Source:** `docs/input/10-roadmap.md`

v0.1 as scoped for weeks 2-10: three real adapters (Docker, E2B, Modal) + FakeBackend +
contract suite + CI matrix + MCP server + two framework adapters + OTel + audit + CLI
(`demo`, `doctor`) + full Diátaxis docs + llms.txt + attestations. That is not an eight-week
scope, and the parts that slip will be the docs and the contract suite — the two things the
whole bet rests on.

**Recommendation:** cut to **Docker + E2B + Fake**; Modal moves to v0.1.1. Two backends fully
carry the "swap with one line" launch narrative. Keep the MCP server (it is the distribution
channel) and exactly one framework adapter (LangGraph). Everything else in `10`'s v0.1 list
stays.

**Decision:** _pending_

---

## Q13 — Doc bug: `is` on a dataclass

**Priority:** P2 · **Status:** OPEN · **Source:** `docs/input/08-testing-strategy.md`

```python
assert sbx_fake.calls[0].network is NetworkPolicy(egress="deny")
```

`is` against a freshly constructed dataclass is always false. Minor in itself, but this file
is explicitly fed to coding agents as input context, so the bug gets copied into generated
tests.

**Fix:** use `==` (and make `NetworkPolicy` a frozen, eq-comparable dataclass). Worth a pass
over the other `docs/input/` snippets for the same class of copy-forward error before they
are used as agent context.

**Decision:** _pending_
