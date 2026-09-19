"""The E2B adapter: Firecracker microVMs via the async ``e2b-code-interpreter`` SDK."""

from __future__ import annotations

# The SDK's typing is partial in places (TypedDict opts, untyped callbacks), and
# e2b_code_interpreter ships no py.typed marker.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
import contextlib
import json
import math
import os
import shlex
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

import anyio
from e2b.exceptions import (
    AuthenticationException,
    FileNotFoundException,
    NotEnoughSpaceException,
    NotFoundException,
    RateLimitException,
    SandboxNotFoundException,
    TimeoutException,
)
from e2b.sandbox.commands.command_handle import CommandExitException
from e2b.sandbox.filesystem.filesystem import FileType
from e2b_code_interpreter import AsyncSandbox as NativeSandbox

from sandboxio import _policy
from sandboxio._record import OperationRecord, Redactor, operation
from sandboxio._teardown import shielded_kill
from sandboxio.api import BackendConfig
from sandboxio.audit import AuditConfig
from sandboxio.errors import (
    AuthError,
    CapabilityNotSupported,
    ConfigurationError,
    ConnectError,
    CreateTimeout,
    CreationError,
    ExecutionError,
    ExecutionTimeout,
    FileSystemError,
    PathNotFound,
    RateLimitError,
    ResourceLimitExceeded,
    SandboxGone,
)
from sandboxio.models import (
    Capability,
    ExecResult,
    FileInfo,
    IsolationTier,
    NetworkPolicy,
    OutputChunk,
    Resources,
    RichOutput,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from types import TracebackType

    from e2b_code_interpreter.models import Context, Execution, Result

__all__ = ["E2BBackend", "E2BConfig", "E2BProcess", "E2BSandbox"]

API_KEY_ENV = "E2B_API_KEY"
DEFAULT_TEMPLATE = "code-interpreter-v1"
WORKDIR = "/home/user"
KILLED_EXIT = 137
META_MANAGED = "sandboxio_managed"
META_SESSION = "sandboxio_session"
SESSION_ID = uuid.uuid4().hex
CAPABILITIES = (
    Capability.RUN_COMMAND
    | Capability.RUN_CODE
    | Capability.STATEFUL_CODE
    | Capability.STREAMING
    | Capability.FILESYSTEM
    | Capability.UPLOAD_DOWNLOAD
    | Capability.NETWORK_POLICY
)
# Jupyter display formats → MIME types. Binary formats arrive base64-encoded already.
FORMATS = {
    "text": "text/plain",
    "html": "text/html",
    "markdown": "text/markdown",
    "svg": "image/svg+xml",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "pdf": "application/pdf",
    "latex": "text/latex",
    "json": "application/json",
    "javascript": "application/javascript",
}


@dataclass(frozen=True)
class E2BConfig(BackendConfig):
    """Typed configuration: ``template`` is the E2B template name or id."""

    backend: ClassVar[str] = "e2b"


def _lifetime(seconds: float) -> int:
    return max(1, math.ceil(seconds))


def _is_gone(exc: BaseException) -> bool:
    if isinstance(exc, FileNotFoundException):
        return False
    text = str(exc).lower()
    return isinstance(exc, SandboxNotFoundException) or (
        "sandbox" in text
        and ("not found" in text or "not running" in text or "timeout" in text)
    )


def _map_common(exc: Exception, *, sandbox_id: str) -> Exception | None:
    """Map SDK exceptions shared by every operation; None means 'not one of ours'."""
    if isinstance(exc, AuthenticationException):
        return AuthError("e2b", env_var=API_KEY_ENV)
    if isinstance(exc, RateLimitException):
        return RateLimitError("e2b throttled the request")
    if isinstance(exc, NotEnoughSpaceException):
        return ResourceLimitExceeded("disk_mb", value="template limit")
    if _is_gone(exc):
        return SandboxGone(f"sandbox {sandbox_id} no longer exists on e2b")
    return None


class E2BBackend:
    """Firecracker microVMs with a live code interpreter.

    >>> backend = E2BBackend(template="code-interpreter-v1")  # doctest: +SKIP
    """

    name = "e2b"
    capabilities = CAPABILITIES
    isolation = IsolationTier.MICROVM

    def __init__(
        self,
        *,
        template: str = DEFAULT_TEMPLATE,
        audit: AuditConfig | None = None,
        api_key: str | None = None,
    ) -> None:
        self.template = template
        self.audit = audit or AuditConfig()
        self.session_id = SESSION_ID
        self._api_key = api_key

    def _key(self) -> str:
        key = self._api_key or os.environ.get(API_KEY_ENV)
        if not key:
            raise AuthError(self.name, env_var=API_KEY_ENV)
        return key

    def metadata(self, metadata: Mapping[str, str] | None) -> dict[str, str]:
        return {**(metadata or {}), META_MANAGED: "true", META_SESSION: self.session_id}

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
    ) -> E2BSandbox:
        _policy.validate_request(
            resources=resources,
            network=network,
            timeout=timeout,
            capabilities=self.capabilities,
            backend=self.name,
            allowlist_supported=True,
        )
        if (resources.cpu, resources.memory_mb, resources.disk_mb) != (None, None, None):
            raise ConfigurationError(
                "CPU, memory and disk on e2b come from the template; per-sandbox caps are "
                "refused rather than ignored.",
                hint="Pick a template with the resources you need and drop Resources(...).",
            )
        key = self._key()
        kwargs: dict[str, Any] = {
            "template": template or self.template,
            "timeout": _lifetime(timeout),
            "metadata": self.metadata(metadata),
            "envs": {**(env or {}), **(secrets or {})},
            "api_key": key,
        }
        if network.egress == "deny" and network.allow:
            # Deny everything, then allow the listed hosts; allow rules take precedence.
            kwargs["network"] = {"deny_out": ["0.0.0.0/0"], "allow_out": list(network.allow)}
        else:
            kwargs["allow_internet_access"] = network.egress == "allow"

        try:
            with anyio.fail_after(timeout):
                native = await NativeSandbox.create(**kwargs)
        except TimeoutError as exc:
            # If the sandbox was created we do not know its id; its own lifetime reclaims it.
            raise CreateTimeout(f"create() exceeded {timeout}s on e2b") from exc
        except anyio.get_cancelled_exc_class():
            raise
        except Exception as exc:
            mapped = _map_common(exc, sandbox_id="?")
            if mapped is not None:
                raise mapped from exc
            raise CreationError(
                f"e2b could not create a sandbox from {kwargs['template']!r}"
            ) from exc

        sb = E2BSandbox(
            self,
            native,
            network=network,
            secrets=secrets or {},
            env=env or {},
            timeout=float(timeout),
            metadata=metadata or {},
        )
        try:
            await anyio.lowlevel.checkpoint_if_cancelled()
        except anyio.get_cancelled_exc_class():
            await shielded_kill(sb.kill, sandbox_id=sb.id, backend=self.name, labels=sb.labels)
            raise
        return sb

    async def connect(self, sandbox_id: str) -> E2BSandbox:
        key = self._key()
        try:
            # The SDK overloads connect() as both classmethod and instance method.
            native = cast("NativeSandbox", await NativeSandbox.connect(sandbox_id, api_key=key))
            info = await native.get_info()
        except Exception as exc:
            mapped = _map_common(exc, sandbox_id=sandbox_id)
            if isinstance(mapped, AuthError):
                raise mapped from exc
            raise ConnectError(f"no running e2b sandbox {sandbox_id!r}") from exc
        if info.metadata.get(META_MANAGED) != "true":
            raise ConnectError(f"e2b sandbox {sandbox_id!r} is not a sandboxio sandbox")
        metadata = {
            k: v for k, v in info.metadata.items() if k not in (META_MANAGED, META_SESSION)
        }
        remaining = max(1.0, (info.end_at - info.started_at).total_seconds())
        return E2BSandbox(
            self,
            native,
            network=NetworkPolicy(egress="allow" if info.allow_internet_access else "deny"),
            secrets={},
            env={},
            timeout=remaining,
            metadata=metadata,
        )


class E2BSandbox:
    """A running microVM. ``native`` is the SDK's ``AsyncSandbox`` (PTY, pause, snapshots)."""

    def __init__(
        self,
        backend: E2BBackend,
        native: NativeSandbox,
        *,
        network: NetworkPolicy,
        secrets: Mapping[str, str],
        env: Mapping[str, str],
        timeout: float,
        metadata: Mapping[str, str],
    ) -> None:
        self._backend = backend
        self._native = native
        self.id = native.sandbox_id
        self.capabilities = backend.capabilities
        self.isolation = backend.isolation
        self.network = network
        self.timeout = timeout
        self.labels: dict[str, str] = dict(metadata)
        self._redact = Redactor(secrets, env)
        self._killed = False
        self._contexts: dict[str | None, Context] = {}
        self._fs = E2BFileSystem(self)

    def __repr__(self) -> str:
        state = "killed" if self._killed else "running"
        caps = "|".join(c.name or "" for c in Capability if c in self.capabilities)
        return f"<E2BSandbox e2b:{self.id} {self.isolation.value} {state} caps={caps}>"

    # --- plumbing ---------------------------------------------------------------------------

    def _need(self, cap: Capability) -> None:
        if cap not in self.capabilities:
            raise CapabilityNotSupported(cap, backend="e2b")

    def _effective_timeout(self, timeout: float | None) -> float:
        _policy.validate_timeout(timeout)
        return self.timeout if timeout is None else timeout

    def _gone(self) -> SandboxGone:
        return SandboxGone(f"sandbox {self.id} no longer exists on e2b")

    def _map(self, exc: Exception) -> Exception:
        mapped = _map_common(exc, sandbox_id=self.id)
        if mapped is not None:
            return mapped
        return ExecutionError(ExecResult(KILLED_EXIT, "", f"e2b: {exc}"))

    def _record(self, event: str, **fields: Any) -> OperationRecord:
        return OperationRecord(
            event=event,
            sandbox_id=self.id,
            backend="e2b",
            isolation=self.isolation,
            metadata=self.labels,
            **fields,
        )

    @staticmethod
    def _shell(cmd: str | list[str]) -> str:
        # E2B only runs shell strings; quoting a list keeps every argument literal.
        return cmd if isinstance(cmd, str) else shlex.join(cmd)

    # --- run --------------------------------------------------------------------------------

    async def run(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        self._need(Capability.RUN_COMMAND)
        if self._killed:
            raise self._gone()
        limit = self._effective_timeout(timeout)
        argv = cmd if isinstance(cmd, list) else [cmd]
        record = self._record("exec", argv=argv)
        async with operation(record, config=self._backend.audit, redact=self._redact):
            result = await self._run_command(self._shell(cmd), env, limit)
            record.exit_code = result.exit_code
            record.bytes_out = len(result.stdout) + len(result.stderr)
        return result

    async def _run_command(
        self, command: str, env: Mapping[str, str] | None, limit: float
    ) -> ExecResult:
        try:
            handle = await self._native.commands.run(
                command, background=True, envs=dict(env or {}), cwd=WORKDIR, timeout=0
            )
        except Exception as exc:
            raise self._map(exc) from exc
        try:
            with anyio.fail_after(limit):
                result = await handle.wait()
        except TimeoutError as exc:
            await self._kill_handle(handle)
            raise ExecutionTimeout(f"execution exceeded {limit}s in sandbox {self.id}") from exc
        except anyio.get_cancelled_exc_class():
            await self._kill_handle(handle)
            raise
        except CommandExitException as exc:
            return ExecResult(int(exc.exit_code), exc.stdout, exc.stderr)
        except TimeoutException as exc:
            # The SDK reports a dropped stream as a timeout; the usual cause is the sandbox's
            # own lifetime ending under the command — which is SandboxGone, not a timeout.
            raise (await self._gone_or(exc)) from exc
        except Exception as exc:
            raise self._map(exc) from exc
        return ExecResult(int(result.exit_code), result.stdout, result.stderr)

    async def _gone_or(self, exc: Exception) -> Exception:
        with anyio.CancelScope(shield=True), anyio.move_on_after(10):
            try:
                if not await self._native.is_running():
                    self._killed = True
                    return self._gone()
            except Exception:
                self._killed = True
                return self._gone()
        return self._map(exc)

    async def _kill_handle(self, handle: Any) -> None:
        # Already dead is fine.
        with (
            anyio.CancelScope(shield=True),
            anyio.move_on_after(10),
            contextlib.suppress(Exception),
        ):
            await handle.kill()

    # --- run_code ---------------------------------------------------------------------------

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
            self._need(Capability.STATEFUL_CODE)
        if self._killed:
            raise self._gone()
        limit = self._effective_timeout(timeout)
        record = self._record("run_code", code=code)
        async with operation(record, config=self._backend.audit, redact=self._redact):
            context = await self._context(context_id, language)
            try:
                with anyio.fail_after(limit):
                    execution = await self._native.run_code(
                        code, context=context, timeout=limit
                    )
            except TimeoutError as exc:
                await self._restart_context(context)
                raise ExecutionTimeout(
                    f"execution exceeded {limit}s in sandbox {self.id}"
                ) from exc
            except anyio.get_cancelled_exc_class():
                await self._restart_context(context)
                raise
            except Exception as exc:
                if isinstance(exc, TimeoutException):
                    await self._restart_context(context)
                    raise ExecutionTimeout(
                        f"execution exceeded {limit}s in sandbox {self.id}"
                    ) from exc
                raise self._map(exc) from exc
            result = _to_result(execution)
            record.exit_code = result.exit_code
            record.bytes_in = len(code)
            record.bytes_out = len(result.stdout) + len(result.stderr)
        return result

    async def _context(self, context_id: str | None, language: str) -> Context:
        """Every run owns a context we can restart; ``None`` is our private default."""
        if context_id not in self._contexts:
            try:
                self._contexts[context_id] = await self._native.create_code_context(
                    cwd=WORKDIR, language=language
                )
            except Exception as exc:
                raise self._map(exc) from exc
        return self._contexts[context_id]

    async def _restart_context(self, context: Context) -> None:
        """The only way to stop a running cell: restart its kernel."""
        # The sandbox may be gone; that is fine.
        with (
            anyio.CancelScope(shield=True),
            anyio.move_on_after(15),
            contextlib.suppress(Exception),
        ):
            await self._native.restart_code_context(context)

    # --- streaming --------------------------------------------------------------------------

    def stream(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> E2BProcess:
        self._need(Capability.STREAMING)
        if self._killed:
            raise self._gone()
        argv = cmd if isinstance(cmd, list) else [cmd]
        return E2BProcess(self, self._shell(cmd), argv, env, self._effective_timeout(timeout))

    # --- lifecycle --------------------------------------------------------------------------

    async def kill(self) -> None:
        if self._killed:
            await anyio.lowlevel.checkpoint()
            return
        self._killed = True
        try:
            await self._native.kill()
        except Exception as exc:
            if not _is_gone(exc):
                raise self._map(exc) from exc

    @property
    def files(self) -> E2BFileSystem:
        self._need(Capability.FILESYSTEM)
        return self._fs

    @property
    def native(self) -> NativeSandbox:
        return self._native

    async def __aenter__(self) -> E2BSandbox:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await shielded_kill(self.kill, sandbox_id=self.id, backend="e2b", labels=self.labels)


def _to_result(execution: Execution) -> ExecResult:
    stdout = "".join(_line(s) for s in execution.logs.stdout)
    stderr = "".join(_line(s) for s in execution.logs.stderr)
    exit_code = 0
    if execution.error is not None:
        exit_code = 1
        stderr += (
            f"{execution.error.traceback}\n{execution.error.name}: {execution.error.value}\n"
        )
    results = tuple(r for res in execution.results for r in _rich(res))
    return ExecResult(exit_code, stdout, stderr, results=results)


def _line(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def _rich(result: Result) -> list[RichOutput]:
    out: list[RichOutput] = []
    for attr, mime in FORMATS.items():
        value = getattr(result, attr, None)
        if value is None:
            continue
        out.append(
            RichOutput(mime, json.dumps(value) if isinstance(value, dict) else str(value))
        )
    return out


class E2BProcess:
    """A streamed command. Output callbacks feed a buffer; completion is polled via the pid."""

    def __init__(
        self,
        sb: E2BSandbox,
        command: str,
        argv: list[str],
        env: Mapping[str, str] | None,
        limit: float,
    ) -> None:
        self._sb = sb
        self._command = command
        self._argv = argv
        self._env = env
        self._limit = limit
        self._handle: Any = None
        self._buffer: list[OutputChunk] = []
        self._exit_code: int | None = None
        self._deadline = 0.0
        self._record: OperationRecord | None = None

    @property
    def returncode(self) -> int | None:
        return self._exit_code

    async def __aenter__(self) -> E2BProcess:
        self._deadline = anyio.current_time() + self._limit
        self._record = self._sb._record("exec", argv=self._argv)  # pyright: ignore[reportPrivateUsage]
        buffer = self._buffer
        try:
            self._handle = await self._sb.native.commands.run(
                self._command,
                background=True,
                envs=dict(self._env or {}),
                cwd=WORKDIR,
                timeout=0,
                on_stdout=lambda line: buffer.append(OutputChunk("stdout", line.encode())),
                on_stderr=lambda line: buffer.append(OutputChunk("stderr", line.encode())),
            )
        except Exception as exc:
            raise self._sb._map(exc) from exc  # pyright: ignore[reportPrivateUsage]
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._exit_code is None:
            await shielded_kill(
                self.kill, sandbox_id=self._sb.id, backend="e2b", labels=self._sb.labels
            )
        if self._record is not None:
            record, self._record = self._record, None
            record.exit_code = self._exit_code
            async with operation(
                record,
                config=self._sb._backend.audit,  # pyright: ignore[reportPrivateUsage]
                redact=self._sb._redact,  # pyright: ignore[reportPrivateUsage]
            ):
                pass

    async def __aiter__(self) -> AsyncIterator[OutputChunk]:
        assert self._handle is not None, "enter the context first: `async with sb.stream(...)`"
        while True:
            if self._buffer:
                yield self._buffer.pop(0)
                continue
            if self._exit_code is not None:
                return
            if self._handle.exit_code is not None:
                self._exit_code = int(self._handle.exit_code)
                continue  # drain anything the last callbacks appended
            if anyio.current_time() >= self._deadline:
                await self.kill()
                raise ExecutionTimeout(
                    f"stream exceeded {self._limit}s in sandbox {self._sb.id}"
                )
            try:
                await anyio.sleep(0.02)
            except anyio.get_cancelled_exc_class():
                await self.kill()
                raise

    async def wait(self) -> ExecResult:
        async for _ in self:  # unconsumed output is drained and discarded
            pass
        assert self._exit_code is not None
        return ExecResult(self._exit_code, "", "", streamed=True)

    async def kill(self) -> None:
        if self._exit_code is None:
            self._exit_code = KILLED_EXIT
            if self._handle is not None:
                await self._sb._kill_handle(self._handle)  # pyright: ignore[reportPrivateUsage]
        await anyio.lowlevel.checkpoint()


class E2BFileSystem:
    """The SDK's filesystem API, with paths resolved inside the microVM."""

    def __init__(self, sb: E2BSandbox) -> None:
        self._sb = sb

    def _op(self, event: str, path: str) -> Any:
        return operation(
            self._sb._record(event, argv=[path]),  # pyright: ignore[reportPrivateUsage]
            config=self._sb._backend.audit,  # pyright: ignore[reportPrivateUsage]
            redact=self._sb._redact,  # pyright: ignore[reportPrivateUsage]
        )

    def _map_fs(self, exc: Exception, path: str) -> Exception:
        if isinstance(exc, FileNotFoundException):
            return PathNotFound(path)
        if isinstance(exc, NotFoundException) and not _is_gone(exc):
            return PathNotFound(path)
        if "not found" in str(exc).lower() or "no such file" in str(exc).lower():
            return PathNotFound(path)
        mapped = _map_common(exc, sandbox_id=self._sb.id)
        return mapped if mapped is not None else FileSystemError(f"e2b: {exc}")

    async def read(self, path: str) -> bytes:
        async with self._op("file_read", path) as record:
            try:
                data = await self._sb.native.files.read(path, format="bytes")
            except Exception as exc:
                raise self._map_fs(exc, path) from exc
            payload = bytes(data)
            record.bytes_out = len(payload)
            record.exit_code = 0
        return payload

    async def write(self, path: str, data: bytes | str) -> None:
        payload = data.encode() if isinstance(data, str) else bytes(data)
        async with self._op("file_write", path) as record:
            try:
                await self._sb.native.files.write(path, payload)
            except Exception as exc:
                raise self._map_fs(exc, path) from exc
            record.bytes_in = len(payload)
            record.exit_code = 0

    async def upload(self, local: str | Path, remote: str) -> None:
        self._sb._need(Capability.UPLOAD_DOWNLOAD)  # pyright: ignore[reportPrivateUsage]
        await self.write(remote, Path(local).read_bytes())

    async def download(self, remote: str, local: str | Path) -> None:
        self._sb._need(Capability.UPLOAD_DOWNLOAD)  # pyright: ignore[reportPrivateUsage]
        Path(local).write_bytes(await self.read(remote))

    async def ls(self, path: str = ".") -> list[FileInfo]:
        async with self._op("file_ls", path) as record:
            try:
                entries = await self._sb.native.files.list(path, depth=1)
            except Exception as exc:
                raise self._map_fs(exc, path) from exc
            record.exit_code = 0
        return sorted(
            (
                FileInfo(
                    e.path, e.size if e.type != FileType.DIR else 0, e.type == FileType.DIR
                )
                for e in entries
            ),
            key=lambda e: e.path,
        )

    async def mkdir(self, path: str, *, parents: bool = False) -> None:
        async with self._op("file_mkdir", path) as record:
            try:
                if not parents:
                    parent = path.rstrip("/").rsplit("/", 1)[0] or "/"
                    if not await self._sb.native.files.exists(parent):
                        raise PathNotFound(parent)
                await self._sb.native.files.make_dir(path)
            except PathNotFound:
                raise
            except Exception as exc:
                raise self._map_fs(exc, path) from exc
            record.exit_code = 0

    async def remove(self, path: str) -> None:
        async with self._op("file_remove", path) as record:
            try:
                if not await self._sb.native.files.exists(path):
                    raise PathNotFound(path)
                await self._sb.native.files.remove(path)
            except PathNotFound:
                raise
            except Exception as exc:
                raise self._map_fs(exc, path) from exc
            record.exit_code = 0
