"""The Docker adapter. Every docker-py call runs in a worker thread (ADR-0002)."""

# docker-py's stubs are partial; the unknown-type family is noise here, not a signal.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import contextlib
import io
import os
import posixpath
import queue
import re
import tarfile
import threading
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal

import anyio
import anyio.lowlevel
import anyio.to_thread

from sandboxio import _policy
from sandboxio._record import OperationRecord, Redactor, operation
from sandboxio._teardown import shielded_kill
from sandboxio.api import BackendConfig
from sandboxio.audit import AuditConfig
from sandboxio.errors import (
    CapabilityNotSupported,
    ConfigurationError,
    ConnectError,
    CreateTimeout,
    CreationError,
    ExecutionError,
    ExecutionTimeout,
    FileSystemError,
    PathNotFound,
    SandboxGone,
    SandboxWarning,
)
from sandboxio.models import (
    Capability,
    ExecResult,
    FileInfo,
    IsolationTier,
    ManagedSandbox,
    NetworkPolicy,
    OutputChunk,
    Resources,
)
from sandboxio_docker._reaper import SESSION_ID, enabled_by_env, process_reaper

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from types import TracebackType

    import docker
    from docker.models.containers import Container

__all__ = ["DockerBackend", "DockerConfig", "DockerProcess", "DockerSandbox"]

DEFAULT_IMAGE = "python:3.12-slim"
WORKDIR = "/work"
KILLED_EXIT = 137
LABEL_MANAGED = "io.sandboxio.managed"
LABEL_SESSION = "io.sandboxio.session"  # value: sandboxio_docker._reaper.SESSION_ID
LABEL_META = "io.sandboxio.meta."
LABEL_TIMEOUT = "io.sandboxio.timeout"
# Modest caps applied when the caller says nothing (spec/05). Disk caps need storage-opt
# support Docker rarely has, so disk_mb is refused rather than ignored.
DEFAULT_CPU = 1.0
DEFAULT_MEMORY_MB = 512
# Ceiling on concurrent streams, since each one parks a worker until its command ends.
DEFAULT_THREADS = 64
_ENV_THREADS = "SBX_DOCKER_THREADS"
_LIMITER: anyio.lowlevel.RunVar[anyio.CapacityLimiter | None] = anyio.lowlevel.RunVar(
    "sandboxio_docker_limiter", None
)
CAPABILITIES = (
    Capability.RUN_COMMAND
    | Capability.RUN_CODE
    | Capability.STREAMING
    | Capability.FILESYSTEM
    | Capability.UPLOAD_DOWNLOAD
    | Capability.NETWORK_POLICY
)


@dataclass(frozen=True)
class DockerConfig(BackendConfig):
    """Typed configuration: ``template`` is the image reference."""

    backend: ClassVar[str] = "docker"


def _thread_cap() -> int:
    """Worker threads this adapter may hold. ``SBX_DOCKER_THREADS`` overrides (ADR-0027)."""
    raw = os.environ.get(_ENV_THREADS)
    if raw is None:
        return DEFAULT_THREADS
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        warnings.warn(
            f"{_ENV_THREADS}={raw!r} is not a positive integer; using {DEFAULT_THREADS}",
            SandboxWarning,
            stacklevel=2,
        )
        return DEFAULT_THREADS
    return value


def _limiter() -> anyio.CapacityLimiter:
    """This adapter's own thread budget, one per event loop.

    A streamed exec holds a worker for the whole command, so on anyio's shared limiter a
    handful of streams starve every other caller in the process.
    """
    limiter = _LIMITER.get(None)
    if limiter is None:
        limiter = anyio.CapacityLimiter(_thread_cap())
        _LIMITER.set(limiter)
    return limiter


async def _thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
    return await anyio.to_thread.run_sync(
        partial(fn, *args, **kwargs), abandon_on_cancel=True, limiter=_limiter()
    )


def _gone(exc: Exception) -> bool:
    """A docker-py error meaning the container no longer runs or exists."""
    import docker.errors

    if isinstance(exc, docker.errors.NotFound):
        return True
    if isinstance(exc, docker.errors.APIError):
        status = exc.response.status_code if exc.response is not None else None
        return status == 409 or "is not running" in str(exc)
    return False


def _map_common(exc: Exception, *, sandbox_id: str) -> Exception | None:
    """Map docker-py errors shared by every operation; None means 'not one of ours'.

    docker-py classifies little beyond "gone", so each caller supplies its own fallback.
    """
    if _gone(exc):
        return SandboxGone(f"sandbox {sandbox_id} no longer exists on docker")
    return None


class DockerBackend:
    """One container per sandbox, ``docker exec`` per operation, ``network: none`` by default.

    >>> backend = DockerBackend(image="python:3.12-slim")  # doctest: +SKIP
    """

    name = "docker"
    capabilities = CAPABILITIES
    isolation = IsolationTier.CONTAINER

    def __init__(
        self,
        *,
        image: str = DEFAULT_IMAGE,
        python: str = "python",
        audit: AuditConfig | None = None,
        reaper: bool | None = None,
        client: docker.DockerClient | None = None,
    ) -> None:
        self.image = image
        self.python = python
        self.audit = audit or AuditConfig()
        self.session_id = SESSION_ID
        self._client = client
        self._reaper = process_reaper()
        self._reaper_wanted = enabled_by_env() if reaper is None else reaper
        self._lock = anyio.Lock()

    async def client(self) -> docker.DockerClient:
        """The docker-py client, created on first use — never at import."""
        async with self._lock:
            if self._client is None:
                import docker

                try:
                    self._client = await _thread(docker.from_env)
                except Exception as exc:
                    raise CreationError(
                        "cannot reach the Docker daemon",
                        hint="Start Docker, or set DOCKER_HOST; `sandboxio doctor` explains.",
                    ) from exc
            return self._client

    def labels(self, metadata: Mapping[str, str] | None, timeout: float) -> dict[str, str]:
        labels = {
            LABEL_MANAGED: "true",
            LABEL_SESSION: self.session_id,
            LABEL_TIMEOUT: str(timeout),
        }
        labels.update({f"{LABEL_META}{k}": v for k, v in (metadata or {}).items()})
        return labels

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
    ) -> DockerSandbox:
        _policy.validate_request(
            resources=resources,
            network=network,
            timeout=timeout,
            capabilities=self.capabilities,
            backend=self.name,
            allowlist_supported=False,
        )
        if resources.disk_mb is not None:
            raise ConfigurationError(
                "Resources.disk_mb is not enforceable on Docker and is refused, not ignored.",
                hint="Drop disk_mb for Docker, or pick a backend that caps disk.",
            )
        image = template or self.image
        container: Container | None = None
        sb: DockerSandbox | None = None
        try:
            with anyio.fail_after(timeout):
                client = await self.client()
                await self._ensure_image(client, image)
                if self._reaper_wanted:
                    await _thread(self._reaper.start, client)
                created: Container = await _thread(
                    client.containers.create,
                    image,
                    command=["sleep", str(int(timeout) + 1)],  # provider-side lifetime backstop
                    detach=True,
                    init=True,
                    network_mode="none" if network.egress == "deny" else "bridge",
                    nano_cpus=int((resources.cpu or DEFAULT_CPU) * 1e9),
                    mem_limit=f"{resources.memory_mb or DEFAULT_MEMORY_MB}m",
                    environment={**(env or {}), **(secrets or {})},
                    working_dir=WORKDIR,
                    labels=self.labels(metadata, float(timeout)),
                )
                container = created
                # Id known: start and own the handle without a cancellation gap.
                with anyio.CancelScope(shield=True):
                    await _thread(created.start)
                    sb = DockerSandbox(
                        self,
                        created,
                        network=network,
                        resources=resources,
                        secrets=secrets or {},
                        env=env or {},
                        timeout=float(timeout),
                        metadata=metadata or {},
                    )
        except TimeoutError as exc:
            await self._discard(container)
            raise CreateTimeout(f"create() exceeded {timeout}s on docker ({image})") from exc
        except anyio.get_cancelled_exc_class():
            await self._discard(container)
            raise
        except (CreationError, ConfigurationError):
            raise
        except Exception as exc:
            await self._discard(container)
            raise CreationError(f"docker could not create a sandbox from {image!r}") from exc

        assert sb is not None
        try:
            await anyio.lowlevel.checkpoint_if_cancelled()
        except anyio.get_cancelled_exc_class():
            await shielded_kill(sb.kill, sandbox_id=sb.id, backend=self.name, labels=sb.labels)
            raise
        return sb

    async def connect(self, sandbox_id: str) -> DockerSandbox:
        import docker.errors

        client = await self.client()
        try:
            container = await _thread(client.containers.get, sandbox_id)
        except docker.errors.NotFound as exc:
            raise ConnectError(f"no container {sandbox_id!r}") from exc
        labels = container.labels or {}
        if labels.get(LABEL_MANAGED) != "true" or container.status != "running":
            raise ConnectError(f"container {sandbox_id!r} is not a running sandboxio sandbox")
        metadata = {
            k[len(LABEL_META) :]: v for k, v in labels.items() if k.startswith(LABEL_META)
        }
        mode = (container.attrs.get("HostConfig") or {}).get("NetworkMode", "none")
        return DockerSandbox(
            self,
            container,
            network=NetworkPolicy(egress="deny" if mode == "none" else "allow"),
            resources=Resources(),
            secrets={},
            env={},
            timeout=float(labels.get(LABEL_TIMEOUT) or 300.0),
            metadata=metadata,
        )

    async def list_managed(
        self, *, labels: Mapping[str, str] | None = None
    ) -> list[ManagedSandbox]:
        """Every container carrying our label, stopped ones included (spec/10 ``reap``)."""
        client = await self.client()
        wanted = [f"{LABEL_MANAGED}=true"]
        wanted += [f"{LABEL_META}{k}={v}" for k, v in (labels or {}).items()]
        try:
            containers: list[Container] = await _thread(
                client.containers.list, all=True, filters={"label": wanted}
            )
        except Exception as exc:
            raise ConnectError(
                "docker could not list sandboxes",
                hint="Inspect `__cause__` for the daemon's reason.",
            ) from exc
        return [_managed(c) for c in containers]

    async def kill_managed(self, sandbox_id: str) -> bool:
        """Remove one container by id or prefix; False if it is already gone."""
        import docker.errors

        client = await self.client()
        try:
            container: Container = await _thread(client.containers.get, sandbox_id)
            await _thread(container.remove, force=True)
        except docker.errors.NotFound:
            return False
        except Exception as exc:
            mapped = _map_common(exc, sandbox_id=sandbox_id)
            if isinstance(mapped, SandboxGone):
                return False
            raise ConnectError(f"docker could not kill sandbox {sandbox_id!r}") from exc
        return True

    async def _ensure_image(self, client: docker.DockerClient, image: str) -> None:
        import docker.errors

        try:
            await _thread(client.images.get, image)
        except docker.errors.ImageNotFound:
            await _thread(client.images.pull, image)  # host-side; unaffected by egress policy

    async def _discard(self, container: Container | None) -> None:
        if container is None:
            return
        # Best effort; the reaper is the backstop.
        with (
            anyio.CancelScope(shield=True),
            anyio.move_on_after(10),
            contextlib.suppress(Exception),
        ):
            await _thread(container.remove, force=True)


def _managed(container: Container) -> ManagedSandbox:
    labels = container.labels or {}
    status = container.status
    state: Literal["running", "stopped", "paused"] = (
        "running" if status == "running" else "paused" if status == "paused" else "stopped"
    )
    return ManagedSandbox(
        sandbox_id=(container.id or "")[:12],
        backend="docker",
        state=state,
        created_at=_created_at(container.attrs.get("Created")),
        labels={k[len(LABEL_META) :]: v for k, v in labels.items() if k.startswith(LABEL_META)},
    )


def _created_at(raw: object) -> datetime | None:
    """Docker's ``Created`` as a datetime, or None when it is absent or unparseable.

    The nanosecond and ``Z`` rewrites are belt-and-braces: 3.11+ parses both unaided.
    """
    if not isinstance(raw, str) or not raw:
        return None
    text = re.sub(r"(\.\d{6})\d+", r"\1", raw.replace("Z", "+00:00"))
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class DockerSandbox:
    """A running container. ``native`` is the docker-py ``Container``."""

    def __init__(
        self,
        backend: DockerBackend,
        container: Container,
        *,
        network: NetworkPolicy,
        resources: Resources,
        secrets: Mapping[str, str],
        env: Mapping[str, str],
        timeout: float,
        metadata: Mapping[str, str],
    ) -> None:
        self._backend = backend
        self._container = container
        self.id = container.id[:12] if container.id else uuid.uuid4().hex[:12]
        self.capabilities = backend.capabilities
        self.isolation = backend.isolation
        self.network = network
        self.resources = resources
        self.timeout = timeout
        self.labels: dict[str, str] = dict(metadata)
        self._redact = Redactor(secrets, env)
        self._killed = False
        self._fs = DockerFileSystem(self)

    def __repr__(self) -> str:
        state = "killed" if self._killed else "running"
        caps = "|".join(c.name or "" for c in Capability if c in self.capabilities)
        return f"<DockerSandbox docker:{self.id} {self.isolation.value} {state} caps={caps}>"

    # --- plumbing ---------------------------------------------------------------------------

    def _need(self, cap: Capability, *, supported_by: tuple[str, ...] = ()) -> None:
        if cap not in self.capabilities:
            raise CapabilityNotSupported(cap, backend="docker", supported_by=supported_by)

    def _effective_timeout(self, timeout: float | None) -> float:
        _policy.validate_timeout(timeout)
        return self.timeout if timeout is None else timeout

    def _gone(self) -> SandboxGone:
        return SandboxGone(f"sandbox {self.id} no longer exists on docker")

    def _map(self, exc: Exception) -> Exception:
        mapped = _map_common(exc, sandbox_id=self.id)
        if mapped is not None:
            return mapped
        return ExecutionError(ExecResult(KILLED_EXIT, "", f"docker: {exc}"))

    def _record(self, event: str, **fields: Any) -> OperationRecord:
        return OperationRecord(
            event=event,
            sandbox_id=self.id,
            backend="docker",
            isolation=self.isolation,
            metadata=self.labels,
            **fields,
        )

    def _argv(self, cmd: str | list[str]) -> list[str]:
        # A str goes through `sh -c` inside the container; a list never touches a shell.
        return ["sh", "-c", cmd] if isinstance(cmd, str) else list(cmd)

    async def _exec_create(self, argv: list[str], env: Mapping[str, str] | None) -> str:
        if self._killed:
            raise self._gone()
        client = await self._backend.client()
        try:
            created = await _thread(
                client.api.exec_create,
                self._container.id,
                argv,
                environment=dict(env or {}),
                workdir=WORKDIR,
            )
        except Exception as exc:
            raise self._map(exc) from exc
        return str(created["Id"])

    async def _exec_run(
        self, argv: list[str], env: Mapping[str, str] | None, limit: float
    ) -> ExecResult:
        """Buffered exec under the deadline; a timeout or cancellation kills the process.

        Output is held whole in memory with no cap — ``stream()`` is the chunked path.
        """
        client = await self._backend.client()
        exec_id = await self._exec_create(argv, env)
        try:
            with anyio.fail_after(limit):
                out, err = await _thread(client.api.exec_start, exec_id, demux=True)
                info = await _thread(client.api.exec_inspect, exec_id)
        except TimeoutError as exc:
            await self._kill_processes()
            raise ExecutionTimeout(f"execution exceeded {limit}s in sandbox {self.id}") from exc
        except anyio.get_cancelled_exc_class():
            await self._kill_processes()
            raise
        except Exception as exc:
            if _gone(exc):
                raise self._gone() from exc
            raise ExecutionError(ExecResult(KILLED_EXIT, "", f"docker: {exc}")) from exc
        return ExecResult(
            int(info.get("ExitCode") or 0),
            (out or b"").decode(errors="replace"),
            (err or b"").decode(errors="replace"),
        )

    async def _kill_processes(self) -> None:
        """Docker cannot signal one exec, so restart the container: every process dies,
        the filesystem stays. Shielded and bounded."""
        # The container may already be gone; that is fine.
        with (
            anyio.CancelScope(shield=True),
            anyio.move_on_after(15),
            contextlib.suppress(Exception),
        ):
            await _thread(self._container.restart, timeout=0)

    # --- AsyncSandbox protocol --------------------------------------------------------------

    async def run(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        self._need(Capability.RUN_COMMAND)
        limit = self._effective_timeout(timeout)
        argv = self._argv(cmd)
        record = self._record("exec", argv=argv)
        async with operation(record, config=self._backend.audit, redact=self._redact):
            result = await self._exec_run(argv, env, limit)
            record.exit_code = result.exit_code
            record.bytes_out = len(result.stdout) + len(result.stderr)
        return result

    async def run_code(
        self,
        code: str,
        *,
        language: str = "python",
        context_id: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        self._need(Capability.RUN_CODE)
        if context_id is not None:
            self._need(Capability.STATEFUL_CODE, supported_by=("e2b", "fake"))
        if language != "python":
            raise ConfigurationError(
                f"language={language!r} is not available on docker; only python is.",
                hint="Run the interpreter yourself with `run([...])`.",
            )
        limit = self._effective_timeout(timeout)
        argv = [self._backend.python, "-c", code]
        record = self._record("run_code", code=code)
        async with operation(record, config=self._backend.audit, redact=self._redact):
            result = await self._exec_run(argv, None, limit)
            record.exit_code = result.exit_code
            record.bytes_in = len(code)
            record.bytes_out = len(result.stdout) + len(result.stderr)
        return result  # results stays None: Docker has no rich outputs (ADR-0024)

    def stream(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> DockerProcess:
        self._need(Capability.STREAMING)
        if self._killed:
            raise self._gone()
        return DockerProcess(self, self._argv(cmd), env, self._effective_timeout(timeout))

    async def kill(self) -> None:
        if self._killed:
            await anyio.lowlevel.checkpoint()
            return
        self._killed = True
        try:
            await _thread(self._container.remove, force=True)
        except Exception as exc:
            if not _gone(exc):
                raise self._map(exc) from exc

    @property
    def files(self) -> DockerFileSystem:
        self._need(Capability.FILESYSTEM)
        return self._fs

    @property
    def native(self) -> Container:
        return self._container

    async def __aenter__(self) -> DockerSandbox:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await shielded_kill(self.kill, sandbox_id=self.id, backend="docker", labels=self.labels)


@dataclass(frozen=True, slots=True)
class _Done:
    outcome: int | Exception


class DockerProcess:
    """A streamed ``exec``. A pump thread reads frames; each chunk hops to the event loop."""

    def __init__(
        self,
        sb: DockerSandbox,
        argv: list[str],
        env: Mapping[str, str] | None,
        limit: float,
    ) -> None:
        self._sb = sb
        self._argv = argv
        self._env = env
        self._limit = limit
        self._exec_id: str | None = None
        self._queue: queue.SimpleQueue[OutputChunk | _Done] = queue.SimpleQueue()
        self._exit_code: int | None = None
        self._deadline = 0.0
        self._record: OperationRecord | None = None

    @property
    def returncode(self) -> int | None:
        return self._exit_code

    async def __aenter__(self) -> DockerProcess:
        client = await self._sb._backend.client()  # pyright: ignore[reportPrivateUsage]
        self._exec_id = await self._sb._exec_create(self._argv, self._env)  # pyright: ignore[reportPrivateUsage]
        self._deadline = anyio.current_time() + self._limit
        self._record = self._sb._record("exec", argv=self._argv)  # pyright: ignore[reportPrivateUsage]
        exec_id, q = self._exec_id, self._queue

        def pump() -> None:
            try:
                for out, err in client.api.exec_start(exec_id, stream=True, demux=True):
                    if out:
                        q.put(OutputChunk("stdout", out))
                    if err:
                        q.put(OutputChunk("stderr", err))
                code = client.api.exec_inspect(exec_id).get("ExitCode")
                q.put(_Done(int(code) if code is not None else KILLED_EXIT))
            except Exception as exc:
                q.put(_Done(exc))

        threading.Thread(
            target=pump, name=f"sandboxio-stream-{exec_id[:8]}", daemon=True
        ).start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._exit_code is None:
            await shielded_kill(
                self.kill,
                sandbox_id=self._sb.id,
                backend="docker",
                labels=self._sb.labels,
            )
        await self._emit()

    async def _emit(self) -> None:
        if self._record is None:
            return
        record, self._record = self._record, None
        record.exit_code = self._exit_code
        async with operation(
            record,
            config=self._sb._backend.audit,  # pyright: ignore[reportPrivateUsage]
            redact=self._sb._redact,  # pyright: ignore[reportPrivateUsage]
        ):
            pass

    async def __aiter__(self) -> AsyncIterator[OutputChunk]:
        assert self._exec_id is not None, "enter the context first: `async with sb.stream(...)`"
        while self._exit_code is None:
            try:
                with anyio.fail_after(max(self._deadline - anyio.current_time(), 0.0)):
                    item = await _thread(self._queue.get)
            except TimeoutError as exc:
                await self._sb._kill_processes()  # pyright: ignore[reportPrivateUsage]
                self._exit_code = KILLED_EXIT
                raise ExecutionTimeout(
                    f"stream exceeded {self._limit}s in sandbox {self._sb.id}"
                ) from exc
            except anyio.get_cancelled_exc_class():
                await self._sb._kill_processes()  # pyright: ignore[reportPrivateUsage]
                self._exit_code = KILLED_EXIT
                raise
            if isinstance(item, _Done):
                self._exit_code = (
                    KILLED_EXIT if isinstance(item.outcome, Exception) else item.outcome
                )
                if isinstance(item.outcome, Exception):
                    if _gone(item.outcome):
                        raise self._sb._gone() from item.outcome  # pyright: ignore[reportPrivateUsage]
                    raise ExecutionError(
                        ExecResult(KILLED_EXIT, "", f"docker: {item.outcome}")
                    ) from item.outcome
                return
            yield item

    async def wait(self) -> ExecResult:
        async for _ in self:  # unconsumed output is drained and discarded
            pass
        assert self._exit_code is not None
        return ExecResult(self._exit_code, "", "", streamed=True)

    async def kill(self) -> None:
        if self._exit_code is None:
            self._exit_code = KILLED_EXIT
            await self._sb._kill_processes()  # pyright: ignore[reportPrivateUsage]
        await anyio.lowlevel.checkpoint()


class DockerFileSystem:
    """Archive endpoints for read/write; ``find``/``mkdir``/``rm`` in the image for the rest."""

    def __init__(self, sb: DockerSandbox) -> None:
        self._sb = sb

    async def _op(self, event: str, path: str) -> Any:
        return operation(
            self._sb._record(event, argv=[path]),  # pyright: ignore[reportPrivateUsage]
            config=self._sb._backend.audit,  # pyright: ignore[reportPrivateUsage]
            redact=self._sb._redact,  # pyright: ignore[reportPrivateUsage]
        )

    def _map_fs(self, exc: Exception, path: str) -> Exception:
        import docker.errors

        if isinstance(exc, docker.errors.NotFound):
            return PathNotFound(path)
        mapped = _map_common(exc, sandbox_id=self._sb.id)
        return mapped if mapped is not None else FileSystemError(f"docker: {exc}")

    async def read(self, path: str) -> bytes:
        async with await self._op("file_read", path) as record:
            try:
                stream, _stat = await _thread(self._sb.native.get_archive, path)
                data = await _thread(lambda: b"".join(stream))
            except Exception as exc:
                raise self._map_fs(exc, path) from exc
            with tarfile.open(fileobj=io.BytesIO(data)) as tar:
                member = next((m for m in tar.getmembers() if m.isfile()), None)
                if member is None:
                    raise FileSystemError(f"{path!r} is not a regular file")
                extracted = tar.extractfile(member)
                payload = extracted.read() if extracted is not None else b""
            record.bytes_out = len(payload)
            record.exit_code = 0
        return payload

    async def write(self, path: str, data: bytes | str) -> None:
        payload = data.encode() if isinstance(data, str) else bytes(data)
        parent, name = posixpath.split(path.rstrip("/"))
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        async with await self._op("file_write", path) as record:
            try:
                ok = await _thread(self._sb.native.put_archive, parent or "/", buf.getvalue())
            except Exception as exc:
                raise self._map_fs(exc, parent or "/") from exc
            if not ok:
                raise FileSystemError(f"docker refused to write {path!r}")
            record.bytes_in = len(payload)
            record.exit_code = 0

    async def upload(self, local: str | Path, remote: str) -> None:
        self._sb._need(Capability.UPLOAD_DOWNLOAD)  # pyright: ignore[reportPrivateUsage]
        await self.write(remote, await _thread(Path(local).read_bytes))

    async def download(self, remote: str, local: str | Path) -> None:
        self._sb._need(Capability.UPLOAD_DOWNLOAD)  # pyright: ignore[reportPrivateUsage]
        data = await self.read(remote)
        await _thread(Path(local).write_bytes, data)

    async def _sh(self, event: str, path: str, argv: list[str]) -> ExecResult:
        async with await self._op(event, path) as record:
            result = await self._sb._exec_run(argv, None, 60)  # pyright: ignore[reportPrivateUsage]
            record.exit_code = result.exit_code
        return result

    async def ls(self, path: str = ".") -> list[FileInfo]:
        argv = ["find", path, "-mindepth", "1", "-maxdepth", "1", "-printf", "%y\\t%s\\t%p\\n"]
        result = await self._sh("file_ls", path, argv)
        if result.exit_code != 0:
            raise PathNotFound(path)
        entries: list[FileInfo] = []
        for line in result.stdout.splitlines():
            kind, size, name = line.split("\t", 2)
            entries.append(FileInfo(name, int(size) if kind != "d" else 0, kind == "d"))
        return sorted(entries, key=lambda e: e.path)

    async def mkdir(self, path: str, *, parents: bool = False) -> None:
        argv = ["mkdir", "-p", path] if parents else ["mkdir", path]
        result = await self._sh("file_mkdir", path, argv)
        if result.exit_code != 0:
            if "No such file" in result.stderr:
                raise PathNotFound(posixpath.dirname(path.rstrip("/")))
            raise FileSystemError(f"mkdir {path!r} failed: {result.stderr.strip()}")

    async def remove(self, path: str) -> None:
        result = await self._sh("file_remove", path, ["rm", "-r", "--", path])
        if result.exit_code != 0:
            if "No such file" in result.stderr:
                raise PathNotFound(path)
            raise FileSystemError(f"rm {path!r} failed: {result.stderr.strip()}")
