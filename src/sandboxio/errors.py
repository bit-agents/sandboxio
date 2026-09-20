"""The sandboxio error tree and warning classes (spec/04, ADR-0010, ADR-0017).

Codes are semver-covered API. Every concrete error carries a stable ``code``, a ``hint``
holding the exact fix, and a ``url`` to its generated docs page. No class here inherits
from a builtin exception, so ``except TimeoutError`` never catches a sandbox timeout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from sandboxio.models import Capability, ExecResult

# TODO(placeholder): the docs domain is not chosen. `.invalid` is RFC 2606-reserved, so
# this can never be mistaken for a live site.
DOCS_ERRORS_URL = "https://docs.sandboxio.invalid/errors"

__all__ = [
    "DOCS_ERRORS_URL",
    "AuditSinkError",
    "AuditSinkWarning",
    "AuthError",
    "BackendNotFound",
    "BackendNotInstalled",
    "CapabilityNotSupported",
    "CatalogEntry",
    "ConfigurationError",
    "ConnectError",
    "CreateTimeout",
    "CreationError",
    "ExecutionError",
    "ExecutionTimeout",
    "ExperimentalWarning",
    "FileSystemError",
    "NetworkPolicyViolation",
    "OrphanedSandboxWarning",
    "PathNotFound",
    "RateLimitError",
    "ResourceLimitExceeded",
    "SandboxError",
    "SandboxGone",
    "SandboxTimeout",
    "SandboxWarning",
    "UnverifiedIsolationWarning",
    "catalog",
]


class SandboxError(Exception):
    """Base of every sandboxio exception; ``except SandboxError`` catches anything we raise.

    Subclasses with ``code = None`` are catch-all bases and cannot be instantiated.
    """

    code: ClassVar[str | None] = None
    default_hint: ClassVar[str] = ""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        if type(self).code is None:
            raise TypeError(f"{type(self).__name__} is a base class; raise a concrete subclass")
        super().__init__(message)
        self.message = message
        self.hint = hint if hint is not None else type(self).default_hint

    @property
    def url(self) -> str:
        return f"{DOCS_ERRORS_URL}/{self.code}"

    def __str__(self) -> str:
        lines = [f"[{self.code}] {self.message}"]
        if self.hint:
            lines.append(f"  Fix:  {self.hint}")
        lines.append(f"  Docs: {self.url}")
        return "\n".join(lines)


# --- SBX_E10xx: configuration -------------------------------------------------------------


class ConfigurationError(SandboxError):
    """The request could not be understood: bad DSN parameter, unknown key, bad option."""

    code = "SBX_E1000"
    default_hint = (
        "Check the argument named in the message against docs/spec/07-configuration.md."
    )


class BackendNotFound(ConfigurationError):
    """No backend is registered under that name."""

    code = "SBX_E1001"
    default_hint = (
        'Pick an available backend, or `sandboxio.register("name", "pkg.module:Class")`.'
    )

    def __init__(self, name: str, *, available: tuple[str, ...]) -> None:
        listing = ", ".join(available) if available else "none"
        super().__init__(
            f"No backend named {name!r}. Available: {listing}.",
            hint=(
                f"Use one of: {listing}."
                if available
                else 'Install a backend extra, e.g. `uv pip install "sandboxio[docker]"`.'
            ),
        )
        self.name = name
        self.available = available


class BackendNotInstalled(ConfigurationError):
    """A first-party backend whose extra is not installed."""

    code = "SBX_E1002"
    default_hint = 'uv pip install "sandboxio[<backend>]"'

    def __init__(self, name: str, *, extra: str) -> None:
        super().__init__(
            f"The {name!r} backend is not installed.",
            hint=f'uv pip install "{extra}"',
        )
        self.name = name
        self.extra = extra


# --- SBX_E11xx: capabilities --------------------------------------------------------------


class CapabilityNotSupported(SandboxError):
    """The backend does not declare the capability this call needs (spec/01 rule 2)."""

    code = "SBX_E1101"
    default_hint = (
        "Branch on `sandbox.capabilities` before calling, or pick a backend that declares it."
    )

    def __init__(
        self,
        capability: Capability,
        *,
        backend: str,
        supported_by: tuple[str, ...] = (),
    ) -> None:
        cap = capability.name or str(capability)
        who = f" Backends that do: {', '.join(supported_by)}." if supported_by else ""
        super().__init__(
            f"Backend {backend!r} does not support {cap}.{who}",
            hint=(
                f"Use one of: {', '.join(supported_by)}."
                if supported_by
                else f"Check `Capability.{cap} in sandbox.capabilities` before calling."
            ),
        )
        self.capability = capability
        self.backend = backend
        self.supported_by = supported_by


# --- SBX_E12xx: lifecycle ------------------------------------------------------------------


class CreationError(SandboxError):
    """The backend failed to produce a usable sandbox."""

    code = "SBX_E1201"
    default_hint = "Inspect `__cause__` for the provider's reason; run `sandboxio doctor`."


class ConnectError(SandboxError):
    """The backend would not service a sandbox-management call.

    ``connect()`` given an id it does not know or that is dead, and the listing and
    teardown calls behind ``sandboxio reap`` — never a failure of code inside a sandbox.
    """

    code = "SBX_E1202"
    default_hint = "Verify the sandbox id is current; `connect()` never creates a sandbox."


class SandboxTimeout(SandboxError):
    """Catch-all base for sandbox-side deadlines. Never raised directly; carries no code."""

    code: ClassVar[str | None] = None


class CreateTimeout(CreationError, SandboxTimeout):
    """``create()`` exceeded its timeout before the sandbox became usable."""

    code = "SBX_E1203"
    default_hint = "Raise `timeout=` on create(), or pick a warmer template/image."


class SandboxGone(SandboxError):
    """The sandbox no longer exists — its lifetime ended or the backend reclaimed it."""

    code = "SBX_E1204"
    default_hint = (
        "Raise the sandbox `timeout=` passed to create(); it governs the sandbox lifetime."
    )


# --- SBX_E13xx: execution ------------------------------------------------------------------


class ExecutionError(SandboxError):
    """A command exited non-zero and the caller asked for that to raise."""

    code = "SBX_E1301"
    default_hint = "Read `exc.result.stderr`; the exit code is in `exc.result.exit_code`."

    def __init__(self, result: ExecResult) -> None:
        super().__init__(f"Command exited with status {result.exit_code}.")
        self.result = result


class ExecutionTimeout(SandboxTimeout):
    """``run()``, ``run_code()`` or a stream exceeded its timeout; the process was killed."""

    code = "SBX_E1302"
    default_hint = "Raise `timeout=` on the call, or make the code finish sooner."


# --- SBX_E14xx: policy ---------------------------------------------------------------------


class NetworkPolicyViolation(SandboxError):
    """Sandboxed code attempted egress the ``NetworkPolicy`` denies."""

    code = "SBX_E1401"
    default_hint = (
        "Add the host to `NetworkPolicy(allow=...)` on a backend that supports allowlists."
    )


class ResourceLimitExceeded(SandboxError):
    """A ``Resources`` cap was hit."""

    code = "SBX_E1402"
    default_hint = "Raise the named cap in `Resources(...)`; caps can be raised, never unset."

    def __init__(self, limit: str, *, value: object) -> None:
        super().__init__(
            f"Resource limit {limit!r} exceeded (current value: {value!r}).",
            hint=f"Raise `Resources({limit}=...)` above {value!r}.",
        )
        self.limit = limit
        self.value = value


# --- SBX_E15xx: provider account -----------------------------------------------------------


class AuthError(SandboxError):
    """A provider credential is missing or rejected."""

    code = "SBX_E1501"
    default_hint = "Set the provider's credential environment variable."

    def __init__(self, backend: str, *, env_var: str) -> None:
        super().__init__(
            f"Backend {backend!r} has no usable credential.",
            hint=f"export {env_var}=...  (see the {backend} how-to for obtaining one)",
        )
        self.backend = backend
        self.env_var = env_var


class RateLimitError(SandboxError):
    """The provider throttled the request. sandboxio does not retry on your behalf in v0.1."""

    code = "SBX_E1502"
    default_hint = (
        "Back off and retry in the caller; see `__cause__` for the provider's retry-after."
    )


# --- SBX_E16xx: observability --------------------------------------------------------------


class AuditSinkError(SandboxError):
    """An audit sink failed and ``on_sink_failure="fail"`` was configured."""

    code = "SBX_E1601"
    default_hint = 'Fix the sink, or use `on_sink_failure="warn"` to proceed without a record.'


# --- SBX_E17xx: filesystem -----------------------------------------------------------------


class FileSystemError(SandboxError):
    """A sandbox filesystem operation failed for a reason other than a missing path."""

    code = "SBX_E1700"
    default_hint = "Inspect `__cause__`; paths are sandbox-internal, never host paths."


class PathNotFound(FileSystemError):
    """The sandbox-internal path does not exist."""

    code = "SBX_E1701"
    default_hint = (
        "List the parent with `sandbox.files.ls()`; paths resolve inside the sandbox."
    )

    def __init__(self, path: str) -> None:
        super().__init__(f"No such path in the sandbox: {path!r}.")
        self.path = path


# --- warnings ---------------------------------------------------------------------------------


class SandboxWarning(UserWarning):
    """Base of every sandboxio warning."""


class UnverifiedIsolationWarning(SandboxWarning):
    """Creating on an ``UNKNOWN``-tier backend. Emitted once per backend per process."""


class OrphanedSandboxWarning(SandboxWarning):
    """Teardown grace expired; a sandbox may still be running. Names id, backend and labels."""


class AuditSinkWarning(SandboxWarning):
    """An audit sink failed under ``on_sink_failure="warn"``; the operation proceeded."""


class ExperimentalWarning(SandboxWarning):
    """The API in use is outside the semver contract."""


# --- catalog ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    code: str
    name: str
    summary: str
    hint: str
    bases: tuple[str, ...]

    @property
    def url(self) -> str:
        return f"{DOCS_ERRORS_URL}/{self.code}"


def _concrete_subclasses(cls: type[SandboxError]) -> list[type[SandboxError]]:
    found: list[type[SandboxError]] = []
    for sub in cls.__subclasses__():
        if sub.code is not None:
            found.append(sub)
        found.extend(_concrete_subclasses(sub))
    return found


def catalog() -> tuple[CatalogEntry, ...]:
    """Every coded error, sorted by code. ``docs/errors/`` is rendered from this.

    >>> [e.code for e in catalog()][:2]
    ['SBX_E1000', 'SBX_E1001']
    """
    entries = {
        cls.code: CatalogEntry(
            code=cls.code,
            name=cls.__name__,
            summary=(cls.__doc__ or "").strip().splitlines()[0],
            hint=cls.default_hint,
            bases=tuple(b.__name__ for b in cls.__bases__ if issubclass(b, SandboxError)),
        )
        for cls in _concrete_subclasses(SandboxError)
        if cls.code is not None
    }
    return tuple(entries[code] for code in sorted(entries))
