"""Audit events and sinks (spec/06). One frozen event per operation, already redacted."""

from __future__ import annotations

import warnings
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

import anyio

from sandboxio.errors import AuditSinkWarning

if TYPE_CHECKING:
    from datetime import datetime

    from sandboxio.models import IsolationTier

__all__ = ["AuditConfig", "AuditEvent", "AuditSink", "NoopSink", "QueueSink"]


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


class AuditSink(Protocol):
    """``emit`` MUST return promptly; buffering is the sink's job, like ``logging.Handler``."""

    async def emit(self, event: AuditEvent) -> None: ...


class NoopSink:
    """The default sink. Records nothing."""

    async def emit(self, event: AuditEvent) -> None:
        return None


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
