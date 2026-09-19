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
               env: dict[str, str] | None = None) -> Process: ...   # NOT a coroutine

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
  `CapabilityNotSupported`. Docker declares it **off** in v0.1
  ([ADR-0024](../adr/0024-stateful-code-on-docker.md)).
- `kill()` MUST be idempotent. A second call on a dead sandbox MUST succeed silently.
- `native` MUST return the live provider object with nothing wrapped or hidden. It is
  **outside the semver contract** and every reference to it in docs MUST say so.

## `Process` (streaming)

Resolved in [ADR-0019](../adr/0019-streaming-process-handle.md).

```python
@dataclass(frozen=True)
class OutputChunk:
    stream: Literal["stdout", "stderr"]
    data: bytes

class Process(Protocol):
    async def __aenter__(self) -> Process: ...
    async def __aexit__(self, *exc) -> None: ...
    def __aiter__(self) -> AsyncIterator[OutputChunk]: ...
    async def wait(self) -> ExecResult: ...
    async def kill(self) -> None: ...
    @property
    def returncode(self) -> int | None: ...     # None while running
```

```python
async with sb.stream(["pytest", "-q"], timeout=300) as proc:
    async for chunk in proc:
        log.write(chunk.data)
    res = await proc.wait()
```

Requirements:

- `stream()` MUST be a plain function and its return value MUST NOT be awaitable, so
  omitting `async with` fails immediately rather than leaking. The process starts on
  `__aenter__`.
- `__aexit__` MUST terminate the process if still running — after normal completion, an
  early `break`, a propagating exception, or cancellation. Shielding and grace period per
  [Q7](../open-questions.md#q7--cancellation-semantics).
- Ordering MUST be preserved **within** each stream. Ordering **between** stdout and stderr
  is explicitly NOT guaranteed.
- `wait()` MUST return the terminal `ExecResult` with `streamed=True` and empty
  `stdout`/`stderr`. It MUST be idempotent. Called with output unconsumed, it drains and
  discards the remainder.
- Missing `Capability.STREAMING` MUST raise `CapabilityNotSupported` from `stream()`
  itself, before the context is entered.
- A timeout MUST raise `ExecutionTimeout` from iteration or from `wait()`.
- Typed keyword arguments only; no `**kwargs`.

**`stream_code` is deferred.** `Process` is shaped to carry interpreter rich outputs later;
streaming code execution lands when a second backend supports it, per the two-backend
promotion rule ([ADR-0003](../adr/0003-no-lowest-common-denominator.md)). Until then it is
reachable through `.native`.

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

Resolved in [ADR-0020](../adr/0020-cancellation-semantics.md). Under structured concurrency
a plain `finally: await self.kill()` is decorative — it is cancelled at its first
checkpoint — so teardown MUST be shielded.

```python
with anyio.move_on_after(TEARDOWN_GRACE, shield=True):
    await self._kill()
```

- Teardown MUST run in a **shielded, bounded** scope. `TEARDOWN_GRACE` defaults to **5 s**,
  overridable by `SBX_TEARDOWN_GRACE`. It is NOT a `create()` parameter.
- Cancelling a task awaiting `run()`, `run_code()` or a stream MUST NOT leave an orphaned
  remote process. Cancellation **kills** the remote process; detach-on-cancel is deferred.
- **Partial creation MUST be shielded narrowly**: the window between the provider returning
  an id and the handle owning it, and no wider. `create()` as a whole MUST NOT be shielded.
- If the grace expires, `OrphanedSandboxWarning` MUST be emitted naming the sandbox id,
  backend and `metadata` labels.
- **Cancellation MUST propagate as cancellation.** `CancelledError` /
  `anyio.get_cancelled_exc_class()` MUST NOT be wrapped in a `SandboxError`;
  `except BaseException` in an adapter is a bug.
- `kill()` MUST be safe to call from inside a shielded scope, MUST be idempotent, and MUST
  NOT block indefinitely.
- The provider-side timeout from `create(timeout=...)` is the guaranteed backstop: it bounds
  the worst-case orphan even when every other mechanism fails
  ([05](05-security-policy.md#mandatory-timeouts)).
- Each of the above is a contract-suite test, not adapter discretion.
