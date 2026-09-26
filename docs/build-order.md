# Build Order

Sequenced implementation plan. Each step has **exit criteria** — the next step does not
start until they are green. Ordering is deliberate: the two things the whole bet rests on
(the contract suite and the docs) are the two things that slip if left last, so they move
early.

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

- [x] `uv` project, `src/` layout, `py.typed`, ruff, pyright strict, mypy strict
- [x] `requires-python = ">=3.11"`; CI matrix 3.11-3.14, dev default 3.14. Making 3.11 a
  **required** check is a branch-protection setting, applied when the repo goes public
- [x] CI with the four hard gates **already failing closed**:
  import budget <150 ms · no sockets at import (`pytest-socket`) · wheel-contents test ·
  type check · doc-sample parse test · doc-link check (`scripts/check_doc_links.py`)
- [x] `LICENSE` (MIT), `LICENSE-DOCS` (CC BY 4.0, [ADR-0026](adr/0026-docs-license-cc-by.md)), `SECURITY.md`, `CONTRIBUTING.md` with DCO and inbound-equals-outbound
- [x] PyPI Trusted Publishing, PEP 740 attestations, `CHANGELOG.md` — the release workflow
  is token-free and attesting; the PyPI-side publisher entry is configured at first release
- [x] `AGENTS.md` at repo root carrying the Step 0 decisions and the links into [`spec/`](spec/README.md)
- [x] Issue templates requiring reproduction; stated triage policy

Adapter extras (`sandboxio[docker]`, `[e2b]`, `[modal]`) are deliberately **not** declared
yet: an extra that installs nothing is a lie, and each provider SDK choice belongs to the
step that writes its adapter.

**Exit:** empty package installs, imports in 0.2 ms, gates green on 3.11 and 3.14, and both
a deliberately-added eager import and a socket at import turn them red. **Done.**

> `AGENTS.md` belongs here, not at the end. Most of this will be built through coding
> agents, and without the pinned decisions in context every session re-invents the sync
> facade.

---

## Step 2 — Core types, zero behaviour (2-3 days)

`models.py`, `errors.py`, `protocols.py`, `registry.py`. No I/O.

Dependencies resolved: [Q4](open-questions.md#q4--timeouterror-shadows-the-builtin) error naming
([ADR-0017](adr/0017-timeout-error-naming.md)), [Q5](open-questions.md#q5--isolationtier-needs-ordering)
tier ordering ([ADR-0018](adr/0018-isolation-tier-ordering.md)). **Unblocked.**

- [x] Value objects per [spec/01](spec/01-domain-model.md), all frozen with value equality
- [x] `IsolationTier` with its rank map, plus the test asserting every member is ranked
- [x] Full error tree with codes, hints and URLs per [spec/04](spec/04-errors.md); the catalog
  is data, and the docs pages generate from it (`scripts/gen_error_catalog.py` → [`errors/`](errors/README.md))
- [x] Protocols per [spec/02](spec/02-ports.md)
- [x] Registry: entry points + `register()`, lazy and cached

Decisions taken here that the spec left implicit: `ConfigurationError` raised directly
carries `SBX_E1000`; `RichOutput` and `FileInfo` got minimal shapes in spec/01;
`ExecResult.results` is a tuple, like every other sequence in a frozen value object.

**Exit:** `BackendNotFound` and `BackendNotInstalled` raise with the exact install command;
`--check` on the generated catalog is a pytest gate; import is ~9 ms. **Done.**

---

## Step 3 — Contract suite first, then FakeBackend (1 week)

The suite is written **before** any adapter, so it specifies behaviour instead of describing
whatever Docker happened to do. This is the step that makes everything after it cheap.

Dependencies resolved: Q6 streaming ([ADR-0019](adr/0019-streaming-process-handle.md)),
Q7 cancellation ([ADR-0020](adr/0020-cancellation-semantics.md)), Q9 observability record
([ADR-0021](adr/0021-observability-record.md)). **Unblocked.**

- [x] `BackendContractSuite` covering the map in [spec/08](spec/08-adapter-contract.md),
  including the four streaming-cleanup cases, the four cancellation cases, and capability honesty
- [x] `FakeBackend` + `sbx_fake` pytest fixture, registered by entry point
- [x] The one operation record, redaction at close, and the no-op + queue audit sinks
- [x] Pulled forward because the fake had to be reachable as `create("fake://")`: the DSN
  parser, `sandboxio.create()`/`connect()` with `require_isolation`, shielded teardown and
  request validation shared by every adapter

Decisions taken here: sinks are configured per backend via `AuditConfig`; a backend that
does not declare `NETWORK_POLICY` refuses to create at all, since deny-by-default cannot be
honoured; the filesystem family `SBX_E1700`/`SBX_E1701` was added under spec/04's rule 3.

**Exit:** `FakeBackend` passes the suite in three configurations (everything declared,
almost nothing declared, `UNKNOWN` tier); three deliberately broken fakes fail it exactly
where they are broken and nowhere else. **Done.**

---

## Step 4 — Docker adapter to 100% (1-2 weeks)

Dependencies resolved: Q8 sync facade ([ADR-0022](adr/0022-sync-facade.md)), Q10 network and
dependencies ([ADR-0023](adr/0023-docker-network-and-dependencies.md)), Q11 `STATEFUL_CODE`
([ADR-0024](adr/0024-stateful-code-on-docker.md)). **Unblocked.**

- [x] Full adapter: lifecycle, `run`, `run_code`, streaming, filesystem — shipped as the
  workspace distribution `sandboxio-docker` (import `sandboxio_docker`), which is what
  `sandboxio[docker]` installs; the same shape a third-party adapter takes
- [x] `network_mode: none` by default; deny verified against a canary host; non-empty `allow`
  raises `CapabilityNotSupported`; `STATEFUL_CODE` declared off
- [x] Ryuk-style reaper (one sidecar per process, `SBX_DOCKER_REAPER=0` disables); CI asserts
  zero leaked containers
- [x] Sync facade ([ADR-0022](adr/0022-sync-facade.md)) landed with the parity test; exercised
  by behaviour tests against the fake and a smoke test on real Docker, **not** by the full
  contract suite — the suite is async, and wrapping sync back into async would not test the
  cancellation rows honestly. Open point for the suite, not the facade.

Decisions taken here: docker-py in worker threads, never an asyncio-only client (ADR-0002's
trio point); a timeout or cancellation restarts the container because Docker cannot signal
one `exec` — every process dies, the filesystem survives, and the docs say so; the PID 1 is
`sleep <timeout>`, which is the provider-side lifetime backstop Docker otherwise lacks;
`disk_mb` is refused rather than silently ignored.

**Threshold:** if Docker cannot pass the suite cleanly, **fix the abstraction before
touching a cloud adapter** — a suite bent to fit Docker is worthless for E2B.

**Exit:** 100% of the suite green on real Docker (locally against OrbStack; the CI job is
in place); zero leaked containers; deny-egress proven against a canary host. **Done.**

---

## Step 5 — E2B adapter (1-2 weeks)

The real stress test of the abstraction: rich outputs, PTY, pause/resume, microVM isolation.

- [x] Full adapter as the workspace distribution `sandboxio-e2b`; rich outputs surfaced
  through `ExecResult.results` as `RichOutput(mime_type, data)` per Jupyter format;
  `STATEFUL_CODE` declared, every run owning a code context we can restart
- [x] PTY and pause/resume stay behind `.native` for v0.1
- [x] Native exception mapping with `__cause__`; `AuthError` names `E2B_API_KEY`
- [x] Nightly + release CI job, gated on the API key

Decisions taken here: a `list[str]` command is `shlex`-quoted into E2B's bash (the SDK
runs shell strings only); a timed-out or cancelled `run_code` restarts its code context,
the only way to stop a cell; a dropped stream the SDK reports as a timeout is checked
against `is_running()` and surfaces as `SandboxGone` when the lifetime ended; CPU and
memory come from the template, so `Resources(...)` is refused — the suite gained
`resource_caps_supported = False` for adapters like this.

What the abstraction did **not** need: no `Capability` widened, nothing pushed to `.native`
that the spec had not already put there.

**Expect to widen `Capability` or push things to `.native` here.** Never bend toward the
lowest common denominator ([ADR-0003](adr/0003-no-lowest-common-denominator.md)).

**Exit:** 100% of the suite for declared capabilities against the real service (73 s,
≈60 sandboxes); `tests/test_one_line_swap.py` runs the same downstream code on `fake://`,
`docker://` and `e2b://`. **Done.**

---

## Step 6 — Distribution surface (2 weeks)

- [x] `sandboxio doctor` (+ `--json`, credential names only, no paid calls; programmatic
  `sandboxio.doctor()` → `DoctorReport`), `sandboxio reap` (dry run by default; Docker lists
  stopped containers too; `--label`, `--kill`), `uvx sandboxio demo` (create · run · stream ·
  egress probe · teardown) — [spec/10](spec/10-cli.md). Console scripts `sandboxio` and the
  `sbx` alias; `python -m sandboxio`.
- [x] MCP server `python -m sandboxio.mcp` behind `sandboxio[mcp]`, six tools, one sandbox per
  process, config fixed at start; `docker/mcp/Dockerfile` (rootless, E2B backend, no socket)
  plus the Docker MCP Catalog `server.yaml`/`tools.json` ([spec/09](spec/09-integrations.md)).
  The release workflow pushes the image on every `v*` tag; the Docker MCP registry pull
  request stays manual.
- [x] LangGraph tool (`sandboxio[langgraph]`) and OpenAI Agents tool (`sandboxio[openai-agents]`),
  each a native tool object under 100 lines, tested against the fake
- [x] `sandboxio/otel.py` — GenAI semconv 1.37.0 `execute_tool` spans, zero-config, every
  attribute string in one file (a test greps for strays); `LoggingSink` and `FileSink`
  beside `NoopSink`/`QueueSink`; `sandboxio[otel]` extra for the API
- [x] Diátaxis docs: [`quickstart.md`](quickstart.md), [`how-to/`](how-to/README.md) (Docker with image
  prep and offline wheelhouse, E2B, offline testing, observability, CI, operations,
  integrations), [`explanation/`](explanation/README.md), the generated [`errors/`](errors/README.md),
  `llms.txt` + generated `llms-full.txt` (`scripts/gen_llms_full.py --check` is a gate), the
  paste-ready [`AGENTS.md` snippet](reference/agents-snippet.md)
- [x] The same Markdown published at `docs.sandboxio.dev` — MkDocs Material, GitHub Pages,
  strict build, `tests/test_docs_site.py` proving every `SBX_E` code resolves at the URL
  the exception prints ([ADR-0029](adr/0029-docs-site-mkdocs.md))
- [x] Copy-paste GitHub Actions workflow for users in [`how-to/ci.md`](how-to/ci.md): fake job
  on PRs, Docker job on `main`, leak check
- [x] `tests/test_readme_examples.py`: every README Python block is executed verbatim —
  scripts against fakes registered as `docker`/`e2b`, pytest-style blocks through pytester
- [x] [`examples/`](https://github.com/bit-agents/sandboxio/blob/main/examples/README.md): complete runnable programs — hello world, the
  one-line backend swap, streaming and timeouts, deny-by-default egress, a LangGraph agent
  and an OpenAI Agents one, and `sbx_fake` for the reader's own tools. `tests/test_examples.py`
  executes each script against the fakes; `examples/test_my_tool.py` is collected by pytest.

Decisions taken here: the CLI is stdlib `argparse` in core, not the Typer app spec/10 named,
because `uvx sandboxio demo` must run from the bare distribution and ADR-0004 forbids a new
base dependency; `rich` is used only for tracebacks under `SBX_DEBUG=1` when importable.
Exit codes are `0/1/2/130`; `doctor` exits `1` when an installed backend has a failing check.
`uvx sandboxio demo` on the bare distribution prints the install command **and** the
`uvx --from "sandboxio[docker]" sandboxio demo` form, since that is the stranger's next step.
`reap` talks to an optional `ReapableBackend` port (`list_managed`/`kill_managed`) and a
`ManagedSandbox` value object, both added to spec/01–02; every first-party backend
implements it. `AuditEvent` gained `code: str | None`, populated only with
`AuditConfig(capture_code=True)` and redacted; the JSON-line sinks render `as_dict()`.
Semconv has no sandbox vocabulary, so beyond `gen_ai.operation.name`/`gen_ai.tool.name` the
span attributes are `sandboxio.*`. `FakeBackend` now applies `NetworkPolicy` to recognised
network calls in `run_code` (`urllib.request.urlopen`, `requests.get`, …) so the demo's
egress probe is honest on `fake://`. Integrations live in core under
`sandboxio.integrations.*` with the framework behind an extra; the MCP server translates
`SandboxError` into the SDK's `ToolError` so the code and fix reach the model (the SDK hides
other exceptions). `SbxSandboxClient` stays v0.2.

**Exit:** every README example runs verbatim — the gate is `tests/test_readme_examples.py`
(six blocks) — and every program under [`examples/`](https://github.com/bit-agents/sandboxio/blob/main/examples/README.md) runs against the
fakes, the gate being `tests/test_examples.py`, which also fails on an example missing from
that index. Quickstart timing on this machine, fresh venv, cold `uv` cache, image already
pulled: `uvx --from ".[docker]" sandboxio demo` **6.1 s** end to end (the demo's own five
steps 2.5 s, create 1.3 s); `uvx --from . sandboxio demo` on the bare distribution 2.6 s to
the install hint. The MCP image builds and runs as uid 10001 with
`python -m sandboxio.mcp` as entrypoint; `0.1.0` pushed it, and the catalog PR stays manual.
Docker suite green including reap, zero containers left; E2B suite green including reap,
zero sandboxes left; 3.11 and 3.14 gates green. **Done.**

---

## v0.1 ship

**Scope: Docker + E2B + Fake. Modal moves to v0.1.1**
([ADR-0025](adr/0025-v01-scope-cut.md)). Two backends fully carry the "swap with one line"
narrative; three does not buy a better launch, it buys a later one. Docker↔E2B is also the
widest gap in the set, so it stresses the abstraction hardest.

Note: no v0.1 backend represents the `GVISOR` tier. The tier stays in the enum — it is a
property of the model, not of what shipped — but the docs must not imply Modal is available.

Launch narrative: *one secure Python API for running AI-agent code in any sandbox — swap
Docker↔E2B with one line; no network by default; test your agent tools offline with the
built-in fake.* Publish the MCP server to the Docker MCP Catalog the same day.

---

## v0.1.1 — Modal

GPU, Volumes with per-tenant `sub_path`, gVisor tier. Third backend also re-tests the
abstraction against a genuinely different filesystem model.

## v0.2

1. **Flight recorder + `sandboxio replay <trace>`** — record code, file diffs, stdio and timing to
   a portable trace; deterministic replay; local static HTML viewer.
2. **Egress learning mode** — `egress="learn"` records attempted domains, emits a
   paste-ready allowlist.
3. **Per-execution meter** — `{duration_ms, cost_usd?, backend}` on every result, plus
   `sandboxio bench`.
4. **Auto dependency inference** — PEP 723 / import parsing → uv provisioning, sandbox-gated.
5. Pre-execution security lint hook (advisory by default).
6. Pydantic AI + CrewAI adapters; OpenAI `SandboxClient` adapter.
7. MCP `search_docs`; adapter authoring guide + template repo; shell completions.
8. **Routing file** — `sandboxio-routing.yaml`, isolation classes and `route_for()`, already
   specified in [spec/07](spec/07-configuration.md#routing-file) and marked deferred there.
   It was written into the spec at design time and never scheduled; this is where it lands.

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
| 3 | — (Q6, Q7, Q9 decided) |
| 4 | — (Q8, Q10, Q11 decided) |
| 5 | Step 4 exit criteria, in full |
| 6 | — (all decided) |
