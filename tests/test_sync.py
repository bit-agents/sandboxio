"""The sync facade behaves like the async API, through a per-sandbox portal (ADR-0022)."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

import sandboxio
from sandboxio import registry
from sandboxio.errors import CreationError, ExecutionTimeout, PathNotFound
from sandboxio.models import ExecResult, IsolationTier
from sandboxio.testing.fake import FakeBackend


@pytest.fixture(autouse=True)
def fresh_registry() -> Iterator[None]:
    registry._reset()  # pyright: ignore[reportPrivateUsage]
    yield
    registry._reset()  # pyright: ignore[reportPrivateUsage]


def test_sync_round_trip_and_the_portal_stops_on_exit() -> None:
    before = threading.active_count()
    with sandboxio.create_sync("fake://") as sb:
        assert threading.active_count() == before + 1, "one portal thread per sandbox"
        assert sb.run(["echo", "hi"]).stdout == "hi\n"
        assert sb.run_code("print('x')").stdout == "x\n"
        sb.files.write("/work/a.txt", b"data")
        assert sb.files.read("/work/a.txt") == b"data"
        assert [i.path for i in sb.files.ls("/work")] == ["/work/a.txt"]
        assert sb.id
        assert sb.isolation is IsolationTier.CONTAINER
    assert threading.active_count() == before
    sb.close()  # idempotent


def test_sync_streaming_crosses_the_portal_per_chunk() -> None:
    with sandboxio.create_sync("fake://") as sb, sb.stream(["seq", "1", "3"]) as proc:
        chunks = [c.data for c in proc]
        res = proc.wait()
    assert chunks == [b"1\n", b"2\n", b"3\n"]
    assert res.streamed and res.ok
    assert proc.returncode == 0


def test_errors_are_the_same_classes_with_cause_intact() -> None:
    fake = FakeBackend()
    sandboxio.register("f", lambda: fake)

    class NativeBoom(Exception):
        pass

    fake.simulate(create_fails=NativeBoom("native"))
    with pytest.raises(CreationError) as info:
        sandboxio.create_sync("f://")
    assert isinstance(info.value.__cause__, NativeBoom)
    assert threading.active_count() == 1 or not any(
        t.name.startswith("anyio") for t in threading.enumerate()
    ), "a failed create must not leave a portal thread behind"

    fake.simulate()
    with sandboxio.create_sync("f://") as sb:
        with pytest.raises(PathNotFound):
            sb.files.read("/work/missing")
        fake.on_run(match="slow", delay=10)
        with pytest.raises(ExecutionTimeout):
            sb.run(["slow"], timeout=1)


def test_connect_sync_reattaches() -> None:
    fake = FakeBackend()
    sandboxio.register("f", lambda: fake)
    with sandboxio.create_sync("f://") as sb, sandboxio.connect_sync("f://", sb.id) as other:
        assert other.id == sb.id
        assert other.run(["echo", "x"]) == ExecResult(0, "x\n", "")
