"""FakeBackend passes the contract suite it ships with (spec/08, ADR-0007)."""

from __future__ import annotations

from collections.abc import Generator, Iterator, Mapping
from contextlib import contextmanager
from typing import ClassVar

import anyio
import pytest

from sandboxio.audit import AuditConfig
from sandboxio.models import Capability, IsolationTier, Resources
from sandboxio.protocols import AsyncSandbox, Backend
from sandboxio.testing.fake import FakeBackend, FakeSandbox
from sandboxio.testing.suite import BackendContractSuite, RecordingSink

_sink = RecordingSink()
_fake = FakeBackend(audit=AuditConfig(sinks=(_sink,)))
_fake.on_run_code(match="time.sleep(3600)", hangs=True)


class TestFakeBackend(BackendContractSuite):
    backend: ClassVar[Backend] = _fake
    audit_sink: ClassVar[RecordingSink | None] = _sink
    allowlist_supported = True
    settle = 0.0

    @pytest.fixture(autouse=True)
    def _reset_simulation(self) -> Iterator[None]:
        _fake.simulate()
        yield
        _fake.simulate()

    async def wait_until_busy(self, sb: AsyncSandbox) -> None:
        with anyio.fail_after(5):
            while _fake.live_processes() == 0:
                await anyio.sleep(0)

    async def assert_no_orphans(self, sb: AsyncSandbox) -> None:
        assert _fake.live_processes() == 0

    async def sandbox_count(self) -> int | None:
        return _fake.live_sandboxes()

    async def applied_resources(self, sb: AsyncSandbox) -> Resources | None:
        assert isinstance(sb, FakeSandbox)
        return sb.resources

    async def provider_labels(self, sb: AsyncSandbox) -> Mapping[str, str] | None:
        assert isinstance(sb, FakeSandbox)
        return sb.labels

    async def expire_sandbox(self, sb: AsyncSandbox) -> None:
        _fake.expire(sb.id)

    @contextmanager
    def simulate_kill_hang(self) -> Generator[None]:
        _fake.simulate(kill_hangs=True)
        try:
            yield
        finally:
            _fake.simulate()

    @contextmanager
    def simulate_slow_create(self) -> Generator[None]:
        _fake.simulate(create_takes=3600)
        try:
            yield
        finally:
            _fake.simulate()

    @contextmanager
    def simulate_provider_failure(self) -> Generator[type[BaseException]]:
        class NativeBoom(Exception):
            pass

        _fake.simulate(create_fails=NativeBoom("provider exploded"))
        try:
            yield NativeBoom
        finally:
            _fake.simulate()

    @contextmanager
    def simulate_missing_credential(self) -> Generator[str]:
        _fake.simulate(auth_missing=True)
        try:
            yield "SBX_FAKE_TOKEN"
        finally:
            _fake.simulate()


_minimal = FakeBackend(capabilities=Capability.RUN_COMMAND | Capability.NETWORK_POLICY)


class TestMinimalFakeBackend(BackendContractSuite):
    """A fake declaring almost nothing: every negative-capability test must bite."""

    backend: ClassVar[Backend] = _minimal
    allowlist_supported = True
    settle = 0.0

    async def wait_until_busy(self, sb: AsyncSandbox) -> None:
        with anyio.fail_after(5):
            while _minimal.live_processes() == 0:
                await anyio.sleep(0)

    async def assert_no_orphans(self, sb: AsyncSandbox) -> None:
        assert _minimal.live_processes() == 0

    async def expire_sandbox(self, sb: AsyncSandbox) -> None:
        _minimal.expire(sb.id)


_unverified = FakeBackend(isolation=IsolationTier.UNKNOWN)


class TestUnknownTierFakeBackend(BackendContractSuite):
    """An adapter that says nothing about isolation has claimed nothing (ADR-0018)."""

    backend: ClassVar[Backend] = _unverified
    allowlist_supported = True
    settle = 0.0

    async def wait_until_busy(self, sb: AsyncSandbox) -> None:
        with anyio.fail_after(5):
            while _unverified.live_processes() == 0:
                await anyio.sleep(0)

    async def assert_no_orphans(self, sb: AsyncSandbox) -> None:
        assert _unverified.live_processes() == 0

    async def expire_sandbox(self, sb: AsyncSandbox) -> None:
        _unverified.expire(sb.id)
