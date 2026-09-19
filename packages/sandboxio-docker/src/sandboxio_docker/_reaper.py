"""Ryuk-style reaper: a sidecar that removes this session's containers if the process dies.

The sidecar watches a TCP connection; when it drops (crash, SIGKILL, laptop lid), every
container carrying our session label is removed after a short grace. Best effort: if the
sidecar cannot start, a warning is emitted and sandboxes still tear down normally.
"""

from __future__ import annotations

import os
import socket
import threading
import time
import uuid
import warnings
from typing import TYPE_CHECKING

from sandboxio.errors import SandboxWarning

if TYPE_CHECKING:
    import docker

RYUK_IMAGE = "testcontainers/ryuk:0.11.0"
LABEL_REAPER = "io.sandboxio.reaper"
LABEL_SESSION = "io.sandboxio.session"
_ENV_DISABLE = "SBX_DOCKER_REAPER"

# One session per process: every DockerBackend in this process labels its containers with
# it, and one sidecar watches them all. Created on first use, never at import.
SESSION_ID = uuid.uuid4().hex
_reaper: Reaper | None = None
_reaper_lock = threading.Lock()


def process_reaper() -> Reaper:
    global _reaper
    with _reaper_lock:
        if _reaper is None:
            _reaper = Reaper(LABEL_SESSION, SESSION_ID)
        return _reaper


def enabled_by_env() -> bool:
    return os.environ.get(_ENV_DISABLE, "1").lower() not in ("0", "false", "no", "off")


def _docker_socket() -> str:
    host = os.environ.get("DOCKER_HOST", "")
    return (
        host.removeprefix("unix://") if host.startswith("unix://") else "/var/run/docker.sock"
    )


class Reaper:
    """Blocking; always call through ``anyio.to_thread``."""

    def __init__(self, session_label: str, session_id: str) -> None:
        self._filter = f"label={session_label}={session_id}\n"
        self._sock: socket.socket | None = None
        self.failed = False

    @property
    def active(self) -> bool:
        return self._sock is not None

    def start(self, client: docker.DockerClient) -> None:
        with _reaper_lock:
            if self._sock is not None or self.failed:
                return
            try:
                self._sock = self._connect(client)
            except Exception as exc:  # the reaper is a safety net, never a blocker
                self.failed = True
                warnings.warn(
                    f"sandboxio reaper unavailable ({exc!r}); a crashed process may leak "
                    f"containers — `sandboxio reap` removes them",
                    SandboxWarning,
                    stacklevel=3,
                )

    def _connect(self, client: docker.DockerClient) -> socket.socket:
        import docker.errors

        try:
            client.images.get(RYUK_IMAGE)
        except docker.errors.ImageNotFound:
            client.images.pull(RYUK_IMAGE)
        container = client.containers.run(
            RYUK_IMAGE,
            detach=True,
            auto_remove=True,
            privileged=True,
            labels={LABEL_REAPER: "true"},
            volumes={_docker_socket(): {"bind": "/var/run/docker.sock", "mode": "rw"}},
            ports={"8080/tcp": None},
            environment={"RYUK_RECONNECTION_TIMEOUT": "10s"},
        )
        deadline = time.monotonic() + 30
        port: int | None = None
        while port is None:
            container.reload()
            bindings = (container.ports or {}).get("8080/tcp") or []
            if bindings:
                port = int(bindings[0]["HostPort"])
            elif time.monotonic() > deadline:
                raise TimeoutError("reaper published no port")
            else:
                time.sleep(0.1)

        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                sock.sendall(self._filter.encode())
                if sock.recv(16).startswith(b"ACK"):
                    sock.settimeout(None)
                    return sock
                sock.close()
                raise ConnectionError("reaper did not acknowledge the filter")
            except OSError as exc:
                last = exc
                time.sleep(0.2)
        raise TimeoutError(f"could not reach the reaper: {last!r}")

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None
