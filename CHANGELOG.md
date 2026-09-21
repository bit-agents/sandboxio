# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) over the surface named in
[spec/03](docs/spec/03-public-api.md#stability-contract).

Every absorbed provider break gets an entry here as well as in the
[churn-absorption log](docs/churn-log.md). How to write an entry is in
[CONTRIBUTING.md](CONTRIBUTING.md#changelog-entries).

## [Unreleased]

### Added

- Project skeleton: `uv` project, `src/` layout, `py.typed`, ruff, mypy strict, pyright strict.
- `examples/`: six runnable programs plus a worked `sbx_fake` test, each executed by CI
  (`tests/test_examples.py`) with the Docker and E2B backends swapped for the fake.
- CI gates, failing closed from commit one: import budget, no sockets at import, no eager
  third-party imports, wheel contents, doc-sample parsing, doc-link checking.
- `AGENTS.md` carrying the pinned decisions for coding agents.
- Core types with no behaviour: `Resources`, `NetworkPolicy`, `Capability`, `IsolationTier`
  with its explicit rank, `ExecResult`, `RichOutput`, `Meter`, `OutputChunk`, `FileInfo`.
- The error tree with stable `SBX_Ennnn` codes, hints and per-code docs pages generated into
  `docs/errors/`; `SandboxWarning` and its subclasses.
- Port protocols (`Backend`, `AsyncSandbox`, `Process`, `AsyncFileSystem`).
- Backend registry: `sandboxio.register()` plus lazy, cached `sandboxio.backends` entry points.
- `sandboxio.create()` / `connect()` with DSN parsing, typed `BackendConfig`, and
  `require_isolation` enforced before provisioning.
- `sandboxio.testing.suite.BackendContractSuite`, the normative adapter contract, and
  `sandboxio.testing.FakeBackend` with the `sbx_fake` pytest fixture and `fake://` DSN.
- Audit: `AuditConfig`, `AuditEvent`, `NoopSink`, `QueueSink`; one redacted operation record
  per operation. Shielded, bounded teardown with `SBX_TEARDOWN_GRACE`.
- Error codes `SBX_E1700` (`FileSystemError`) and `SBX_E1701` (`PathNotFound`).
- `sandboxio-docker`, the Docker adapter, installed by `sandboxio[docker]`: `network: none`
  by default, allowlists refused, `STATEFUL_CODE` off, a Ryuk-style reaper, and a
  provider-side lifetime backstop.
- The sync facade: `create_sync()`, `connect_sync()`, `sandboxio.sync.Sandbox` with a
  per-sandbox portal thread, and the CI parity test against the async protocols.
- `sandboxio-e2b`, the E2B adapter, installed by `sandboxio[e2b]`: `MICROVM` tier,
  deny-by-default egress with native allowlists, stateful code contexts, rich outputs.
- Audit sinks `LoggingSink` (stdlib logger, JSON lines) and `FileSink`;
  `AuditEvent.as_dict()`/`to_json()`; `AuditConfig(capture_code=True)` now populates
  `AuditEvent.code`, redacted.
- The `sandboxio` command (`sbx` alias, `python -m sandboxio`): `doctor` (+ `--json`,
  credential names only, no paid calls), `reap` (dry run by default, `--kill`, `--label`),
  `demo` (create, run, stream, prove egress is denied, tear down). Programmatic
  `sandboxio.doctor()` returning `DoctorReport`.
- `ReapableBackend` optional port with `list_managed()`/`kill_managed()` on every
  first-party backend, and the `ManagedSandbox` value object.
- `FakeBackend` applies `NetworkPolicy` to recognised network calls in `run_code`
  (`urllib.request.urlopen`, `requests.get`, …), the way it already did for `curl`.
- Docs: quickstart, how-to pages (Docker, E2B, offline testing, observability, CI,
  operations, integrations), explanation pages (isolation tiers, deny by default, error
  codes), the paste-ready `AGENTS.md` snippet, `llms.txt` + generated `llms-full.txt`, and
  the gate that runs every README Python block verbatim.
- `sandboxio.integrations.langgraph` and `sandboxio.integrations.openai_agents`
  (`make_code_tool`, `make_command_tool`) behind `sandboxio[langgraph]` and
  `sandboxio[openai-agents]`.
- The MCP server `python -m sandboxio.mcp` behind `sandboxio[mcp]`, its Dockerfile and the
  Docker MCP Catalog metadata under `docker/mcp/`.
- OTel rendering of the operation record in `sandboxio.otel`: GenAI semconv **1.37.0**
  `execute_tool` spans nesting under the caller's span, opt-in `sandboxio[otel]` extra for
  the API, no-op without a configured tracer provider.
- A documentation site built from `docs/` with MkDocs Material, published at
  `docs.sandboxio.dev`. The Markdown stays the source.
- [The version policy](docs/explanation/version-policy.md): what counts as breaking, how long
  a deprecation lives, and why the verdict can differ for callers and adapter authors.
- [Why sandboxio and not something else](docs/explanation/comparisons.md): when a provider
  SDK, a framework's sandbox layer or plain Docker is the better choice, and when not to use
  this at all.
- [Troubleshooting](docs/how-to/troubleshooting.md): diagnosis by symptom rather than by
  error code — the deny-egress failure that surfaces inside your own process, the three
  different timeouts, why a failed command does not raise, and leaked containers.
- [The security model](docs/explanation/security-model.md): the threat model in and out of
  scope, the five defaults, the tier decision table, and what the project does not claim.
- [FAQ](docs/faq.md): the questions a newcomer asks first, each answered short with a link
  to the long version.

### Changed

- **Breaking:** `sandboxio[openai-agents]` now requires `openai-agents>=0.19` and
  `sandboxio[mcp]` requires `mcp>=2.0`. The previous bounds (`>=0.1`, `>=1.2`) were never
  tested: the integration tests fail below 0.19 and hang on `mcp` 1.2. Nothing is released,
  so no installed version changes.

### Fixed

- `CapabilityNotSupported` names the backends that do support the capability. It previously
  fell back to a generic "check `capabilities`" hint at every raise site but one.
- A credential-shaped DSN parameter is refused with the variable to export — `E2B_API_KEY`
  for `e2b://` — rather than a description of one.
- `create("modal://…")` reports a backend planned for v0.1.1. It previously offered
  `uv pip install "sandboxio[modal]"`, an extra that does not exist, so the suggested fix
  failed.

Nothing is released. There is no public API yet — see
[docs/build-order.md](docs/build-order.md).
