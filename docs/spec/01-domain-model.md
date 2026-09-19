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

A single execution within a sandbox, returned by `stream()`. An async context manager that
iterates tagged output chunks and terminates in an `ExecResult`
([ADR-0019](../adr/0019-streaming-process-handle.md)).

- MUST terminate the remote process on context exit if it is still running — on normal
  completion, early `break`, exception, or cancellation.
- MUST distinguish stdout from stderr, and MUST preserve ordering **within** each stream.
  Ordering **between** the two streams is explicitly not guaranteed.
- MUST expose the terminal `ExecResult`, including `exit_code`, via `wait()`.

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
    COST_REPORTING = auto()          # post-hoc cost attribution by label (v0.2)
```

Rules:

1. A declared capability MUST have a passing contract test for that backend.
2. An undeclared capability, if invoked, MUST raise `CapabilityNotSupported` — never a
   silent no-op, never a degraded emulation.
3. Capabilities are discovered, not inferred from backend name. Callers branch on flags.

## IsolationTier

```python
class IsolationTier(Enum):
    UNKNOWN   = "unknown"     # undeclared or unverified — satisfies NO requirement
    CONTAINER = "container"   # runc, shared kernel — trusted/dev/CI code only
    GVISOR    = "gvisor"      # user-space kernel — defence in depth, not VM-equivalent
    MICROVM   = "microvm"     # dedicated guest kernel — floor for untrusted multi-tenant
```

Ordering is an **explicit internal rank map** (`UNKNOWN 0, CONTAINER 10, GVISOR 20,
MICROVM 30`), not a property of the member values ([ADR-0018](../adr/0018-isolation-tier-ordering.md)).

- The rank orders **one thing only: resistance to kernel escape by an adversarial tenant**,
  under the threat model in [05](05-security-policy.md#threat-model). It MUST NOT be
  presented as a general "more secure" scale.
- Rich comparisons (`<`, `<=`, `>`, `>=`) derive from the rank; arithmetic is not available.
  `tier.satisfies(minimum)` is the form the docs teach.
- Ranks are spaced by 10 so a tier can be inserted without renumbering. Adding a stronger
  tier means an existing `require_isolation` accepts it automatically.
- Every member MUST have a rank, asserted by a test that enumerates the class.
- Every backend and every sandbox MUST report a tier.
- A tier above `CONTAINER` MUST be justified by provider documentation, recorded with a date
  ([ADR-0006](../adr/0006-isolation-tiers-first-class.md)).

### `UNKNOWN`

- `UNKNOWN` is the **default for any adapter that does not declare a tier**. An adapter
  author who says nothing has claimed nothing.
- It satisfies **no** requirement, including `require_isolation=CONTAINER`.
- `require_isolation=UNKNOWN` is meaningless and MUST raise `ConfigurationError`.
- Creating on an `UNKNOWN`-tier backend MUST emit `UnverifiedIsolationWarning` once per
  backend per process.

| Backend | Tier | Notes |
|---------|------|-------|
| Docker (local) | `CONTAINER` | shared kernel; trusted code only |
| E2B | `MICROVM` | Firecracker |
| Modal | `GVISOR` | not hardware-VM equivalent |
| Fake | `CONTAINER` | executes nothing; MUST NOT be used outside tests |
| Daytona | `UNKNOWN` | unverified — not claimed at any tier until documented with a date |

## ExecResult

```python
@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    results: list[RichOutput] | None = None   # interpreter rich outputs; None if unsupported
    meter: Meter | None = None                # v0.2 — duration + backend, no cost
    streamed: bool = False                    # True → stdout/stderr empty by construction
```

- `ok` property: `exit_code == 0`.
- `raise_for_status()` raises `ExecutionError` on non-zero exit.
- Returns MUST be dataclasses, never raw dicts — `result.stdout` must autocomplete.
- `results` MUST be `None` when the backend lacks rich outputs, and MUST NOT be faked from
  parsed stdout.
- `streamed` is `True` only for a result from `Process.wait()`. When set, `stdout` and
  `stderr` MUST be empty — the caller already consumed the bytes, and streaming exists to
  avoid buffering them twice.
