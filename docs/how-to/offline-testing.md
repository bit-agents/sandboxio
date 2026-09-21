# How to test agent tools offline

`sandboxio.testing.FakeBackend` is a supported product surface, not a test helper: it passes
the same contract suite as Docker and E2B, executes nothing, and needs no daemon, network or
account. Your tool's tests run in milliseconds anywhere pytest runs.

This page as a runnable file, executed by CI like every other example:
[`examples/test_my_tool.py`](https://github.com/bit-agents/sandboxio/blob/main/examples/test_my_tool.py).

## The fixture

The package registers a pytest plugin, so `sbx_fake` is available with no `conftest.py`.

```python
import pytest
from sandboxio import ExecResult, NetworkPolicy


@pytest.mark.anyio
async def test_my_tool(sbx_fake):
    sbx_fake.on_run_code(match="import pandas", returns=ExecResult(0, "2.2.1\n", ""))
    res = await sbx_fake.sandbox.run_code("import pandas; print(pandas.__version__)")
    assert "2.2.1" in res.stdout
    assert sbx_fake.calls[0].op == "create"
    assert sbx_fake.calls[0].network == NetworkPolicy(egress="deny")   # == not is
```

- `sbx_fake.sandbox` is a ready sandbox; `sbx_fake.calls` records every call with its
  arguments, including the policy in effect at create.
- `on_run(match=..., returns=...)` and `on_run_code(...)` script responses by substring.
  `hangs=True` makes the operation run until its timeout — the way to test your timeout
  handling in three seconds of wall time (virtual time, `time_scale=0.01`).
- Unscripted commands go through a tiny virtual shell (`echo`, `sh -c`, `printenv`, `seq`,
  `sleep`, `curl`, `cat`); anything else exits `127`. Unscripted `run_code` recognises
  assignments, literals and `print()` without executing; a recognised network call such as
  `urllib.request.urlopen(...)` obeys the sandbox's `NetworkPolicy`, like `curl` does.

## Through the DSN, for code that creates its own sandbox

```python
import sandboxio
from sandboxio import ExecResult
from sandboxio.testing import FakeBackend


async def my_tool(query: str) -> str:
    async with await sandboxio.create("docker://python:3.12-slim") as sb:
        return (await sb.run_code(f"print({query!r}.upper())")).stdout


async def test_tool_without_docker() -> None:
    fake = FakeBackend()
    fake.on_run_code(match="upper", returns=ExecResult(0, "HELLO\n", ""))
    sandboxio.register("docker", lambda: fake)          # the DSN now resolves to the fake
    assert await my_tool("hello") == "HELLO\n"
    assert fake.calls[0].timeout == 300
```

`register()` beats entry points, so production code keeps its `docker://` DSN and the test
decides what that means. This is how the README's Docker examples run in this repository's
own CI.

## Simulating the provider misbehaving

```python
from sandboxio.testing import FakeBackend

fake = FakeBackend()
fake.simulate(create_takes=3600)            # create() hits its timeout → CreateTimeout
fake.simulate(create_fails=RuntimeError())  # → CreationError with __cause__
fake.simulate(kill_hangs=True)              # teardown exceeds the grace → OrphanedSandboxWarning
fake.simulate(auth_missing=True)            # → AuthError naming SBX_FAKE_TOKEN
fake.simulate()                             # back to normal
fake.expire("fake-0001")                    # the provider reclaimed it → SandboxGone
```

Declare fewer capabilities to test your capability branches:

```python
from sandboxio import Capability
from sandboxio.testing import FakeBackend

minimal = FakeBackend(capabilities=Capability.RUN_COMMAND | Capability.NETWORK_POLICY)
```

## What the fake will not do

It will not emulate a feature a real backend lacks, and if it ever diverges from a real
backend that is a suite gap fixed with a shared test, not a special case in the fake
([spec/08](../spec/08-adapter-contract.md#fakebackend)). It reports `IsolationTier.CONTAINER`
while isolating nothing — it is for tests, and `require_isolation` behaves accordingly.
