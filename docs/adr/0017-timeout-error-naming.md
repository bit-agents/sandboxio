# ADR-0017 — `SandboxTimeout` does not inherit the builtin; timeouts split by phase

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q4](../open-questions.md#q4--timeouterror-shadows-the-builtin)
**Related:** [ADR-0010](0010-stable-error-codes.md), [ADR-0015](0015-python-version-floor.md)

## Context

The input taxonomy named the timeout class `TimeoutError` (`SBX_E1302`), shadowing the
builtin. Since 3.11 — our floor ([ADR-0015](0015-python-version-floor.md)) — the builtin
`TimeoutError` is what `asyncio` and `anyio` raise, so `except sandboxio.TimeoutError`
becomes ambiguous about which library's timeout it catches.

The decisive constraint is that **builtin `TimeoutError` is a subclass of `OSError`**
(MRO: `TimeoutError → OSError → Exception`). Inheriting it therefore imports `OSError` into
our tree: `except OSError` would swallow sandbox timeouts, every instance carries dead
`errno` / `strerror` / `filename` attributes, and `OSError.__str__` and `__reduce__` need
overriding to keep our rendering contract.

Prior art is genuinely split, so it does not settle the question:

| Library | Class | Shadows the name | Inherits the builtin |
|---------|-------|------------------|----------------------|
| httpx | `TimeoutException(TransportError)` | no | no |
| aiohttp | `ServerTimeoutError(ServerConnectionError, asyncio.TimeoutError)` | no | **yes** |
| redis-py | `TimeoutError(RedisError)` | **yes** | no |
| urllib3 | `TimeoutError(HTTPError)` | **yes** | no |

httpx and urllib3 both additionally split timeouts into granular subtypes.

Separately, the catalog had **one** timeout code for situations with different remedies —
creation timing out (the backend is slow) versus execution timing out (the agent's code is
hung) — and **no** error at all for a sandbox whose own lifetime ends mid-use, which would
have surfaced as a confusing `ExecutionError` or `ConnectError`.

## Decision

**No sandboxio exception inherits from a builtin exception, and no name in the `sandboxio`
namespace shadows a builtin.** Enforced by ruff's flake8-builtins rules (A001/A004), not by
review.

```
SandboxError
├── CreationError                                    SBX_E1201
├── ConnectError                                     SBX_E1202
├── CreateTimeout(CreationError, SandboxTimeout)     SBX_E1203
├── SandboxGone                                      SBX_E1204
├── ExecutionError                                   SBX_E1301
├── SandboxTimeout                                   — base, never raised directly
│   └── ExecutionTimeout                             SBX_E1302
└── …
```

- **`SandboxTimeout` is a catch-all base with no code of its own.** `except SandboxTimeout`
  gets every timeout; the concrete classes carry the codes.
- **`SBX_E1302` keeps its meaning** — execution timed out — so nothing already documented
  changes meaning. `CreateTimeout` takes a new lifecycle code rather than reusing it.
- **`CreateTimeout` inherits both `CreationError` and `SandboxTimeout`**, so either catch
  works. Multiple inheritance inside our own tree is unambiguous and cheap.
- **`SandboxGone` (`SBX_E1204`) is not a timeout.** It means the sandbox no longer exists —
  its lifetime expired, or the backend reclaimed it — while the caller was still using it.
  Its hint points at the sandbox `timeout=` that governs lifetime, which is the actual fix.
- **No `sandboxio.TimeoutError` alias.** One name per concept.
- Internally, `anyio.fail_after` raises the builtin `TimeoutError`; adapters and core catch
  it and re-raise the matching sandboxio class with `__cause__` preserved. **A bare builtin
  `TimeoutError` escaping any public entry point is a bug**, checked by the contract suite.

## Consequences

- `except TimeoutError` does **not** catch sandboxio timeouts. This is the cost, and it is
  paid deliberately.
- In exchange we get a distinction that inheritance would destroy: with an outer
  `asyncio.timeout()` around a sandbox call, builtin `TimeoutError` means *the caller's
  deadline fired* and `SandboxTimeout` means *the sandbox's own limit fired*. Under the
  inheriting design these are indistinguishable without `isinstance`. For a library whose
  thesis is legible errors, telling two deadlines apart is worth more than `OSError`
  interop.
- The generic-catch use cases are already served: `except SandboxError` for "anything
  sandboxio can raise", and `.code` for a stable programmatic token
  ([ADR-0010](0010-stable-error-codes.md)).
- Users porting from a provider SDK that raises builtin timeouts must change their `except`
  clause. The migration guide must say so explicitly, because the failure mode is an
  uncaught exception rather than a type error.
- Three new codes means three new docs pages, generated from the catalog like the rest.
- The no-shadowing rule is general, so a future `ConnectionError`-style name is already
  decided against.
