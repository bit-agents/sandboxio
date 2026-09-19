# 01 — Domain Model

## Entities

### Sandbox

A live, isolated execution environment with an identity and a lifecycle.

- MUST expose a stable `id` unique within its backend for the sandbox's lifetime.
- MUST expose `capabilities: Capability` and `isolation: IsolationTier` reflecting **this
  sandbox instance**, not a static backend default — a backend MAY produce sandboxes with
  differing capabilities depending on template or options.
- MUST be an async context manager whose exit tears the sandbox down, including on exception
  and on cancellation ([05](05-security-policy.md#guaranteed-teardown)).
- MUST expose `.files` and `.native`.

Lifecycle states: `creating → running → (killed | failed)`. `paused` is deferred to
`.native` until at least two backends support it stably ([ADR-0003](../adr/0003-no-lowest-common-denominator.md)).

### Process

A single execution within a sandbox — a command or a code run. Produced by streaming
execution; carries the terminal `ExecResult`.

**OPEN ([Q6](../open-questions.md#q6--stream-loses-stderr-and-exit-code))** — `Process` is
named in the design but has no interface. It MUST provide stdout/stderr separation and a
terminal exit code; the shape is undecided.

### FileSystem

Read/write access scoped to one sandbox. Never host filesystem access.

### Template

A base environment specification: a container image reference, or a provider template id.
sandboxio does not build images in v0.1.

### Session

**Post-MVP.** A logical, resumable binding of tenant or agent-run to sandbox. Not in v0.1;
the v0.1 equivalent is `metadata` labelling ([05](05-security-policy.md#tenancy)).

## Value objects

All value objects MUST be frozen dataclasses with value equality. Callers compare with `==`,
never `is` ([Q13](../open-questions.md#q13--doc-bug-is-on-a-dataclass)).

```python
@dataclass(frozen=True)
class Resources:
    cpu: float | None = None          # cores; None = backend default, never unbounded
    memory_mb: int | None = None
    disk_mb: int | None = None
    gpu: str | None = None            # e.g. "T4"; CapabilityNotSupported if unsupported

@dataclass(frozen=True)
class NetworkPolicy:
    egress: Literal["deny", "allow", "learn"] = "deny"
    allow: tuple[str, ...] = ()       # hostnames and/or CIDRs
    ingress_ports: tuple[int, ...] = ()
```

- `Resources` defaults MUST resolve to modest concrete caps, never "unlimited"
  ([05](05-security-policy.md#resource-caps)).
- `egress="learn"` is v0.2 and MUST raise `CapabilityNotSupported` in v0.1 rather than
  silently behaving as `deny`.

## Capability

A `Flag` enum. Additions are backwards compatible; removals are breaking.

```python
class Capability(Flag):
    RUN_COMMAND = auto(); RUN_CODE = auto(); STATEFUL_CODE = auto()
    STREAMING = auto(); FILESYSTEM = auto(); UPLOAD_DOWNLOAD = auto()
    PTY = auto(); PAUSE_RESUME = auto(); SNAPSHOT_FORK = auto()
    GPU = auto(); LSP = auto(); GIT = auto(); NETWORK_POLICY = auto(); TUNNELS = auto()
```

Rules:

1. A declared capability MUST have a passing contract test for that backend.
2. An undeclared capability, if invoked, MUST raise `CapabilityNotSupported` — never a
   silent no-op, never a degraded emulation.
3. Capabilities are discovered, not inferred from backend name. Callers branch on flags.

## IsolationTier

```python
class IsolationTier(Enum):
    CONTAINER = "container"   # runc, shared kernel — trusted/dev/CI code only
    GVISOR    = "gvisor"      # user-space kernel — defence in depth, not VM-equivalent
    MICROVM   = "microvm"     # dedicated guest kernel — floor for untrusted multi-tenant
```

- Every backend and every sandbox MUST report a tier.
- A tier above `CONTAINER` MUST be justified by provider documentation, recorded with a date
  ([ADR-0006](../adr/0006-isolation-tiers-first-class.md)).
- **OPEN ([Q5](../open-questions.md#q5--isolationtier-needs-ordering))** — comparison
  semantics for `require_isolation=`.

| Backend | Tier | Notes |
|---------|------|-------|
| Docker (local) | `CONTAINER` | shared kernel; trusted code only |
| E2B | `MICROVM` | Firecracker |
| Modal | `GVISOR` | not hardware-VM equivalent |
| Fake | `CONTAINER` | no isolation at all; MUST NOT be used outside tests |
| Daytona | unverified | MUST NOT be claimed above `CONTAINER` until verified |

## ExecResult

```python
@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    results: list[RichOutput] | None = None   # interpreter rich outputs; None if unsupported
    meter: Meter | None = None                # v0.2
```

- `ok` property: `exit_code == 0`.
- `raise_for_status()` raises `ExecutionError` on non-zero exit.
- Returns MUST be dataclasses, never raw dicts — `result.stdout` must autocomplete.
- `results` MUST be `None` when the backend lacks rich outputs, and MUST NOT be faked from
  parsed stdout.
