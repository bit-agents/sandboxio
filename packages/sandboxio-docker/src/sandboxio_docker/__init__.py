"""Docker adapter for sandboxio: one container per sandbox, ``exec`` per operation."""

from __future__ import annotations

from sandboxio_docker._backend import DockerBackend, DockerConfig, DockerSandbox

__version__ = "0.1.0rc4"

__all__ = ["DockerBackend", "DockerConfig", "DockerSandbox", "__version__"]
