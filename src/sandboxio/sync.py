"""The sync facade (ADR-0022): hand-written delegation over a per-sandbox blocking portal.

Every sandbox owns one portal thread for its lifetime, so N sync sandboxes means N threads;
the async API is the answer for heavy concurrency. Each streamed chunk crosses the portal,
so sync streaming costs a thread round-trip per chunk. Errors are the same classes as the
async API with ``__cause__`` intact; portal frames appear in tracebacks.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from sandboxio import api
from sandboxio.models import NetworkPolicy, Resources

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from contextlib import AbstractContextManager
    from pathlib import Path
    from types import TracebackType

    from anyio.from_thread import BlockingPortal

    from sandboxio.api import BackendConfig
    from sandboxio.models import (
        Capability,
        ExecResult,
        FileInfo,
        IsolationTier,
        OutputChunk,
    )
    from sandboxio.protocols import AsyncFileSystem, AsyncSandbox
    from sandboxio.protocols import Process as AsyncProcess

__all__ = ["FileSystem", "Process", "Sandbox", "connect_sync", "create_sync"]

_END = object()


async def _anext(iterator: AsyncIterator[OutputChunk]) -> OutputChunk | object:
    try:
        return await iterator.__anext__()
    except StopAsyncIteration:
        return _END


class Process:
    """Sync view of a streamed execution. ``with`` is required, as with the async form."""

    def __init__(self, inner: AsyncProcess, portal: BlockingPortal) -> None:
        self._inner = inner
        self._portal = portal

    def __enter__(self) -> Process:
        self._portal.call(self._inner.__aenter__)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._portal.call(self._inner.__aexit__, exc_type, exc, tb)

    def __iter__(self) -> Iterator[OutputChunk]:
        iterator = self._inner.__aiter__()
        while True:
            item = self._portal.call(_anext, iterator)
            if item is _END:
                return
            yield item  # type: ignore[misc]

    def wait(self) -> ExecResult:
        return self._portal.call(self._inner.wait)

    def kill(self) -> None:
        self._portal.call(self._inner.kill)

    @property
    def returncode(self) -> int | None:
        return self._inner.returncode


class FileSystem:
    """Sync view of a sandbox filesystem."""

    def __init__(self, inner: AsyncFileSystem, portal: BlockingPortal) -> None:
        self._inner = inner
        self._portal = portal

    def read(self, path: str) -> bytes:
        return self._portal.call(self._inner.read, path)

    def write(self, path: str, data: bytes | str) -> None:
        self._portal.call(self._inner.write, path, data)

    def upload(self, local: str | Path, remote: str) -> None:
        self._portal.call(self._inner.upload, local, remote)

    def download(self, remote: str, local: str | Path) -> None:
        self._portal.call(self._inner.download, remote, local)

    def ls(self, path: str = ".") -> list[FileInfo]:
        return self._portal.call(self._inner.ls, path)

    def mkdir(self, path: str, *, parents: bool = False) -> None:
        self._portal.call(functools.partial(self._inner.mkdir, path, parents=parents))

    def remove(self, path: str) -> None:
        self._portal.call(self._inner.remove, path)


class Sandbox:
    """Sync view of a sandbox; owns the portal thread and stops it on ``__exit__``/``close()``.

    >>> with create_sync("fake://") as sb:  # doctest: +SKIP
    ...     print(sb.run(["echo", "hi"]).stdout)
    """

    def __init__(
        self,
        inner: AsyncSandbox,
        portal: BlockingPortal,
        portal_cm: AbstractContextManager[BlockingPortal],
    ) -> None:
        self._inner = inner
        self._portal = portal
        self._portal_cm: AbstractContextManager[BlockingPortal] | None = portal_cm
        self._files = FileSystem(inner.files, portal) if _has_files(inner) else None

    @property
    def id(self) -> str:
        return self._inner.id

    @property
    def capabilities(self) -> Capability:
        return self._inner.capabilities

    @property
    def isolation(self) -> IsolationTier:
        return self._inner.isolation

    def run(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        return self._portal.call(
            functools.partial(self._inner.run, cmd, timeout=timeout, env=env)
        )

    def run_code(
        self,
        code: str,
        *,
        language: str = "python",
        context_id: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        return self._portal.call(
            functools.partial(
                self._inner.run_code,
                code,
                language=language,
                context_id=context_id,
                timeout=timeout,
            )
        )

    def stream(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> Process:
        return Process(self._inner.stream(cmd, timeout=timeout, env=env), self._portal)

    def kill(self) -> None:
        self._portal.call(self._inner.kill)

    @property
    def files(self) -> FileSystem:
        if self._files is None:
            self._files = FileSystem(self._inner.files, self._portal)  # raises if undeclared
        return self._files

    @property
    def native(self) -> object:
        return self._inner.native

    def close(self) -> None:
        """Stop the portal thread. Idempotent; ``__exit__`` calls it."""
        cm, self._portal_cm = self._portal_cm, None
        if cm is not None:
            cm.__exit__(None, None, None)

    def __enter__(self) -> Sandbox:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            self._portal.call(self._inner.__aexit__, exc_type, exc, tb)
        finally:
            self.close()


def _has_files(inner: AsyncSandbox) -> bool:
    try:
        inner.files  # noqa: B018 — probing whether FILESYSTEM is declared
    except Exception:
        return False
    return True


def _start_portal() -> tuple[BlockingPortal, AbstractContextManager[BlockingPortal]]:
    from anyio.from_thread import start_blocking_portal

    cm = start_blocking_portal()
    return cm.__enter__(), cm


def _wrap(call: Any) -> Sandbox:
    portal, cm = _start_portal()
    try:
        inner: AsyncSandbox = portal.call(call)
    except BaseException:
        cm.__exit__(None, None, None)
        raise
    return Sandbox(inner, portal, cm)


def create_sync(
    target: str | BackendConfig | None = None,
    *,
    template: str | None = None,
    resources: Resources = Resources(),
    network: NetworkPolicy = NetworkPolicy(),
    env: dict[str, str] | None = None,
    secrets: dict[str, str] | None = None,
    timeout: float = api.DEFAULT_TIMEOUT,
    metadata: dict[str, str] | None = None,
    require_isolation: IsolationTier | None = None,
) -> Sandbox:
    """``sandboxio.create()`` for sync code. Entry is explicit; ``create()`` never guesses.

    >>> with create_sync("fake://") as sb:  # doctest: +SKIP
    ...     res = sb.run_code("print('hello')")
    """
    return _wrap(
        functools.partial(
            api.create,
            target,
            template=template,
            resources=resources,
            network=network,
            env=env,
            secrets=secrets,
            timeout=timeout,
            metadata=metadata,
            require_isolation=require_isolation,
        )
    )


def connect_sync(target: str | BackendConfig, sandbox_id: str) -> Sandbox:
    """``sandboxio.connect()`` for sync code."""
    return _wrap(functools.partial(api.connect, target, sandbox_id))
