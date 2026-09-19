# ADR-0019 — Streaming returns a `Process` context manager, not a bare iterator

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q6](../open-questions.md#q6--stream-loses-stderr-and-exit-code)
**Related:** [ADR-0003](0003-no-lowest-common-denominator.md), [ADR-0007](0007-contract-suite-as-spec.md)
**Depends on:** [ADR-0020](0020-cancellation-semantics.md) for teardown semantics

## Context

The input design specified `def stream(self, cmd, **kw) -> AsyncIterator[bytes]`. That
loses the stdout/stderr separation `ExecResult` provides, has nowhere to put an exit code,
and carries a `**kwargs` black hole the API rules forbid.

The decisive constraint is neither of those. **Breaking out of an `async for` does not
close the iterator.** An abandoned async generator is finalized by the event loop's
asyncgen hooks or by GC, at an unpredictable time. For a local generator that is untidy;
for a handle on a remote sandbox process it is a leaked, billing sandbox
([hazard H2](../hazards.md#h2--leaked-sandboxes)). The requirement that abandoning a stream
terminates the remote process therefore rules out a bare `AsyncIterator`, whatever it
yields.

Prior art makes resource lifetime explicit rather than implicit: `anyio.abc.Process`
extends `AsyncResource` — an async context manager — alongside `wait()`, `terminate()`,
`kill()` and `returncode`; `httpx` requires `async with client.stream(...) as response`.

`anyio`'s separate `.stdout` / `.stderr` byte streams were considered and rejected:
consuming two streams needs a task group, and draining one before the other stalls when the
other's buffer fills. That is the classic subprocess deadlock, and the wrong default for
the common case of streaming output to a log.

## Decision

`stream()` returns a **`Process`**: an async context manager that iterates tagged chunks.

```python
@dataclass(frozen=True)
class OutputChunk:
    stream: Literal["stdout", "stderr"]
    data: bytes

async with sb.stream(["pytest", "-q"], timeout=300) as proc:
    async for chunk in proc:
        log.write(chunk.data)
    res = await proc.wait()        # ExecResult, exit_code populated
```

- **`stream()` is a plain function, not a coroutine**, and the returned object is not
  awaitable. Forgetting `async with` fails immediately and obviously instead of leaking
  quietly. The process starts on `__aenter__`.
- **`__aexit__` terminates the process if it is still running** — whether iteration
  completed, the caller broke early, an exception propagated, or the task was cancelled.
  Shielding and grace period per [ADR-0020](0020-cancellation-semantics.md).
- **Ordering is guaranteed within each stream, not between them.** Two pipes cannot be
  globally ordered, and claiming otherwise would be a lie the contract suite could not test.
- `wait()` returns the terminal `ExecResult`. It is idempotent; calling it with output still
  unconsumed drains and **discards** the remainder.
- Missing `Capability.STREAMING` raises `CapabilityNotSupported` from `stream()` itself,
  before the context is entered.
- Typed keyword arguments only — the same `timeout` and `env` as `run()`. No `**kwargs`.

### `ExecResult.streamed`

`ExecResult` gains `streamed: bool = False`. When true, `stdout` and `stderr` are **empty
by construction**: streaming exists precisely to avoid buffering the whole output, and the
caller already took delivery of the bytes. An empty string that silently means "consumed
elsewhere" is a 2am bug, so the flag makes it explicit rather than leaving it to
documentation.

### `stream_code` deferred

Streaming an interpreter — stdout, stderr and rich outputs as they arrive — is arguably
more valuable to agents than streaming shell commands, and E2B supports it. It is deferred:
`Process` is defined so it can carry rich outputs later, and `stream_code` lands when a
second backend supports it, per the two-backend promotion rule in
[ADR-0003](0003-no-lowest-common-denominator.md). Until then it is reachable through
`.native`.

## Consequences

- Callers must remember `async with`. This is the cost, and it is paid deliberately; the
  non-awaitable return makes the mistake loud rather than silent.
- `Process` finally has an interface, closing a gap where the domain model named an entity
  the ports never defined.
- Streaming and buffered execution now return visibly different `ExecResult`s. Code that
  treats the two interchangeably will notice via `streamed`, which is the intent.
- The contract suite gains cases that are genuinely awkward to write — break-early,
  raise-inside, cancel-inside — and they are the ones that matter. An adapter that passes
  them cannot leak a process through the streaming path.
- Rejecting split `.stdout`/`.stderr` readers means an advanced caller who really wants
  independent backpressure per stream has to use `.native`. Acceptable: that caller exists
  far less often than the one who deadlocks on it.
