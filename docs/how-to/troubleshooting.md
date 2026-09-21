# Troubleshooting

Diagnosis by **symptom**, for when you do not already have an `SBX_E` code to look up. If
you do have one, go straight to the [error reference](../errors/README.md) — every code has
a page, and every exception already carries the fix in its `hint`.

Before anything else:

```bash
sandboxio doctor          # what is installed, reachable and missing, with a fix per line
sandboxio doctor --json   # the same, paste-friendly; prints credential names, never values
```

`doctor` exits `0` when every installed backend is healthy. It makes no provider API call,
so it costs nothing to run twice.

## Symptom index

| What you saw | Go to |
|--------------|-------|
| `ModuleNotFoundError`, or an error naming an extra you have not installed | [Nothing is installed yet](#nothing-is-installed-yet) |
| `cannot reach the Docker daemon` | [Docker is not reachable](#docker-is-not-reachable) |
| Code inside the sandbox cannot resolve a hostname or connect | [The sandbox has no network — by design](#the-sandbox-has-no-network--by-design) |
| The command clearly failed, but no exception was raised | [A failed command is not an exception](#a-failed-command-is-not-an-exception) |
| A call raised after roughly 300 seconds | [Three different timeouts](#three-different-timeouts) |
| `except TimeoutError:` did not catch a sandbox timeout | [Three different timeouts](#three-different-timeouts) |
| `CapabilityNotSupported`, for a call that works on another backend | [The backend refuses instead of pretending](#the-backend-refuses-instead-of-pretending) |
| `ConfigurationError` about `Resources(...)` | [The backend refuses instead of pretending](#the-backend-refuses-instead-of-pretending) |
| Containers still on the host after the process exited | [Sandboxes that outlived the process](#sandboxes-that-outlived-the-process) |
| `OrphanedSandboxWarning` | [Sandboxes that outlived the process](#sandboxes-that-outlived-the-process) |
| `UnverifiedIsolationWarning`, or `create()` refusing a tier | [Isolation warnings and refusals](#isolation-warnings-and-refusals) |
| `AuthError`, `RateLimitError` | [Provider credentials](#provider-credentials) |
| A secret you passed is not visible inside the sandbox | [Secrets are not `env`](#secrets-are-not-env) |
| A test passes but nothing actually ran | [The fake executes nothing](#the-fake-executes-nothing) |

## Nothing is installed yet

The core package contains no backend. Two different errors say so:

| Code | Means | Fix |
|------|-------|-----|
| [`SBX_E1002`](../errors/SBX_E1002.md) `BackendNotInstalled` | a first-party backend whose extra is missing | `uv pip install "sandboxio[docker]"` |
| [`SBX_E1001`](../errors/SBX_E1001.md) `BackendNotFound` | no backend is registered under that name at all | check the spelling; the hint lists what *is* registered |

A third-party adapter is `BackendNotFound` rather than `BackendNotInstalled` — sandboxio
cannot know its install command, so the hint names what it does know.

## Docker is not reachable

```text
sandboxio.errors.CreationError: [SBX_E1201] cannot reach the Docker daemon
  Fix:  Start Docker, or set DOCKER_HOST; `sandboxio doctor` explains.
```

The adapter creates its client on first use, never at import, so this surfaces at
`create()` rather than at `import sandboxio`. Work through it in this order:

1. `docker info` — if that fails, this is a Docker problem, not a sandboxio one.
2. `sandboxio doctor` — it reports reachability and the engine version.
3. A non-default socket (Colima, Rancher Desktop, a remote engine) needs `DOCKER_HOST`
   exported in the same shell that runs your program.

## The sandbox has no network — by design

This is the single most common surprise, and it usually does **not** raise a sandboxio
error. `create()` denies egress by default, so the failure happens *inside* your code: a
DNS resolution error, a connection refused, a `pip install` that cannot reach PyPI. What
comes back is an `ExecResult` with a non-zero `exit_code` and the real reason in `stderr`.

```python
import sandboxio

async with await sandboxio.create() as sb:
    res = await sb.run(["python", "-c", "import urllib.request; urllib.request.urlopen('https://example.com')"])
    print(res.exit_code, res.stderr)   # non-zero, and a socket error — not an SBX code
```

That is the deny-by-default policy working ([why](../explanation/deny-by-default.md)). Your
options, in order of preference:

1. **Bake the dependencies into the image**, or upload an **offline wheelhouse** — both
   work under the default policy
   ([Docker how-to](docker.md#getting-dependencies-into-a-deny-egress-sandbox)).
2. **Allowlist the hosts you need**, on a backend that can enforce one
   ([E2B how-to](e2b.md#network-allowlists)). Docker cannot, and says so rather than
   granting full access.
3. **Open egress explicitly** with `NetworkPolicy(egress="allow")`, when the code is
   trusted and you have decided that is acceptable.

Two things this is *not*:

- **Not an image-pull problem.** `docker pull` runs on the host daemon, outside the
  container's network namespace, so a deny-egress sandbox still starts from a remote image.
- **Not** [`SBX_E1401`](../errors/SBX_E1401.md) `NetworkPolicyViolation` in most cases. That
  code is raised where the backend itself reports a blocked attempt; a container with
  `network: none` has nothing to report, because there is no network stack to block.

## A failed command is not an exception

`run()` and `run_code()` return an `ExecResult`. A non-zero exit is data, not a raise —
the same shape as `subprocess.run()` without `check=True`:

```python
import sandboxio

async with await sandboxio.create() as sb:
    res = await sb.run(["pytest", "-q"])
    if not res.ok:                 # exit_code != 0
        print(res.stderr)
    res.raise_for_status()         # ExecutionError (SBX_E1301) with the result attached
```

If a step in your pipeline "silently did nothing", check `res.ok` first. When it did raise,
[`SBX_E1301`](../errors/SBX_E1301.md) carries the whole result: `exc.result.stderr` and
`exc.result.exit_code`.

## Three different timeouts

They look alike and have different fixes:

| Raised | Code | What ran out | Fix |
|--------|------|--------------|-----|
| `CreateTimeout` | [`SBX_E1203`](../errors/SBX_E1203.md) | the sandbox did not become usable in time | raise `timeout=` on `create()`, or use a warmer image/template |
| `ExecutionTimeout` | [`SBX_E1302`](../errors/SBX_E1302.md) | one `run()`, `run_code()` or stream | raise `timeout=` on the call, or make the code finish sooner |
| `SandboxGone` | [`SBX_E1204`](../errors/SBX_E1204.md) | the sandbox's whole lifetime, while you were using it | raise `timeout=` on `create()` — this is the sandbox-level budget, not the call's |

`SandboxGone` is deliberately **not** a timeout subclass: the fix is a different parameter.

`timeout=None` on a call means *inherit the sandbox timeout*, never *unbounded*, and
`timeout=None` on `create()` is refused outright. There is no way to ask for forever.

**`except TimeoutError:` will not catch any of these.** On Python 3.11+ the builtin is what
`asyncio` raises, so inheriting from it would make "my deadline fired" and "the sandbox's
limit fired" indistinguishable ([ADR-0017](../adr/0017-timeout-error-naming.md)). Catch the
library's own base instead:

```python
import sandboxio

try:
    async with await sandboxio.create() as sb:
        await sb.run("sleep 999", timeout=5)
except sandboxio.SandboxTimeout as exc:     # CreateTimeout and ExecutionTimeout
    print(exc.code, exc.hint)
```

## The backend refuses instead of pretending

A backend that cannot honour a typed argument raises rather than quietly ignoring it. This
is the rule that makes the defaults worth trusting, and it is also why a call that works on
one backend can fail on another:

| You asked for | On | Result |
|---------------|-----|--------|
| `NetworkPolicy(allow=[...])` | Docker | `CapabilityNotSupported` — Docker has no per-host egress filtering ([ADR-0023](../adr/0023-docker-network-and-dependencies.md)). Allowlists are an E2B/Modal capability |
| `run_code(context_id=...)` | Docker | `CapabilityNotSupported` — `STATEFUL_CODE` is off for Docker in v0.1 ([ADR-0024](../adr/0024-stateful-code-on-docker.md)) |
| `Resources(disk_mb=...)` | Docker | `ConfigurationError` — Docker cannot cap disk; drop it or pick a backend that can |
| `Resources(...)` | E2B | `ConfigurationError` — caps belong to the template; pick a template with the resources you need |
| `egress="learn"` | anything | raises in v0.1 rather than degrading to `deny` |

Never write a `try/except` that swallows one of these into a fallback: the refusal is the
feature. Discover instead of guessing:

```python
import sandboxio
from sandboxio import Capability

async with await sandboxio.create() as sb:
    if Capability.STATEFUL_CODE in sb.capabilities:
        await sb.run_code("x = 41", context_id="session-1")
```

## Sandboxes that outlived the process

Normal teardown happens on context-manager exit, including on exception and on
cancellation. What survives that is visible and removable:

```bash
sandboxio reap                          # lists, running and stopped — dry run by default
sandboxio reap --label tenant_id=acme   # narrowed by your own metadata
sandboxio reap --kill                   # removes what was listed
```

Three ways a container is still there:

- **The process crashed with the reaper disabled** (`SBX_DOCKER_REAPER=0`). The Ryuk-style
  sidecar normally removes the session's containers when the process dies.
- **The lifetime expired.** The container's PID 1 is `sleep <timeout>`; when it fires,
  Docker leaves the container *stopped*, not removed.
- **Teardown exceeded its grace.** You will have seen `OrphanedSandboxWarning` with the id
  and labels — that warning exists precisely so `reap` has something to go on. Raise
  `SBX_TEARDOWN_GRACE` if a slow host makes 5 seconds too tight.

Always ran under `async with`, and still leaking? That is a bug worth an issue — CI asserts
zero `io.sandboxio.managed` containers remain after every Docker job, so a reproduction is
actionable ([H2](../hazards.md#h2--leaked-sandboxes)).

## Isolation warnings and refusals

`UnverifiedIsolationWarning` means the backend reports `UNKNOWN` — its adapter has not
verified what it isolates with. It is emitted once per backend, and an `UNKNOWN` backend
satisfies no `require_isolation=` requirement at all.

`create(require_isolation=...)` raising `ConfigurationError` is the feature working: the
check runs **before** provisioning, so nothing was created and nothing was billed. Either
point at a backend that meets the tier, or lower the requirement deliberately —
`require_isolation=UNKNOWN` is meaningless and raises.

Read [isolation tiers](../explanation/isolation-tiers.md) before deciding which way to go.
`CONTAINER` is not a boundary against hostile code.

## Provider credentials

[`SBX_E1501`](../errors/SBX_E1501.md) `AuthError` names the exact environment variable it
wanted — export that one, in the shell that runs your program, and re-run
`sandboxio doctor` to confirm it is seen. `doctor` reports variables by name with set/unset
and never prints a value.

[`SBX_E1502`](../errors/SBX_E1502.md) `RateLimitError` is the provider throttling you.
sandboxio does not retry on your behalf in v0.1 — back off in your own code.

## Secrets are not `env`

`secrets=` and `env=` are separate parameters on purpose. Values passed as `secrets=` are
redacted everywhere they could surface: messages, notes, reprs, audit events, spans and CLI
output. If you are grepping logs for a secret to confirm it arrived, you will not find it —
that is the redaction, not a delivery failure.

Credentials in a DSN are refused: the DSN carries a backend, a template and `timeout`, and
nothing else. Use typed configuration and the provider's environment variable
([spec/05](../spec/05-security-policy.md#secrets)).

## The fake executes nothing

`fake://` and the `sbx_fake` fixture run no code at all. A test that asserts on real output
without scripting a result first is asserting on a default, not on your logic:

```python
import pytest
from sandboxio import ExecResult


@pytest.mark.anyio
async def test_tool(sbx_fake):
    sbx_fake.on_run_code(match="import pandas", returns=ExecResult(0, "2.2.1\n", ""))
    res = await sbx_fake.sandbox.run_code("import pandas; print(pandas.__version__)")
    assert "2.2.1" in res.stdout
```

The fake reports `CONTAINER` while isolating nothing, because it is for tests — never use
it as a stand-in for a security boundary. More in
[offline testing](offline-testing.md).

## Still stuck

- Include `sandboxio doctor --json` in any report; it is built for pasting and prints no
  secrets.
- A reproducible bug goes to [issues](https://github.com/bit-agents/sandboxio/issues/new/choose);
  a question goes to [discussions](https://github.com/bit-agents/sandboxio/discussions)
  ([SUPPORT.md](https://github.com/bit-agents/sandboxio/blob/main/SUPPORT.md)).
- A security vulnerability goes privately through the Security tab, never an issue
  ([SECURITY.md](https://github.com/bit-agents/sandboxio/blob/main/SECURITY.md)).
- A default that appears to apply and does not is the highest-severity bug this project can
  have ([H1](../hazards.md#h1--a-security-default-silently-does-not-apply)). Report it as
  one.
