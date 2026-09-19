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
    LABEL_MANAGED,
    LABEL_META,
    LABEL_SESSION,
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


@pytest.fixture(scope="session", autouse=True)
def _no_leaks_at_session_end() -> Iterator[None]:
    yield
    _backend._reaper.close()  # pyright: ignore[reportPrivateUsage]
    leaked = _client.containers.list(all=True, filters={"label": LABEL_MANAGED})
    assert not leaked, f"leaked sandboxio containers: {[c.id[:12] for c in leaked]}"


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
