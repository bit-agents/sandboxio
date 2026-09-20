from __future__ import annotations

import anyio
import pytest

from sandboxio._teardown import DEFAULT_TEARDOWN_GRACE, shielded_kill, teardown_grace
from sandboxio.errors import ConnectError, OrphanedSandboxWarning

pytestmark = pytest.mark.anyio


def test_grace_defaults_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SBX_TEARDOWN_GRACE", raising=False)
    assert teardown_grace() == DEFAULT_TEARDOWN_GRACE
    monkeypatch.setenv("SBX_TEARDOWN_GRACE", "0.25")
    assert teardown_grace() == 0.25
    monkeypatch.setenv("SBX_TEARDOWN_GRACE", "nonsense")
    with pytest.warns(OrphanedSandboxWarning):
        assert teardown_grace() == DEFAULT_TEARDOWN_GRACE


async def test_shielded_kill_runs_even_when_the_caller_is_cancelled() -> None:
    killed = anyio.Event()

    async def kill() -> None:
        await anyio.sleep(0.01)
        killed.set()

    async def body() -> None:
        try:
            await anyio.sleep_forever()
        finally:
            assert await shielded_kill(kill, sandbox_id="sb", backend="fake")

    async with anyio.create_task_group() as tg:
        tg.start_soon(body)
        await anyio.sleep(0.01)
        tg.cancel_scope.cancel()
    assert killed.is_set()


async def test_grace_expiry_warns_with_id_backend_and_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SBX_TEARDOWN_GRACE", "0.02")

    async def hangs() -> None:
        await anyio.sleep_forever()

    with pytest.warns(OrphanedSandboxWarning) as record:
        ok = await shielded_kill(
            hangs, sandbox_id="sb-9", backend="fake", labels={"tenant_id": "t"}
        )
    assert not ok
    text = str(record[0].message)
    assert "sb-9" in text and "fake" in text and "tenant_id=t" in text


async def test_a_failing_kill_warns_instead_of_replacing_the_callers_exception() -> None:
    """spec/02 teardown is shielded and bounded; a broken kill is the warning path, not
    a second exception on top of whatever the caller's block already raised."""

    async def boom() -> None:
        raise ConnectError("daemon refused the remove")

    with pytest.warns(OrphanedSandboxWarning) as record:
        ok = await shielded_kill(
            boom, sandbox_id="sb-7", backend="fake", labels={"tenant_id": "t"}
        )
    assert not ok
    text = str(record[0].message)
    assert "sb-7" in text and "tenant_id=t" in text
    assert "daemon refused the remove" in text, "the swallowed reason has to survive somewhere"


async def test_a_cancelled_kill_still_propagates_as_cancellation() -> None:
    """ADR-0020: cancellation is never converted into a warning."""

    async def kill() -> None:
        raise anyio.get_cancelled_exc_class()()

    with pytest.raises(anyio.get_cancelled_exc_class()):
        await shielded_kill(kill, sandbox_id="sb", backend="fake")
