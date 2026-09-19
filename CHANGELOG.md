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

Nothing is released. There is no public API yet — see
[docs/build-order.md](docs/build-order.md).
