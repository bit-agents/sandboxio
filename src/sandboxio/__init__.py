"""One secure Python API for running AI-agent code in any sandbox.

Importing this package imports no adapter, no provider SDK and no third-party code
beyond the base dependencies (ADR-0004, ADR-0012).
"""

from __future__ import annotations

from sandboxio.errors import (
    AuditSinkError,
    AuditSinkWarning,
    AuthError,
    BackendNotFound,
    BackendNotInstalled,
    CapabilityNotSupported,
    ConfigurationError,
    ConnectError,
    CreateTimeout,
    CreationError,
    ExecutionError,
    ExecutionTimeout,
    ExperimentalWarning,
    NetworkPolicyViolation,
    OrphanedSandboxWarning,
    RateLimitError,
    ResourceLimitExceeded,
    SandboxError,
    SandboxGone,
    SandboxTimeout,
    SandboxWarning,
    UnverifiedIsolationWarning,
)
from sandboxio.models import (
    Capability,
    ExecResult,
    FileInfo,
    IsolationTier,
    Meter,
    NetworkPolicy,
    OutputChunk,
    Resources,
    RichOutput,
)
from sandboxio.registry import register

__version__ = "0.0.0"

__all__ = [
    "AuditSinkError",
    "AuditSinkWarning",
    "AuthError",
    "BackendNotFound",
    "BackendNotInstalled",
    "Capability",
    "CapabilityNotSupported",
    "ConfigurationError",
    "ConnectError",
    "CreateTimeout",
    "CreationError",
    "ExecResult",
    "ExecutionError",
    "ExecutionTimeout",
    "ExperimentalWarning",
    "FileInfo",
    "IsolationTier",
    "Meter",
    "NetworkPolicy",
    "NetworkPolicyViolation",
    "OrphanedSandboxWarning",
    "OutputChunk",
    "RateLimitError",
    "ResourceLimitExceeded",
    "Resources",
    "RichOutput",
    "SandboxError",
    "SandboxGone",
    "SandboxTimeout",
    "SandboxWarning",
    "UnverifiedIsolationWarning",
    "__version__",
    "register",
]
