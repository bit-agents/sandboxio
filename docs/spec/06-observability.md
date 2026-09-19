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
                  ├── OTel span          (sbx/otel.py attribute mapping)
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

- Sink protocol: `async def emit(event: AuditEvent) -> None`.
- Ship three sinks: stdlib-logging (JSON lines), file, no-op. Default is no-op — the library
  is quiet unless asked ([ADR-0012](../adr/0012-no-telemetry-no-import-side-effects.md)).
- Code is **hashed by default**; full-code capture is opt-in.
- Secrets and env values MUST NOT appear in an event, ever, including in `argv`.
- A failing sink MUST NOT fail the operation; it MUST be reported through the library
  logger. Auditing is not a correctness dependency of execution.

## Tracing

- Sandbox operations map to OTel GenAI `execute_tool` spans, nesting under the caller's
  `invoke_agent` span.
- Attributes: backend, isolation tier, sandbox id, exit code, duration, bytes in/out.
- Content capture (code, file contents) is **opt-in**, per the spec's privacy modes.
  Secrets are never captured at any setting.
- **All attribute strings live in `sbx/otel.py`.** No other module writes an attribute name.
  The targeted semconv version is pinned and documented; a bump is a changelog entry.
- Zero-config: participate if the host app configured a tracer provider, no-op otherwise.
  sbx MUST NOT install exporters or start providers.

## Metering (v0.2)

```python
@dataclass(frozen=True)
class Meter:
    duration_ms: int
    backend: str
    cost_usd: float | None = None
    cost_is_estimate: bool = True
```

- **OPEN ([Q9](../open-questions.md#q9--one-event-three-sinks-audit--otel--meter))** —
  whether `cost_usd` is knowable at execution time for E2B and Modal, or only post-hoc from
  billing. If post-hoc, it is an estimate and MUST be labelled one; a wrong cost number is
  worse than no cost number.

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
