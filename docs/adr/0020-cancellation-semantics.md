# ADR-0020 — Shielded teardown with a bounded grace; the mandatory timeout is the backstop

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q7](../open-questions.md#q7--cancellation-semantics)
**Related:** [ADR-0002](0002-async-first-anyio.md), [ADR-0005](0005-secure-by-default.md), [ADR-0019](0019-streaming-process-handle.md)

## Context

The input set has no prose on cancellation at all, yet it is behind the most expensive
failure mode in the project ([hazard H2](../hazards.md#h2--leaked-sandboxes)): an orphaned
cloud sandbox bills until something reclaims it.

Under structured concurrency, cancellation propagates into the adapter's own awaits, so the
obvious implementation does nothing:

```python
async with await sandboxio.create() as sb:   # __aexit__ does: await sb.kill()
    await sb.run(agent_code)                 # ← task cancelled here
```

`__aexit__` runs, but `await sb.kill()` hits its first checkpoint inside the still-active
cancel scope and re-raises immediately. A naive `finally: await sb.kill()` is decorative.
anyio provides the fix directly: `move_on_after(delay, shield=True)` is a bounded scope that
external cancellation cannot interrupt.

The reframing that decided the design: **`create(timeout=...)` is already mandatory**
([ADR-0005](0005-secure-by-default.md)) and cannot be cancelled away, because it is enforced
provider-side. That TTL *is* the backstop — it bounds the worst-case orphan no matter what
else fails. The mandatory timeout was specified as a security control; it is equally a
cost-control one.

A background-reaper design was considered and rejected: it requires a detached task with no
owner, which is the global-mutable-state anti-pattern
([ADR-0012](0012-no-telemetry-no-import-side-effects.md)) and has nowhere legitimate to live
under structured concurrency.

## Decision

**Shielded teardown with a bounded grace, backed by the provider-side timeout.**

```python
with anyio.move_on_after(TEARDOWN_GRACE, shield=True):
    await self._kill()
```

- **`TEARDOWN_GRACE` defaults to 5 seconds**, overridable by `SBX_TEARDOWN_GRACE`. It is
  not a `create()` parameter — the signature stays tight. Five seconds covers one API call
  generously while keeping Ctrl-C tolerable. Sandboxes in a task group tear down
  concurrently, each in its own shielded scope, so the wall-clock cost is about one grace
  period, not one per sandbox.
- **Cancellation kills the remote process.** Detach-on-cancel is a real use case for long
  agent runs whose client disconnects, but it needs a second backend proving reconnect
  before it becomes typed API. Deferred, per the two-backend promotion rule
  ([ADR-0003](0003-no-lowest-common-denominator.md)); reachable meanwhile through `.native`.
- **If the grace expires, emit `OrphanedSandboxWarning`** naming the sandbox id, backend and
  `metadata` labels, so an operator can reap it. Silence here is the worst outcome. It and
  `UnverifiedIsolationWarning` share a `SandboxWarning` base.
- **Labels plus `sandboxio reap` are the operator-facing backstop** for what still slips
  through — `metadata` is propagated to provider-native labels, which is what makes orphans
  findable at all.

### Three rules that hold regardless

1. **Cancellation propagates as cancellation.** `CancelledError` /
   `anyio.get_cancelled_exc_class()` MUST NOT be wrapped in a `SandboxError`. A library that
   swallows cancellation breaks every task group above it. `except BaseException` in an
   adapter is a bug.
2. **Partial creation gets a narrow shield.** Cancelled between "the provider returned an
   id" and "the handle owns it", nothing owns the sandbox. Shield **that window only** —
   never the whole `create()`, which can legitimately take tens of seconds.
3. **`kill()` must be safe to call from inside a shielded scope**, must be idempotent, and
   must not block indefinitely.

`Process.__aexit__` follows the same rules ([ADR-0019](0019-streaming-process-handle.md)).

## Consequences

- Cancelling a run now costs up to 5 seconds. That is the price of not leaking, and it is
  visible rather than hidden; the env override exists for callers who disagree.
- Shielding is sometimes considered an anti-pattern. It is used here in the one place it is
  warranted — releasing a remote resource — and it is bounded, so it can never make a
  program unkillable.
- We ship no background tasks and hold no global state, which keeps the "quiet library"
  promise intact.
- The contract suite gains the hardest tests in the project: cancel mid-`run`, mid-`create`
  and mid-stream, each asserting no orphan survives, plus an assertion that cancellation
  surfaces as cancellation and not as a `SandboxError`. The fake backend must simulate all
  of them, including grace expiry.
- Worst case remains a leak for the length of the sandbox timeout — 300 s by default. That
  is the floor this design can reach without background tasks, and it is why the mandatory
  timeout is non-negotiable.
- `sandboxio reap` becomes part of the CLI contract, not a nice-to-have.
