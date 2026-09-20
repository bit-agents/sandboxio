"""The E2B adapter's pure helpers, without an API key.

``test_e2b_contract.py`` is the spec for this adapter, but it skips whenever
``E2B_API_KEY`` is unset — nightly only. Error classification and Jupyter output decoding
are decidable from their inputs, so they are asserted here instead.
"""

# e2b_code_interpreter ships no py.typed marker, exactly as the adapter notes.
# pyright: reportPrivateUsage=false, reportMissingTypeStubs=false
from __future__ import annotations

from typing import Any, cast

import anyio
import anyio.lowlevel
import pytest

pytest.importorskip("e2b")
pytest.importorskip("sandboxio_e2b")

from e2b.exceptions import (
    AuthenticationException,
    FileNotFoundException,
    NotEnoughSpaceException,
    NotFoundException,
    RateLimitException,
    SandboxException,
    SandboxNotFoundException,
    TimeoutException,
)
from e2b_code_interpreter.models import (
    Execution,
    ExecutionError,
    Logs,
    Result,
)

from sandboxio.errors import (
    AuthError,
    RateLimitError,
    ResourceLimitExceeded,
    SandboxGone,
    SandboxTimeout,
)
from sandboxio.models import OutputChunk
from sandboxio_e2b._backend import (
    API_KEY_ENV,
    POLL_MAX,
    POLL_MIN,
    E2BProcess,
    _is_gone,
    _lifetime,
    _line,
    _map_common,
    _rich,
    _to_result,
)

pytestmark = pytest.mark.anyio


# --- _lifetime ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "lifetime"),
    [(30.0, 30), (1.0, 1), (1.2, 2), (59.9, 60), (0.001, 1), (0.0, 1), (-5.0, 1)],
)
def test_lifetime_rounds_up_and_never_asks_e2b_for_zero_seconds(
    seconds: float, lifetime: int
) -> None:
    """E2B takes whole seconds; rounding down would kill the sandbox before its deadline."""
    assert _lifetime(seconds) == lifetime


# --- _is_gone -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "gone"),
    [
        (SandboxNotFoundException("whatever"), True),
        (NotFoundException("sandbox abc123 not found"), True),
        (TimeoutException("sandbox timeout exceeded"), True),
        (SandboxException("sandbox is not running"), True),
        (SandboxException("SANDBOX NOT FOUND"), True),
        (SandboxException("sandbox is healthy"), False),
        (NotFoundException("template not found"), False),
        (ValueError("file not found"), False),
    ],
    ids=[
        "typed",
        "text-not-found",
        "text-timeout",
        "text-not-running",
        "uppercase",
        "no-verdict-word",
        "no-sandbox-word",
        "foreign",
    ],
)
def test_is_gone_sniffs_the_message_when_the_sdk_gives_no_type(
    exc: BaseException, gone: bool
) -> None:
    assert _is_gone(exc) is gone


def test_a_missing_file_is_never_a_missing_sandbox() -> None:
    """FileNotFoundException subclasses NotFoundException, and its text says 'sandbox'
    often enough that only the explicit guard keeps `read()` from reporting SandboxGone."""
    assert _is_gone(FileNotFoundException("no such file in sandbox: not found")) is False


# --- _map_common ----------------------------------------------------------------------------


def test_map_common_translates_auth_failures_and_names_the_env_var() -> None:
    mapped = _map_common(AuthenticationException("401"), sandbox_id="sb-1")
    assert isinstance(mapped, AuthError)
    assert API_KEY_ENV in mapped.hint


def test_map_common_translates_throttling() -> None:
    exc = RateLimitException("429")  # type: ignore[no-untyped-call]  # the SDK ships none
    mapped = _map_common(exc, sandbox_id="sb-1")
    assert isinstance(mapped, RateLimitError) and mapped.code == "SBX_E1502"


def test_map_common_reports_a_full_disk_as_the_resource_that_ran_out() -> None:
    mapped = _map_common(NotEnoughSpaceException("no space"), sandbox_id="sb-1")
    assert isinstance(mapped, ResourceLimitExceeded)
    assert "disk_mb" in mapped.message


def test_map_common_names_the_sandbox_that_vanished() -> None:
    mapped = _map_common(SandboxNotFoundException("gone"), sandbox_id="sb-42")
    assert isinstance(mapped, SandboxGone) and "sb-42" in mapped.message


@pytest.mark.parametrize(
    "exc",
    [
        FileNotFoundException("/work/missing.txt"),
        SandboxException("something else entirely"),
        ValueError("not an SDK error"),
    ],
    ids=["file-not-found", "unclassified-sdk", "foreign"],
)
def test_map_common_declines_what_the_caller_must_map_itself(exc: Exception) -> None:
    """None is the 'not one of ours' signal; a wrong guess here masks PathNotFound."""
    assert _map_common(exc, sandbox_id="sb-1") is None


# --- _line ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "line"), [("out", "out\n"), ("out\n", "out\n"), ("", "\n"), ("a\nb", "a\nb\n")]
)
def test_line_terminates_every_log_chunk_exactly_once(raw: str, line: str) -> None:
    """E2B splits logs into chunks that may or may not carry their newline."""
    assert _line(raw) == line


# --- _rich ----------------------------------------------------------------------------------


def test_rich_serialises_dicts_as_json_and_everything_else_as_text() -> None:
    out = _rich(Result(text="hi", png="QkFTRTY0", json={"a": 1}))
    assert [(o.mime_type, o.data) for o in out] == [
        ("text/plain", "hi"),
        ("image/png", "QkFTRTY0"),
        ("application/json", '{"a": 1}'),
    ]


def test_rich_skips_the_formats_the_execution_did_not_produce() -> None:
    assert _rich(Result()) == []
    assert [o.mime_type for o in _rich(Result(svg="<svg/>"))] == ["image/svg+xml"]


def test_rich_ignores_sdk_attributes_that_are_not_display_formats() -> None:
    """``chart`` and ``is_main_result`` are E2B metadata, not MIME output."""
    out = _rich(Result(text="hi", chart={"type": "line"}, is_main_result=True))
    assert [o.mime_type for o in out] == ["text/plain"]


# --- _to_result -----------------------------------------------------------------------------


def test_to_result_joins_logs_and_reports_success() -> None:
    res = _to_result(Execution(logs=Logs(stdout=["a\n", "b"], stderr=["warn"])))
    assert res.exit_code == 0 and res.ok
    assert res.stdout == "a\nb\n" and res.stderr == "warn\n"


def test_to_result_turns_a_python_exception_into_exit_1_and_a_stderr_traceback() -> None:
    """E2B reports interpreter errors out of band; sandboxio callers only read exit codes."""
    res = _to_result(
        Execution(
            logs=Logs(stderr=["earlier\n"]),
            error=ExecutionError(name="ValueError", value="bad", traceback="Traceback..."),
        )
    )
    assert res.exit_code == 1 and not res.ok
    assert res.stderr == "earlier\nTraceback...\nValueError: bad\n"


def test_to_result_carries_rich_output_from_every_result() -> None:
    res = _to_result(
        Execution(results=[Result(text="one"), Result(png="QkFTRTY0")], logs=Logs())
    )
    assert res.results is not None
    assert [(o.mime_type, o.data) for o in res.results] == [
        ("text/plain", "one"),
        ("image/png", "QkFTRTY0"),
    ]


# --- E2BProcess polling ---------------------------------------------------------------------


class StubHandle:
    exit_code: int | None = None


class StubSandbox:
    id = "sb-1"

    async def _kill_handle(self, handle: object) -> None:
        return None


def process(limit: float) -> E2BProcess:
    proc = E2BProcess(cast(Any, StubSandbox()), "sleep 1", ["sleep", "1"], None, limit)
    proc._handle = StubHandle()
    proc._deadline = anyio.current_time() + limit
    return proc


async def drain(proc: E2BProcess) -> list[OutputChunk]:
    return [chunk async for chunk in proc]


async def test_a_silent_stream_backs_off_to_the_cap_instead_of_spinning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fixed 20 ms polling is tens of thousands of idle wake-ups/s at high concurrency."""
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) == 6:
            proc._handle.exit_code = 0
        await anyio.lowlevel.checkpoint()

    monkeypatch.setattr(anyio, "sleep", fake_sleep)
    proc = process(30.0)
    assert await drain(proc) == []
    assert slept == [POLL_MIN, 0.04, 0.08, POLL_MAX, POLL_MAX, POLL_MAX]


async def test_output_resets_the_backoff_so_a_chatty_stream_stays_responsive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        proc._buffer.append(OutputChunk("stdout", b"tick"))
        if len(slept) == 4:
            proc._handle.exit_code = 0
        await anyio.lowlevel.checkpoint()

    monkeypatch.setattr(anyio, "sleep", fake_sleep)
    proc = process(30.0)
    assert len(await drain(proc)) == 4
    assert slept == [POLL_MIN] * 4, "a stream producing output must never drift to the cap"


async def test_the_backoff_never_sleeps_past_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 100 ms poll on a 10 ms budget would report the timeout 90 ms late."""
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        await anyio.lowlevel.checkpoint()

    monkeypatch.setattr(anyio, "sleep", fake_sleep)
    proc = process(30.0)
    proc._deadline = anyio.current_time() + 0.005
    with pytest.raises(SandboxTimeout):
        await drain(proc)
    assert all(s <= 0.005 for s in slept), slept
