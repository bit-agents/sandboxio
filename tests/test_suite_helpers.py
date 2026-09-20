"""The contract suite's own teardown helper: a wedged provider must not hang a run."""

from __future__ import annotations

import time
from typing import ClassVar, cast

import anyio
import pytest

from sandboxio.errors import ConnectError
from sandboxio.protocols import AsyncSandbox, Backend
from sandboxio.testing.suite import BackendContractSuite

pytestmark = pytest.mark.anyio

# Finite, so a regression fails the assertion instead of hanging: `discard` shields, and a
# shielded scope cannot be cancelled from outside.
WEDGED = 5.0


class _WedgedBackend:
    name = "wedged"

    async def kill_managed(self, sandbox_id: str) -> bool:
        await anyio.sleep(WEDGED)
        return True


class _Suite(BackendContractSuite):
    backend: ClassVar[Backend] = cast(Backend, _WedgedBackend())


class _Sandbox:
    id = "sb-wedged"


async def test_discard_gives_up_on_a_wedged_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SBX_TEARDOWN_GRACE", "0.1")
    started = time.monotonic()
    await _Suite().discard(cast(AsyncSandbox, _Sandbox()))
    assert time.monotonic() - started < WEDGED / 2, "discard waited for the wedged provider"


async def test_discard_never_replaces_the_failure_the_test_was_reporting() -> None:
    class _Refusing:
        name = "refusing"

        async def kill_managed(self, sandbox_id: str) -> bool:
            raise ConnectError("the daemon refused")

    class _RefusingSuite(BackendContractSuite):
        backend: ClassVar[Backend] = cast(Backend, _Refusing())

    # It runs in a `finally`; raising here would mask what the test actually found.
    await _RefusingSuite().discard(cast(AsyncSandbox, _Sandbox()))


async def test_discard_is_a_no_op_on_a_backend_that_cannot_reap() -> None:
    class _Plain:
        name = "plain"

    class _PlainSuite(BackendContractSuite):
        backend: ClassVar[Backend] = cast(Backend, _Plain())

    await _PlainSuite().discard(cast(AsyncSandbox, _Sandbox()))
