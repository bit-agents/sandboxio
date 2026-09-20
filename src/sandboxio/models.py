"""Value objects, capability flags and isolation tiers (spec/01).

Everything here is a frozen dataclass or an enum. Compare with ``==``, never ``is``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, Flag, auto
from typing import TYPE_CHECKING, Literal

from sandboxio.errors import ConfigurationError, ExecutionError

if TYPE_CHECKING:
    from datetime import datetime

__all__ = [
    "Capability",
    "ExecResult",
    "FileInfo",
    "IsolationTier",
    "ManagedSandbox",
    "Meter",
    "NetworkPolicy",
    "OutputChunk",
    "Resources",
    "RichOutput",
]


@dataclass(frozen=True, slots=True)
class Resources:
    """Resource caps. ``None`` means the backend's modest default, never unbounded.

    >>> Resources(memory_mb=2048, gpu="T4")
    Resources(cpu=None, memory_mb=2048, disk_mb=None, gpu='T4')
    """

    cpu: float | None = None
    memory_mb: int | None = None
    disk_mb: int | None = None
    gpu: str | None = None


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    """Egress policy; deny-by-default. ``allow`` holds hostnames and/or CIDRs.

    >>> NetworkPolicy().egress
    'deny'
    """

    egress: Literal["deny", "allow", "learn"] = "deny"
    allow: tuple[str, ...] = ()
    ingress_ports: tuple[int, ...] = ()


class Capability(Flag):
    """What a sandbox can do. Discovered per instance, never inferred from the backend name.

    >>> Capability.RUN_CODE in (Capability.RUN_CODE | Capability.FILESYSTEM)
    True
    """

    RUN_COMMAND = auto()
    RUN_CODE = auto()
    STATEFUL_CODE = auto()
    STREAMING = auto()
    FILESYSTEM = auto()
    UPLOAD_DOWNLOAD = auto()
    PTY = auto()
    PAUSE_RESUME = auto()
    SNAPSHOT_FORK = auto()
    GPU = auto()
    LSP = auto()
    GIT = auto()
    NETWORK_POLICY = auto()
    TUNNELS = auto()
    COST_REPORTING = auto()


class IsolationTier(Enum):
    """Resistance to kernel escape by an adversarial tenant — that one property, nothing else.

    Ordered by an explicit rank (ADR-0018); ``tier.satisfies(minimum)`` is the form to use.

    >>> IsolationTier.MICROVM.satisfies(IsolationTier.CONTAINER)
    True
    """

    UNKNOWN = "unknown"
    CONTAINER = "container"
    GVISOR = "gvisor"
    MICROVM = "microvm"

    @property
    def rank(self) -> int:
        return _RANK[self]

    def satisfies(self, minimum: IsolationTier) -> bool:
        """True if this tier is at least ``minimum``. ``UNKNOWN`` satisfies nothing."""
        if minimum is IsolationTier.UNKNOWN:
            raise ConfigurationError(
                "require_isolation=IsolationTier.UNKNOWN is meaningless.",
                hint="Require a concrete tier: CONTAINER, GVISOR or MICROVM.",
            )
        return self is not IsolationTier.UNKNOWN and self.rank >= minimum.rank

    def __lt__(self, other: IsolationTier) -> bool:
        return self.rank < other.rank

    def __le__(self, other: IsolationTier) -> bool:
        return self.rank <= other.rank

    def __gt__(self, other: IsolationTier) -> bool:
        return self.rank > other.rank

    def __ge__(self, other: IsolationTier) -> bool:
        return self.rank >= other.rank


# Spaced by 10 so a tier can be inserted without renumbering (ADR-0018).
_RANK: dict[IsolationTier, int] = {
    IsolationTier.UNKNOWN: 0,
    IsolationTier.CONTAINER: 10,
    IsolationTier.GVISOR: 20,
    IsolationTier.MICROVM: 30,
}


@dataclass(frozen=True, slots=True)
class RichOutput:
    """One interpreter display output, keyed by MIME type; binary payloads are base64 text."""

    mime_type: str
    data: str


@dataclass(frozen=True, slots=True)
class Meter:
    """Per-execution measurement (v0.2). Deliberately no cost field (spec/06)."""

    duration_ms: int
    backend: str


@dataclass(frozen=True, slots=True)
class ExecResult:
    """Outcome of ``run()``, ``run_code()`` or ``Process.wait()``.

    >>> ExecResult(0, "hi\\n", "").ok
    True
    """

    exit_code: int
    stdout: str
    stderr: str
    results: tuple[RichOutput, ...] | None = None
    meter: Meter | None = None
    streamed: bool = False

    def __post_init__(self) -> None:
        if self.streamed and (self.stdout or self.stderr):
            raise ValueError(
                "a streamed ExecResult carries no stdout/stderr; the caller consumed them"
            )

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def raise_for_status(self) -> None:
        """Raise ``ExecutionError`` on a non-zero exit."""
        if not self.ok:
            raise ExecutionError(self)


@dataclass(frozen=True, slots=True)
class OutputChunk:
    """One piece of streamed output, tagged with the stream it came from."""

    stream: Literal["stdout", "stderr"]
    data: bytes


@dataclass(frozen=True, slots=True)
class FileInfo:
    """A directory entry inside the sandbox."""

    path: str
    size: int
    is_dir: bool


@dataclass(frozen=True, slots=True)
class ManagedSandbox:
    """A sandbox the provider still holds under sandboxio's label; what ``reap`` lists.

    ``labels`` is the caller's ``metadata`` as the provider stored it. A stopped sandbox is
    one whose lifetime ended without teardown — Docker leaves the container behind.

    >>> ManagedSandbox("abc123", "docker", "stopped", None, {"tenant_id": "acme"}).state
    'stopped'
    """

    sandbox_id: str
    backend: str
    state: Literal["running", "stopped", "paused"]
    created_at: datetime | None = None
    labels: dict[str, str] = field(default_factory=lambda: dict[str, str]())
