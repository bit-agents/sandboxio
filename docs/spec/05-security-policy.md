# 05 — Security Policy

The v0.1 headline. See [ADR-0005](../adr/0005-secure-by-default.md) and
[ADR-0006](../adr/0006-isolation-tiers-first-class.md).

## Threat model

In scope:

1. Malicious or buggy agent-generated code — exfiltration, resource exhaustion, escape
   attempts.
2. Prompt-injected agents invoking tools with attacker-chosen code or arguments. sandboxio cannot
   prevent the injection; it bounds the blast radius.
3. Cross-tenant leakage — tenant A's code, files or state reaching tenant B.
4. Credential leakage into sandboxes, logs, traces or audit events.
5. Supply-chain compromise of sandboxio itself ([ADR-0004](../adr/0004-thin-core-lazy-adapters.md),
   [runbook](../runbook.md#release)).

Explicitly out of scope, and documented as such: making untrusted code safe on the
`CONTAINER` tier; defending against prompt injection; managing tenant identity or
authorization.

## Network policy

- Default is `NetworkPolicy(egress="deny")`. This applies to `create()` with no arguments.
- Adapters map it to the provider's real control:

| Backend | Mechanism |
|---------|-----------|
| Docker | network mode `none` |
| E2B | `allow_internet_access=False`, `update_network` for allowlists |
| Modal | empty `outbound_cidr_allowlist` — **not** legacy `block_network=True`, which is incompatible |
| Vercel | deny-all `networkPolicy` |
| Daytona | `network_block_all=True` |

- A backend that cannot enforce a requested policy MUST raise `CapabilityNotSupported`.
  Accepting and ignoring a network policy is the single most dangerous possible bug in this
  library.
- `egress="learn"` is v0.2; in v0.1 it MUST raise rather than degrade to `deny`.
- Where the backend reports blocked egress attempts, the count MUST appear in the audit
  record ([06](06-observability.md)).

**OPEN ([Q10](../open-questions.md#q10--deny-by-default-vs-the-demo))** — how dependency
installation and the zero-config demo work under this default.

## Mandatory timeouts

- `create()`, `run()` and `run_code()` MUST refuse unbounded execution. Default 300 s.
- `timeout=None` at the call site means "inherit the sandbox timeout", never "no limit".
- Timeout MUST raise (`CreateTimeout` or `ExecutionTimeout`), MUST NOT hang, and MUST NOT
  return partial output as success.
- A sandbox whose lifetime expires while in use MUST raise `SandboxGone`
  ([04](04-errors.md#timeouts)).

## Resource caps

- Modest CPU, memory and disk defaults MUST always be applied.
- A caller MAY raise a cap. A caller MUST NOT be able to unset one.
- Exceeding a cap MUST surface as `ResourceLimitExceeded` naming the limit, where the
  backend reports it.

## Guaranteed teardown

- Context-manager exit MUST kill the sandbox, including on exception and on cancellation
  ([Q7](../open-questions.md#q7--cancellation-semantics)).
- The Docker adapter MUST ship a Ryuk-style reaper so a crashed test run leaks no
  containers. CI asserts zero sandboxio-labelled containers remain after Docker jobs.
- `kill()` MUST be idempotent.

## Secrets

- `secrets=` is a **separate parameter from `env=`**, and MUST be redacted from logs,
  exception messages, reprs, audit events and spans.
- Secrets MUST NOT appear in a DSN. The DSN parser SHOULD detect credential-looking
  parameters and raise `ConfigurationError` pointing at the env-var convention.
- Where a backend supports broker-style injection (Vercel credential brokering, Modal
  Secrets), adapters SHOULD prefer it over writing values into the environment.
- sandboxio MUST NOT persist credentials anywhere.
- Provider credentials themselves: docs MUST prescribe least-privilege, short-lived keys.

## Tenancy

- Default pattern is **one sandbox per session or tenant-run**, labelled
  `metadata={"tenant_id": ..., "session_id": ...}`.
- Labels MUST propagate to provider-native labels where supported, so orphans are findable.
- Tenant-scoped storage MUST be used where the backend provides it (Modal Volume `sub_path`).
- Warm pools and fork-per-tenant are **opt-in documented patterns**. sandboxio MUST NOT silently
  share a sandbox across tenants under any circumstance.

## Isolation enforcement

- `require_isolation=` MUST be evaluated before provisioning; failure raises
  `ConfigurationError` and provisions nothing.
- **OPEN ([Q5](../open-questions.md#q5--isolationtier-needs-ordering))** — comparison
  semantics.
- Docs MUST state that `CONTAINER` is for trusted/dev/CI code, that gVisor is defence in
  depth rather than VM-equivalent, and that `MICROVM` is the recommended floor for untrusted
  multi-tenant code.

## Deferred to v0.2+

- Egress learning mode (`egress="learn"`) → records attempted domains, emits a paste-ready
  allowlist.
- Pre-execution security lint hook (Bandit/Semgrep) with a policy callback
  (`allow | block | require_approval`), **advisory by default** — static analysis cannot
  parse every generated snippet.
- First-class recipe for the MCP code-execution pattern: MCP tools as code APIs executed in
  a sandbox, returning summarized results.
