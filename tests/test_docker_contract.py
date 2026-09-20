"""The Docker adapter against a real daemon (build-order step 4). Run with `-m docker`."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, ClassVar

import pytest

from sandboxio.audit import AuditConfig
from sandboxio.models import Resources
from sandboxio.protocols import AsyncSandbox, Backend
from sandboxio.testing.suite import BackendContractSuite, RecordingSink

docker = pytest.importorskip("docker")
sandboxio_docker = pytest.importorskip("sandboxio_docker")
from sandboxio_docker._backend import (  # noqa: E402
    DEFAULT_MEMORY_MB,
    DEFAULT_PIDS,
    LABEL_MANAGED,
    LABEL_META,
    LABEL_SESSION,
    SECURITY_OPT,
    DockerBackend,
    DockerSandbox,
)

pytestmark = [
    pytest.mark.docker,
    pytest.mark.allow_hosts(["127.0.0.1"]),
    # docker-py leaves response sockets to the GC; that is its hygiene, not ours.
    pytest.mark.filterwarnings("ignore::ResourceWarning"),
    pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning"),
]

try:
    _client = docker.from_env()
    _client.ping()
except Exception as exc:  # pragma: no cover - environment dependent
    pytest.skip(f"no Docker daemon: {exc!r}", allow_module_level=True)

_sink = RecordingSink()
_backend = DockerBackend(audit=AuditConfig(sinks=(_sink,)), client=_client)
IDLE = ("sleep", "docker-init")


def _session_containers() -> list[Any]:
    found: list[Any] = _client.containers.list(
        all=True, filters={"label": f"{LABEL_SESSION}={_backend.session_id}"}
    )
    return found


def _describe(container: Any) -> str:
    try:
        attrs: Mapping[str, Any] = container.attrs
        labels: Mapping[str, str] = attrs.get("Config", {}).get("Labels") or {}
        session = labels.get(LABEL_SESSION, "-")
        whose = "this session" if session == _backend.session_id else "OTHER session"
        return (
            f"{container.id[:12]} name={container.name} status={container.status!r} "
            f"cmd={attrs.get('Config', {}).get('Cmd')} "
            f"created={attrs.get('Created')} "
            f"finished={attrs.get('State', {}).get('FinishedAt')} "
            f"session={session[:12]} ({whose})"
        )
    except Exception as exc:  # pragma: no cover - diagnostics must not mask the failure
        return f"{container.id[:12]} <undescribable: {exc!r}>"


@pytest.fixture(scope="session", autouse=True)
def _no_leaks_at_session_end() -> Iterator[None]:
    yield
    _backend._reaper.close()  # pyright: ignore[reportPrivateUsage]
    leaked: list[Any] = _client.containers.list(all=True, filters={"label": LABEL_MANAGED})
    if leaked:
        # Assert now, not after a settle: the reaper's grace would hide the leak behind it.
        detail = "\n  ".join(_describe(c) for c in leaked)
        pytest.fail(f"leaked {len(leaked)} sandboxio containers:\n  {detail}")


class TestDockerBackend(BackendContractSuite):
    backend: ClassVar[Backend] = _backend
    audit_sink: ClassVar[RecordingSink | None] = _sink
    allowlist_supported = False
    sandbox_timeout = 120.0
    short_timeout = 1.0
    settle = 0.5

    def cmd_egress(self, host: str) -> list[str]:
        code = (
            "import urllib.request; "
            f"urllib.request.urlopen('http://{host}/', timeout=5); print('OK')"
        )
        return ["python", "-c", code]

    async def assert_no_orphans(self, sb: AsyncSandbox) -> None:
        assert isinstance(sb, DockerSandbox)
        ids = {c.id[:12] for c in _session_containers()}
        if sb._killed:  # pyright: ignore[reportPrivateUsage]
            assert sb.id not in ids, "killed sandbox still has a container"
            return
        assert sb.id in ids
        sb.native.reload()
        assert sb.native.status == "running"
        rows = sb.native.top().get("Processes") or []
        stray = [
            r[-1]
            for r in rows
            if not any(r[-1].startswith(i) or f"/{i}" in r[-1] for i in IDLE)
        ]
        assert not stray, f"processes survived in {sb.id}: {stray}"

    async def sandbox_count(self) -> int | None:
        return len(_session_containers())

    async def applied_resources(self, sb: AsyncSandbox) -> Resources | None:
        assert isinstance(sb, DockerSandbox)
        sb.native.reload()
        host = sb.native.attrs["HostConfig"]
        return Resources(cpu=host["NanoCpus"] / 1e9, memory_mb=host["Memory"] // (1024 * 1024))

    async def provider_labels(self, sb: AsyncSandbox) -> Mapping[str, str] | None:
        assert isinstance(sb, DockerSandbox)
        sb.native.reload()
        return {
            k[len(LABEL_META) :]: v
            for k, v in sb.native.labels.items()
            if k.startswith(LABEL_META)
        }

    async def expire_sandbox(self, sb: AsyncSandbox) -> None:
        assert isinstance(sb, DockerSandbox)
        sb.native.stop(timeout=0)  # what the provider-side lifetime backstop does


def test_sync_facade_on_real_docker() -> None:
    import sandboxio

    with sandboxio.create_sync("docker://python:3.12-slim", timeout=60) as sb:
        assert sb.run(["echo", "sync"]).stdout == "sync\n"
        sb.files.write("/work/x.txt", "sync-written")
        assert sb.files.read("/work/x.txt") == b"sync-written"
        with sb.stream(["seq", "1", "3"]) as proc:
            assert b"".join(c.data for c in proc) == b"1\n2\n3\n"  # chunking is not promised
            assert proc.wait().ok
    assert not any(c.id.startswith(sb.id) for c in _client.containers.list(all=True)), (
        "sync __exit__ must remove the container"
    )


@pytest.mark.anyio
async def test_reap_sees_stopped_containers_and_kill_managed_removes_them() -> None:
    """A lifetime-expired container is left stopped; `sandboxio reap` is its cleanup path."""
    sb = await _backend.create(timeout=60, metadata={"tenant_id": "reap-test"})
    try:
        assert isinstance(sb, DockerSandbox)
        sb.native.stop(timeout=0)  # what the provider-side lifetime backstop does
        found = {
            m.sandbox_id: m
            for m in await _backend.list_managed(labels={"tenant_id": "reap-test"})
        }
        assert found[sb.id].state == "stopped"
        assert found[sb.id].labels == {"tenant_id": "reap-test"}
        assert found[sb.id].created_at is not None
        assert await _backend.kill_managed(sb.id) is True
        assert await _backend.kill_managed(sb.id) is False
        assert sb.id not in {m.sandbox_id for m in await _backend.list_managed()}
    finally:
        await sb.kill()


def test_cli_reap_and_demo_on_real_docker(capsys: pytest.CaptureFixture[str]) -> None:
    import json

    from sandboxio import cli

    code = cli.main(["demo", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert [s["step"] for s in payload["steps"]] == [
        "create",
        "run_code",
        "stream",
        "egress",
        "teardown",
    ]
    assert "hello from CPython" in payload["steps"][1]["detail"]
    assert payload["steps"][3]["ok"], "deny-by-default egress must hold on Docker"
    code = cli.main(["reap", "--backend", "docker", "--json"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["backends"]["docker"].endswith("found")


@pytest.mark.anyio
async def test_every_container_carries_the_hardening_flags() -> None:
    """ADR-0028. The CONTAINER tier is still not a safety guarantee (spec/05 threat model);
    these close the cheap holes an escape does not need."""
    sb = await _backend.create(timeout=60)
    try:
        host = sb.native.attrs["HostConfig"]
        assert host["PidsLimit"] == DEFAULT_PIDS, "a fork bomb must not reach host PIDs"
        assert host["CapDrop"] == ["ALL"]
        assert host["SecurityOpt"] == SECURITY_OPT
        assert host["Memory"] == host["MemorySwap"], "unequal limits leave swap available"
        assert host["Memory"] == DEFAULT_MEMORY_MB * 1024 * 1024
    finally:
        await sb.kill()


@pytest.mark.anyio
async def test_a_raised_memory_cap_raises_the_swap_cap_with_it() -> None:
    sb = await _backend.create(timeout=60, resources=Resources(memory_mb=1024))
    try:
        host = sb.native.attrs["HostConfig"]
        assert host["Memory"] == host["MemorySwap"] == 1024 * 1024 * 1024
    finally:
        await sb.kill()


@pytest.mark.anyio
async def test_dropping_all_capabilities_leaves_ordinary_code_working() -> None:
    """The flags are worthless if they make the adapter unusable."""
    sb = await _backend.create(timeout=60)
    try:
        assert (await sb.run(["python", "-c", "print(6*7)"])).stdout.strip() == "42"
        await sb.files.write("probe.txt", "ok")
        assert (await sb.files.read("probe.txt")) == b"ok"
    finally:
        await sb.kill()
