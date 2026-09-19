# Build Order

Sequenced implementation plan. Each step has **exit criteria** — the next step does not
start until they are green. Ordering is deliberate: the two things the whole bet rests on
(the contract suite and the docs) are the two things that slip if left last, so they move
early.

Scope reference: [`input/10-roadmap.md`](input/10-roadmap.md). Where this file and that one
differ, this one is current.

---

## Step 0 — Lock the P0 decisions (½ day)

Nothing is committed until the name is settled, because it is baked into module paths, DSN
schemes, the entry-point group, error codes, env vars and docs URLs.

- [x] [Q1](open-questions.md#q1--project-name) name — **`sandboxio`**, short code `SBX` ([ADR-0014](adr/0014-project-name.md))
- [x] [Q2](open-questions.md#q2--python-version-floor) Python floor — **>=3.11**, dev on 3.14 ([ADR-0015](adr/0015-python-version-floor.md))
- [x] [Q3](open-questions.md#q3--license) license — **MIT** + DCO ([ADR-0016](adr/0016-license-mit.md))

**Exit:** three ADRs written ([0014](adr/0014-project-name.md), [0015](adr/0015-python-version-floor.md), [0016](adr/0016-license-mit.md)); the name reserved on PyPI; the repo named. **Done.**

---

## Step 1 — Skeleton and gates, before any feature code (1 day)

Gates are cheap now and expensive to retrofit: an accidental eager import spreads fast, and
an import budget added in month three is a week of untangling.

- `uv` project, `src/` layout, `py.typed`, ruff, pyright strict, mypy strict
- `requires-python = ">=3.11"`; CI matrix 3.11-3.14 with 3.11 a **required** check, dev default 3.14
- CI with the four hard gates **already failing closed**:
  import budget <150 ms · no sockets at import (`pytest-socket`) · wheel-contents test ·
  type check
- `LICENSE` (MIT), `SECURITY.md`, `CONTRIBUTING.md` with DCO and inbound-equals-outbound, PyPI Trusted Publishing, PEP 740 attestations, `CHANGELOG.md`
- `AGENTS.md` at repo root carrying the Step 0 decisions and the links into [`spec/`](spec/)
- Issue templates requiring reproduction; stated triage policy

**Exit:** empty package installs, imports in <150 ms, CI green, and a deliberately-added
eager import turns CI red.

> `AGENTS.md` belongs here, not at the end. Most of this will be built through coding
> agents, and without the pinned decisions in context every session re-invents the sync
> facade.

---

## Step 2 — Core types, zero behaviour (2-3 days)

`models.py`, `errors.py`, `protocols.py`, `registry.py`. No I/O.

Dependencies resolved: [Q4](open-questions.md#q4--timeouterror-shadows-the-builtin) error naming
([ADR-0017](adr/0017-timeout-error-naming.md)), [Q5](open-questions.md#q5--isolationtier-needs-ordering)
tier ordering ([ADR-0018](adr/0018-isolation-tier-ordering.md)). **Unblocked.**

- Value objects per [spec/01](spec/01-domain-model.md), all frozen with value equality
- `IsolationTier` with its rank map, plus the test asserting every member is ranked
- Full error tree with codes, hints and URLs per [spec/04](spec/04-errors.md); the catalog
  is data, and the docs pages generate from it
- Protocols per [spec/02](spec/02-ports.md)
- Registry: entry points + `register()`, lazy and cached

**Exit:** `BackendNotFound` and `BackendNotInstalled` raise with correct hints and install
commands; catalog-to-docs generation runs in CI; import budget still green.

---

## Step 3 — Contract suite first, then FakeBackend (1 week)

The suite is written **before** any adapter, so it specifies behaviour instead of describing
whatever Docker happened to do. This is the step that makes everything after it cheap.

Depends on: ~~Q6 streaming shape~~ (decided, [ADR-0019](adr/0019-streaming-process-handle.md)),
[Q7](open-questions.md#q7--cancellation-semantics) cancellation,
[Q9](open-questions.md#q9--one-event-three-sinks-audit--otel--meter) one-record design.

- `BackendContractSuite` covering the map in [spec/08](spec/08-adapter-contract.md),
  including cancellation, shielded teardown and capability honesty
- `FakeBackend` + `sbx_fake` pytest fixture, registered by entry point
- The one operation record, redaction, and a no-op audit sink

**Exit:** `FakeBackend` passes 100% of the suite; a deliberately broken fake (swallowed
timeout, faked capability, leaked secret) fails it.

---

## Step 4 — Docker adapter to 100% (1-2 weeks)

Depends on: [Q10](open-questions.md#q10--deny-by-default-vs-the-demo) network/demo story,
[Q11](open-questions.md#q11--stateful_code-on-docker) `STATEFUL_CODE`.

- Full adapter: lifecycle, `run`, `run_code`, streaming, filesystem
- `network_mode: none` by default; deny verified against a canary host
- Ryuk-style reaper; CI asserts zero leaked containers
- Sync facade ([Q8](open-questions.md#q8--sync-facade-mechanism)) landed and tested through
  the same suite

**Threshold:** if Docker cannot pass the suite cleanly, **fix the abstraction before
touching a cloud adapter** — a suite bent to fit Docker is worthless for E2B.

**Exit:** 100% of the suite green on real Docker in CI; zero leaked containers; deny-egress
proven.

---

## Step 5 — E2B adapter (1-2 weeks)

The real stress test of the abstraction: rich outputs, PTY, pause/resume, microVM isolation.

- Full adapter; rich outputs surfaced through `ExecResult.results`
- PTY and pause/resume stay behind `.native` for v0.1
- Native exception mapping with `__cause__`
- Nightly + release CI job, gated on the API key

**Expect to widen `Capability` or push things to `.native` here.** Never bend toward the
lowest common denominator ([ADR-0003](adr/0003-no-lowest-common-denominator.md)).

**Exit:** 100% of the suite for declared capabilities; a one-line DSN swap between Docker
and E2B runs the same downstream code unchanged.

---

## Step 6 — Distribution surface (2 weeks)

- `sandboxio doctor`, `uvx sandboxio demo` ([spec/10](spec/10-cli.md))
- MCP server, containerized, published to the Docker MCP Catalog
  ([spec/09](spec/09-integrations.md))
- LangGraph tool adapter; OpenAI Agents tool adapter
- OTel span mapping through `sandboxio/otel.py`; stdlib-logging and file audit sinks
- Diátaxis docs: quickstart, per-backend how-tos, offline-testing how-to, generated error
  reference, explanation pages; `llms.txt` + `llms-full.txt`; paste-ready `AGENTS.md`
  snippet
- Copy-paste GitHub Actions workflow for users: fake job on PRs, docker job on main

**Exit:** a stranger completes the quickstart in under 5 minutes on a clean machine; every
README example runs verbatim (a copied example that does not run is a **P0 bug**).

---

## v0.1 ship

**Scope cut ([Q12](open-questions.md#q12--v01-scope-cut)): Docker + E2B + Fake. Modal moves
to v0.1.1.** Two backends fully carry the "swap with one line" narrative; three does not buy
a better launch, it buys a later one.

Launch narrative: *one secure Python API for running AI-agent code in any sandbox — swap
Docker↔E2B with one line; no network by default; test your agent tools offline with the
built-in fake.* Publish the MCP server to the Docker MCP Catalog the same day.

---

## v0.1.1 — Modal

GPU, Volumes with per-tenant `sub_path`, gVisor tier. Third backend also re-tests the
abstraction against a genuinely different filesystem model.

## v0.2 — differentiation (ROI order)

1. **Flight recorder + `sandboxio replay <trace>`** — record code, file diffs, stdio and timing to
   a portable trace; deterministic replay; local static HTML viewer. The signature feature.
2. **Egress learning mode** — `egress="learn"` records attempted domains, emits a
   paste-ready allowlist. Nobody else does record-then-generate.
3. **Per-execution meter** — `{duration_ms, cost_usd?, backend}` on every result, plus
   `sandboxio bench`.
4. **Auto dependency inference** — PEP 723 / import parsing → uv provisioning, sandbox-gated.
5. Pre-execution security lint hook (advisory by default).
6. Pydantic AI + CrewAI adapters; OpenAI `SandboxClient` adapter.
7. MCP `search_docs`; adapter authoring guide + template repo; shell completions.

## v0.3+ — capability-gated and ecosystem

Snapshot/fork once ≥2 backends are stable · shadow mode (run on two backends, diff) ·
Daytona and Vercel adapters · K8s agent-sandbox adapter near CRD 1.0 · TUI dashboard ·
`sandboxio-server` **only when its trigger fires**
([ADR-0009](adr/0009-library-first-server-later.md)).

---

## Dependency summary

| Step | Blocked by |
|------|-----------|
| 0 | — |
| 1 | Q1, Q2, Q3 |
| 2 | — (Q4, Q5 decided) |
| 3 | ~~Q6~~, Q7, Q9 |
| 4 | Q8, Q10, Q11 |
| 5 | Step 4 exit criteria, in full |
| 6 | Q12 (scope), Q10 (demo) |
