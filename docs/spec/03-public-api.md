# 03 — Public API

Design target: autocomplete-driven and AI-legible. A coding assistant reading only the type
signatures should produce correct sandboxio code.

## Module surface

<!-- doc-sample: skip -->
```python
sandboxio.create(...)          # async, returns AsyncSandbox
sandboxio.create_sync(...)     # sync facade
sandboxio.connect(...)         # async, by sandbox id
sandboxio.register(name, path) # runtime backend registration
sandboxio.doctor()             # programmatic environment diagnosis -> DoctorReport

sandboxio.Capability, sandboxio.IsolationTier, sandboxio.Resources, sandboxio.NetworkPolicy, sandboxio.ExecResult
sandboxio.errors.*             # full error tree, also re-exported at top level
sandboxio.testing.*            # FakeBackend, fixtures, BackendContractSuite
```

Importing `sandboxio` MUST NOT import any adapter or provider SDK
([ADR-0004](../adr/0004-thin-core-lazy-adapters.md)).

## `create()`

```python
async def create(
    target: str | BackendConfig | None = None,   # DSN, typed config, or None → local Docker
    *,
    template: str | None = None,
    resources: Resources = Resources(),
    network: NetworkPolicy = NetworkPolicy(),    # egress="deny" by default
    env: dict[str, str] | None = None,
    secrets: dict[str, str] | None = None,       # separate from env; redacted everywhere
    timeout: float = 300,                        # required cap; unbounded is refused
    metadata: dict[str, str] | None = None,      # tenant_id, session_id, run_id, …
    require_isolation: IsolationTier | None = None,
) -> AsyncSandbox: ...
```

- `target=None` MUST resolve to local Docker and MUST work with no API key, no account and
  no config file.
- Backend names appearing as plain identifiers MUST be `Literal["docker","e2b","modal","fake"]`.
- `require_isolation` MUST be checked **before** provisioning, raising `ConfigurationError`
  if the resolved backend is weaker ([05](05-security-policy.md#isolation-enforcement)).
- `timeout` MUST NOT accept `None` or a non-positive value.

## Canonical usage

```python
import sandboxio

async with await sandboxio.create() as sb:                      # zero-config, local Docker
    res = await sb.run_code("print('hello')")
    print(res.stdout)

sb = await sandboxio.create("docker://python:3.12-slim")        # one-line backend swap
sb = await sandboxio.create("e2b://code-interpreter")
sb = await sandboxio.create("modal://base?gpu=T4")

res = await sb.run(["pytest", "-q"], timeout=120)
res = await sb.run_code("import pandas; print(pandas.__version__)")

await sb.files.upload("model.pkl", "/work/model.pkl")
data = await sb.files.read("/work/out.json")

async with sb.stream(["pytest", "-q"], timeout=300) as proc:   # async with is required
    async for chunk in proc:
        log.write(chunk.data)                   # OutputChunk(stream=..., data=bytes)
    res = await proc.wait()                     # res.streamed is True; stdout/stderr empty

try:
    await sb.run("sleep 999", timeout=5)
except sandboxio.SandboxTimeout:          # NOT builtin TimeoutError — see spec/04
    await sb.kill()

if sandboxio.Capability.GPU in sb.capabilities: ...
if sb.isolation is not sandboxio.IsolationTier.MICROVM:
    log.warning("weaker than microVM isolation for untrusted multi-tenant code")

sb.native.tunnels()        # Modal-specific — outside the semver contract
```

> The streaming `pip install` example from the input docs is **removed**: it cannot run
> under the default deny-egress policy, and Docker cannot express an allowlist to make it
> work ([ADR-0023](../adr/0023-docker-network-and-dependencies.md)). Dependency patterns are
> in [05](05-security-policy.md#getting-dependencies-into-a-deny-egress-sandbox); streaming
> itself is specified in [02](02-ports.md#process-streaming).

## Sync facade

Resolved in [ADR-0022](../adr/0022-sync-facade.md).

```python
with sandboxio.create_sync("docker://python:3.12-slim") as sb:
    res = sb.run_code("print('hello')")
```

- Mirrors the async surface 1:1. Entry is **explicit**; `create()` MUST NOT auto-detect sync
  context and return a different type ([ADR-0002](../adr/0002-async-first-anyio.md)).
- Implemented as **hand-written delegation** across an anyio `BlockingPortal`. It MUST
  contain no adapter logic — only delegation.
- **A parity test MUST assert** that every public async member has a sync counterpart with a
  matching `inspect.signature` once coroutine-ness is discounted. Adding an async method
  without its sync counterpart MUST fail CI.
- **The portal is per-sandbox**: `create_sync()` starts it, `__exit__` / `close()` stops it.
  A shared module-level portal is forbidden as global state
  ([ADR-0012](../adr/0012-no-telemetry-no-import-side-effects.md)).
- **N sync sandboxes means N threads.** Docs MUST state this, and MUST name the async API as
  the answer for heavy concurrency.
- Sync streaming is supported. Each `OutputChunk` crosses the portal, so each chunk costs a
  thread round-trip; the docs MUST state the cost rather than hide it.
- Errors raised through the facade MUST be the same classes with `__cause__` intact. Portal
  frames in the traceback are acceptable.

## Typing requirements

- `py.typed` MUST be present in the wheel, asserted in CI. Without it, downstream mypy
  treats the whole package as `Any`.
- Public API MUST type-check under pyright strict and mypy strict.
- `@overload` where return type depends on arguments. Dataclass returns, never raw dicts.
- Every public symbol MUST carry a docstring with a runnable example.

## Stability contract

**Covered by semver:** port protocols, error codes ([04](04-errors.md)), DSN grammar
([07](07-configuration.md)), `ExecResult` shape, `Capability` and `IsolationTier` members,
the contract suite.

**Not covered:** `.native` and everything reached through it; anything under
`sandboxio.experimental.*`; anything emitting `ExperimentalWarning`.

**Deprecation:** `DeprecationWarning` with correct `stacklevel`, plus PEP 702
`@typing_extensions.deprecated`, plus a changelog entry, plus a generous window. Warnings
alone do not reach users; the type-checker annotation is what does.
