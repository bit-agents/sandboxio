"""Audit events and sinks (spec/06). One frozen event per operation, already redacted."""

from __future__ import annotations

import json
import logging
import threading
import warnings
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

import anyio
import anyio.to_thread

from sandboxio.errors import AuditSinkWarning

if TYPE_CHECKING:
    from datetime import datetime

    from sandboxio.models import IsolationTier

__all__ = [
    "AuditConfig",
    "AuditEvent",
    "AuditSink",
    "FileSink",
    "LoggingSink",
    "NoopSink",
    "QueueSink",
]


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """What happened, without secrets. Code is hashed; full capture is opt-in."""

    ts: datetime
    event: str
    sandbox_id: str
    backend: str
    isolation: IsolationTier
    tenant_id: str | None
    session_id: str | None
    code_sha256: str
    argv: tuple[str, ...] | None
    exit_code: int | None
    duration_ms: int
    bytes_in: int
    bytes_out: int
    network_denials: int
    code: str | None = None  # populated only with AuditConfig(capture_code=True); redacted

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready rendering; what ``LoggingSink`` and ``FileSink`` write, one per line.

        >>> sorted(event.as_dict())[:3]  # doctest: +SKIP
        ['argv', 'backend', 'bytes_in']
        """
        return {
            "ts": self.ts.isoformat(),
            "event": self.event,
            "sandbox_id": self.sandbox_id,
            "backend": self.backend,
            "isolation": self.isolation.value,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "code_sha256": self.code_sha256,
            "argv": None if self.argv is None else list(self.argv),
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
            "network_denials": self.network_denials,
            **({"code": self.code} if self.code is not None else {}),
        }

    def to_json(self) -> str:
        """One JSON line, no newline, keys in field order."""
        return json.dumps(self.as_dict(), separators=(",", ":"), ensure_ascii=False)


class AuditSink(Protocol):
    """``emit`` MUST return promptly; buffering is the sink's job, like ``logging.Handler``."""

    async def emit(self, event: AuditEvent) -> None: ...


class NoopSink:
    """The default sink. Records nothing."""

    async def emit(self, event: AuditEvent) -> None:
        return None


class LoggingSink:
    """One JSON line per event on a stdlib logger. Configures nothing: the host owns handlers.

    >>> import logging
    >>> sink = LoggingSink(logging.getLogger("myapp.audit"), level=logging.INFO)
    """

    def __init__(
        self, logger: logging.Logger | str = "sandboxio.audit", *, level: int = logging.INFO
    ) -> None:
        self._logger = logging.getLogger(logger) if isinstance(logger, str) else logger
        self._level = level

    async def emit(self, event: AuditEvent) -> None:
        # ``extra`` carries the fields for structured handlers; the message is the JSON line.
        self._logger.log(self._level, "%s", event.to_json(), extra={"audit": event.as_dict()})


class FileSink:
    """Append one JSON line per event to a file. Each event is one open-append-close.

    The append runs in a worker thread, so a slow or network-mounted disk delays the
    operation but never the event loop; wrap in ``QueueSink`` to stop delaying it at all.

    >>> sink = FileSink("audit.jsonl")  # doctest: +SKIP
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _append(self, line: str) -> None:
        # Concurrent operations now reach this from different workers, not the one loop thread.
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    async def emit(self, event: AuditEvent) -> None:
        # Abandonable, so SBX_AUDIT_TIMEOUT still bounds emit when the disk stops answering.
        await anyio.to_thread.run_sync(
            self._append, event.to_json() + "\n", abandon_on_cancel=True
        )


class QueueSink:
    """Bounded queue; ``emit`` never blocks. The host runs ``drain()`` in its own task group.

    >>> sink = QueueSink(target=my_sink, maxlen=1000)  # doctest: +SKIP
    """

    def __init__(self, target: AuditSink, *, maxlen: int = 1000) -> None:
        self._target = target
        self._queue: deque[AuditEvent] = deque(maxlen=maxlen)
        self._wakeup = anyio.Event()
        self.dropped = 0

    async def emit(self, event: AuditEvent) -> None:
        if len(self._queue) == self._queue.maxlen:
            self.dropped += 1
            warnings.warn(
                f"QueueSink full; dropping the oldest event ({self.dropped} dropped so far)",
                AuditSinkWarning,
                stacklevel=2,
            )
        self._queue.append(event)
        self._wakeup.set()

    def __len__(self) -> int:
        return len(self._queue)

    async def drain(self) -> None:
        """Forward queued events to the target forever; cancel the task to stop."""
        while True:
            while self._queue:
                await self._target.emit(self._queue.popleft())
            self._wakeup = anyio.Event()
            await self._wakeup.wait()

    async def flush(self) -> None:
        """Forward everything queued so far, then return."""
        while self._queue:
            await self._target.emit(self._queue.popleft())


@dataclass(frozen=True, slots=True)
class AuditConfig:
    """How an adapter records operations. The default records nothing and never fails one."""

    sinks: tuple[AuditSink, ...] = field(default_factory=tuple)
    on_sink_failure: Literal["warn", "fail"] = "warn"
    capture_code: bool = False
