# Error codes

Every sandboxio exception carries one of these codes, a hint with the exact fix, and
a link to its page here. Codes are stable across releases
([spec/04](../spec/04-errors.md), [ADR-0010](../adr/0010-stable-error-codes.md)).

| Code | Class | Meaning |
|------|-------|---------|
| [SBX_E1000](SBX_E1000.md) | `ConfigurationError` | The request could not be understood: bad DSN parameter, unknown key, bad option. |
| [SBX_E1001](SBX_E1001.md) | `BackendNotFound` | No backend is registered under that name. |
| [SBX_E1002](SBX_E1002.md) | `BackendNotInstalled` | A first-party backend whose extra is not installed. |
| [SBX_E1101](SBX_E1101.md) | `CapabilityNotSupported` | The backend does not declare the capability this call needs (spec/01 rule 2). |
| [SBX_E1201](SBX_E1201.md) | `CreationError` | The backend failed to produce a usable sandbox. |
| [SBX_E1202](SBX_E1202.md) | `ConnectError` | ``connect()`` was asked for an id the backend does not know or that is dead. |
| [SBX_E1203](SBX_E1203.md) | `CreateTimeout` | ``create()`` exceeded its timeout before the sandbox became usable. |
| [SBX_E1204](SBX_E1204.md) | `SandboxGone` | The sandbox no longer exists — its lifetime ended or the backend reclaimed it. |
| [SBX_E1301](SBX_E1301.md) | `ExecutionError` | A command exited non-zero and the caller asked for that to raise. |
| [SBX_E1302](SBX_E1302.md) | `ExecutionTimeout` | ``run()``, ``run_code()`` or a stream exceeded its timeout; the process was killed. |
| [SBX_E1401](SBX_E1401.md) | `NetworkPolicyViolation` | Sandboxed code attempted egress the ``NetworkPolicy`` denies. |
| [SBX_E1402](SBX_E1402.md) | `ResourceLimitExceeded` | A ``Resources`` cap was hit. |
| [SBX_E1501](SBX_E1501.md) | `AuthError` | A provider credential is missing or rejected. |
| [SBX_E1502](SBX_E1502.md) | `RateLimitError` | The provider throttled the request. sandboxio does not retry on your behalf in v0.1. |
| [SBX_E1601](SBX_E1601.md) | `AuditSinkError` | An audit sink failed and ``on_sink_failure="fail"`` was configured. |
| [SBX_E1700](SBX_E1700.md) | `FileSystemError` | A sandbox filesystem operation failed for a reason other than a missing path. |
| [SBX_E1701](SBX_E1701.md) | `PathNotFound` | The sandbox-internal path does not exist. |

<!-- Generated from src/sandboxio/errors.py by scripts/gen_error_catalog.py. Do not edit by hand. -->
