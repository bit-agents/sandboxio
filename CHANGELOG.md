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

Nothing is released. There is no public API yet — see
[docs/build-order.md](docs/build-order.md).
