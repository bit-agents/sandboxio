# ADR-0027 — Blocking adapters get their own thread budget, not anyio's

**Status:** Accepted
**Date:** 2026-09-20
**Related:** [ADR-0002](0002-async-first-anyio.md) — async-first on anyio · [ADR-0019](0019-streaming-process-handle.md) — the streaming handle whose consumer parks a worker

## Context

docker-py is synchronous, so every call in the Docker adapter goes through
`anyio.to_thread.run_sync`. Without a `limiter` argument that draws on anyio's **default**
thread limiter — a single process-wide pool, default 40 workers, shared with every other
library the host application runs and with anything the host offloads itself.

Most of those calls are short. One is not: `DockerProcess.__aiter__` consumes the pump
thread's queue with a blocking `get()`, so a streamed exec **parks one worker for the whole
duration of the command**, not per chunk. Forty concurrent streams empty the default pool.
What starves is not only sandboxio — it is the host's own `to_thread` calls, and the sync
facade's portal work behind them ([ADR-0022](0022-sync-facade.md)).

The alternative considered was removing the blocking `queue.get()` and feeding chunks into
an anyio memory object stream instead. The pump is a raw `threading.Thread`, so that needs
a `BlockingPortal` to reach the event loop, which is a larger rework of the streaming path
than the starvation it fixes.

## Decision

We will give the Docker adapter its own `anyio.CapacityLimiter` and pass it to every
`to_thread.run_sync` call, so its blocking work never draws on the default pool.

- Default **64** workers, overridable by **`SBX_DOCKER_THREADS`**. A value that is not a
  positive integer warns (`SandboxWarning`) and falls back to the default.
- The limiter is held in an `anyio.lowlevel.RunVar`, one per event loop, created on first
  use. A `CapacityLimiter` is bound to the loop that made it, and the sync facade runs a
  portal per sandbox, so a module-level singleton would be wrong.
- This is an internal budget, not public API. No `BackendConfig` field, no DSN parameter.
- We are **not** deciding anything about buffered output size here. `run()` and
  `read()` still buffer without a cap; that is a separate question with a user-visible
  answer.

A future adapter that wraps a synchronous SDK follows the same pattern with its own
limiter and its own `SBX_<BACKEND>_THREADS` variable.

## Consequences

The concurrent-stream ceiling becomes explicit and tunable, and it rises from "whatever is
left of anyio's 40 after the host took its share" to a documented 64 that nothing else
competes for. Host applications stop being collateral damage of sandbox concurrency.

The cost: 64 OS threads is a real resource, and a host running several `DockerBackend`
instances across several event loops gets one budget each rather than one overall. We
accept that — the budgets are per loop because the primitive is, and a process with many
loops already pays for many thread pools.

Teardown is not exempt from the budget. A `kill()` still needs a worker, so a fully
saturated limiter delays it; `_kill_processes` is already bounded by `move_on_after(15)`
and degrades to `OrphanedSandboxWarning` rather than hanging. The risk is strictly lower
than before, because the budget is larger and uncontended.
