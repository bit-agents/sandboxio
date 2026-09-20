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
- A backend that cannot enforce a requested policy MUST raise `CapabilityNotSupported`.
  Accepting and ignoring a network policy is the single most dangerous possible bug in this
  library ([H1](../hazards.md#h1--a-security-default-silently-does-not-apply)).
- `egress="learn"` is v0.2; in v0.1 it MUST raise rather than degrade to `deny`.
- Where the backend reports blocked egress attempts, the count MUST appear in the audit
  record ([06](06-observability.md)).
- **Network policy governs the sandbox's egress, not the host's image pull.** `docker pull`
  runs on the host daemon, outside the container, so a deny-egress sandbox still starts from
  a remote image. This distinction is what made the zero-config demo look like it conflicted
  with the default when it never did.

Adapters map the policy to the provider's real control:

| Backend | Deny | Allowlist |
|---------|------|-----------|
| Docker | network mode `none` | **not supported** — Docker has no per-host egress filtering; `--network` accepts only `none \| bridge \| host \| container \| <custom>`. A non-empty `allow` MUST raise `CapabilityNotSupported` ([ADR-0023](../adr/0023-docker-network-and-dependencies.md)) |
| E2B | `allow_internet_access=False` | `network={deny_out: [0.0.0.0/0], allow_out: [...]}` at create |
| Modal | empty `outbound_cidr_allowlist` — **not** legacy `block_network=True`, which is incompatible | `outbound_cidr_allowlist` |
| Vercel | deny-all `networkPolicy` | `networkPolicy` |
| Daytona | `network_block_all=True` | unverified |

Per-backend docs MUST state that allowlists are an E2B/Modal capability, so nobody writes
one against Docker and assumes it applies.

### Getting dependencies into a deny-egress sandbox

Two supported patterns on Docker, both working under the default policy:

1. **Image prep** — dependencies baked into the image ahead of time. The primary pattern.
2. **Offline wheelhouse** — `files.upload()` the wheels, then
   `uv pip install --offline --find-links /wheels`. Needs no network at all.

A mutable "install then lock down" setup window is **rejected**: Docker cannot change a
running container's network mode, and a policy that varies over a sandbox's life makes the
policy in effect time-varying in the audit record.

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

### Where caps belong to the template

Some providers fix CPU, memory and disk in the image or template, with no per-sandbox
override: E2B is the v0.1 example. Such a backend still applies concrete caps — the
template's — so the guarantee above holds, but it cannot honour a caller's `Resources`.

- It MUST refuse a non-default `Resources(...)` with `ConfigurationError` naming the
  template as the place to change them, and MUST NOT accept and ignore the value.
- It MUST declare `resource_caps_supported = False` to the contract suite
  ([08](08-adapter-contract.md#coverage-map)), which then asserts the refusal instead of
  the per-sandbox cap rows.
- A backend that can neither apply caps nor name a template that does MUST NOT create.

## Guaranteed teardown

- Context-manager exit MUST kill the sandbox, including on exception and on cancellation,
  in a **shielded scope bounded by `TEARDOWN_GRACE`** (default 5 s)
  ([02](02-ports.md#cancellation-and-teardown)).
- The mandatory `create(timeout=...)` is the guaranteed backstop for teardown that fails:
  it is enforced provider-side and cannot be cancelled away. This is why timeouts are
  non-negotiable — the rule is as much about cost as about security.
- Grace expiry MUST emit `OrphanedSandboxWarning` with the sandbox id and labels so an
  operator can reap it.
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

- `require_isolation=` MUST be evaluated **before provisioning**; failure raises
  `ConfigurationError` and provisions nothing.
- Comparison uses the explicit rank in [01](01-domain-model.md#isolationtier), which orders
  escape resistance only ([ADR-0018](../adr/0018-isolation-tier-ordering.md)).
- An `UNKNOWN`-tier backend satisfies no requirement at all, and creating on one without a
  requirement MUST emit `UnverifiedIsolationWarning`.
- `require_isolation=UNKNOWN` MUST raise `ConfigurationError`.
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
