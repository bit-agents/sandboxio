# Architecture Decision Records

One file per decision. Format: Context → Decision → Consequences. Immutable once Accepted —
a reversal is a **new** ADR that supersedes the old one, which is then marked `Superseded by
ADR-nnnn` rather than edited. A later ADR that narrows part of an earlier one without
reversing it is an **amendment**: the earlier ADR keeps its status and gains an
`Amended by` pointer, so the record stays navigable without being rewritten.

**Status values:** `Proposed` · `Accepted` · `Superseded by ADR-nnnn` · `Deprecated`

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-ports-and-adapters.md) | Ports and adapters (hexagonal) architecture | Accepted |
| [0002](0002-async-first-anyio.md) | Async-first core on anyio; sync facade derived | Accepted |
| [0003](0003-no-lowest-common-denominator.md) | No lowest common denominator: capabilities + `.native` | Accepted |
| [0004](0004-thin-core-lazy-adapters.md) | Thin core; adapters behind extras, lazily imported | Accepted |
| [0005](0005-secure-by-default.md) | Secure by default, enforced in v0.1 | Accepted |
| [0006](0006-isolation-tiers-first-class.md) | Isolation tier is a first-class, reported property | Accepted |
| [0007](0007-contract-suite-as-spec.md) | The contract suite is the adapter specification | Accepted |
| [0008](0008-dsn-and-typed-config.md) | Dual configuration: DSN strings and typed config objects | Accepted |
| [0009](0009-library-first-server-later.md) | Library first; MCP is the first server; `sandboxio-server` is gated | Accepted |
| [0010](0010-stable-error-codes.md) | Error codes are public, semver-covered API | Accepted |
| [0011](0011-otel-mapping-layer.md) | OTel GenAI semconv isolated behind one mapping module | Accepted |
| [0012](0012-no-telemetry-no-import-side-effects.md) | No telemetry, no import side effects | Accepted |
| [0013](0013-complement-openai-sandboxclient.md) | Complement OpenAI's `SandboxClient`, do not compete with it | Accepted |
| [0014](0014-project-name.md) | Project name: `sandboxio`, short code `SBX` | Accepted |
| [0015](0015-python-version-floor.md) | Python floor 3.11; develop on 3.14 | Accepted |
| [0016](0016-license-mit.md) | MIT license; DCO for contributions | Accepted |
| [0017](0017-timeout-error-naming.md) | `SandboxTimeout` does not inherit the builtin; timeouts split by phase | Accepted |
| [0018](0018-isolation-tier-ordering.md) | `IsolationTier` ordering via an explicit rank; `UNKNOWN` is the default | Accepted |
| [0019](0019-streaming-process-handle.md) | Streaming returns a `Process` context manager, not a bare iterator | Accepted |
| [0020](0020-cancellation-semantics.md) | Shielded teardown with a bounded grace; the mandatory timeout is the backstop | Accepted |
| [0021](0021-observability-record.md) | One operation record, three renderings; no inline cost | Accepted |
| [0022](0022-sync-facade.md) | Hand-written sync facade over a per-sandbox portal, with a parity test | Accepted |
| [0023](0023-docker-network-and-dependencies.md) | Docker cannot filter egress; dependencies come from images or wheelhouses | Accepted |
| [0024](0024-stateful-code-on-docker.md) | Docker declares `STATEFUL_CODE` off in v0.1 | Accepted |
| [0025](0025-v01-scope-cut.md) | v0.1 ships Docker + E2B + Fake; Modal moves to v0.1.1 | Accepted |
| [0026](0026-docs-license-cc-by.md) | Documentation under CC BY 4.0; code stays MIT | Accepted |

Decisions not yet made live in [`../open-questions.md`](../open-questions.md) and graduate
to an ADR here when settled.
