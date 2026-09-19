# ADR-0002 — Async-first core on anyio; sync facade derived

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0001](0001-ports-and-adapters.md)
**Open questions:** [Q8 facade mechanism](../open-questions.md#q8--sync-facade-mechanism)
**Related:** [ADR-0020](0020-cancellation-semantics.md) — cancellation and teardown semantics

## Context

Agent workloads are I/O-bound and concurrent: many sandboxes, long-running executions,
streamed output. Every target backend ships an async SDK. E2B and Daytona both expose dual
sync/async APIs, which users now expect.

Hand-maintaining two implementations per adapter doubles the surface that provider churn can
break, and the two copies drift. anyio additionally buys trio compatibility and — more
importantly here — structured concurrency and cancel scopes, which is the only sane way to
guarantee teardown of a remote resource.

## Decision

We will make the core async-first on **anyio**:

- **Adapters implement async only.** A sync adapter implementation is not a supported thing.
- The sync facade is **derived**, not written twice, via an anyio blocking portal. The exact
  mechanism — build-time codegen, runtime wrapper with generated stubs, or hand-written thin
  class — is [Q8](../open-questions.md#q8--sync-facade-mechanism).
- Sync entry is **explicit** (`create_sync`). We reject context auto-detection that returns
  different types from one call site: it defeats type checkers and violates one-obvious-way.
- Cancellation and teardown semantics are part of the port contract, not adapter discretion,
  and are proven by the contract suite. Defined in [ADR-0020](0020-cancellation-semantics.md).

## Consequences

- Sync users pay a thread-portal hop. Acceptable: sandbox operations are network-bound and
  measured in hundreds of milliseconds at best.
- anyio is a real base dependency, in tension with "near-zero deps"
  ([ADR-0004](0004-thin-core-lazy-adapters.md)). We accept it: it is small, pure-Python,
  import-cheap, and the structured-concurrency guarantees are load-bearing for
  guaranteed teardown.
- Tracebacks crossing the portal are worse than native ones. The facade must not swallow
  `__cause__`, and the contract suite checks error identity through the sync path too.
- Any adapter that blocks the event loop (a sync provider SDK called directly) is a bug, not
  a style issue. Adapters wrapping sync SDKs must go through `anyio.to_thread`.
