from __future__ import annotations

import builtins
import re

import pytest

import sandboxio
from sandboxio import errors
from sandboxio.errors import (
    DOCS_ERRORS_URL,
    BackendNotFound,
    BackendNotInstalled,
    CapabilityNotSupported,
    CreateTimeout,
    CreationError,
    ExecutionTimeout,
    SandboxError,
    SandboxGone,
    SandboxTimeout,
    SandboxWarning,
    catalog,
)
from sandboxio.models import Capability

CODE = re.compile(r"^SBX_E\d{4}$")


def _all_error_classes() -> list[type[SandboxError]]:
    seen: dict[type[SandboxError], None] = {}
    stack = [SandboxError]
    while stack:
        cls = stack.pop()
        if cls not in seen:
            seen[cls] = None
            stack.extend(cls.__subclasses__())
    return list(seen)


CONCRETE = [c for c in _all_error_classes() if c.code is not None]
PUBLIC_NAMES = [n for n in errors.__all__ if isinstance(getattr(errors, n), type)]


def test_catalog_matches_the_spec_table() -> None:
    assert {(e.name, e.code) for e in catalog()} == {
        ("ConfigurationError", "SBX_E1000"),
        ("BackendNotFound", "SBX_E1001"),
        ("BackendNotInstalled", "SBX_E1002"),
        ("CapabilityNotSupported", "SBX_E1101"),
        ("CreationError", "SBX_E1201"),
        ("ConnectError", "SBX_E1202"),
        ("CreateTimeout", "SBX_E1203"),
        ("SandboxGone", "SBX_E1204"),
        ("ExecutionError", "SBX_E1301"),
        ("ExecutionTimeout", "SBX_E1302"),
        ("NetworkPolicyViolation", "SBX_E1401"),
        ("ResourceLimitExceeded", "SBX_E1402"),
        ("AuthError", "SBX_E1501"),
        ("RateLimitError", "SBX_E1502"),
        ("AuditSinkError", "SBX_E1601"),
    }


def test_codes_are_well_formed_and_unique() -> None:
    codes = [c.code for c in CONCRETE]
    assert all(CODE.match(c) for c in codes if c), codes
    assert len(codes) == len(set(codes))


def test_every_concrete_error_has_a_default_hint() -> None:
    assert all(c.default_hint for c in CONCRETE), [
        c.__name__ for c in CONCRETE if not c.default_hint
    ]


@pytest.mark.parametrize("cls", _all_error_classes(), ids=lambda c: c.__name__)
def test_no_error_inherits_a_builtin_other_than_exception(cls: type[SandboxError]) -> None:
    builtin_bases = {b for b in cls.__mro__ if b.__module__ == "builtins"}
    assert builtin_bases == {Exception, BaseException, object}


@pytest.mark.parametrize("name", PUBLIC_NAMES + list(sandboxio.__all__))
def test_no_public_name_shadows_a_builtin(name: str) -> None:
    assert not hasattr(builtins, name) or name == "__version__"


def test_bases_cannot_be_raised_directly() -> None:
    for base in (SandboxError, SandboxTimeout):
        with pytest.raises(TypeError, match="base class"):
            base("nope")


def test_create_timeout_is_both_a_creation_error_and_a_timeout() -> None:
    exc = CreateTimeout("slow")
    assert isinstance(exc, CreationError)
    assert isinstance(exc, SandboxTimeout)
    assert exc.code == "SBX_E1203"


def test_sandbox_gone_is_not_a_timeout() -> None:
    assert not issubclass(SandboxGone, SandboxTimeout)
    assert "timeout=" in SandboxGone.default_hint


def test_builtin_timeout_except_does_not_catch_ours() -> None:
    with pytest.raises(SandboxTimeout):
        try:
            raise ExecutionTimeout("hung")
        except TimeoutError:  # this clause must be dead
            pytest.fail("builtin TimeoutError must not catch a sandbox timeout")


def test_rendering_follows_the_spec_shape() -> None:
    text = str(BackendNotInstalled("e2b", extra="sandboxio[e2b]"))
    assert text.splitlines() == [
        "[SBX_E1002] The 'e2b' backend is not installed.",
        '  Fix:  uv pip install "sandboxio[e2b]"',
        f"  Docs: {DOCS_ERRORS_URL}/SBX_E1002",
    ]


def test_url_is_one_per_code() -> None:
    urls = {e.url for e in catalog()}
    assert len(urls) == len(catalog())
    assert all(u.endswith(e.code) for u, e in zip(sorted(urls), catalog(), strict=True))


def test_cause_is_preserved_when_wrapping() -> None:
    provider = RuntimeError("provider said no")
    try:
        try:
            raise provider
        except RuntimeError as inner:
            raise CreationError("could not start") from inner
    except CreationError as exc:
        assert exc.__cause__ is provider


def test_backend_not_found_lists_what_is_available() -> None:
    exc = BackendNotFound("nope", available=("docker", "fake"))
    assert exc.available == ("docker", "fake")
    assert "docker, fake" in exc.message
    assert exc.hint == "Use one of: docker, fake."


def test_capability_not_supported_names_who_supports_it() -> None:
    exc = CapabilityNotSupported(Capability.GPU, backend="docker", supported_by=("modal",))
    assert "GPU" in exc.message
    assert "modal" in exc.hint


def test_warnings_share_a_base() -> None:
    for name in (
        "UnverifiedIsolationWarning",
        "OrphanedSandboxWarning",
        "AuditSinkWarning",
        "ExperimentalWarning",
    ):
        assert issubclass(getattr(errors, name), SandboxWarning)
    assert issubclass(SandboxWarning, UserWarning)


def test_errors_are_re_exported_at_top_level() -> None:
    for entry in catalog():
        assert getattr(sandboxio, entry.name) is getattr(errors, entry.name)
