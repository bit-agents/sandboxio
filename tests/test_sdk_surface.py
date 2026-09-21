"""The provider SDK surface the adapters bind to, checked without a credential.

The nightly canary installs these SDKs unpinned, so an upstream rename fails here rather
than in a user's issue (spec/08 CI matrix).
"""

from __future__ import annotations

import typing
from typing import cast

import pytest

E2B_EXCEPTIONS = (
    "AuthenticationException",
    "FileNotFoundException",
    "NotEnoughSpaceException",
    "NotFoundException",
    "RateLimitException",
    "SandboxNotFoundException",
    "TimeoutException",
)

E2B_SANDBOX = (
    "connect",
    "create",
    "create_code_context",
    "get_info",
    "is_running",
    "kill",
    "list",
    "restart_code_context",
    "run_code",
    "sandbox_id",
    "set_timeout",
)

E2B_SUBRESOURCES = (
    ("files", ("exists", "list", "make_dir", "read", "remove", "write")),
    ("commands", ("run",)),
)


def _async_sandbox() -> type:
    sdk = pytest.importorskip("e2b_code_interpreter")
    return cast("type", sdk.AsyncSandbox)


def test_the_mapped_e2b_exceptions_still_exist() -> None:
    exceptions = pytest.importorskip("e2b.exceptions")
    missing = [name for name in E2B_EXCEPTIONS if not hasattr(exceptions, name)]
    assert not missing, (
        f"e2b.exceptions dropped {missing}; the adapter maps each to an SBX code"
    )


def test_the_called_e2b_sandbox_methods_still_exist() -> None:
    missing = [name for name in E2B_SANDBOX if not hasattr(_async_sandbox(), name)]
    assert not missing, f"e2b AsyncSandbox dropped {missing}"


@pytest.mark.parametrize(("prop", "methods"), E2B_SUBRESOURCES)
def test_the_called_e2b_subresource_methods_still_exist(
    prop: str, methods: tuple[str, ...]
) -> None:
    accessor = getattr(_async_sandbox(), prop, None)
    assert accessor is not None, f"e2b AsyncSandbox dropped .{prop}"
    target = typing.get_type_hints(accessor.fget)["return"]
    missing = [name for name in methods if not hasattr(target, name)]
    assert not missing, f"e2b {target.__name__} dropped {missing}"


def test_the_adapter_imports_against_the_installed_sdk() -> None:
    """Covers the submodule paths the surface checks above cannot name."""
    pytest.importorskip("sandboxio_e2b")
