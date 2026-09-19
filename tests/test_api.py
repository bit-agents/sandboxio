from __future__ import annotations

import warnings
from collections.abc import Iterator

import pytest

import sandboxio
from sandboxio import api, registry
from sandboxio.errors import (
    BackendNotFound,
    BackendNotInstalled,
    ConfigurationError,
    ConnectError,
    UnverifiedIsolationWarning,
)
from sandboxio.models import IsolationTier, NetworkPolicy
from sandboxio.testing.fake import FakeBackend

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def fresh_registry() -> Iterator[None]:
    registry._reset()  # pyright: ignore[reportPrivateUsage]
    yield
    registry._reset()  # pyright: ignore[reportPrivateUsage]


async def test_create_fake_by_dsn_through_the_entry_point() -> None:
    async with await sandboxio.create("fake://") as sb:
        assert (await sb.run(["echo", "hi"])).stdout == "hi\n"
        assert sb.isolation is IsolationTier.CONTAINER


async def test_default_target_is_docker_which_is_not_installed_yet() -> None:
    with pytest.raises(BackendNotInstalled) as info:
        await sandboxio.create()
    assert info.value.hint == 'uv pip install "sandboxio[docker]"'


async def test_unknown_scheme_lists_available_backends() -> None:
    with pytest.raises(BackendNotFound) as info:
        await sandboxio.create("nope://")
    assert "fake" in info.value.available


async def test_dsn_timeout_and_template_flow_into_create() -> None:
    fake = FakeBackend()
    sandboxio.register("f", lambda: fake)
    async with await sandboxio.create("f://tpl?timeout=42"):
        pass
    assert fake.calls[0].template == "tpl"
    assert fake.calls[0].timeout == 42.0
    assert fake.calls[0].network == NetworkPolicy(egress="deny")


async def test_template_given_twice_must_agree() -> None:
    fake = FakeBackend()
    sandboxio.register("f", lambda: fake)
    with pytest.raises(ConfigurationError):
        await sandboxio.create("f://a", template="b")
    async with await sandboxio.create("f://a", template="a"):
        pass


@pytest.mark.parametrize("bad", ["f://?timeout=0", "f://?timeout=-1", "f://?timeout=soon"])
async def test_unbounded_or_garbage_timeout_is_refused(bad: str) -> None:
    sandboxio.register("f", FakeBackend)
    with pytest.raises(ConfigurationError):
        await sandboxio.create(bad)


async def test_unknown_dsn_parameter_is_never_ignored() -> None:
    sandboxio.register("f", FakeBackend)
    with pytest.raises(ConfigurationError) as info:
        await sandboxio.create("f://?gpu=T4")
    assert "gpu" in info.value.message


async def test_require_isolation_is_checked_before_provisioning() -> None:
    fake = FakeBackend()
    sandboxio.register("f", lambda: fake)
    with pytest.raises(ConfigurationError):
        await sandboxio.create("f://", require_isolation=IsolationTier.MICROVM)
    assert fake.calls == [], "nothing may be provisioned when the tier check fails"
    with pytest.raises(ConfigurationError):
        await sandboxio.create("f://", require_isolation=IsolationTier.UNKNOWN)


async def test_unknown_tier_warns_once_per_backend_per_process() -> None:
    fake = FakeBackend(isolation=IsolationTier.UNKNOWN)
    sandboxio.register("f", lambda: fake)
    api._warned_unknown_tier.discard("fake")  # pyright: ignore[reportPrivateUsage]
    with pytest.warns(UnverifiedIsolationWarning):
        async with await sandboxio.create("f://"):
            pass
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        async with await sandboxio.create("f://"):
            pass


async def test_typed_config_selects_the_backend() -> None:
    from dataclasses import dataclass
    from typing import ClassVar

    @dataclass(frozen=True)
    class FConfig(api.BackendConfig):
        backend: ClassVar[str] = "f"

    fake = FakeBackend()
    sandboxio.register("f", lambda: fake)
    async with await sandboxio.create(FConfig(template="t1")):
        pass
    assert fake.calls[0].template == "t1"


async def test_connect_reaches_the_backend_and_never_creates() -> None:
    fake = FakeBackend()
    sandboxio.register("f", lambda: fake)
    async with await sandboxio.create("f://") as sb:
        other = await sandboxio.connect("f://", sb.id)
        assert other.id == sb.id
    with pytest.raises(ConnectError):
        await sandboxio.connect("f://", "missing")
    assert [c.op for c in fake.calls].count("create") == 1
