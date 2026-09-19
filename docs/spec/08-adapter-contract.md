# 08 — Adapter Contract

`sandboxio.testing.suite` is **normative**. Where this prose and the suite disagree, the suite
wins; behaviour covered by neither is not guaranteed
([ADR-0007](../adr/0007-contract-suite-as-spec.md)).

## Conforming in one import

```python
from sandboxio.testing.suite import BackendContractSuite

class TestFlyAdapter(BackendContractSuite):
    backend = FlyBackend(...)
```

The suite reads `backend.capabilities` and runs the matching tests, **plus** negative tests
for every undeclared capability.

Command probes (`cmd_echo`, `cmd_hang`, …) default to a POSIX shell and are overridable
for other images. Behaviour probes (`assert_no_orphans`, `simulate_kill_hang`,
`expire_sandbox`, …) let the suite drive situations only the adapter can provoke; a probe
the adapter does not implement **skips visibly** rather than passing. Observability rows
need the adapter constructed with an `AuditConfig` holding a `RecordingSink`, exposed as
`audit_sink`. `FakeBackend`'s own subclass in `tests/test_fake_contract.py` is the reference.

## Coverage map

| Area | Requirements |
|------|--------------|
| Lifecycle | create → run → kill; context-manager teardown on normal exit **and** on exception; double-`kill()` idempotent; `connect()` to unknown id raises `ConnectError` |
| Cancellation | cancel mid-`run`, mid-`run_code`, mid-stream and mid-`create` each leave no orphan; teardown is shielded and bounded; only the id-known window of `create()` is shielded, not the whole call |
| Cancellation identity | cancellation surfaces as `CancelledError` / the anyio cancelled class, **never** wrapped in a `SandboxError`; `kill()` is callable from inside a shielded scope; grace expiry emits `OrphanedSandboxWarning` |
| `run` | exit codes; stdout/stderr separated; `env` injected; `list[str]` does not go through a shell; timeout raises `ExecutionTimeout` and does not hang |
| `run_code` | basic execution; syntax and runtime errors surface with non-zero exit; rich outputs present iff declared; `context_id` works iff `STATEFUL_CODE`, else raises |
| Streaming | `stream()` is not awaitable; per-stream ordering preserved; stdout/stderr distinguishable; `wait()` returns `streamed=True` with empty stdout/stderr and is idempotent; `CapabilityNotSupported` raised from `stream()` before entry |
| Streaming cleanup | the remote process is terminated after **each** of: full iteration, early `break`, exception inside the block, cancellation inside the block — four separate cases, each asserting no orphan remains |
| Filesystem | read/write/upload/download/ls/mkdir/remove round-trips; binary safety; missing path raises mapped error; no host-path escape |
| Policy | **deny actually denies** — egress to a canary host fails; allowlist permits only listed hosts; resource caps applied; caps cannot be unset |
| Errors | every provider exception mapped into the sandboxio tree; `__cause__` preserved; unsupported typed kwargs raise `CapabilityNotSupported`; `AuthError` names the missing env var |
| Timeouts | `create()` timeout raises `CreateTimeout`, execution timeout raises `ExecutionTimeout`, expired sandbox raises `SandboxGone`; **no bare builtin `TimeoutError` escapes any public entry point** |
| Capability honesty | every declared flag has a passing test; every undeclared flag raises when invoked |
| Isolation honesty | the backend reports a tier; an undeclared tier resolves to `UNKNOWN`; `require_isolation` above the reported tier fails **before** provisioning; `UNKNOWN` satisfies nothing |
| Observability | one operation record per operation; secrets absent from every sink; `metadata` propagated to provider-native labels |
| Sync parity | every public async member has a sync counterpart with a matching signature; errors through the facade are the same classes with `__cause__` intact; the per-sandbox portal is stopped on exit |

## Adapter rules

1. **Map every native exception**, `raise ... from e`. A raw provider exception escaping the
   adapter is a bug.
2. **Never silently no-op.** An unhonourable typed argument raises.
3. **Never fake a capability.** No parsing stdout into `results`, no emulated stateful
   contexts, no pretend network policy.
4. **Never block the event loop.** Sync provider SDKs go through `anyio.to_thread`.
5. **Propagate `metadata`** to provider labels so orphans are findable.
6. **Apply policy before user code can run**, or raise.
7. **Pin nothing hard.** Adapters declare loose lower bounds; the nightly latest-SDK canary
   is what catches breakage ([runbook](../runbook.md#provider-churn-response)).

## FakeBackend

`sandboxio.testing.FakeBackend` is a supported **product surface**, not an internal test helper.
It MUST pass the same contract suite.

- In-memory; no Docker, no cloud, no network.
- Deterministic: seeded outputs, virtual clock for timeouts, scripted responses
  (`fake.on_run_code(match="import pandas", returns=ExecResult(0, "2.2.1\n", ""))`).
- Records every call for assertions (`fake.calls`), including audit events and the policy in
  effect.
- Simulates failures on demand: timeout, `NetworkPolicyViolation`, non-zero exit, flakiness.
- Reachable as `sandboxio.create("fake://")` through the same DSN mechanism as real backends.
- Ships a pytest plugin with an `sbx_fake` fixture, registered by entry point.

```python
def test_my_agent_tool(sbx_fake):
    sbx_fake.on_run_code(match="import pandas", returns=ExecResult(0, "2.2.1\n", ""))
    result = my_agent_tool(sandbox=sbx_fake.sandbox, query="check pandas version")
    assert "2.2.1" in result
    assert sbx_fake.calls[0].network == NetworkPolicy(egress="deny")   # == not is (Q13)
```

If `FakeBackend` diverges from real backends, that is a **suite gap**: the fix is a new
shared test, not a special case in the fake.

## CI matrix

| Job | Backend | When |
|-----|---------|------|
| unit + fake contract | FakeBackend | every PR |
| docker contract | Docker via testcontainers, Ryuk cleanup | every PR |
| e2b contract | E2B (real) | nightly + release, gated on secret |
| modal contract | Modal (real) | nightly + release, gated on secret |
| **latest-SDK canary** | all cloud adapters against `pip install -U <provider>` | nightly — the churn early-warning system |
| framework matrix | LangGraph / OpenAI Agents adapters across supported versions | weekly |

Python matrix: **3.11, 3.12, 3.13, 3.14** on the unit and fake-contract job; 3.11 is a
required check and 3.14 is the default ([ADR-0015](../adr/0015-python-version-floor.md)).
Note `crewai` caps at `<3.14`, so its adapter job runs on 3.11-3.13 only.

Canary failures MUST open an auto-labelled `provider-churn` issue, which feeds the public
churn-absorption log.

## Hygiene gates (CI-enforced)

- Import budget: `python -X importtime -c "import sandboxio"` under 150 ms; hard fail over 200 ms.
- No network at import, verified with `pytest-socket`.
- No leaked containers: Docker jobs assert zero sandboxio-labelled containers remain.
- pyright + mypy strict on the public API; `py.typed` present in the wheel.
- Wheel contents: base install pulls no adapter code; extras resolve.
- Error catalog: every code has a docs page and vice versa.

## Adapter authoring

An **adapter template repo** wired to the contract suite ships alongside the authoring
guide. It is the ecosystem lever: a third party should reach a conforming adapter without
reading core's source.
