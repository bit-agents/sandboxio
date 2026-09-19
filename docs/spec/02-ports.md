# 02 — Port Interfaces

Protocols adapters implement. Structural (`typing.Protocol`), so third parties need not
import a base class. Type-checking conformance is necessary but **not sufficient** — the
contract suite is what proves correctness ([08](08-adapter-contract.md)).

## `Backend`

```python
class Backend(Protocol):
    name: str
    capabilities: Capability
    isolation: IsolationTier

    async def create(
        self, *,
        template: str | None = None,
        resources: Resources = Resources(),
        network: NetworkPolicy = NetworkPolicy(),
        env: dict[str, str] | None = None,
        secrets: dict[str, str] | None = None,
        timeout: float = 300,
        metadata: dict[str, str] | None = None,
    ) -> AsyncSandbox: ...

    async def connect(self, sandbox_id: str) -> AsyncSandbox: ...
```

- `create()` MUST NOT return until the sandbox is usable, or MUST raise.
- `create()` MUST apply `network` and `resources` **before** any user code can run. A
  backend that can only apply policy post-creation MUST raise `CapabilityNotSupported`
  rather than create an unpoliced sandbox.
- `connect()` MUST raise `ConnectError` for an unknown or dead id; it MUST NOT create one.
- `metadata` MUST be propagated to provider-native labels where the provider supports them,
  so external reconciliation and reaping can find orphans.

## `AsyncSandbox`

```python
class AsyncSandbox(Protocol):
    id: str
    capabilities: Capability
    isolation: IsolationTier

    async def run(self, cmd: str | list[str], *,
                  timeout: float | None = None,
                  env: dict[str, str] | None = None) -> ExecResult: ...

    async def run_code(self, code: str, *,
                       language: str = "python",
                       context_id: str | None = None,
                       timeout: float | None = None) -> ExecResult: ...

    def stream(self, cmd: str | list[str], *,
               timeout: float | None = None,
               env: dict[str, str] | None = None) -> Process: ...   # OPEN (Q6)

    async def kill(self) -> None: ...

    @property
    def files(self) -> AsyncFileSystem: ...
    @property
    def native(self) -> object: ...

    async def __aenter__(self) -> AsyncSandbox: ...
    async def __aexit__(self, *exc) -> None: ...
```

Requirements:

- **No `**kwargs` anywhere in the public surface.** Every argument is named and typed.
- `run` with a `list[str]` MUST NOT go through a shell. With a `str` it MAY, and the
  behaviour MUST be documented per adapter.
- `timeout=None` means "inherit the sandbox timeout", never "unbounded"
  ([05](05-security-policy.md#mandatory-timeouts)).
- A timeout MUST raise `ExecutionTimeout`, and MUST NOT hang or return a partial result as
  success. A sandbox that has ceased to exist MUST raise `SandboxGone`, not a timeout
  ([04](04-errors.md#timeouts)).
- `run_code` with `context_id` requires `Capability.STATEFUL_CODE`; without it, MUST raise
  `CapabilityNotSupported`. **OPEN ([Q11](../open-questions.md#q11--stateful_code-on-docker))**
  for Docker.
- `kill()` MUST be idempotent. A second call on a dead sandbox MUST succeed silently.
- `native` MUST return the live provider object with nothing wrapped or hidden. It is
  **outside the semver contract** and every reference to it in docs MUST say so.

## `Process` (streaming)

**OPEN ([Q6](../open-questions.md#q6--stream-loses-stderr-and-exit-code))** — the design
specifies `AsyncIterator[bytes]`, which loses stderr separation and the exit code. Required
properties whatever the final shape:

- stdout and stderr MUST be distinguishable.
- Ordering within a single stream MUST be preserved.
- The consumer MUST be able to obtain the terminal `ExecResult`, including `exit_code`.
- Abandoning the iterator MUST terminate the remote process, not leak it.

## `AsyncFileSystem`

```python
class AsyncFileSystem(Protocol):
    async def read(self, path: str) -> bytes: ...
    async def write(self, path: str, data: bytes | str) -> None: ...
    async def upload(self, local: str | Path, remote: str) -> None: ...
    async def download(self, remote: str, local: str | Path) -> None: ...
    async def ls(self, path: str = ".") -> list[FileInfo]: ...
    async def mkdir(self, path: str, *, parents: bool = False) -> None: ...
    async def remove(self, path: str) -> None: ...
```

- All paths are **sandbox-internal**. An adapter MUST NOT resolve a path against the host
  filesystem, except for the explicit `local` arguments of `upload`/`download`.
- `read` returns `bytes`; text decoding is the caller's. Round-trips MUST be binary-safe.
- A missing path MUST raise a mapped sandboxio error, never return empty.
- Large transfers SHOULD stream rather than buffer whole files in memory.

## Cancellation and teardown

**OPEN ([Q7](../open-questions.md#q7--cancellation-semantics))** — normative once decided.
Required properties:

- Cancelling a task awaiting `run()` MUST NOT leave an orphaned remote process.
- Teardown MUST run under a shielded cancel scope with a bounded grace period.
- Cancellation during `create()` MUST NOT leak a provisioned-but-unreferenced sandbox; where
  best-effort cleanup cannot be guaranteed, `metadata` labels plus a reaper are the backstop.
- Every one of the above is a contract-suite test, not adapter discretion.
