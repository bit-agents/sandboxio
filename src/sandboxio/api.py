"""``sandboxio.create()`` and ``sandboxio.connect()`` (spec/03)."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from sandboxio import _dsn, registry
from sandboxio.errors import ConfigurationError, UnverifiedIsolationWarning
from sandboxio.models import IsolationTier, NetworkPolicy, Resources

if TYPE_CHECKING:
    from sandboxio.protocols import AsyncSandbox, Backend

__all__ = ["BackendConfig", "connect", "create"]

DEFAULT_BACKEND = "docker"
DEFAULT_TIMEOUT = 300.0

# Backends already warned about in this process — the spec wants the warning once per
# backend, not once per sandbox (spec/01).
_warned_unknown_tier: set[str] = set()


@dataclass(frozen=True)
class BackendConfig:
    """Base for typed backend configuration. Adapters subclass with their own fields.

    >>> @dataclass(frozen=True)
    ... class FakeConfig(BackendConfig):
    ...     backend: ClassVar[str] = "fake"
    """

    backend: ClassVar[str]
    template: str | None = None


def _validate_timeout(timeout: float | None) -> float:
    if timeout is None or not timeout > 0:
        raise ConfigurationError(
            f"timeout={timeout!r} is not allowed; execution must be bounded.",
            hint="Pass a positive number of seconds, e.g. timeout=300.",
        )
    return float(timeout)


def _resolve(target: str | BackendConfig | None) -> tuple[Backend, str | None, float | None]:
    """Turn the target into a backend instance, a template and a DSN-supplied timeout."""
    if target is None:
        return registry.resolve(DEFAULT_BACKEND)(), None, None
    if isinstance(target, BackendConfig):
        return registry.resolve(target.backend)(), target.template, None

    parsed = _dsn.parse(target)
    timeout: float | None = None
    for key, value in parsed.params.items():
        if key == "timeout":
            try:
                timeout = float(value)
            except ValueError:
                raise ConfigurationError(
                    f"DSN parameter timeout={value!r} is not a number."
                ) from None
        else:
            raise ConfigurationError(
                f"Unknown DSN parameter {key!r} for backend {parsed.backend!r}.",
                hint="Only `timeout` is a DSN parameter; anything else is typed-config only.",
            )
    return registry.resolve(parsed.backend)(), parsed.template, timeout


def check_isolation(backend: Backend, required: IsolationTier | None) -> None:
    """Enforce ``require_isolation`` before anything is provisioned (spec/05)."""
    tier = backend.isolation
    if required is None:
        if tier is IsolationTier.UNKNOWN and backend.name not in _warned_unknown_tier:
            _warned_unknown_tier.add(backend.name)
            warnings.warn(
                f"backend {backend.name!r} declares no isolation tier; it satisfies no "
                "require_isolation and may provide no isolation at all",
                UnverifiedIsolationWarning,
                stacklevel=3,
            )
        return
    if not tier.satisfies(required):  # raises ConfigurationError for required=UNKNOWN
        raise ConfigurationError(
            f"backend {backend.name!r} reports isolation {tier.value!r}, "
            f"below the required {required.value!r}; nothing was provisioned.",
            hint="Pick a backend at or above the required tier, or lower require_isolation.",
        )


async def create(
    target: str | BackendConfig | None = None,
    *,
    template: str | None = None,
    resources: Resources = Resources(),
    network: NetworkPolicy = NetworkPolicy(),
    env: dict[str, str] | None = None,
    secrets: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    metadata: dict[str, str] | None = None,
    require_isolation: IsolationTier | None = None,
) -> AsyncSandbox:
    """Create a sandbox. ``None`` means local Docker; a DSN or typed config picks anything else.

    >>> async with await create("fake://") as sb:  # doctest: +SKIP
    ...     print((await sb.run(["echo", "hi"])).stdout)
    """
    backend, dsn_template, dsn_timeout = _resolve(target)
    if template is not None and dsn_template is not None and template != dsn_template:
        raise ConfigurationError(
            f"template given twice: {dsn_template!r} in the DSN, {template!r} as an argument."
        )
    effective_timeout = _validate_timeout(dsn_timeout if dsn_timeout is not None else timeout)
    check_isolation(backend, require_isolation)
    return await backend.create(
        template=template if template is not None else dsn_template,
        resources=resources,
        network=network,
        env=env,
        secrets=secrets,
        timeout=effective_timeout,
        metadata=metadata,
    )


async def connect(target: str | BackendConfig, sandbox_id: str) -> AsyncSandbox:
    """Attach to an existing sandbox by id. Never creates one."""
    backend, _, _ = _resolve(target)
    return await backend.connect(sandbox_id)
