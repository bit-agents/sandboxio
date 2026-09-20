# How to record and trace sandbox operations

Every `run`, `run_code`, stream and file operation produces **one** record. It is redacted
once, at close, and then rendered to whichever sinks you configured and to an OpenTelemetry
span. There is no third code path, so "no secret reaches any sink" is one testable claim
([spec/06](../spec/06-observability.md), [ADR-0021](../adr/0021-observability-record.md)).

## Audit sinks

Sinks are configured per backend instance, never globally:

```python
import logging

import sandboxio
from sandboxio.audit import AuditConfig, FileSink, LoggingSink, QueueSink
from sandboxio_docker import DockerBackend

audit = AuditConfig(
    sinks=(
        LoggingSink(logging.getLogger("myapp.audit")),   # one JSON line per event
        FileSink("audit.jsonl"),                          # appended, one JSON line per event
    ),
    on_sink_failure="warn",      # "fail" raises AuditSinkError and fails the operation
    capture_code=False,          # True adds the (redacted) code; the hash is always there
)
sandboxio.register("docker", lambda: DockerBackend(audit=audit))
```

| Sink | Behaviour |
|------|-----------|
| `NoopSink` | the default; records nothing |
| `LoggingSink(logger, level=INFO)` | `logger.log(level, <json line>, extra={"audit": {...}})`; configures no handler — your logging config decides where it goes |
| `FileSink(path)` | opens, appends one JSON line, closes, in a worker thread; a local write, like `logging.FileHandler` |
| `QueueSink(target, maxlen=1000)` | `emit` enqueues instantly; **you** run `await sink.drain()` in your own task group; overflow drops the oldest and warns |

`emit` is awaited inline and bounded by `SBX_AUDIT_TIMEOUT` (default 5 s). A sink that does
network I/O belongs behind `QueueSink`. Under `on_sink_failure="fail"`, an unrecorded
operation is a failed operation — the setting for a regulated buyer.

One event, as a JSON line:

```json
{"ts": "2026-09-19T10:00:00.000000+00:00", "event": "run_code", "sandbox_id": "8c2af94cd1bc",
 "backend": "docker", "isolation": "container", "tenant_id": "acme", "session_id": "s-1",
 "code_sha256": "…", "argv": null, "exit_code": 0, "duration_ms": 115, "bytes_in": 42,
 "bytes_out": 6, "network_denials": 0}
```

`argv` and `code` are redacted: every value passed as `secrets=` and every credential-shaped
`env` value is replaced by `***` wherever it appears. Code is hashed; the text itself is only
present with `capture_code=True`, redacted the same way.

## OpenTelemetry spans

Nothing to configure. If your application has set a tracer provider, each operation is an
`execute_tool` span nesting under whatever span is current — your agent framework's
`invoke_agent` span, typically. With no provider, nothing happens; sandboxio never installs
an exporter or starts a provider.

```bash
uv add "sandboxio[otel]"         # the OTel API only; you already have it if you trace anything
```

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)   # from here on, every sandbox operation is a span
```

Span attributes, from GenAI semantic conventions **1.37.0** plus a `sandboxio.*` namespace
because the convention has no sandbox vocabulary:

| Attribute | Value |
|-----------|-------|
| `gen_ai.operation.name` | `execute_tool` |
| `gen_ai.tool.name` | `exec`, `run_code`, `file_read`, … |
| `sandboxio.backend`, `sandboxio.isolation`, `sandboxio.sandbox.id` | as reported |
| `sandboxio.tenant_id`, `sandboxio.session_id` | from `metadata` |
| `sandboxio.exit_code`, `sandboxio.duration_ms`, `sandboxio.bytes_in`, `sandboxio.bytes_out`, `sandboxio.network_denials` | measured |
| `sandboxio.code_sha256`, `sandboxio.argv` | redacted |
| `sandboxio.code` | only with `capture_code=True`, redacted |
| `error.type` | the exception class, when the operation raised |

Every attribute string lives in `sandboxio/otel.py` and nowhere else, so a convention rename
is a one-file change and a changelog entry ([ADR-0011](../adr/0011-otel-mapping-layer.md)).

## Debugging

`SBX_DEBUG=1` is the only verbosity switch: the CLI shows full tracebacks (with `rich` when
it is importable). The library never prints and configures no logging. Every object has a
`repr` that tells you what you need — `<DockerSandbox docker:8c2af94cd1bc container running
caps=RUN_COMMAND|RUN_CODE|…>` — and never a secret.
