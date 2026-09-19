"""Type-level conformance: a minimal adapter must satisfy the ports without a base class.

pyright strict and mypy strict check the assignments; the runtime test only proves import.
"""

from __future__ import annotations

from _conforming import MinimalBackend, MinimalFiles, MinimalProcess, MinimalSandbox
from sandboxio.protocols import AsyncFileSystem, AsyncSandbox, Backend, Process

# These assignments are the assertions; a non-conforming class fails type checking.
_process: Process = MinimalProcess()
_files: AsyncFileSystem = MinimalFiles()
_sandbox: AsyncSandbox = MinimalSandbox()
_backend: Backend = MinimalBackend()


def test_minimal_adapter_conforms_at_type_check_time() -> None:
    assert _backend.name == "minimal"
