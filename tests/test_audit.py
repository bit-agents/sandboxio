from __future__ import annotations

import anyio
import pytest

from sandboxio._record import OperationRecord, Redactor, emit, operation
from sandboxio.audit import AuditConfig, AuditEvent, NoopSink, QueueSink
from sandboxio.errors import AuditSinkError, AuditSinkWarning
from sandboxio.models import IsolationTier

pytestmark = pytest.mark.anyio


class Recording:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


class Failing:
    async def emit(self, event: AuditEvent) -> None:
        raise RuntimeError("sink down")


class Hanging:
    async def emit(self, event: AuditEvent) -> None:
        await anyio.sleep_forever()


def _record() -> OperationRecord:
    return OperationRecord(
        event="exec",
        sandbox_id="sb-1",
        backend="fake",
        isolation=IsolationTier.CONTAINER,
        metadata={"tenant_id": "t", "session_id": "s"},
        argv=["echo", "hunter2", "ok"],
        code="print(1)",
    )


def test_redactor_wipes_secrets_and_credential_shaped_env_values() -> None:
    redact = Redactor({"TOKEN": "hunter2"}, {"HOME": "/root", "AWS_SECRET_KEY": "aws-xyz"})
    assert redact("say hunter2 and aws-xyz but not /root") == "say *** and *** but not /root"
    assert redact.argv(["hunter2"]) == ("***",)
    assert redact.argv(None) is None
    assert redact.leaks("contains aws-xyz")
    assert not redact.leaks("clean")


def test_redactor_handles_nested_secrets_longest_first() -> None:
    redact = Redactor({"A": "abc", "B": "abcdef"}, None)
    assert redact("abcdef abc") == "*** ***"


def test_close_renders_a_redacted_frozen_event() -> None:
    rec = _record()
    rec.exit_code = 0
    event = rec.close(Redactor({"T": "hunter2"}, None))
    assert event.argv == ("echo", "***", "ok")
    assert event.tenant_id == "t" and event.session_id == "s"
    assert len(event.code_sha256) == 64
    assert event.duration_ms >= 0


async def test_emit_warn_mode_keeps_going_and_reaches_later_sinks() -> None:
    good = Recording()
    config = AuditConfig(sinks=(Failing(), good))
    with pytest.warns(AuditSinkWarning):
        await emit(_record().close(Redactor(None, None)), config)
    assert len(good.events) == 1


async def test_emit_fail_mode_raises_audit_sink_error_with_cause() -> None:
    config = AuditConfig(sinks=(Failing(),), on_sink_failure="fail")
    with pytest.raises(AuditSinkError) as info:
        await emit(_record().close(Redactor(None, None)), config)
    assert isinstance(info.value.__cause__, RuntimeError)


async def test_emit_is_bounded_by_the_audit_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SBX_AUDIT_TIMEOUT", "0.05")
    config = AuditConfig(sinks=(Hanging(),), on_sink_failure="fail")
    with anyio.fail_after(5), pytest.raises(AuditSinkError) as info:
        await emit(_record().close(Redactor(None, None)), config)
    assert isinstance(info.value.__cause__, TimeoutError)


async def test_operation_emits_once_even_when_the_body_raises() -> None:
    sink = Recording()
    config = AuditConfig(sinks=(sink,))
    with pytest.raises(ValueError, match="boom"):
        async with operation(_record(), config=config, redact=Redactor(None, None)) as rec:
            rec.exit_code = 1
            raise ValueError("boom")
    assert [e.exit_code for e in sink.events] == [1]


async def test_operation_emits_when_the_body_is_cancelled() -> None:
    sink = Recording()
    config = AuditConfig(sinks=(sink,))

    async def body() -> None:
        async with operation(_record(), config=config, redact=Redactor(None, None)):
            await anyio.sleep_forever()

    async with anyio.create_task_group() as tg:
        tg.start_soon(body)
        await anyio.sleep(0.01)
        tg.cancel_scope.cancel()
    assert len(sink.events) == 1


async def test_noop_sink_records_nothing() -> None:
    await NoopSink().emit(_record().close(Redactor(None, None)))


async def test_queue_sink_enqueues_instantly_and_drains_to_the_target() -> None:
    target = Recording()
    queue = QueueSink(target, maxlen=2)
    event = _record().close(Redactor(None, None))
    await queue.emit(event)
    await queue.emit(event)
    with pytest.warns(AuditSinkWarning):
        await queue.emit(event)  # overflow drops the oldest
    assert queue.dropped == 1 and len(queue) == 2
    await queue.flush()
    assert len(target.events) == 2 and len(queue) == 0

    async with anyio.create_task_group() as tg:
        tg.start_soon(queue.drain)
        await queue.emit(event)
        with anyio.fail_after(5):
            while len(target.events) < 3:
                await anyio.sleep(0)
        tg.cancel_scope.cancel()
