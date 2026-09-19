"""Port interfaces adapters implement (spec/02).

Structural ``Protocol`` classes: a third-party adapter conforms without importing a base
class. Passing the type checker is necessary, the contract suite is what proves conformance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sandboxio.models import NetworkPolicy, Resources

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path
    from types import TracebackType

    from sandboxio.models import Capability, ExecResult, FileInfo, IsolationTier, OutputChunk

__all__ = ["AsyncFileSystem", "AsyncSandbox", "Backend", "Process"]


class Process(Protocol):
    """A single streamed execution. Entering starts it; exiting kills it if still running."""

    async def __aenter__(self) -> Process: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def __aiter__(self) -> AsyncIterator[OutputChunk]: ...

    async def wait(self) -> ExecResult: ...

    async def kill(self) -> None: ...

    @property
    def returncode(self) -> int | None: ...


class AsyncFileSystem(Protocol):
    """Filesystem scoped to one sandbox. Only the ``local`` arguments name host paths."""

    async def read(self, path: str) -> bytes: ...

    async def write(self, path: str, data: bytes | str) -> None: ...

    async def upload(self, local: str | Path, remote: str) -> None: ...

    async def download(self, remote: str, local: str | Path) -> None: ...

    async def ls(self, path: str = ".") -> list[FileInfo]: ...

    async def mkdir(self, path: str, *, parents: bool = False) -> None: ...

    async def remove(self, path: str) -> None: ...


class AsyncSandbox(Protocol):
    """A live sandbox. ``capabilities`` and ``isolation`` describe this instance."""

    id: str
    capabilities: Capability
    isolation: IsolationTier

    async def run(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecResult: ...

    async def run_code(
        self,
        code: str,
        *,
        language: str = "python",
        context_id: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult: ...

    def stream(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> Process: ...

    async def kill(self) -> None: ...

    @property
    def files(self) -> AsyncFileSystem: ...

    @property
    def native(self) -> object: ...

    async def __aenter__(self) -> AsyncSandbox: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


class Backend(Protocol):
    """A sandbox provider. ``create()`` applies policy before any user code can run."""

    name: str
    capabilities: Capability
    isolation: IsolationTier

    async def create(
        self,
        *,
        template: str | None = None,
        resources: Resources = Resources(),
        network: NetworkPolicy = NetworkPolicy(),
        env: dict[str, str] | None = None,
        secrets: dict[str, str] | None = None,
        timeout: float = 300,
        metadata: dict[str, str] | None = None,
    ) -> AsyncSandbox: ...

    async def connect(self, sandbox_id: str) -> AsyncSandbox: ...
