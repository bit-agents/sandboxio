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
| [Q3](#q3--license) | License | P0 | OPEN |
| [Q4](#q4--timeouterror-shadows-the-builtin) | `TimeoutError` shadows the builtin | P1 | OPEN |
| [Q5](#q5--isolationtier-needs-ordering) | `IsolationTier` needs ordering | P1 | OPEN |
| [Q6](#q6--stream-loses-stderr-and-exit-code) | `stream()` loses stderr and exit code | P1 | OPEN |
| [Q7](#q7--cancellation-semantics) | Cancellation semantics | P1 | OPEN |
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

**Priority:** P0 · **Status:** OPEN · **Source:** not covered in `docs/input/`

Positioning is "self-hostable, enterprise supply-chain friendly", and the market doc calls
out Daytona's license changes / closed-sourcing as a risk. No license is chosen anywhere.

**Options**
- **Apache-2.0** — explicit patent grant; expected by enterprise review and by an adapter
  ecosystem; matches the fsspec/OTel neighbourhood.
- **MIT** — shortest, most permissive, no patent grant.
- Source-available / BSL — contradicts the stated positioning.

**Recommendation:** Apache-2.0. Decide CLA/DCO at the same time (DCO is lighter and enough).

**Decision:** _pending_

---

## Q4 — `TimeoutError` shadows the builtin

**Priority:** P1 · **Status:** OPEN · **Source:** `docs/input/04-api-design.md`

The error taxonomy defines `sandboxio.TimeoutError` (`SBX_E1302`) and examples use
`except sandboxio.TimeoutError`. On 3.11+ the builtin `TimeoutError` is what `asyncio` raises, so
a shadowing name makes it ambiguous whether a caller is catching sandboxio's error, the builtin,
or both — and readers will assume the wrong one.

**Options**
- Rename canonical class to `SandboxTimeout`, keep `TimeoutError` as a deprecated alias.
- Keep the name but inherit from builtin `TimeoutError` so both catches work.
- Both: `SandboxTimeout(SandboxError, TimeoutError)` + alias.

**Recommendation:** both — canonical `SandboxTimeout`, inheriting the builtin, with
`sandboxio.TimeoutError` as an alias. Same question applies to any other builtin-shadowing names
in the taxonomy (`ConnectionError`-adjacent ones).

**Decision:** _pending_

---

## Q5 — `IsolationTier` needs ordering

**Priority:** P1 · **Status:** OPEN · **Source:** `docs/input/05-security.md`

`require_isolation=IsolationTier.MICROVM` must raise `ConfigurationError` "if the resolved
backend is weaker" — that implies a comparison. A plain `Enum` does not compare, and
`CONTAINER | GVISOR | MICROVM` is not obviously a total order in the first place (gVisor is
documented as defence-in-depth, explicitly *not* hardware-VM equivalent).

**Options**
- `IntEnum` with declared ranks — simple, but leaks arithmetic into the public API.
- Plain `Enum` + explicit internal rank map + a `satisfies()` helper.
- Set-of-acceptable-tiers instead of a floor: `require_isolation={MICROVM, GVISOR}`.

**Recommendation:** plain `Enum` + explicit rank map + `tier.satisfies(minimum)`. Keeps the
ordering a documented policy claim rather than an accident of enum values, and stays
extensible when a new tier lands mid-scale.

**Decision:** _pending_

---

## Q6 — `stream()` loses stderr and exit code

**Priority:** P1 · **Status:** OPEN · **Source:** `docs/input/03-architecture.md`, `04-api-design.md`

`def stream(self, cmd, **kw) -> AsyncIterator[bytes]` yields undifferentiated bytes: no
stdout/stderr split (which `ExecResult` does provide), no exit code, no terminal result. A
caller streaming `pip install` cannot tell failure from success without a second call. The
`**kw` also violates the "no kwargs black holes" rule in `04`.

**Options**
- Yield tagged chunks: `AsyncIterator[Chunk]` where `Chunk(stream="stdout"|"stderr", data: bytes)`.
- Async context manager returning a handle with `.stdout`/`.stderr` iterators and an
  awaitable `.result()` / `.wait()` → `ExecResult`.
- Keep bytes, add an out-of-band `.result` attribute on the iterator object.

**Recommendation:** option 2 — a `Process` handle (already named in the domain model but
never given an interface) that exposes tagged streaming *and* terminates in an `ExecResult`.
Also replace `**kw` with the same typed kwargs as `run()`.

**Decision:** _pending_

---

## Q7 — Cancellation semantics

**Priority:** P1 · **Status:** OPEN · **Source:** not covered in `docs/input/`

Undefined: what happens when the caller's anyio task is cancelled mid-`run()` or mid-`create()`.
Under structured concurrency, cancellation propagates into the adapter's own awaits — so a
naive `finally: await sb.kill()` is itself cancelled and every cancelled agent run leaks a
cloud sandbox (and bills for it). Partial-creation is the worse case: cancelled between
provider-side create and returning the handle, nothing owns the sandbox.

**Needs deciding**
- Teardown runs under a shielded cancel scope with a bounded grace period — what period?
- Does cancellation kill the remote process, or detach and leave it running?
- `create()` cancelled mid-flight: best-effort shielded cleanup, or reconcile later via the
  `metadata` labels + reaper?
- Does `Process`/stream cancellation differ from `run()` cancellation?

**Recommendation:** define it as part of the **contract suite**, not just prose — shielded
teardown with a bounded grace period, cancellation kills the remote process, and creation is
cleaned up best-effort with the reaper as backstop. Every adapter then proves it.

**Decision:** _pending_

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
