"""The adapter contract suite (spec/08, ADR-0007). Normative: where prose and this file
disagree, this file wins.

Subclass once per adapter and set ``backend``. Probe methods marked *override* let the
suite drive a real backend; defaults assume a POSIX shell with ``sh``, ``echo``, ``printenv``,
``seq``, ``sleep`` and ``curl`` in the image. Probes that return ``pytest.skip`` by default
cover behaviour only the adapter can provoke (a hanging kill, an expired sandbox).
"""

from __future__ import annotations

import inspect
import uuid
from typing import TYPE_CHECKING, Any, ClassVar

import anyio
import pytest

import sandboxio
from sandboxio import api, registry
from sandboxio.errors import (
    CapabilityNotSupported,
    ConfigurationError,
    ConnectError,
    CreateTimeout,
    CreationError,
    ExecutionError,
    ExecutionTimeout,
    FileSystemError,
    OrphanedSandboxWarning,
    SandboxError,
    SandboxGone,
    SandboxTimeout,
    UnverifiedIsolationWarning,
)
from sandboxio.models import (
    Capability,
    IsolationTier,
    NetworkPolicy,
    OutputChunk,
    Resources,
    RichOutput,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Mapping
    from contextlib import AbstractContextManager
    from pathlib import Path

    from sandboxio.audit import AuditEvent
    from sandboxio.protocols import AsyncSandbox, Backend

__all__ = ["BackendContractSuite", "RecordingSink"]

# A suite-side ceiling so a hung adapter fails instead of stalling CI.
HARD_LIMIT = 60.0


class _SkipProbe:
    """Default for probes an adapter cannot provide: entering the block skips the test."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def __enter__(self) -> Any:
        pytest.skip(self.reason)

    def __exit__(self, *exc: object) -> None:
        return None


class RecordingSink:
    """Audit sink that keeps every event; wire one into the adapter and set ``audit_sink``."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


class BackendContractSuite:
    """Every test here is a requirement. Skips are visible on purpose."""

    pytestmark: ClassVar[Any] = pytest.mark.anyio

    backend: ClassVar[Backend]
    template: ClassVar[str | None] = None
    sandbox_timeout: ClassVar[float] = 120.0
    short_timeout: ClassVar[float] = 0.5
    settle: ClassVar[float] = 0.2
    allowlist_supported: ClassVar[bool] = False
    canary_host: ClassVar[str] = "example.com"
    audit_sink: ClassVar[RecordingSink | None] = None

    code_ok: ClassVar[str] = "print('hello from run_code')"
    code_ok_stdout: ClassVar[str] = "hello from run_code\n"
    code_syntax_error: ClassVar[str] = "def (:"
    code_runtime_error: ClassVar[str] = "raise RuntimeError('boom')"
    code_stateful_set: ClassVar[str] = "x = 41 + 1"
    code_stateful_get: ClassVar[str] = "print(x)"
    code_stateful_stdout: ClassVar[str] = "42\n"

    # --- command probes (override for a non-POSIX image) -------------------------------------

    def cmd_echo(self, text: str) -> list[str]:
        return ["echo", text]

    def cmd_stderr(self, text: str) -> list[str]:
        return ["sh", "-c", f"echo {text} >&2"]

    def cmd_both(self) -> list[str]:
        return ["sh", "-c", "echo out; echo err >&2"]

    def cmd_exit(self, code: int) -> list[str]:
        return ["sh", "-c", f"exit {code}"]

    def cmd_env(self, var: str) -> list[str]:
        return ["printenv", var]

    def cmd_lines(self, n: int) -> list[str]:
        return ["seq", "1", str(n)]

    def cmd_hang(self) -> list[str]:
        return ["sleep", "3600"]

    def cmd_output_then_hang(self) -> list[str]:
        return ["sh", "-c", "echo started; sleep 3600"]

    def cmd_egress(self, host: str) -> list[str]:
        return ["curl", "-sS", "--max-time", "5", f"http://{host}/"]

    # --- behaviour probes (override when the adapter can provoke the situation) ---------------

    async def wait_until_busy(self, sb: AsyncSandbox) -> None:
        """Return once an operation started in another task is really in flight."""
        await anyio.sleep(self.settle)

    async def assert_no_orphans(self, sb: AsyncSandbox) -> None:
        """Fail if a process or sandbox survived. Adapters SHOULD override this no-op."""

    async def sandbox_count(self) -> int | None:
        """Live sandboxes on the backend, or None if the adapter cannot tell."""
        return None

    async def applied_resources(self, sb: AsyncSandbox) -> Resources | None:
        """The caps the provider actually applied, or None if unobservable."""
        return None

    async def provider_labels(self, sb: AsyncSandbox) -> Mapping[str, str] | None:
        """``metadata`` as the provider sees it, or None if unobservable."""
        return None

    async def expire_sandbox(self, sb: AsyncSandbox) -> None:
        pytest.skip("adapter cannot expire a sandbox out of band")

    def simulate_kill_hang(self) -> AbstractContextManager[None]:
        return _SkipProbe("adapter cannot simulate a hanging kill")

    def simulate_slow_create(self) -> AbstractContextManager[None]:
        return _SkipProbe("adapter cannot simulate a slow create")

    def simulate_provider_failure(self) -> AbstractContextManager[type[BaseException]]:
        return _SkipProbe("adapter cannot simulate a provider failure")

    def simulate_missing_credential(self) -> AbstractContextManager[str]:
        return _SkipProbe("adapter needs no credential")

    # --- plumbing ---------------------------------------------------------------------------

    async def create(self, **overrides: Any) -> AsyncSandbox:
        kwargs: dict[str, Any] = {"template": self.template, "timeout": self.sandbox_timeout}
        kwargs.update(overrides)
        return await self.backend.create(**kwargs)

    @pytest.fixture
    async def sb(self) -> AsyncIterator[AsyncSandbox]:
        async with await self.create() as sandbox:
            yield sandbox

    @pytest.fixture
    def registered(self) -> Iterator[str]:
        """The backend reachable through ``sandboxio.create()`` under a unique DSN scheme."""
        name = f"contract-{uuid.uuid4().hex[:8]}"
        sandboxio.register(name, lambda: self.backend)
        yield f"{name}://"
        registry._registered.pop(name, None)  # pyright: ignore[reportPrivateUsage]
        registry._loaded.pop(name, None)  # pyright: ignore[reportPrivateUsage]

    def declared(self, cap: Capability) -> bool:
        return cap in self.backend.capabilities

    def needs(self, cap: Capability) -> None:
        if not self.declared(cap):
            pytest.skip(f"{cap.name} not declared")

    def lacks(self, cap: Capability) -> None:
        if self.declared(cap):
            pytest.skip(f"{cap.name} declared; negative test does not apply")

    async def run_cancelled(self, sb: AsyncSandbox, op: Any, *args: Any) -> None:
        """Start ``op``, cancel it mid-flight, assert cancellation stayed cancellation."""
        seen: list[BaseException] = []

        async def target() -> None:
            try:
                await op(*args)
            except BaseException as exc:
                seen.append(exc)
                raise

        with anyio.fail_after(HARD_LIMIT):
            async with anyio.create_task_group() as tg:
                tg.start_soon(target)
                await self.wait_until_busy(sb)
                tg.cancel_scope.cancel()
        assert seen, "the operation finished before it could be cancelled; slow it down"
        assert isinstance(seen[0], anyio.get_cancelled_exc_class()), seen[0]
        assert not isinstance(seen[0], SandboxError)
        await self.assert_no_orphans(sb)

    # --- lifecycle --------------------------------------------------------------------------

    async def test_sandbox_reports_identity_capabilities_and_tier(
        self, sb: AsyncSandbox
    ) -> None:
        assert isinstance(sb.id, str)
        assert sb.id
        assert isinstance(sb.capabilities, Capability)
        assert isinstance(sb.isolation, IsolationTier)
        assert sb.capabilities == self.backend.capabilities

    async def test_create_run_kill_and_kill_again(self) -> None:
        sb = await self.create()
        try:
            self.needs(Capability.RUN_COMMAND)
            assert (await sb.run(self.cmd_echo("hi"))).stdout == "hi\n"
        finally:
            await sb.kill()
            await sb.kill()  # idempotent, silent
        await self.assert_no_orphans(sb)

    async def test_context_exit_tears_down(self) -> None:
        sb = await self.create()
        async with sb:
            pass
        with pytest.raises(SandboxGone):
            await sb.run(self.cmd_echo("late"))
        await self.assert_no_orphans(sb)

    async def test_context_exit_on_exception_tears_down(self) -> None:
        class Boom(Exception):
            pass

        sb = await self.create()
        with pytest.raises(Boom):
            async with sb:
                raise Boom
        with pytest.raises(SandboxGone):
            await sb.run(self.cmd_echo("late"))
        await self.assert_no_orphans(sb)

    async def test_connect_unknown_id_raises_connect_error(self) -> None:
        before = await self.sandbox_count()
        with pytest.raises(ConnectError):
            await self.backend.connect(f"no-such-sandbox-{uuid.uuid4().hex}")
        if before is not None:
            assert await self.sandbox_count() == before, "connect() must never create"

    async def test_connect_reattaches_to_a_live_sandbox(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_COMMAND)
        other = await self.backend.connect(sb.id)
        assert other.id == sb.id
        assert (await other.run(self.cmd_echo("via-connect"))).stdout == "via-connect\n"

    async def test_repr_is_informative_and_safe(self) -> None:
        secret = "sbx-repr-secret-" + uuid.uuid4().hex
        async with await self.create(secrets={"TOKEN": secret}) as sb:
            text = repr(sb)
            assert sb.id in text
            assert secret not in text

    # --- cancellation -----------------------------------------------------------------------

    async def test_cancel_mid_run_leaves_no_orphan(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_COMMAND)
        await self.run_cancelled(sb, sb.run, self.cmd_hang())

    async def test_cancel_mid_run_code_leaves_no_orphan(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_CODE)
        await self.run_cancelled(sb, sb.run_code, "import time; time.sleep(3600)")

    async def test_cancel_mid_stream_leaves_no_orphan(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.STREAMING)

        async def consume() -> None:
            async with sb.stream(self.cmd_hang()) as proc:
                async for _ in proc:
                    pass

        await self.run_cancelled(sb, consume)

    async def test_cancel_mid_create_leaves_no_orphan(self) -> None:
        with self.simulate_slow_create():
            before = await self.sandbox_count()
            with anyio.fail_after(HARD_LIMIT):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(self.create)
                    await anyio.sleep(self.settle)
                    tg.cancel_scope.cancel()
            if before is not None:
                assert await self.sandbox_count() == before

    async def test_kill_works_inside_a_shielded_scope(self, sb: AsyncSandbox) -> None:
        with anyio.CancelScope(shield=True), anyio.fail_after(HARD_LIMIT):
            await sb.kill()

    async def test_grace_expiry_emits_orphaned_sandbox_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SBX_TEARDOWN_GRACE", "0.05")
        with self.simulate_kill_hang(), pytest.warns(OrphanedSandboxWarning) as record:
            sb = await self.create(metadata={"tenant_id": "t-1"})
            async with sb:
                pass
        message = str(record[0].message)
        assert sb.id in message
        assert "tenant_id=t-1" in message

    # --- run --------------------------------------------------------------------------------

    async def test_run_exit_codes(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_COMMAND)
        res = await sb.run(self.cmd_exit(3))
        assert res.exit_code == 3
        assert not res.ok
        with pytest.raises(ExecutionError) as info:
            res.raise_for_status()
        assert info.value.result == res
        assert (await sb.run(self.cmd_exit(0))).ok

    async def test_run_separates_stdout_and_stderr(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_COMMAND)
        res = await sb.run(self.cmd_both())
        assert res.stdout == "out\n"
        assert res.stderr == "err\n"

    async def test_run_injects_env(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_COMMAND)
        res = await sb.run(self.cmd_env("SBX_CONTRACT_VAR"), env={"SBX_CONTRACT_VAR": "v1"})
        assert res.stdout == "v1\n"

    async def test_run_list_does_not_go_through_a_shell(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_COMMAND)
        res = await sb.run(["echo", "$SBX_CONTRACT_VAR"], env={"SBX_CONTRACT_VAR": "expanded"})
        assert res.stdout == "$SBX_CONTRACT_VAR\n"

    async def test_run_timeout_raises_execution_timeout_and_does_not_hang(
        self, sb: AsyncSandbox
    ) -> None:
        self.needs(Capability.RUN_COMMAND)
        with anyio.fail_after(HARD_LIMIT), pytest.raises(ExecutionTimeout) as info:
            await sb.run(self.cmd_hang(), timeout=self.short_timeout)
        assert not isinstance(info.value, TimeoutError)
        await self.assert_no_orphans(sb)

    async def test_run_timeout_none_inherits_the_sandbox_timeout(self) -> None:
        self.needs(Capability.RUN_COMMAND)
        async with await self.create(timeout=self.short_timeout) as sb:
            with anyio.fail_after(HARD_LIMIT), pytest.raises((SandboxTimeout, SandboxGone)):
                await sb.run(self.cmd_hang(), timeout=None)

    async def test_run_refuses_a_non_positive_timeout(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_COMMAND)
        for bad in (0, -1):
            with pytest.raises(ConfigurationError):
                await sb.run(self.cmd_echo("x"), timeout=bad)

    async def test_run_undeclared_raises(self, sb: AsyncSandbox) -> None:
        self.lacks(Capability.RUN_COMMAND)
        with pytest.raises(CapabilityNotSupported):
            await sb.run(self.cmd_echo("x"))

    # --- run_code ---------------------------------------------------------------------------

    async def test_run_code_basic(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_CODE)
        res = await sb.run_code(self.code_ok)
        assert res.ok
        assert res.stdout == self.code_ok_stdout

    async def test_run_code_syntax_error_is_non_zero(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_CODE)
        res = await sb.run_code(self.code_syntax_error)
        assert res.exit_code != 0
        assert res.stderr

    async def test_run_code_runtime_error_is_non_zero(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_CODE)
        res = await sb.run_code(self.code_runtime_error)
        assert res.exit_code != 0

    async def test_run_code_rich_outputs_are_typed_or_absent(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_CODE)
        res = await sb.run_code(self.code_ok)
        if res.results is not None:
            assert isinstance(res.results, tuple)
            assert all(isinstance(r, RichOutput) for r in res.results)

    async def test_run_code_stateful_context(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.STATEFUL_CODE)
        ctx = f"ctx-{uuid.uuid4().hex[:6]}"
        assert (await sb.run_code(self.code_stateful_set, context_id=ctx)).ok
        res = await sb.run_code(self.code_stateful_get, context_id=ctx)
        assert res.stdout == self.code_stateful_stdout

    async def test_run_code_context_undeclared_raises(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_CODE)
        self.lacks(Capability.STATEFUL_CODE)
        with pytest.raises(CapabilityNotSupported):
            await sb.run_code(self.code_ok, context_id="c1")

    async def test_run_code_undeclared_raises(self, sb: AsyncSandbox) -> None:
        self.lacks(Capability.RUN_CODE)
        with pytest.raises(CapabilityNotSupported):
            await sb.run_code(self.code_ok)

    # --- streaming --------------------------------------------------------------------------

    async def test_stream_is_not_awaitable(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.STREAMING)
        proc = sb.stream(self.cmd_echo("x"))
        assert not inspect.isawaitable(proc)
        assert proc.returncode is None
        await self.assert_no_orphans(sb)  # nothing started without `async with`

    async def test_stream_preserves_order_within_a_stream(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.STREAMING)
        out: list[bytes] = []
        async with sb.stream(self.cmd_lines(20)) as proc:
            async for chunk in proc:
                assert isinstance(chunk, OutputChunk)
                if chunk.stream == "stdout":
                    out.append(chunk.data)
            res = await proc.wait()
        assert b"".join(out) == "".join(f"{i}\n" for i in range(1, 21)).encode()
        assert res.ok

    async def test_stream_distinguishes_stdout_and_stderr(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.STREAMING)
        got: dict[str, bytes] = {"stdout": b"", "stderr": b""}
        async with sb.stream(self.cmd_both()) as proc:
            async for chunk in proc:
                got[chunk.stream] += chunk.data
        assert got == {"stdout": b"out\n", "stderr": b"err\n"}

    async def test_stream_wait_is_streamed_empty_and_idempotent(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.STREAMING)
        async with sb.stream(self.cmd_exit(4)) as proc:
            first = await proc.wait()  # unconsumed output is drained and discarded
            second = await proc.wait()
        assert first == second
        assert first.streamed
        assert first.stdout == "" and first.stderr == ""
        assert first.exit_code == 4
        assert proc.returncode == 4

    async def test_stream_timeout_raises_execution_timeout(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.STREAMING)
        with anyio.fail_after(HARD_LIMIT), pytest.raises(ExecutionTimeout):
            async with sb.stream(self.cmd_hang(), timeout=self.short_timeout) as proc:
                async for _ in proc:
                    pass
        await self.assert_no_orphans(sb)

    async def test_stream_cleanup_after_full_iteration(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.STREAMING)
        async with sb.stream(self.cmd_lines(3)) as proc:
            async for _ in proc:
                pass
        assert proc.returncode is not None
        await self.assert_no_orphans(sb)

    async def test_stream_cleanup_after_early_break(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.STREAMING)
        proc = sb.stream(self.cmd_output_then_hang())
        seen = 0
        with anyio.fail_after(HARD_LIMIT):
            async with proc:
                async for _ in proc:
                    seen += 1
                    break
        assert seen == 1
        assert proc.returncode is not None
        await self.assert_no_orphans(sb)

    async def test_stream_cleanup_after_exception_in_block(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.STREAMING)

        class Boom(Exception):
            pass

        proc = sb.stream(self.cmd_hang())
        with anyio.fail_after(HARD_LIMIT), pytest.raises(Boom):
            async with proc:
                raise Boom
        assert proc.returncode is not None
        await self.assert_no_orphans(sb)

    async def test_stream_cleanup_after_cancellation_in_block(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.STREAMING)
        holder: list[Any] = []

        async def consume() -> None:
            async with sb.stream(self.cmd_hang()) as proc:
                holder.append(proc)
                async for _ in proc:
                    pass

        await self.run_cancelled(sb, consume)
        assert holder and holder[0].returncode is not None

    async def test_stream_undeclared_raises_before_entry(self, sb: AsyncSandbox) -> None:
        self.lacks(Capability.STREAMING)
        with pytest.raises(CapabilityNotSupported):
            sb.stream(self.cmd_echo("x"))

    # --- filesystem -------------------------------------------------------------------------

    async def test_files_round_trip_text_and_binary(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.FILESYSTEM)
        await sb.files.write("/work/hello.txt", "héllo\n")
        assert await sb.files.read("/work/hello.txt") == "héllo\n".encode()
        payload = bytes(range(256)) * 4
        await sb.files.write("/work/blob.bin", payload)
        assert await sb.files.read("/work/blob.bin") == payload

    async def test_files_ls_mkdir_remove(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.FILESYSTEM)
        await sb.files.mkdir("/work/d1/d2", parents=True)
        await sb.files.write("/work/d1/d2/f", b"x")
        names = {info.path.rsplit("/", 1)[-1] for info in await sb.files.ls("/work/d1/d2")}
        assert names == {"f"}
        dirs = [i for i in await sb.files.ls("/work/d1") if i.is_dir]
        assert len(dirs) == 1
        await sb.files.remove("/work/d1/d2/f")
        assert await sb.files.ls("/work/d1/d2") == []

    async def test_files_missing_path_raises_mapped_error(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.FILESYSTEM)
        with pytest.raises(FileSystemError) as info:
            await sb.files.read(f"/work/absent-{uuid.uuid4().hex}")
        assert isinstance(info.value, SandboxError)

    async def test_files_never_resolve_host_paths(
        self, sb: AsyncSandbox, tmp_path: Path
    ) -> None:
        self.needs(Capability.FILESYSTEM)
        sentinel = f"host-only-{uuid.uuid4().hex}".encode()
        host_file = tmp_path / "host.txt"
        host_file.write_bytes(sentinel)
        try:
            data = await sb.files.read(str(host_file))
        except SandboxError:
            return
        assert data != sentinel

    async def test_files_upload_download(self, sb: AsyncSandbox, tmp_path: Path) -> None:
        self.needs(Capability.UPLOAD_DOWNLOAD)
        payload = bytes(range(256))
        src = tmp_path / "up.bin"
        src.write_bytes(payload)
        await sb.files.upload(src, "/work/up.bin")
        assert await sb.files.read("/work/up.bin") == payload
        dst = tmp_path / "down.bin"
        await sb.files.download("/work/up.bin", dst)
        assert dst.read_bytes() == payload

    async def test_files_undeclared_raises(self, sb: AsyncSandbox) -> None:
        self.lacks(Capability.FILESYSTEM)
        with pytest.raises(CapabilityNotSupported):
            _ = sb.files

    # --- policy -----------------------------------------------------------------------------

    async def test_deny_actually_denies(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_COMMAND)
        res = await sb.run(self.cmd_egress(self.canary_host), timeout=30)
        assert res.exit_code != 0, "deny-by-default egress reached the canary host"

    async def test_allowlist_permits_only_listed_hosts(self) -> None:
        self.needs(Capability.RUN_COMMAND)
        policy = NetworkPolicy(egress="deny", allow=(self.canary_host,))
        if not self.allowlist_supported:
            with pytest.raises(CapabilityNotSupported):
                await self.create(network=policy)
            return
        async with await self.create(network=policy) as sb:
            assert (await sb.run(self.cmd_egress(self.canary_host), timeout=30)).ok
            other = f"{uuid.uuid4().hex[:10]}.invalid"
            assert not (await sb.run(self.cmd_egress(other), timeout=30)).ok

    async def test_learn_mode_raises_in_v01(self) -> None:
        with pytest.raises(CapabilityNotSupported):
            await self.create(network=NetworkPolicy(egress="learn"))

    async def test_resource_caps_are_applied(self) -> None:
        async with await self.create(resources=Resources(memory_mb=256)) as sb:
            applied = await self.applied_resources(sb)
            if applied is None:
                pytest.skip("adapter cannot report applied resources")
            assert applied.memory_mb == 256

    async def test_resource_caps_cannot_be_unset(self) -> None:
        for bad in (Resources(memory_mb=0), Resources(cpu=-1)):
            with pytest.raises(ConfigurationError):
                await self.create(resources=bad)

    async def test_gpu_request_without_gpu_capability_raises(self) -> None:
        self.lacks(Capability.GPU)
        with pytest.raises(CapabilityNotSupported):
            await self.create(resources=Resources(gpu="T4"))

    async def test_create_refuses_unbounded_timeout(self) -> None:
        for bad in (0, -5):
            with pytest.raises(ConfigurationError):
                await self.create(timeout=bad)

    # --- errors and timeouts ----------------------------------------------------------------

    async def test_provider_failure_is_mapped_with_cause(self) -> None:
        with self.simulate_provider_failure() as native, pytest.raises(CreationError) as info:
            await self.create()
        assert isinstance(info.value.__cause__, native)

    async def test_missing_credential_raises_auth_error_naming_the_variable(self) -> None:
        with (
            self.simulate_missing_credential() as var,
            pytest.raises(sandboxio.AuthError) as info,
        ):
            await self.create()
        assert var in info.value.hint

    async def test_create_timeout_raises_create_timeout(self) -> None:
        with (
            self.simulate_slow_create(),
            anyio.fail_after(HARD_LIMIT),
            pytest.raises(CreateTimeout) as info,
        ):
            await self.create(timeout=self.short_timeout)
        assert isinstance(info.value, CreationError)
        assert isinstance(info.value, SandboxTimeout)
        assert not isinstance(info.value, TimeoutError)

    async def test_expired_sandbox_raises_sandbox_gone(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_COMMAND)
        await self.expire_sandbox(sb)
        with pytest.raises(SandboxGone):
            await sb.run(self.cmd_echo("x"))

    # --- isolation honesty ------------------------------------------------------------------

    async def test_backend_and_sandbox_report_a_tier(self, sb: AsyncSandbox) -> None:
        assert isinstance(self.backend.isolation, IsolationTier)
        assert sb.isolation == self.backend.isolation

    async def test_require_isolation_above_tier_fails_before_provisioning(
        self, registered: str
    ) -> None:
        tier = self.backend.isolation
        stronger = [t for t in IsolationTier if t > tier]
        if not stronger:
            pytest.skip("backend already reports the strongest tier")
        before = await self.sandbox_count()
        with pytest.raises(ConfigurationError):
            await sandboxio.create(registered, require_isolation=stronger[0])
        if before is not None:
            assert await self.sandbox_count() == before

    async def test_require_isolation_at_or_below_tier_passes(self, registered: str) -> None:
        tier = self.backend.isolation
        if tier is IsolationTier.UNKNOWN:
            with pytest.raises(ConfigurationError):
                await sandboxio.create(registered, require_isolation=IsolationTier.CONTAINER)
            return
        async with await sandboxio.create(registered, require_isolation=tier) as sb:
            assert sb.isolation == tier

    async def test_unknown_tier_warns_once(self, registered: str) -> None:
        if self.backend.isolation is not IsolationTier.UNKNOWN:
            pytest.skip("backend declares a tier")
        api._warned_unknown_tier.discard(self.backend.name)  # pyright: ignore[reportPrivateUsage]
        with pytest.warns(UnverifiedIsolationWarning):
            async with await sandboxio.create(registered):
                pass

    # --- observability ----------------------------------------------------------------------

    def _events(self) -> list[AuditEvent]:
        if self.audit_sink is None:
            pytest.skip("set `audit_sink` to a RecordingSink wired into the backend")
        return self.audit_sink.events

    async def test_one_record_per_operation(self, sb: AsyncSandbox) -> None:
        self.needs(Capability.RUN_COMMAND)
        events = self._events()
        before = len(events)
        await sb.run(self.cmd_echo("one"))
        assert len(events) == before + 1
        event = events[-1]
        assert event.sandbox_id == sb.id
        assert event.backend == self.backend.name
        assert event.exit_code == 0
        assert event.argv is not None and "one" in " ".join(event.argv)

    async def test_secrets_reach_no_sink(self) -> None:
        self.needs(Capability.RUN_COMMAND)
        events = self._events()
        secret = "sbx-sink-secret-" + uuid.uuid4().hex
        async with await self.create(secrets={"API_TOKEN": secret}) as sb:
            await sb.run(self.cmd_echo(secret))
            await sb.run(self.cmd_env("API_TOKEN"))
        for event in events:
            assert secret not in repr(event)

    async def test_metadata_propagates_to_provider_labels(self) -> None:
        labels = {"tenant_id": "acme", "session_id": "s-1"}
        async with await self.create(metadata=labels) as sb:
            seen = await self.provider_labels(sb)
            if seen is None:
                pytest.skip("adapter cannot read provider labels")
            assert {k: seen.get(k) for k in labels} == labels
            if self.audit_sink is not None and self.declared(Capability.RUN_COMMAND):
                await sb.run(self.cmd_echo("labelled"))
                assert self.audit_sink.events[-1].tenant_id == "acme"

    # --- capability honesty -----------------------------------------------------------------

    async def test_every_declared_capability_has_a_test_in_this_suite(self) -> None:
        covered = {
            Capability.RUN_COMMAND,
            Capability.RUN_CODE,
            Capability.STATEFUL_CODE,
            Capability.STREAMING,
            Capability.FILESYSTEM,
            Capability.UPLOAD_DOWNLOAD,
            Capability.NETWORK_POLICY,
            Capability.GPU,
        }
        untested = [
            c for c in Capability if c in self.backend.capabilities and c not in covered
        ]
        assert not untested, (
            f"declared but not covered by the suite: {[c.name for c in untested]}; "
            "keep it behind `.native` until the suite covers it (ADR-0003)"
        )

    async def test_network_policy_undeclared_refuses_to_create(self) -> None:
        self.lacks(Capability.NETWORK_POLICY)
        with pytest.raises(CapabilityNotSupported):
            await self.create()
