"""``upload``/``download`` must not touch the host disk on the event loop thread.

A blocking read there stalls every other coroutine in the process. Each adapter is
asserted to land on a worker thread rather than timed: a thread id is deterministic,
a stopwatch is not. ``FileSink`` is held to the same rule in ``test_audit.py``.
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
import pytest

from sandboxio.models import Capability

if TYPE_CHECKING:
    from collections.abc import Iterator


class Watcher:
    """Records which thread each host-disk call ran on."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, payload: bytes = b"payload") -> None:
        self.threads: list[int] = []
        self.written: bytes | None = None
        self._payload = payload

        def read_bytes(_self: Path) -> bytes:
            self.threads.append(threading.get_ident())
            return self._payload

        def write_bytes(_self: Path, data: bytes) -> int:
            self.threads.append(threading.get_ident())
            self.written = data
            return len(data)

        monkeypatch.setattr(Path, "read_bytes", read_bytes)
        monkeypatch.setattr(Path, "write_bytes", write_bytes)

    def assert_off_loop(self) -> None:
        assert self.threads, "the host file was never touched"
        assert threading.get_ident() not in self.threads, (
            "host disk I/O ran on the event loop thread; wrap it in a worker thread"
        )


class StubSandbox:
    """Enough of a sandbox for a filesystem to resolve capabilities against."""

    id = "sb-1"

    def _need(self, capability: Capability) -> None:
        assert capability is Capability.UPLOAD_DOWNLOAD


def e2b_filesystem(payload: bytes) -> Any:
    from sandboxio_e2b._backend import E2BFileSystem

    class FS(E2BFileSystem):
        def __init__(self) -> None:
            self._sb = StubSandbox()  # type: ignore[assignment]
            self.remote: bytes | None = None

        async def read(self, path: str) -> bytes:
            return payload

        async def write(self, path: str, data: bytes | str) -> None:
            self.remote = data if isinstance(data, bytes) else data.encode()

    return FS()


def docker_filesystem(payload: bytes) -> Any:
    from sandboxio_docker._backend import DockerFileSystem

    class FS(DockerFileSystem):
        def __init__(self) -> None:
            self._sb = StubSandbox()  # type: ignore[assignment]
            self.remote: bytes | None = None

        async def read(self, path: str) -> bytes:
            return payload

        async def write(self, path: str, data: bytes | str) -> None:
            self.remote = data if isinstance(data, bytes) else data.encode()

    return FS()


@pytest.fixture(params=["e2b", "docker"])
def filesystem(request: pytest.FixtureRequest) -> Iterator[Any]:
    pytest.importorskip(f"sandboxio_{request.param}")
    factory = e2b_filesystem if request.param == "e2b" else docker_filesystem
    yield factory(b"payload")


def test_upload_reads_the_host_file_off_the_event_loop(
    filesystem: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    watcher = Watcher(monkeypatch, payload=b"local bytes")

    async def go() -> None:
        await filesystem.upload(tmp_path / "in.bin", "/work/out.bin")

    anyio.run(go)
    watcher.assert_off_loop()
    assert filesystem.remote == b"local bytes", "the file still has to arrive"


def test_download_writes_the_host_file_off_the_event_loop(
    filesystem: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    watcher = Watcher(monkeypatch)

    async def go() -> None:
        await filesystem.download("/work/in.bin", tmp_path / "out.bin")

    anyio.run(go)
    watcher.assert_off_loop()
    assert watcher.written == b"payload", "the file still has to arrive"
