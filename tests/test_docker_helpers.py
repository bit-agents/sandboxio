"""The Docker adapter's pure helpers, without a daemon.

The contract suite in ``test_docker_contract.py`` is the spec, but it only runs under
``-m docker``. These branches — error classification, label/timestamp decoding, reaper
env parsing — are decidable from their inputs alone, so they belong in the default run.
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, cast

import anyio
import anyio.to_thread
import pytest
import requests

pytest.importorskip("docker")
pytest.importorskip("sandboxio_docker")

import docker.errors
from docker.models.containers import Container

from sandboxio.errors import (
    ExecutionError,
    FileSystemError,
    PathNotFound,
    SandboxGone,
    SandboxWarning,
)
from sandboxio_docker import _reaper
from sandboxio_docker._backend import (
    _ENV_THREADS,
    DEFAULT_THREADS,
    DockerFileSystem,
    DockerSandbox,
    _created_at,
    _gone,
    _limiter,
    _managed,
    _map_common,
    _thread,
    _thread_cap,
)


def api_error(message: str, status: int | None = None) -> docker.errors.APIError:
    response = None
    if status is not None:
        response = requests.Response()
        response.status_code = status
    return docker.errors.APIError(message, response=response)


def container(**attrs: object) -> Container:
    return Container(attrs=attrs)


pytestmark = pytest.mark.anyio


# --- _gone ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "gone"),
    [
        (docker.errors.NotFound("no such container"), True),
        (api_error("conflict", status=409), True),
        (api_error("Container abc is not running"), True),
        (api_error("server exploded", status=500), False),
        (api_error("boom"), False),
        (ValueError("not a docker error at all"), False),
    ],
    ids=["not-found", "409", "not-running-text", "500", "unlabelled", "foreign"],
)
def test_gone_recognises_only_dead_containers(exc: Exception, gone: bool) -> None:
    """Anything `_gone` rejects is re-raised by callers, so a false positive hides a fault."""
    assert _gone(exc) is gone


# --- _created_at ----------------------------------------------------------------------------


def test_created_at_reads_dockers_nanosecond_timestamp_at_microsecond_precision() -> None:
    """Docker writes nine fractional digits and a ``Z``; ``datetime`` holds six and a tzinfo."""
    assert _created_at("2026-09-20T10:00:00.123456789Z") == datetime(
        2026, 9, 20, 10, 0, 0, 123456, tzinfo=UTC
    )


def test_created_at_reads_a_six_digit_fraction_unchanged() -> None:
    assert _created_at("2026-09-20T10:00:00.123456Z") == datetime(
        2026, 9, 20, 10, 0, 0, 123456, tzinfo=UTC
    )


def test_created_at_parses_dockers_zero_timestamp() -> None:
    """A container that never started carries year one, not an empty string."""
    assert _created_at("0001-01-01T00:00:00Z") == datetime(1, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("raw", ["", "yesterday", None, 0, 1758362400], ids=str)
def test_created_at_is_none_for_anything_unparseable(raw: object) -> None:
    assert _created_at(raw) is None


# --- _managed -------------------------------------------------------------------------------


def test_managed_shortens_the_id_and_strips_the_label_prefix() -> None:
    managed = _managed(
        container(
            Id="a" * 64,
            Created="2026-09-20T10:00:00.123456789Z",
            State={"Status": "running"},
            Config={
                "Labels": {
                    "io.sandboxio.meta.tenant_id": "acme",
                    "io.sandboxio.managed": "true",
                    "com.example.unrelated": "keep out",
                }
            },
        )
    )
    assert managed.sandbox_id == "a" * 12, "reap prints the short id users see in `docker ps`"
    assert managed.backend == "docker"
    assert managed.state == "running"
    assert managed.labels == {"tenant_id": "acme"}, "only caller metadata comes back"
    assert managed.created_at == datetime(2026, 9, 20, 10, 0, 0, 123456, tzinfo=UTC)


@pytest.mark.parametrize(
    ("status", "state"),
    [
        ("running", "running"),
        ("paused", "paused"),
        ("exited", "stopped"),
        ("created", "stopped"),
        ("restarting", "stopped"),
        ("dead", "stopped"),
    ],
)
def test_managed_maps_every_docker_status_onto_the_three_spec_states(
    status: str, state: str
) -> None:
    got = _managed(container(Id="b" * 64, State={"Status": status}, Config={"Labels": {}}))
    assert got.state == state


def test_managed_survives_a_container_with_neither_id_nor_labels() -> None:
    """docker-py returns None for both on a partially inspected container."""
    got = _managed(container(State={"Status": "exited"}, Config={"Labels": None}))
    assert got.sandbox_id == "" and got.labels == {} and got.created_at is None


# --- reaper env parsing ---------------------------------------------------------------------


def test_the_reaper_is_on_when_the_env_var_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SBX_DOCKER_REAPER", raising=False)
    assert _reaper.enabled_by_env() is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "No", "off", "OFF"])
def test_documented_falsey_values_disable_the_reaper_case_insensitively(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBX_DOCKER_REAPER", value)
    assert _reaper.enabled_by_env() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "please"])
def test_anything_else_leaves_the_reaper_on(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Opting out is explicit; an unrecognised value must not silently disable the net."""
    monkeypatch.setenv("SBX_DOCKER_REAPER", value)
    assert _reaper.enabled_by_env() is True


DEFAULT_SOCKET = "/var/run/docker.sock"


@pytest.mark.parametrize(
    ("host", "socket_path"),
    [
        ("unix:///var/run/docker.sock", DEFAULT_SOCKET),
        ("unix:///Users/dev/.colima/docker.sock", "/Users/dev/.colima/docker.sock"),
        ("tcp://127.0.0.1:2375", DEFAULT_SOCKET),
        ("ssh://user@host", DEFAULT_SOCKET),
        ("", DEFAULT_SOCKET),
    ],
    ids=["default-unix", "colima", "tcp", "ssh", "empty"],
)
def test_docker_socket_strips_the_unix_scheme_and_falls_back_otherwise(
    host: str, socket_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sidecar needs a host path to bind; a non-unix DOCKER_HOST has none to offer."""
    monkeypatch.setenv("DOCKER_HOST", host)
    assert _reaper._docker_socket() == socket_path


def test_docker_socket_without_docker_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    assert _reaper._docker_socket() == DEFAULT_SOCKET


# --- the adapter's thread budget --------------------------------------------------------


def test_thread_cap_defaults_when_the_env_says_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_ENV_THREADS, raising=False)
    assert _thread_cap() == DEFAULT_THREADS


@pytest.mark.parametrize("raw", ["8", "  8  ", "128"])
def test_thread_cap_honours_the_env_override(raw: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV_THREADS, raw)
    assert _thread_cap() == int(raw)


@pytest.mark.parametrize("raw", ["0", "-1", "lots", "", "6.5"])
def test_thread_cap_warns_and_falls_back_on_nonsense(
    raw: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A zero cap would deadlock every docker call; silently accepting it is worse."""
    monkeypatch.setenv(_ENV_THREADS, raw)
    with pytest.warns(SandboxWarning, match=_ENV_THREADS):
        assert _thread_cap() == DEFAULT_THREADS


async def test_docker_work_does_not_borrow_from_the_shared_default_pool() -> None:
    """ADR-0027: a streamed exec parks a worker for the whole command, so on anyio's
    default limiter a handful of streams starve every other caller in the process."""
    default = anyio.to_thread.current_default_thread_limiter()
    started, release = threading.Event(), threading.Event()

    def blocking() -> None:
        started.set()
        release.wait()

    async with anyio.create_task_group() as tg:
        tg.start_soon(_thread, blocking)
        while not started.is_set():
            await anyio.sleep(0.001)
        assert _limiter().borrowed_tokens == 1
        assert default.borrowed_tokens == 0, "docker must not eat the host's thread budget"
        release.set()


async def test_the_limiter_is_reused_within_a_loop_and_sized_from_the_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_ENV_THREADS, "3")
    limiter = _limiter()
    assert limiter.total_tokens == 3
    assert _limiter() is limiter, "one budget per loop, not one per call"


def test_each_event_loop_gets_its_own_limiter() -> None:
    """The sync facade runs a portal per sandbox; a limiter cannot cross event loops."""
    limiters: list[anyio.CapacityLimiter] = []

    async def go() -> None:
        limiters.append(_limiter())

    anyio.run(go)
    anyio.run(go)
    assert limiters[0] is not limiters[1]


# --- exception mapping ------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        docker.errors.NotFound("no such container"),
        api_error("container is not running"),
        api_error("conflict", status=409),
    ],
    ids=["not-found", "not-running", "conflict"],
)
def test_map_common_reports_a_vanished_container_as_sandbox_gone(exc: Exception) -> None:
    mapped = _map_common(exc, sandbox_id="c0ffee")
    assert isinstance(mapped, SandboxGone) and "c0ffee" in mapped.message


@pytest.mark.parametrize(
    "exc",
    [api_error("server error", status=500), requests.ConnectionError("daemon went away")],
    ids=["api-error", "daemon-unreachable"],
)
def test_map_common_declines_what_the_caller_must_map_itself(exc: Exception) -> None:
    """None is the 'not one of ours' signal; each caller supplies its own fallback."""
    assert _map_common(exc, sandbox_id="c0ffee") is None


def test_the_sandbox_fallback_never_lets_a_raw_docker_error_through() -> None:
    """spec/04 rule 1: a raw provider exception crossing the boundary is a bug."""
    sb = cast(Any, DockerSandbox.__new__(DockerSandbox))
    sb.id = "c0ffee"
    mapped = DockerSandbox._map(sb, api_error("server error", status=500))
    assert isinstance(mapped, ExecutionError)
    assert "docker: " in mapped.result.stderr


def test_the_filesystem_fallback_separates_a_missing_path_from_a_dead_daemon() -> None:
    fs = cast(Any, DockerFileSystem.__new__(DockerFileSystem))
    fs._sb = cast(Any, type("S", (), {"id": "c0ffee"})())
    missing = fs._map_fs(docker.errors.NotFound("no such file"), "/work/x")
    assert isinstance(missing, PathNotFound)
    assert isinstance(fs._map_fs(api_error("conflict", status=409), "/work/x"), SandboxGone)
    assert isinstance(fs._map_fs(api_error("boom", status=500), "/work/x"), FileSystemError)
