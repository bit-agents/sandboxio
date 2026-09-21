"""E2B adapter for sandboxio: Firecracker microVMs with a live code interpreter."""

from __future__ import annotations

from sandboxio_e2b._backend import E2BBackend, E2BConfig, E2BSandbox

__version__ = "0.1.0rc2"

__all__ = ["E2BBackend", "E2BConfig", "E2BSandbox", "__version__"]
