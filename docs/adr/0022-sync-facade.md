# ADR-0022 — Hand-written sync facade over a per-sandbox portal, with a parity test

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q8](../open-questions.md#q8--sync-facade-mechanism)
**Related:** [ADR-0002](0002-async-first-anyio.md), [ADR-0019](0019-streaming-process-handle.md), [ADR-0012](0012-no-telemetry-no-import-side-effects.md)

## Context

[ADR-0002](0002-async-first-anyio.md) says adapters implement async only and the sync facade
is "generated" via an anyio blocking portal — ambiguous between build-time codegen and a
runtime wrapper, and the choice affects typing fidelity, wheel contents and traceback
quality.

**Codegen does not avoid the portal.** `unasync`-style generation works when the generated
sync code calls *sync* libraries — httpcore emits a sync transport over sync sockets. Our
adapters are async-only, so any generated sync method still crosses a portal at runtime.
Codegen therefore decides *where the delegating wrapper lives*, not *whether one exists*.

That leaves the real question: where the wrapper lives, and how the types stay honest.

| Option | Types honest, no drift | Build machinery | Traceback |
|--------|------------------------|-----------------|-----------|
| Generated class, committed, CI-diffed | yes | AST generator + check | good |
| Runtime `__getattr__` proxy + `.pyi` | **stubs drift silently** | none | portal frames, opaque |
| **Hand-written thin class** | yes, if parity-tested | none | **best** |
| No sync facade | n/a | none | n/a |

A runtime proxy is opaque to pyright until stubbed, and stub drift is exactly the failure
`py.typed` exists to prevent. Omitting the facade entirely was rejected: E2B and Daytona
both ship dual APIs, and the "drop into your existing stack" pitch includes sync Django,
Flask and Celery codebases.

anyio supplies the primitives directly — `start_blocking_portal`, `portal.call()`, and
`portal.wrap_async_context_manager()`, which is precisely the `async with sb` → `with sb`
mapping. None of that is ours to invent.

## Decision

**A hand-written thin sync facade, with a CI-enforced parity test.**

- The sync surface (~30 members across `Sandbox`, `FileSystem`, `Process`, `Backend`) is
  written by hand as delegating methods. No codegen, no build step, no stubs.
- **A parity test introspects the async protocols** and asserts every public async member
  has a sync counterpart whose `inspect.signature` matches once coroutine-ness is
  discounted. This is what removes the drift objection; it is also the test that would have
  been needed to validate generated stubs anyway. For a surface this size, a generator costs
  more than it saves.
- **The portal is per-sandbox.** The sync `Sandbox` owns a `BlockingPortal` for its
  lifetime: `create_sync()` starts it, `__exit__` / `close()` stops it. Per-call portals
  spawn a thread per call; a shared module-level portal is global mutable state
  ([ADR-0012](0012-no-telemetry-no-import-side-effects.md)).
- **Sync streaming is offered**, and its cost is documented: every `OutputChunk` crosses the
  portal, so each chunk is a thread round-trip. Omitting it would make the sync facade
  visibly second-class; hiding the cost would be worse.
- Errors raised through the facade MUST be the same classes with `__cause__` intact
  ([spec/03](../spec/03-public-api.md#sync-facade)). Portal frames appear in the traceback;
  that is acceptable and documented.

This supersedes the parenthetical lean in [ADR-0002](0002-async-first-anyio.md) toward a
runtime wrapper with generated stubs, which predated the codegen-still-needs-a-portal point.

## Consequences

- **N sync sandboxes means N threads.** Documented plainly, with the async API named as the
  answer for heavy concurrency. This is the main cost of the design and it must not be
  buried.
- Adding a public async method without its sync counterpart fails CI rather than shipping a
  half-facade. That is the whole value of the parity test.
- Hand-written delegation is more lines than a proxy, but they are trivial lines, and they
  are real code that IDEs, pyright and tracebacks all understand.
- Sync streaming will be measurably slower than async streaming. Acceptable: a caller
  streaming tens of thousands of chunks synchronously has chosen the wrong API, and the docs
  say so.
- If the surface grows substantially, generating the delegating class becomes the better
  trade. The parity test is the migration safety net either way, so that switch stays cheap.
