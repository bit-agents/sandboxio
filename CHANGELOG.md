# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) over the surface named in
[spec/03](docs/spec/03-public-api.md#stability-contract).

Every absorbed provider break gets an entry here as well as in the churn-absorption log.

## [Unreleased]

### Added

- Project skeleton: `uv` project, `src/` layout, `py.typed`, ruff, mypy strict, pyright strict.
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

Nothing is released. There is no public API yet — see
[docs/build-order.md](docs/build-order.md).
