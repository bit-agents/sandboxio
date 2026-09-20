"""The Docker adapter's pure helpers, without a daemon.

The contract suite in ``test_docker_contract.py`` is the spec, but it only runs under
``-m docker``. These branches — error classification, label/timestamp decoding, reaper
env parsing — are decidable from their inputs alone, so they belong in the default run.
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from datetime import UTC, datetime

import pytest
import requests

pytest.importorskip("docker")
pytest.importorskip("sandboxio_docker")

import docker.errors
from docker.models.containers import Container

from sandboxio_docker import _reaper
from sandboxio_docker._backend import _created_at, _gone, _managed


def api_error(message: str, status: int | None = None) -> docker.errors.APIError:
    response = None
    if status is not None:
        response = requests.Response()
        response.status_code = status
    return docker.errors.APIError(message, response=response)


def container(**attrs: object) -> Container:
    return Container(attrs=attrs)


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
