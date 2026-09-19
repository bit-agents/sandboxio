"""The E2B adapter against the real service (step 5): `-m e2b`, needs `E2B_API_KEY`."""

# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import os
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from typing import Any, ClassVar

import pytest

from sandboxio.audit import AuditConfig
from sandboxio.protocols import AsyncSandbox, Backend
from sandboxio.testing.suite import BackendContractSuite, RecordingSink

e2b = pytest.importorskip("e2b")
sandboxio_e2b = pytest.importorskip("sandboxio_e2b")
from sandboxio_e2b._backend import (  # noqa: E402
    API_KEY_ENV,
    META_MANAGED,
    META_SESSION,
    E2BBackend,
    E2BSandbox,
)

pytestmark = [pytest.mark.e2b, pytest.mark.enable_socket]

if not os.environ.get(API_KEY_ENV):
    pytest.skip(f"{API_KEY_ENV} not set", allow_module_level=True)

_sink = RecordingSink()
_backend = E2BBackend(audit=AuditConfig(sinks=(_sink,)))


async def _session_sandboxes() -> list[Any]:
    from e2b.sandbox.sandbox_api import SandboxQuery
    from e2b_code_interpreter import AsyncSandbox

    paginator = AsyncSandbox.list(
        query=SandboxQuery(metadata={META_SESSION: _backend.session_id})
    )
    found: list[Any] = []
    while paginator.has_next:
        found.extend(await paginator.next_items())
    return found


class TestE2BBackend(BackendContractSuite):
    backend: ClassVar[Backend] = _backend
    audit_sink: ClassVar[RecordingSink | None] = _sink
    allowlist_supported = True
    resource_caps_supported = False
    sandbox_timeout = 120.0
    short_timeout = 2.0
    settle = 1.0

    async def wait_until_busy(self, sb: AsyncSandbox) -> None:
        import anyio

        await anyio.sleep(self.settle)

    async def assert_no_orphans(self, sb: AsyncSandbox) -> None:
        assert isinstance(sb, E2BSandbox)
        if sb._killed:  # pyright: ignore[reportPrivateUsage]
            assert not await sb.native.is_running(), "killed sandbox still running"
            return
        procs = await sb.native.commands.list()
        stray = [p for p in procs if "sleep" in p.cmd or any("sleep" in a for a in p.args)]
        assert not stray, f"processes survived in {sb.id}: {[p.cmd for p in stray]}"

    async def sandbox_count(self) -> int | None:
        return len(await _session_sandboxes())

    async def provider_labels(self, sb: AsyncSandbox) -> Mapping[str, str] | None:
        assert isinstance(sb, E2BSandbox)
        info = await sb.native.get_info()
        return {k: v for k, v in info.metadata.items() if k not in (META_MANAGED, META_SESSION)}

    async def expire_sandbox(self, sb: AsyncSandbox) -> None:
        assert isinstance(sb, E2BSandbox)
        await sb.native.kill()  # what the provider-side lifetime does

    @contextmanager
    def simulate_missing_credential(self) -> Generator[str]:
        saved = os.environ.pop(API_KEY_ENV)
        try:
            yield API_KEY_ENV
        finally:
            os.environ[API_KEY_ENV] = saved
