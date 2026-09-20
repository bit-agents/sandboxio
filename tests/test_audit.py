from __future__ import annotations

import json
import logging
from pathlib import Path

import anyio
import pytest

from sandboxio._record import OperationRecord, Redactor, emit, operation
from sandboxio.audit import AuditConfig, AuditEvent, FileSink, LoggingSink, NoopSink, QueueSink
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


# --- shipped sinks --------------------------------------------------------------------------


def _event() -> AuditEvent:
    rec = _record()
    rec.exit_code = 0
    return rec.close(Redactor({"T": "hunter2"}, None))


def test_as_dict_is_json_ready_and_redacted() -> None:
    event = _event()
    payload = event.as_dict()
    assert payload["isolation"] == "container"
    assert payload["argv"] == ["echo", "***", "ok"]
    assert "code" not in payload, "code is hashed unless capture_code=True"
    line = event.to_json()
    assert "\n" not in line and "hunter2" not in line
    assert json.loads(line) == payload


def test_capture_code_keeps_the_redacted_code() -> None:
    rec = _record()
    rec.code = "print('hunter2')"
    event = rec.close(Redactor({"T": "hunter2"}, None), capture_code=True)
    assert event.code == "print('***')"
    assert event.as_dict()["code"] == "print('***')"


async def test_logging_sink_writes_one_json_line_and_configures_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("test.sandboxio.audit")
    sink = LoggingSink(logger, level=logging.INFO)
    with caplog.at_level(logging.INFO, logger=logger.name):
        await sink.emit(_event())
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert json.loads(record.getMessage())["event"] == "exec"
    assert getattr(record, "audit")["sandbox_id"] == "sb-1"  # noqa: B009 — structured extra
    assert "hunter2" not in record.getMessage()
    assert logger.handlers == [] and logging.getLogger("sandboxio").handlers == []


async def test_logging_sink_accepts_a_logger_name() -> None:
    sink = LoggingSink("test.sandboxio.named")
    await sink.emit(_event())  # no handler configured: silently dropped, never printed


async def test_file_sink_appends_json_lines(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    sink = FileSink(path)
    await sink.emit(_event())
    await sink.emit(_event())
    lines = path.read_text().splitlines()
    assert len(lines) == 2 and all(json.loads(line)["event"] == "exec" for line in lines)
    assert "hunter2" not in path.read_text()
    await FileSink(str(path)).emit(_event())  # a second instance appends, never truncates
    assert len(path.read_text().splitlines()) == 3


async def test_sinks_receive_the_redacted_event_from_a_real_operation(tmp_path: Path) -> None:
    from sandboxio.testing.fake import FakeBackend

    path = tmp_path / "audit.jsonl"
    logger = logging.getLogger("test.sandboxio.e2e")
    captured: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    logger.addHandler(Capture())
    logger.setLevel(logging.INFO)
    try:
        fake = FakeBackend(
            audit=AuditConfig(sinks=(LoggingSink(logger), FileSink(path)), capture_code=True)
        )
        secret = "sbx-secret-" + "x" * 8
        async with await fake.create(secrets={"API_TOKEN": secret}) as sb:
            await sb.run(["echo", secret])
            await sb.run_code(f"print({secret!r})")
    finally:
        logger.handlers.clear()
    text = path.read_text()
    assert len(captured) == 2 and len(text.splitlines()) == 2
    assert secret not in text and all(secret not in line for line in captured)
    assert json.loads(text.splitlines()[1])["code"] == "print('***')"
