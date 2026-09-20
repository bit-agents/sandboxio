"""OTel rendering of the operation record (spec/06, ADR-0011).

Every span attribute name in sandboxio is a constant in this module; no other module writes
one. Target: OpenTelemetry GenAI semantic conventions ``SEMCONV_VERSION`` — sandbox
operations are ``execute_tool`` spans, nesting under whatever span the caller has current.

The OTel API is imported on first operation, never at ``import sandboxio``. With no
``opentelemetry-api`` installed, or no tracer provider configured, everything here is a no-op.
sandboxio never installs an exporter and never starts a provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.trace import Span

    from sandboxio._record import OperationRecord
    from sandboxio.audit import AuditEvent

__all__ = ["SEMCONV_VERSION", "attributes", "finish", "start"]

# Bumping this is a changelog entry (ADR-0011).
SEMCONV_VERSION = "1.37.0"
INSTRUMENTATION_NAME = "sandboxio"

# --- semconv attributes ---------------------------------------------------------------------
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
ERROR_TYPE = "error.type"
OPERATION_EXECUTE_TOOL = "execute_tool"

# --- sandboxio attributes: semconv has no vocabulary for a sandbox, so these are namespaced --
BACKEND = "sandboxio.backend"
ISOLATION = "sandboxio.isolation"
SANDBOX_ID = "sandboxio.sandbox.id"
TENANT_ID = "sandboxio.tenant_id"
SESSION_ID = "sandboxio.session_id"
CODE_SHA256 = "sandboxio.code_sha256"
ARGV = "sandboxio.argv"
EXIT_CODE = "sandboxio.exit_code"
DURATION_MS = "sandboxio.duration_ms"
BYTES_IN = "sandboxio.bytes_in"
BYTES_OUT = "sandboxio.bytes_out"
NETWORK_DENIALS = "sandboxio.network_denials"
CODE = "sandboxio.code"  # only with AuditConfig(capture_code=True); redacted

_trace_module: Any = None
_probed = False


def _trace() -> Any:
    """The ``opentelemetry.trace`` module, or None when the API is not installed."""
    global _trace_module, _probed
    if not _probed:
        _probed = True
        try:
            import opentelemetry.trace
        except ImportError:
            return None
        _trace_module = opentelemetry.trace
    return _trace_module


def span_name(record: OperationRecord) -> str:
    return f"{OPERATION_EXECUTE_TOOL} {record.event}"


def start(record: OperationRecord) -> Span | None:
    """Open the span when the record opens, so a long execution is visible while it runs."""
    trace = _trace()
    if trace is None:
        return None
    from sandboxio import __version__

    tracer = trace.get_tracer(INSTRUMENTATION_NAME, __version__)
    span: Span = tracer.start_span(span_name(record))
    if not span.is_recording():  # no provider configured: stay out of the way entirely
        span.end()
        return None
    span.set_attributes(
        {
            GEN_AI_OPERATION_NAME: OPERATION_EXECUTE_TOOL,
            GEN_AI_TOOL_NAME: record.event,
            BACKEND: record.backend,
            ISOLATION: record.isolation.value,
            SANDBOX_ID: record.sandbox_id,
        }
    )
    return span


def attributes(event: AuditEvent) -> dict[str, Any]:
    """The closed record as span attributes. Already redacted; None values are left out.

    >>> attributes(event)["sandboxio.backend"]  # doctest: +SKIP
    'fake'
    """
    attrs: dict[str, Any] = {
        GEN_AI_OPERATION_NAME: OPERATION_EXECUTE_TOOL,
        GEN_AI_TOOL_NAME: event.event,
        BACKEND: event.backend,
        ISOLATION: event.isolation.value,
        SANDBOX_ID: event.sandbox_id,
        TENANT_ID: event.tenant_id,
        SESSION_ID: event.session_id,
        CODE_SHA256: event.code_sha256,
        ARGV: None if event.argv is None else list(event.argv),
        EXIT_CODE: event.exit_code,
        DURATION_MS: event.duration_ms,
        BYTES_IN: event.bytes_in,
        BYTES_OUT: event.bytes_out,
        NETWORK_DENIALS: event.network_denials,
        CODE: event.code,
    }
    return {k: v for k, v in attrs.items() if v is not None}


def finish(span: Span | None, event: AuditEvent, error: BaseException | None) -> None:
    """Render the closed record onto the span and end it."""
    if span is None:
        return
    trace = _trace()
    span.set_attributes(attributes(event))
    if error is not None:
        span.set_attribute(ERROR_TYPE, type(error).__qualname__)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(event.event)))
    span.end()
