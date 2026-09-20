"""The one operation record (ADR-0021). Opened at start, closed at end; redacted once at close.

Internal; adapters use ``operation()`` and never build ``AuditEvent`` by hand.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import warnings
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import anyio

from sandboxio import otel
from sandboxio.audit import AuditConfig, AuditEvent
from sandboxio.errors import AuditSinkError, AuditSinkWarning

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable, Mapping, Sequence

    from sandboxio.models import IsolationTier

DEFAULT_AUDIT_TIMEOUT = 5.0
REDACTED = "***"

# Env values that look like credentials are redacted even when not passed as secrets.
_CREDENTIAL_KEY = re.compile(r"(?i)(token|secret|password|passwd|api[_-]?key|credential|auth)")


class Redactor:
    """Replaces every secret value, wherever it appears. Built once per sandbox."""

    def __init__(
        self, secrets: Mapping[str, str] | None, env: Mapping[str, str] | None
    ) -> None:
        values = set((secrets or {}).values())
        values |= {v for k, v in (env or {}).items() if _CREDENTIAL_KEY.search(k)}
        # Longest first so a secret that contains another is wiped whole.
        self._values = sorted((v for v in values if v), key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for value in self._values:
            text = text.replace(value, REDACTED)
        return text

    def argv(self, argv: Sequence[str] | None) -> tuple[str, ...] | None:
        return None if argv is None else tuple(self(a) for a in argv)

    def leaks(self, text: str) -> bool:
        return any(v in text for v in self._values)


@dataclass
class OperationRecord:
    """Mutable while the operation runs; rendered to a frozen ``AuditEvent`` at close."""

    event: str
    sandbox_id: str
    backend: str
    isolation: IsolationTier
    metadata: Mapping[str, str]
    argv: Sequence[str] | None = None
    code: str | None = None
    exit_code: int | None = None
    bytes_in: int = 0
    bytes_out: int = 0
    network_denials: int = 0
    started: float = field(default_factory=time.monotonic)
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))

    def close(self, redact: Redactor, *, capture_code: bool = False) -> AuditEvent:
        return AuditEvent(
            ts=self.ts,
            event=self.event,
            sandbox_id=self.sandbox_id,
            backend=self.backend,
            isolation=self.isolation,
            tenant_id=self.metadata.get("tenant_id"),
            session_id=self.metadata.get("session_id"),
            code_sha256=hashlib.sha256((self.code or "").encode()).hexdigest(),
            argv=redact.argv(self.argv),
            exit_code=self.exit_code,
            duration_ms=int((time.monotonic() - self.started) * 1000),
            bytes_in=self.bytes_in,
            bytes_out=self.bytes_out,
            network_denials=self.network_denials,
            code=redact(self.code) if capture_code and self.code is not None else None,
        )


def audit_timeout() -> float:
    raw = os.environ.get("SBX_AUDIT_TIMEOUT")
    try:
        return float(raw) if raw is not None else DEFAULT_AUDIT_TIMEOUT
    except ValueError:
        return DEFAULT_AUDIT_TIMEOUT


async def emit(event: AuditEvent, config: AuditConfig) -> None:
    """Deliver to every sink inline, bounded; failure follows ``on_sink_failure``."""
    for sink in config.sinks:
        failure: BaseException | None = None
        try:
            with anyio.fail_after(audit_timeout()):
                await sink.emit(event)
        except TimeoutError as exc:
            failure = exc
        except Exception as exc:  # a sink must never take the operation down unasked
            failure = exc
        if failure is None:
            continue
        if config.on_sink_failure == "fail":
            raise AuditSinkError(
                f"audit sink {type(sink).__name__} failed for {event.event} "
                f"on sandbox {event.sandbox_id}"
            ) from failure
        warnings.warn(
            f"audit sink {type(sink).__name__} failed: {failure!r}; operation proceeded",
            AuditSinkWarning,
            stacklevel=2,
        )


@asynccontextmanager
async def operation(
    record: OperationRecord, *, config: AuditConfig, redact: Redactor
) -> AsyncGenerator[OperationRecord]:
    """Open a record around an operation and emit it at close, even on error or cancellation."""
    span = otel.start(record)
    error: BaseException | None = None
    try:
        yield record
    except BaseException as exc:
        error = exc
        raise
    finally:
        event = record.close(redact, capture_code=config.capture_code)
        otel.finish(span, event, error)
        # Emitting during cancellation must not be cancelled away — a regulated buyer needs
        # the record of the operation that was interrupted. Bounded, so never unkillable.
        with anyio.move_on_after(audit_timeout(), shield=True):
            try:
                await emit(event, config)
            except AuditSinkError:
                # An operation that already failed keeps its own exception: the caller needs
                # the reason their command failed, not the audit plumbing's.
                if error is None:
                    raise
                warnings.warn(
                    f"audit sink failed while {record.event} was already failing with "
                    f"{error!r}; the operation's own exception is the one raised",
                    AuditSinkWarning,
                    stacklevel=2,
                )


def total_bytes(chunks: Iterable[bytes | str]) -> int:
    return sum(len(c) if isinstance(c, bytes) else len(c.encode()) for c in chunks)
