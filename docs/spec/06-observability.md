# 06 — Observability

Three surfaces — audit, tracing, metering — MUST be three renderings of **one** internal
record. See [ADR-0011](../adr/0011-otel-mapping-layer.md) and
[Q9](../open-questions.md#q9--one-event-three-sinks-audit--otel--meter).

## The operation record

Every `run`, `run_code`, stream and file operation produces exactly one internal record.
Redaction is applied **once, upstream of all sinks**, so "no secret reaches any sink" is a
single testable claim.

```
record → redact → ├── audit sink(s)      (AuditEvent)
                  ├── OTel span          (sandboxio/otel.py attribute mapping)
                  └── ExecResult.meter   (v0.2)
```

Adding a field means one change in three renderers, not three independent changes.

## Audit

```python
@dataclass(frozen=True)
class AuditEvent:
    ts: datetime
    event: str                      # "exec" | "run_code" | "file_read" | "file_write" | ...
    sandbox_id: str
    backend: str
    isolation: IsolationTier
    tenant_id: str | None           # from metadata
    session_id: str | None          # from metadata
    code_sha256: str
    argv: list[str] | None
    exit_code: int | None
    duration_ms: int
    bytes_in: int
    bytes_out: int
    network_denials: int            # blocked egress attempts, where the backend reports them
```

Sinks are configured per backend instance through `AuditConfig(sinks=..., on_sink_failure=...,
capture_code=...)`, passed to the adapter's constructor — never through global state.

### Sink protocol

```python
class AuditSink(Protocol):
    async def emit(self, event: AuditEvent) -> None: ...
```

- `emit` **MUST return promptly.** Buffering is the sink's responsibility, as with
  `logging.Handler`. A sink that blocks on network I/O adds latency to every execution.
- It is awaited **inline**, bounded by `SBX_AUDIT_TIMEOUT` (default 5 s). sandboxio owns no
  background drain task ([ADR-0020](../adr/0020-cancellation-semantics.md)).
- Failure or timeout is governed by **`on_sink_failure`**:
  - `"warn"` (default) — emit `AuditSinkWarning`, the operation proceeds.
  - `"fail"` — raise `AuditSinkError` (`SBX_E1601`); the operation fails. For a regulated
    buyer, an unrecorded operation may be one that should not have happened.
- Shipped sinks: **no-op (default)**, stdlib-logging JSON lines, file, and **`QueueSink`** —
  a bounded wrapper whose `emit` enqueues instantly and whose `drain()` coroutine the
  **host application** runs in its own task group. Overflow drops oldest and warns.
- Code is **hashed by default**; full-code capture is opt-in.
- Secrets and env values MUST NOT appear in an event, ever, including in `argv`.

## Tracing

- Sandbox operations map to OTel GenAI `execute_tool` spans, nesting under the caller's
  `invoke_agent` span.
- Attributes: backend, isolation tier, sandbox id, exit code, duration, bytes in/out.
- Content capture (code, file contents) is **opt-in**, per the spec's privacy modes.
  Secrets are never captured at any setting.
- **All attribute strings live in `sandboxio/otel.py`.** No other module writes an attribute name.
  The targeted semconv version is pinned and documented; a bump is a changelog entry.
- Zero-config: participate if the host app configured a tracer provider, no-op otherwise.
  sandboxio MUST NOT install exporters or start providers.

## Metering (v0.2)

```python
@dataclass(frozen=True)
class Meter:
    duration_ms: int
    backend: str
```

**There is no `cost_usd`.** Per-execution cost does not exist at execution time on either
backend: E2B's SDK exposes no cost surface at all, and Modal's billing is a post-hoc,
account-level `workspace_billing_report(start, end, resolution="d", tag_names=[...])`
attributed per object, not per execution. An inline figure could only be a client-side
estimate from a price table we maintain — a churn surface with no SDK release to trip the
canary, and wrong under committed-use pricing
([ADR-0021](../adr/0021-observability-record.md)).

### Cost reconciliation (capability-gated, v0.2)

Cost ships as post-hoc attribution instead, using the `metadata` labels that
[05](05-security-policy.md#tenancy) already requires be propagated to provider-native
labels.

```python
@dataclass(frozen=True)
class CostEntry:
    object_id: str
    description: str
    interval_start: datetime
    cost_usd: Decimal            # Decimal, never float
    labels: dict[str, str]

# Backend-level, requires Capability.COST_REPORTING
async def costs(self, *, since: datetime, until: datetime | None = None,
                labels: dict[str, str] | None = None) -> list[CostEntry]: ...
```

- Requires `Capability.COST_REPORTING`; otherwise `CapabilityNotSupported`. Modal supports
  it, E2B does not.
- Amounts MUST be `Decimal`. Money is never a float.
- Resolution is the provider's, not ours, and MUST be reported rather than interpolated —
  Modal's default is daily.
- Surfaced as `sandboxio costs --since ... --label tenant_id=...` ([10](10-cli.md)).

## Redaction

Applied once, before any sink, to:

- everything in `secrets=`, by value, wherever it appears;
- credential-shaped environment values;
- anything the caller marks sensitive.

Redaction MUST cover: log records, exception messages and `__notes__`, `__repr__` output,
audit events, span attributes, and CLI output.

## Debugging

- `SBX_DEBUG=1` or `debug=True` raises verbosity via structured logging. Nothing else does.
- Library logger uses `NullHandler`. The library MUST NOT print.
- High-quality `__repr__` everywhere:
  `<Sandbox e2b:i8x3… microvm running caps=RUN_CODE|FILESYSTEM>`.
