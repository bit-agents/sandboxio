"""Request validation every adapter runs before provisioning (spec/05). Internal."""

from __future__ import annotations

from sandboxio.errors import CapabilityNotSupported, ConfigurationError
from sandboxio.models import Capability, NetworkPolicy, Resources


def validate_timeout(timeout: float | None, *, what: str = "timeout") -> None:
    if timeout is None:
        return
    if not timeout > 0:
        raise ConfigurationError(
            f"{what}={timeout!r} is not allowed; execution must be bounded.",
            hint="Pass a positive number of seconds.",
        )


def validate_request(
    *,
    resources: Resources,
    network: NetworkPolicy,
    timeout: float,
    capabilities: Capability,
    backend: str,
    allowlist_supported: bool,
) -> None:
    """Refuse what the backend cannot honour — before any user code can run."""
    validate_timeout(timeout)
    for name in ("cpu", "memory_mb", "disk_mb"):
        value = getattr(resources, name)
        if value is not None and not value > 0:
            raise ConfigurationError(
                f"Resources.{name}={value!r} would unset a cap; caps are only ever raised.",
                hint=f"Pass a positive {name}, or None for the backend default.",
            )
    if resources.gpu is not None and Capability.GPU not in capabilities:
        raise CapabilityNotSupported(Capability.GPU, backend=backend)
    if Capability.NETWORK_POLICY not in capabilities:
        raise CapabilityNotSupported(Capability.NETWORK_POLICY, backend=backend)
    if network.egress == "learn":
        raise CapabilityNotSupported(
            Capability.NETWORK_POLICY,
            backend=backend,
        )
    if network.allow and not allowlist_supported:
        raise CapabilityNotSupported(Capability.NETWORK_POLICY, backend=backend)
