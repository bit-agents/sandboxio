"""``FakeBackend``: in-memory, deterministic, executes nothing (spec/08).

A supported product surface, not a test helper: it passes the same contract suite as the
real adapters. Commands are interpreted by a tiny virtual shell (``echo``, ``sh -c``,
``printenv``, ``seq``, ``sleep``, ``curl``, ``cat``) so the suite's defaults work unscripted;
anything else is scripted with ``on_run`` / ``on_run_code`` or exits 127.

Time is virtual: ``time_scale`` real seconds per virtual second (default 0.01), so a
``timeout=300`` still fires — in three seconds.
"""

from __future__ import annotations

import ast
import itertools
import posixpath
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import anyio

from sandboxio import _policy
from sandboxio._record import OperationRecord, Redactor, operation
from sandboxio._teardown import shielded_kill
from sandboxio.audit import AuditConfig
from sandboxio.errors import (
    AuthError,
    CapabilityNotSupported,
    ConnectError,
    CreateTimeout,
    CreationError,
    ExecutionTimeout,
    PathNotFound,
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
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
    from types import TracebackType

__all__ = ["FakeBackend", "FakeProcess", "FakeSandbox", "RecordedCall"]

DEFAULT_CAPABILITIES = (
    Capability.RUN_COMMAND
    | Capability.RUN_CODE
    | Capability.STATEFUL_CODE
    | Capability.STREAMING
    | Capability.FILESYSTEM
    | Capability.UPLOAD_DOWNLOAD
    | Capability.NETWORK_POLICY
)
KILLED_EXIT = 137
WORKDIR = "/work"


@dataclass(frozen=True, slots=True)
class RecordedCall:
    """One call the fake received. Compare fields with ``==``; ``calls[0]`` is the create."""

    op: str
    sandbox_id: str | None = None
    cmd: tuple[str, ...] | None = None
    code: str | None = None
    context_id: str | None = None
    path: str | None = None
    template: str | None = None
    resources: Resources | None = None
    network: NetworkPolicy | None = None
    timeout: float | None = None
    metadata: Mapping[str, str] | None = None
    env_keys: tuple[str, ...] = ()
    secret_keys: tuple[str, ...] = ()


@dataclass(slots=True)
class _Script:
    match: str
    returns: ExecResult | BaseException | None
    hangs: bool
    delay: float


@dataclass(slots=True)
class _Simulation:
    create_takes: float | None = None
    create_fails: BaseException | None = None
    kill_hangs: bool = False
    auth_missing: bool = False


class FakeBackend:
    """Deterministic in-memory backend. Reports ``CONTAINER`` while isolating nothing.

    >>> fake = FakeBackend()
    >>> fake.on_run_code(match="import pandas", returns=ExecResult(0, "2.2.1\\n", ""))
    """

    name = "fake"
    sandbox_class: ClassVar[type[FakeSandbox]]  # set after FakeSandbox is defined

    def __init__(
        self,
        *,
        capabilities: Capability = DEFAULT_CAPABILITIES,
        isolation: IsolationTier = IsolationTier.CONTAINER,
        audit: AuditConfig | None = None,
        time_scale: float = 0.01,
    ) -> None:
        self.capabilities = capabilities
        self.isolation = isolation
        self.audit = audit or AuditConfig()
        self.time_scale = time_scale
        self.calls: list[RecordedCall] = []
        self.simulation = _Simulation()
        self._run_scripts: list[_Script] = []
        self._code_scripts: list[_Script] = []
        self._live: dict[str, FakeSandbox] = {}
        self._ids = itertools.count(1)
        self._default_sandbox: FakeSandbox | None = None

    # --- scripting ----------------------------------------------------------------------------

    def on_run(
        self,
        match: str,
        returns: ExecResult | BaseException | None = None,
        *,
        hangs: bool = False,
        delay: float = 0.0,
    ) -> None:
        """Script ``run()``: a command containing ``match`` returns/raises/hangs as told."""
        self._run_scripts.append(_Script(match, returns, hangs, delay))

    def on_run_code(
        self,
        match: str,
        returns: ExecResult | BaseException | None = None,
        *,
        hangs: bool = False,
        delay: float = 0.0,
    ) -> None:
        """Script ``run_code()``: code containing ``match`` returns/raises/hangs as told."""
        self._code_scripts.append(_Script(match, returns, hangs, delay))

    def simulate(
        self,
        *,
        create_takes: float | None = None,
        create_fails: BaseException | None = None,
        kill_hangs: bool = False,
        auth_missing: bool = False,
    ) -> None:
        """Make the provider misbehave: slow/failing creates, hanging kills, no credential."""
        self.simulation = _Simulation(create_takes, create_fails, kill_hangs, auth_missing)

    def expire(self, sandbox_id: str) -> None:
        """The provider reclaimed this sandbox; further use raises ``SandboxGone``."""
        sb = self._live.pop(sandbox_id, None)
        if sb is not None:
            sb._expired = True  # pyright: ignore[reportPrivateUsage]

    # --- introspection ------------------------------------------------------------------------

    def live_sandboxes(self) -> int:
        return len(self._live)

    def live_processes(self) -> int:
        return sum(sb.live_processes() for sb in self._live.values())

    @property
    def sandbox(self) -> FakeSandbox:
        """A ready sandbox for tests that do not want to call ``create()`` themselves."""
        if self._default_sandbox is None or not self._default_sandbox.alive:
            self.calls.append(
                RecordedCall(
                    "create",
                    resources=Resources(),
                    network=NetworkPolicy(),
                    timeout=300.0,
                    metadata={},
                )
            )
            self._default_sandbox = self._new_sandbox(
                template=None,
                resources=Resources(),
                network=NetworkPolicy(),
                env=None,
                secrets=None,
                timeout=300.0,
                metadata=None,
            )
        return self._default_sandbox

    # --- Backend protocol ---------------------------------------------------------------------

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
    ) -> FakeSandbox:
        _policy.validate_request(
            resources=resources,
            network=network,
            timeout=timeout,
            capabilities=self.capabilities,
            backend=self.name,
            allowlist_supported=True,
        )
        self.calls.append(
            RecordedCall(
                "create",
                template=template,
                resources=resources,
                network=network,
                timeout=timeout,
                metadata=dict(metadata or {}),
                env_keys=tuple(env or ()),
                secret_keys=tuple(secrets or ()),
            )
        )
        sim = self.simulation
        if sim.auth_missing:
            raise AuthError(self.name, env_var="SBX_FAKE_TOKEN")
        if sim.create_fails is not None:
            raise CreationError(
                "the fake provider refused to create a sandbox"
            ) from sim.create_fails
        if sim.create_takes is not None:
            try:
                with anyio.fail_after(timeout * self.time_scale):
                    await self._vsleep(sim.create_takes)
            except TimeoutError as exc:
                raise CreateTimeout(f"create() exceeded {timeout}s on {self.name}") from exc

        # The provider has "returned an id": own it without a cancellation gap, then kill it
        # if the caller was cancelled meanwhile and nobody will ever own the handle.
        sb = self._own(
            template=template,
            resources=resources,
            network=network,
            env=env,
            secrets=secrets,
            timeout=float(timeout),
            metadata=metadata,
        )
        try:
            await anyio.lowlevel.checkpoint_if_cancelled()
        except anyio.get_cancelled_exc_class():
            await shielded_kill(sb.kill, sandbox_id=sb.id, backend=self.name, labels=sb.labels)
            raise
        return sb

    async def connect(self, sandbox_id: str) -> FakeSandbox:
        await anyio.lowlevel.checkpoint()
        sb = self._live.get(sandbox_id)
        if sb is None:
            raise ConnectError(f"no live sandbox {sandbox_id!r} on {self.name}")
        return sb

    # --- internals ----------------------------------------------------------------------------

    def _own(self, **kwargs: Any) -> FakeSandbox:
        with anyio.CancelScope(shield=True):
            return self._new_sandbox(**kwargs)
        raise AssertionError("unreachable")  # a shielded scope never swallows

    def _new_sandbox(
        self,
        *,
        template: str | None,
        resources: Resources,
        network: NetworkPolicy,
        env: dict[str, str] | None,
        secrets: dict[str, str] | None,
        timeout: float,
        metadata: dict[str, str] | None,
    ) -> FakeSandbox:
        sb = self.sandbox_class(
            self,
            sandbox_id=f"fake-{next(self._ids):04d}",
            template=template,
            resources=resources,
            network=network,
            env=env or {},
            secrets=secrets or {},
            timeout=timeout,
            metadata=metadata or {},
        )
        self._live[sb.id] = sb
        return sb

    async def _vsleep(self, virtual_seconds: float) -> None:
        await anyio.sleep(virtual_seconds * self.time_scale)

    def _script_for(self, scripts: list[_Script], haystack: str) -> _Script | None:
        return next((s for s in scripts if s.match in haystack), None)


class FakeSandbox:
    """A sandbox that runs nothing. Behaves exactly as the contract says, which is the point."""

    def __init__(
        self,
        backend: FakeBackend,
        *,
        sandbox_id: str,
        template: str | None,
        resources: Resources,
        network: NetworkPolicy,
        env: dict[str, str],
        secrets: dict[str, str],
        timeout: float,
        metadata: dict[str, str],
    ) -> None:
        self._backend = backend
        self.id = sandbox_id
        self.template = template
        self.resources = resources
        self.network = network
        self.timeout = timeout
        self.labels: dict[str, str] = dict(metadata)
        self.capabilities = backend.capabilities
        self.isolation = backend.isolation
        self._env = {**env, **secrets}
        self._redact = Redactor(secrets, env)
        self._alive = True
        self._expired = False
        self._procs: set[FakeProcess | object] = set()
        self._contexts: dict[str, dict[str, Any]] = {}
        self._fs = FakeFileSystem(self)
        self._native = FakeNative(self)

    # --- state ------------------------------------------------------------------------------

    @property
    def alive(self) -> bool:
        return self._alive and not self._expired

    def live_processes(self) -> int:
        return len(self._procs)

    def _check_alive(self) -> None:
        if not self.alive:
            raise SandboxGone(f"sandbox {self.id} no longer exists on {self._backend.name}")

    def _need(self, cap: Capability) -> None:
        if cap not in self.capabilities:
            raise CapabilityNotSupported(cap, backend=self._backend.name)

    def _effective_timeout(self, timeout: float | None) -> float:
        _policy.validate_timeout(timeout)
        return self.timeout if timeout is None else timeout

    def _record(self, event: str, **fields: Any) -> OperationRecord:
        return OperationRecord(
            event=event,
            sandbox_id=self.id,
            backend=self._backend.name,
            isolation=self.isolation,
            metadata=self.labels,
            **fields,
        )

    def _log(self, op: str, **fields: Any) -> None:
        self._backend.calls.append(RecordedCall(op, sandbox_id=self.id, **fields))

    def __repr__(self) -> str:
        state = "running" if self.alive else "killed"
        caps = "|".join(c.name or "" for c in Capability if c in self.capabilities)
        return f"<FakeSandbox fake:{self.id} {self.isolation.value} {state} caps={caps}>"

    # --- AsyncSandbox protocol --------------------------------------------------------------

    async def run(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        self._check_alive()
        self._need(Capability.RUN_COMMAND)
        limit = self._effective_timeout(timeout)
        argv = tuple(shlex.split(cmd) if isinstance(cmd, str) else cmd)
        self._log("run", cmd=argv, timeout=timeout, env_keys=tuple(env or ()))
        record = self._record("exec", argv=list(argv))
        async with operation(record, config=self._backend.audit, redact=self._redact):
            result, denials = await self._exec(argv, {**self._env, **(env or {})}, limit)
            record.exit_code = result.exit_code
            record.bytes_out = len(result.stdout) + len(result.stderr)
            record.network_denials = denials
        return result

    async def run_code(
        self,
        code: str,
        *,
        language: str = "python",
        context_id: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        self._check_alive()
        self._need(Capability.RUN_CODE)
        if context_id is not None:
            self._need(Capability.STATEFUL_CODE)
        limit = self._effective_timeout(timeout)
        self._log("run_code", code=code, context_id=context_id, timeout=timeout)
        record = self._record("run_code", code=code)
        async with operation(record, config=self._backend.audit, redact=self._redact):
            script = self._backend._script_for(self._backend._code_scripts, code)  # pyright: ignore[reportPrivateUsage]
            result = await self._guarded(
                limit,
                lambda: self._scripted_or(
                    script, lambda: self._interpret_code(code, context_id)
                ),
            )
            record.exit_code = result.exit_code
            record.bytes_in = len(code)
            record.bytes_out = len(result.stdout) + len(result.stderr)
        return result

    def stream(
        self,
        cmd: str | list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> FakeProcess:
        self._check_alive()
        self._need(Capability.STREAMING)
        limit = self._effective_timeout(timeout)
        argv = tuple(shlex.split(cmd) if isinstance(cmd, str) else cmd)
        self._log("stream", cmd=argv, timeout=timeout, env_keys=tuple(env or ()))
        return FakeProcess(self, argv, {**self._env, **(env or {})}, limit)

    async def kill(self) -> None:
        if self._backend.simulation.kill_hangs:
            await anyio.sleep_forever()
        if not self._alive:
            await anyio.lowlevel.checkpoint()
            return
        self._alive = False
        for proc in list(self._procs):
            if isinstance(proc, FakeProcess):
                proc._finish(KILLED_EXIT)  # pyright: ignore[reportPrivateUsage]
        self._procs.clear()
        self._backend._live.pop(self.id, None)  # pyright: ignore[reportPrivateUsage]
        self._log("kill")
        await anyio.lowlevel.checkpoint()

    @property
    def files(self) -> FakeFileSystem:
        self._need(Capability.FILESYSTEM)
        return self._fs

    @property
    def native(self) -> FakeNative:
        return self._native

    async def __aenter__(self) -> FakeSandbox:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await shielded_kill(
            self.kill, sandbox_id=self.id, backend=self._backend.name, labels=self.labels
        )

    # --- execution --------------------------------------------------------------------------

    async def _guarded(
        self, limit: float, work: Callable[[], Awaitable[ExecResult]]
    ) -> ExecResult:
        """Run ``work`` as a tracked process under the virtual deadline."""
        token = object()
        self._procs.add(token)
        try:
            with anyio.fail_after(limit * self._backend.time_scale):
                return await work()
        except TimeoutError as exc:
            raise ExecutionTimeout(
                f"execution exceeded {limit}s in sandbox {self.id}",
            ) from exc
        finally:
            self._procs.discard(token)

    async def _scripted_or(
        self, script: _Script | None, fallback: Callable[[], Awaitable[ExecResult]]
    ) -> ExecResult:
        if script is None:
            await anyio.lowlevel.checkpoint()
            return await fallback()
        if script.delay:
            await self._backend._vsleep(script.delay)  # pyright: ignore[reportPrivateUsage]
        if script.hangs:
            await anyio.sleep_forever()
        returns = script.returns
        if isinstance(returns, BaseException):
            raise returns
        await anyio.lowlevel.checkpoint()
        return returns if returns is not None else ExecResult(0, "", "")

    async def _exec(
        self, argv: tuple[str, ...], env: Mapping[str, str], limit: float
    ) -> tuple[ExecResult, int]:
        script = self._backend._script_for(self._backend._run_scripts, " ".join(argv))  # pyright: ignore[reportPrivateUsage]
        shell = _VirtualShell(self, env)

        async def go() -> ExecResult:
            return await self._scripted_or(script, lambda: shell.run(argv))

        result = await self._guarded(limit, go)
        return result, shell.denials

    async def _interpret_code(self, code: str, context_id: str | None) -> ExecResult:
        """Recognise assignments, literals and prints without executing anything (spec/08)."""
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return ExecResult(
                1, "", f'  File "<fake>", line {exc.lineno}\nSyntaxError: {exc.msg}\n'
            )
        scope = self._contexts.setdefault(context_id, {}) if context_id is not None else {}
        out: list[str] = []
        for node in tree.body:
            try:
                _step(node, scope, out)
            except _Unsupported:
                continue
            except _CodeError as exc:
                return ExecResult(1, "".join(out), f"Traceback (fake)\n{exc}\n")
        return ExecResult(0, "".join(out), "")


class _Unsupported(Exception):
    """A construct the fake does not model; it is ignored, never executed."""


class _CodeError(Exception):
    """What the fake reports as a runtime error."""


_BINOPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
}


def _eval(node: ast.expr, scope: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in scope:
            raise _CodeError(f"NameError: name {node.id!r} is not defined")
        return scope[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval(node.left, scope), _eval(node.right, scope)
        if not isinstance(left, (int, float, str)) or not isinstance(right, (int, float, str)):
            raise _Unsupported
        try:
            return _BINOPS[type(node.op)](left, right)
        except (TypeError, ZeroDivisionError) as exc:
            raise _CodeError(f"{type(exc).__name__}: {exc}") from None
    raise _Unsupported


def _step(node: ast.stmt, scope: dict[str, Any], out: list[str]) -> None:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name):
            scope[target.id] = _eval(node.value, scope)
        return
    if isinstance(node, ast.Raise):
        name = "Exception"
        exc = node.exc
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            name = exc.func.id
        elif isinstance(exc, ast.Name):
            name = exc.id
        raise _CodeError(name)
    if isinstance(node, ast.Expr):
        call = node.value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "print"
        ):
            out.append(" ".join(str(_eval(a, scope)) for a in call.args) + "\n")
            return
    raise _Unsupported


FakeBackend.sandbox_class = FakeSandbox


class _VirtualShell:
    """Enough of a shell for the contract suite's defaults. Executes nothing real.

    Output is produced lazily, one chunk per line, so a script that prints and then sleeps
    streams its first line before it blocks — as a real process would.
    """

    def __init__(self, sb: FakeSandbox, env: Mapping[str, str]) -> None:
        self._sb = sb
        self._env = env
        self.denials = 0
        self.exit_code = 0

    async def run(self, argv: tuple[str, ...]) -> ExecResult:
        out: list[bytes] = []
        err: list[bytes] = []
        async for chunk in self.stream(argv):
            (out if chunk.stream == "stdout" else err).append(chunk.data)
        return ExecResult(
            self.exit_code,
            b"".join(out).decode(errors="replace"),
            b"".join(err).decode(errors="replace"),
        )

    async def stream(self, argv: tuple[str, ...]) -> AsyncIterator[OutputChunk]:
        self.exit_code = 0
        await anyio.lowlevel.checkpoint()
        if not argv:
            return
        prog, *args = argv
        if prog == "echo":
            yield _out(self._echo(args))
        elif prog == "true":
            pass
        elif prog == "false":
            self.exit_code = 1
        elif prog == "printenv":
            value = self._env.get(args[0]) if args else None
            if value is None:
                self.exit_code = 1
            else:
                yield _out(f"{value}\n")
        elif prog == "env":
            for key, value in self._env.items():
                yield _out(f"{key}={value}\n")
        elif prog == "seq" and len(args) == 2:
            for i in range(int(args[0]), int(args[1]) + 1):
                yield _out(f"{i}\n")
        elif prog == "sleep":
            await self._sb._backend._vsleep(  # pyright: ignore[reportPrivateUsage]
                float(args[0]) if args else 0.0
            )
        elif prog in ("curl", "wget"):
            async for chunk in self._egress(args):
                yield chunk
        elif prog == "cat":
            try:
                data = self._sb._fs.read_sync(args[0])  # pyright: ignore[reportPrivateUsage]
            except PathNotFound:
                self.exit_code = 1
                yield _err(f"cat: {args[0]}: No such file or directory\n")
            else:
                yield OutputChunk("stdout", data)
        elif prog in ("sh", "bash") and len(args) >= 2 and args[0] == "-c":
            async for chunk in self._script(args[1]):
                yield chunk
        else:
            self.exit_code = 127
            yield _err(f"fake: command not found: {prog}\n")

    @staticmethod
    def _echo(args: list[str]) -> str:
        if args and args[0] == "-n":
            return " ".join(args[1:])
        return " ".join(args) + "\n"

    def _expand(self, text: str) -> str:
        for key, value in self._env.items():
            text = text.replace(f"${{{key}}}", value).replace(f"${key}", value)
        return text

    async def _script(self, script: str) -> AsyncIterator[OutputChunk]:
        for raw in [s.strip() for s in script.replace("\n", ";").split(";") if s.strip()]:
            to_stderr = ">&2" in raw
            words = [w for w in shlex.split(self._expand(raw)) if w != ">&2"]
            if not words:
                continue
            if words[0] == "exit":
                self.exit_code = int(words[1]) if len(words) > 1 else 0
                return
            sub = _VirtualShell(self._sb, self._env)
            async for chunk in sub.stream(tuple(words)):
                if to_stderr and chunk.stream == "stdout":
                    yield OutputChunk("stderr", chunk.data)
                else:
                    yield chunk
            self.denials += sub.denials
            if sub.exit_code != 0:
                self.exit_code = sub.exit_code
                return
        self.exit_code = 0

    async def _egress(self, args: list[str]) -> AsyncIterator[OutputChunk]:
        url = next((a for a in args if not a.startswith("-") and not a.isdigit()), "")
        host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        policy = self._sb.network
        if policy.egress == "allow" or host in policy.allow:
            yield _out("OK\n")
            return
        self.denials += 1
        self.exit_code = 7
        yield _err(f"curl: (7) Failed to connect to {host}: egress denied\n")


def _out(text: str) -> OutputChunk:
    return OutputChunk("stdout", text.encode())


def _err(text: str) -> OutputChunk:
    return OutputChunk("stderr", text.encode())


async def _replay(result: ExecResult) -> AsyncIterator[OutputChunk]:
    for line in result.stdout.splitlines(keepends=True):
        yield _out(line)
    for line in result.stderr.splitlines(keepends=True):
        yield _err(line)


async def _forever() -> AsyncIterator[OutputChunk]:
    await anyio.sleep_forever()
    yield _out("")  # unreachable; makes this an async generator


class FakeProcess:
    """A streamed execution. Output arrives as the virtual shell produces it; exit kills it."""

    def __init__(
        self, sb: FakeSandbox, argv: tuple[str, ...], env: Mapping[str, str], limit: float
    ) -> None:
        self._sb = sb
        self._argv = argv
        self._env = env
        self._limit = limit
        self._shell: _VirtualShell | None = None
        self._source: AsyncIterator[OutputChunk] | None = None
        self._scripted_exit: int | None = None
        self._exit_code: int | None = None
        self._deadline = 0.0

    @property
    def returncode(self) -> int | None:
        return self._exit_code

    async def __aenter__(self) -> FakeProcess:
        self._sb._check_alive()  # pyright: ignore[reportPrivateUsage]
        backend = self._sb._backend  # pyright: ignore[reportPrivateUsage]
        script = backend._script_for(  # pyright: ignore[reportPrivateUsage]
            backend._run_scripts,  # pyright: ignore[reportPrivateUsage]
            " ".join(self._argv),
        )
        self._deadline = anyio.current_time() + self._limit * backend.time_scale
        returns = script.returns if script is not None else None
        if isinstance(returns, BaseException):
            raise returns
        if script is not None and script.hangs:
            self._source = _forever()
        elif returns is not None:
            self._source = _replay(returns)
            self._scripted_exit = returns.exit_code
        elif script is not None:
            self._source = _replay(ExecResult(0, "", ""))
            self._scripted_exit = 0
        else:
            self._shell = _VirtualShell(self._sb, self._env)
            self._source = self._shell.stream(self._argv)
        self._sb._procs.add(self)  # pyright: ignore[reportPrivateUsage]
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
                backend=self._sb._backend.name,  # pyright: ignore[reportPrivateUsage]
                labels=self._sb.labels,
            )

    async def __aiter__(self) -> AsyncIterator[OutputChunk]:
        assert self._source is not None, "enter the context first: `async with sb.stream(...)`"
        while self._exit_code is None:
            try:
                # One step per scope: a cancel scope must never span a `yield`.
                with anyio.fail_after(max(self._deadline - anyio.current_time(), 0.0)):
                    chunk = await self._source.__anext__()
            except StopAsyncIteration:
                self._finish(self._final_exit())
                return
            except TimeoutError as exc:
                self._finish(KILLED_EXIT)
                raise ExecutionTimeout(
                    f"stream exceeded {self._limit}s in sandbox {self._sb.id}"
                ) from exc
            yield chunk

    def _final_exit(self) -> int:
        if self._scripted_exit is not None:
            return self._scripted_exit
        assert self._shell is not None
        return self._shell.exit_code

    async def wait(self) -> ExecResult:
        async for _ in self:  # unconsumed output is drained and discarded
            pass
        assert self._exit_code is not None
        return ExecResult(self._exit_code, "", "", streamed=True)

    async def kill(self) -> None:
        self._finish(KILLED_EXIT)
        source = self._source
        aclose = getattr(source, "aclose", None)
        if aclose is not None:
            with anyio.CancelScope(shield=True):
                await aclose()
        await anyio.lowlevel.checkpoint()

    def _finish(self, code: int) -> None:
        if self._exit_code is None:
            self._exit_code = code
        self._sb._procs.discard(self)  # pyright: ignore[reportPrivateUsage]


class FakeFileSystem:
    """In-memory files rooted at ``/``; relative paths resolve under ``/work``."""

    def __init__(self, sb: FakeSandbox) -> None:
        self._sb = sb
        self._files: dict[str, bytes] = {}
        self._dirs: set[str] = {"/", WORKDIR}

    def _norm(self, path: str) -> str:
        joined = path if path.startswith("/") else posixpath.join(WORKDIR, path)
        return posixpath.normpath(joined)

    def _parent_exists(self, path: str) -> bool:
        return posixpath.dirname(path) in self._dirs

    def read_sync(self, path: str) -> bytes:
        p = self._norm(path)
        if p not in self._files:
            raise PathNotFound(p)
        return self._files[p]

    async def _op(self, event: str, path: str, **fields: Any) -> None:
        self._sb._check_alive()  # pyright: ignore[reportPrivateUsage]
        self._sb._log(event, path=path)  # pyright: ignore[reportPrivateUsage]
        await anyio.lowlevel.checkpoint()

    async def read(self, path: str) -> bytes:
        await self._op("file_read", path)
        record = self._sb._record("file_read", argv=[path])  # pyright: ignore[reportPrivateUsage]
        async with operation(record, config=self._sb._backend.audit, redact=self._sb._redact):  # pyright: ignore[reportPrivateUsage]
            data = self.read_sync(path)
            record.bytes_out = len(data)
            record.exit_code = 0
        return data

    async def write(self, path: str, data: bytes | str) -> None:
        await self._op("file_write", path)
        p = self._norm(path)
        if not self._parent_exists(p):
            raise PathNotFound(posixpath.dirname(p))
        payload = data.encode() if isinstance(data, str) else bytes(data)
        record = self._sb._record("file_write", argv=[path])  # pyright: ignore[reportPrivateUsage]
        async with operation(record, config=self._sb._backend.audit, redact=self._sb._redact):  # pyright: ignore[reportPrivateUsage]
            self._files[p] = payload
            record.bytes_in = len(payload)
            record.exit_code = 0

    async def upload(self, local: str | Path, remote: str) -> None:
        self._sb._need(Capability.UPLOAD_DOWNLOAD)  # pyright: ignore[reportPrivateUsage]
        await self.write(remote, Path(local).read_bytes())

    async def download(self, remote: str, local: str | Path) -> None:
        self._sb._need(Capability.UPLOAD_DOWNLOAD)  # pyright: ignore[reportPrivateUsage]
        Path(local).write_bytes(await self.read(remote))

    async def ls(self, path: str = ".") -> list[FileInfo]:
        await self._op("file_ls", path)
        p = self._norm(path)
        if p not in self._dirs:
            raise PathNotFound(p)
        entries: list[FileInfo] = []
        for f, data in self._files.items():
            if posixpath.dirname(f) == p:
                entries.append(FileInfo(f, len(data), False))
        for d in self._dirs:
            if d != p and posixpath.dirname(d) == p:
                entries.append(FileInfo(d, 0, True))
        return sorted(entries, key=lambda e: e.path)

    async def mkdir(self, path: str, *, parents: bool = False) -> None:
        await self._op("file_mkdir", path)
        p = self._norm(path)
        if not parents and not self._parent_exists(p):
            raise PathNotFound(posixpath.dirname(p))
        current = p
        while current not in self._dirs:
            self._dirs.add(current)
            current = posixpath.dirname(current)

    async def remove(self, path: str) -> None:
        await self._op("file_remove", path)
        p = self._norm(path)
        if p in self._files:
            del self._files[p]
        elif p in self._dirs and p not in ("/", WORKDIR):
            self._dirs.discard(p)
        else:
            raise PathNotFound(p)


@dataclass(slots=True)
class FakeNative:
    """What ``.native`` returns: the fake's internals, outside the semver contract."""

    sandbox: FakeSandbox

    @property
    def files(self) -> dict[str, bytes]:
        return self.sandbox._fs._files  # pyright: ignore[reportPrivateUsage]

    @property
    def contexts(self) -> dict[str, dict[str, Any]]:
        return self.sandbox._contexts  # pyright: ignore[reportPrivateUsage]
