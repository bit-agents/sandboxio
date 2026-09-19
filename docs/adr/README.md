# Architecture Decision Records

One file per decision. Format: Context → Decision → Consequences. Immutable once Accepted —
a reversal is a **new** ADR that supersedes the old one, which is then marked `Superseded by
ADR-nnnn` rather than edited.

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

Decisions not yet made live in [`../open-questions.md`](../open-questions.md) and graduate
to an ADR here when settled.
