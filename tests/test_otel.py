"""Spans are the second rendering of the operation record (spec/06, ADR-0011).

A recording tracer built on the OTel *API* only: sandboxio never depends on the SDK, so the
test does not either.
"""

from __future__ import annotations

import re
import textwrap
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.trace import (
    NoOpTracer,
    NoOpTracerProvider,
    Span,
    SpanContext,
    SpanKind,
    Status,
    StatusCode,
    TraceFlags,
)
from opentelemetry.util import types

import sandboxio
from _helpers import REPO_ROOT, run_python
from sandboxio import otel
from sandboxio.audit import AuditConfig
from sandboxio.testing.fake import FakeBackend

pytestmark = pytest.mark.anyio


class RecordingSpan(Span):
    def __init__(self, name: str, parent: Span) -> None:
        self.name = name
        self.parent = parent
        self.attributes: dict[str, Any] = {}
        self.status: Status | StatusCode | None = None
        self.ended = False
        self._context = SpanContext(
            uuid.uuid4().int & ((1 << 128) - 1),
            uuid.uuid4().int & ((1 << 64) - 1),
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )

    def end(self, end_time: int | None = None) -> None:
        self.ended = True

    def get_span_context(self) -> SpanContext:
        return self._context

    def set_attributes(self, attributes: Mapping[str, types.AttributeValue]) -> None:
        self.attributes.update(attributes)

    def set_attribute(self, key: str, value: types.AttributeValue) -> None:
        self.attributes[key] = value

    def add_event(
        self, name: str, attributes: types.Attributes = None, timestamp: int | None = None
    ) -> None:
        return None

    def update_name(self, name: str) -> None:
        self.name = name

    def is_recording(self) -> bool:
        return not self.ended

    def set_status(self, status: Status | StatusCode, description: str | None = None) -> None:
        self.status = status

    def record_exception(
        self,
        exception: BaseException,
        attributes: types.Attributes = None,
        timestamp: int | None = None,
        escaped: bool = False,
    ) -> None:
        return None


class RecordingTracer(NoOpTracer):
    def __init__(self) -> None:
        self.spans: list[RecordingSpan] = []

    def start_span(
        self,
        name: str,
        context: Any = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: types.Attributes = None,
        links: Any = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ) -> Span:
        span = RecordingSpan(name, trace.get_current_span(context))
        if attributes:
            span.set_attributes(attributes)
        self.spans.append(span)
        return span


class RecordingProvider(NoOpTracerProvider):
    def __init__(self) -> None:
        self.tracer = RecordingTracer()
        self.requested: list[tuple[str, str | None]] = []

    def get_tracer(
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: str | None = None,
        schema_url: str | None = None,
        attributes: types.Attributes | None = None,
    ) -> RecordingTracer:
        self.requested.append((instrumenting_module_name, instrumenting_library_version))
        return self.tracer


_PROVIDER = RecordingProvider()


@pytest.fixture(scope="module", autouse=True)
def _install_provider() -> None:
    # The API allows exactly one provider per process; this module is the only one that
    # sets it, and every other test keeps running unchanged with spans recorded here.
    trace.set_tracer_provider(_PROVIDER)


@pytest.fixture
def spans() -> Iterator[list[RecordingSpan]]:
    _PROVIDER.tracer.spans.clear()
    yield _PROVIDER.tracer.spans
    _PROVIDER.tracer.spans.clear()


async def test_every_operation_is_one_execute_tool_span(spans: list[RecordingSpan]) -> None:
    fake = FakeBackend()
    async with await fake.create(metadata={"tenant_id": "acme"}) as sb:
        await sb.run(["echo", "hi"])
        await sb.run_code("print(1)")
        await sb.files.write("/work/a.txt", "x")
    names = [s.name for s in spans]
    assert names == ["execute_tool exec", "execute_tool run_code", "execute_tool file_write"]
    span = spans[0]
    assert span.ended
    assert span.attributes[otel.GEN_AI_OPERATION_NAME] == "execute_tool"
    assert span.attributes[otel.GEN_AI_TOOL_NAME] == "exec"
    assert span.attributes[otel.BACKEND] == "fake"
    assert span.attributes[otel.ISOLATION] == "container"
    assert span.attributes[otel.SANDBOX_ID] == sb.id
    assert span.attributes[otel.TENANT_ID] == "acme"
    assert span.attributes[otel.EXIT_CODE] == 0
    assert span.attributes[otel.ARGV] == ["echo", "hi"]
    assert otel.CODE not in span.attributes and otel.ERROR_TYPE not in span.attributes
    assert _PROVIDER.requested[-1] == ("sandboxio", sandboxio.__version__)


async def test_spans_nest_under_the_callers_span(spans: list[RecordingSpan]) -> None:
    fake = FakeBackend()
    parent = _PROVIDER.tracer.start_span("invoke_agent demo")
    with trace.use_span(parent):
        async with await fake.create() as sb:
            await sb.run(["echo", "nested"])
    child = spans[-1]
    assert child.name == "execute_tool exec"
    assert child.parent is parent


async def test_secrets_reach_no_span_attribute(spans: list[RecordingSpan]) -> None:
    secret = "sbx-span-secret-" + uuid.uuid4().hex
    fake = FakeBackend(audit=AuditConfig(capture_code=True))
    async with await fake.create(secrets={"API_TOKEN": secret}) as sb:
        await sb.run(["echo", secret])
        await sb.run_code(f"print({secret!r})")
    assert len(spans) == 2
    for span in spans:
        assert secret not in repr(span.attributes)
    assert spans[1].attributes[otel.CODE] == "print('***')"


async def test_a_failed_operation_carries_error_type_and_error_status(
    spans: list[RecordingSpan],
) -> None:
    fake = FakeBackend()
    async with await fake.create() as sb:
        with pytest.raises(sandboxio.PathNotFound):
            await sb.files.read("/nope")
    span = spans[-1]
    assert span.attributes[otel.ERROR_TYPE] == "PathNotFound"
    assert isinstance(span.status, Status) and span.status.status_code is StatusCode.ERROR
    assert span.ended


def test_attributes_leave_none_values_out() -> None:
    from sandboxio._record import OperationRecord, Redactor
    from sandboxio.models import IsolationTier

    rec = OperationRecord("exec", "sb", "fake", IsolationTier.CONTAINER, metadata={})
    attrs = otel.attributes(rec.close(Redactor(None, None)))
    assert otel.TENANT_ID not in attrs and otel.EXIT_CODE not in attrs
    assert attrs[otel.SANDBOX_ID] == "sb"


NO_PROVIDER = """
import anyio
from sandboxio import otel
from sandboxio.testing.fake import FakeBackend

async def main():
    fake = FakeBackend()
    async with await fake.create() as sb:
        assert (await sb.run(["echo", "x"])).stdout == "x\\n"
    from sandboxio._record import OperationRecord
    from sandboxio.models import IsolationTier
    rec = OperationRecord("exec", "sb", "fake", IsolationTier.CONTAINER, metadata={})
    assert otel.start(rec) is None, "no provider configured must mean no span at all"
    print("ok")

anyio.run(main)
"""

NO_API = """
import sys
sys.modules["opentelemetry"] = None  # simulates `pip install sandboxio` without [otel]
import anyio
from sandboxio import otel
from sandboxio.testing.fake import FakeBackend

async def main():
    fake = FakeBackend()
    async with await fake.create() as sb:
        assert (await sb.run(["echo", "x"])).stdout == "x\\n"
    assert otel._trace() is None
    print("ok")

anyio.run(main)
"""


@pytest.mark.parametrize("script", [NO_PROVIDER, NO_API], ids=["no-provider", "no-api"])
def test_zero_config_means_no_op(script: str) -> None:
    proc = run_python("-c", textwrap.dedent(script))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok" and proc.stderr == ""


ATTRIBUTE_LITERAL = re.compile(r"""["'](gen_ai\.|error\.type|sandboxio\.[a-z_]+\.[a-z_]+)""")
SETTER = re.compile(r"\.set_attributes?\(")


def test_every_attribute_string_lives_in_otel_py() -> None:
    """ADR-0011: a semconv rename is a one-file change."""
    offenders: list[str] = []
    for root in (REPO_ROOT / "src", REPO_ROOT / "packages"):
        for path in root.rglob("*.py"):
            if path.name == "otel.py":
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                literal = ATTRIBUTE_LITERAL.search(line)
                if literal and not literal.group(1).startswith("sandboxio.testing"):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
                if SETTER.search(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_semconv_version_is_pinned_and_documented() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", otel.SEMCONV_VERSION)
    spec = (REPO_ROOT / "docs" / "spec" / "06-observability.md").read_text()
    assert otel.SEMCONV_VERSION in spec, "spec/06 must name the targeted semconv version"
    assert isinstance(Path(otel.__file__), Path)
