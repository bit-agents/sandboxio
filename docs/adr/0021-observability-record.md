# ADR-0021 — One operation record, three renderings; no inline cost

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q9](../open-questions.md#q9--one-event-three-sinks-audit--otel--meter)
**Related:** [ADR-0011](0011-otel-mapping-layer.md), [ADR-0005](0005-secure-by-default.md), [ADR-0020](0020-cancellation-semantics.md)

## Context

Audit events, OTel span attributes and `ExecResult.meter` carry overlapping fields. Emitted
independently they drift, and the redaction rule — secrets never reach logs, exceptions,
reprs, spans or audit events — would have to be implemented and tested once per sink.

Three questions were open under that heading.

**Is `cost_usd` knowable at execution time?** Both SDKs were installed and inspected:

- **E2B exposes no cost surface.** Four occurrences of `cost` in the package: one comment
  about buffering, three MCP tool descriptions about *AWS* billing.
- **Modal has real billing, but post-hoc and account-level.**
  `workspace_billing_report(start, end, resolution="d", tag_names=[...])` returns
  `object_id, description, environment_name, interval_start, cost: Decimal, tags`.
  `modal/sandbox.pyi` has no cost or usage attribute. Attribution is per *object*, default
  resolution is **daily**, and the docstring warns the resource breakdown changes as
  Modal's billing model evolves.

So per-execution cost does not exist at execution time. An inline `cost_usd` could only be
a client-side estimate from a price table we maintain — a second churn surface where prices
change with no SDK release to trip the canary, and wrong by construction under committed-use
or negotiated pricing.

What Modal *does* offer is `tag_names`, which is exactly the `metadata` labels
[spec/05](../spec/05-security-policy.md#tenancy) already requires propagating.

**Record lifecycle and sink behaviour** were also unspecified. OTel spans are inherently
open/close; audit events are inherently completed facts. And the existing rule that a
*failing* sink must not fail the operation said nothing about a *slow* one, which silently
adds latency to every execution.

## Decision

### One record, opened and closed

An internal mutable `_OperationRecord` is opened when an operation starts and closed when it
finishes. Redaction is applied **once**, at close, before anything is rendered.

```
open  → OTel span started (live)
close → redact → ├── AuditEvent (frozen)  → sink(s)
                 ├── span attributes + end
                 └── Meter                → ExecResult.meter
```

A live span matters for the debugging story: a ten-minute execution must be visible in a
trace viewer while it runs, not only after it ends. Progress checkpoints for long streams
are deferred until someone asks.

### No inline cost

`Meter` carries `duration_ms` and `backend`. **No `cost_usd`, no `cost_is_estimate`** — the
latter was solving a problem we chose not to create.

Cost ships instead as **capability-gated post-hoc reconciliation**: a new
`Capability.COST_REPORTING`, a backend-level `costs(since, until, labels)` returning
`CostEntry` rows with `Decimal` amounts, and a v0.2 `sandboxio costs` command that queries
by our `metadata` labels. Modal supports it; E2B raises `CapabilityNotSupported` until it
does.

### Sinks

```python
class AuditSink(Protocol):
    async def emit(self, event: AuditEvent) -> None: ...
```

- `emit` **MUST return promptly**; buffering is the sink's responsibility, as with
  `logging.Handler`.
- It is awaited **inline**, bounded by `SBX_AUDIT_TIMEOUT` (default 5 s). We own no
  background drain task — the same reasoning that rejected a background reaper in
  [ADR-0020](0020-cancellation-semantics.md).
- Failure or timeout is governed by **`on_sink_failure: "warn" | "fail"`**, default `warn`.
  `fail` raises `AuditSinkError` (`SBX_E1601`) and fails the operation. The default suits
  most users; the option exists because for a regulated buyer an unrecorded operation may be
  one that should not have happened.
- Shipped sinks: no-op (default), stdlib-logging JSON lines, file, and **`QueueSink`** — a
  bounded wrapper whose `emit` enqueues instantly and whose `drain()` coroutine the **host**
  runs in its own task group. Overflow drops oldest and warns.

## Consequences

- The input set pitched the inline cost meter as a differentiator — *"no sandbox competitor
  does it."* The reason no one does it is that the data is not there. We lose a marketing
  line and avoid a maintenance liability that would have produced confidently wrong numbers.
- Post-hoc reconciliation is arguably the better product: per-tenant spend attribution is
  what the compliance buyer actually asks for, and it reuses labels we already mandate.
- Cost accuracy now depends on labels being propagated correctly, which raises the stakes on
  that requirement — it is already a contract-suite row.
- Adding `on_sink_failure: "fail"` means audit can now break execution. That is the point,
  but it must be opt-in and loudly documented, and `AuditSinkError` needs its own docs page.
- `QueueSink` pushes task ownership onto the host. That is more work for the user than a
  background thread would be, and it is the honest trade for a library that holds no global
  state.
- One redaction point makes "no secret reaches any sink" a single testable claim, which was
  the original motivation.
