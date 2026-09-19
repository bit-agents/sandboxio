"""A minimal adapter that satisfies every port without importing a base class."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sandboxio.models import Capability, ExecResult, IsolationTier, NetworkPolicy, Resources

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path
    from types import TracebackType

    from sandboxio.models import FileInfo, OutputChunk
    from sandboxio.protocols import AsyncFileSystem, AsyncSandbox, Process


class MinimalProcess:
    async def __aenter__(self) -> MinimalProcess:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def __aiter__(self) -> AsyncIterator[OutputChunk]:
        raise NotImplementedError

    async def wait(self) -> ExecResult:
        return ExecResult(0, "", "", streamed=True)

    async def kill(self) -> None:
        return None

    @property
    def returncode(self) -> int | None:
        return None


class MinimalFiles:
    async def read(self, path: str) -> bytes:
        return b""

    async def write(self, path: str, data: bytes | str) -> None:
        return None

    async def upload(self, local: str | Path, remote: str) -> None:
        return None

    async def download(self, remote: str, local: str | Path) -> None:
        return None

    async def ls(self, path: str = ".") -> list[FileInfo]:
        return []

    async def mkdir(self, path: str, *, parents: bool = False) -> None:
        return None

    async def remove(self, path: str) -> None:
        return None


class MinimalSandbox:
    id = "sb-1"
    capabilities = Capability.RUN_COMMAND
    isolation = IsolationTier.CONTAINER

    async def run(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        return ExecResult(0, "", "")

    async def run_code(
        self,
        code: str,
        *,
        language: str = "python",
        context_id: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        return ExecResult(0, "", "")

    def stream(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> Process:
        return MinimalProcess()

    async def kill(self) -> None:
        return None

    @property
    def files(self) -> AsyncFileSystem:
        return MinimalFiles()

    @property
    def native(self) -> object:
        return self

    async def __aenter__(self) -> MinimalSandbox:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


class MinimalBackend:
    name = "minimal"
    capabilities = Capability.RUN_COMMAND
    isolation = IsolationTier.UNKNOWN

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
    ) -> AsyncSandbox:
        return MinimalSandbox()

    async def connect(self, sandbox_id: str) -> AsyncSandbox:
        return MinimalSandbox()
