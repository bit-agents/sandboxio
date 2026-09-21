# The security model

What sandboxio protects you from, what it does not, and what remains your job. Read this
before running code you did not write.

The normative version is [spec/05](../spec/05-security-policy.md), written as a contract in
RFC-2119 language. This page is the same model in the order a reader needs it, and where
the two disagree the spec wins.

## The one-sentence version

sandboxio bounds the blast radius of code an agent generates. It does not make that code
safe, and no library can — what it can do is make the bound explicit, apply it by default,
and fail loudly when a backend cannot honour it.

## What is in scope

1. **Malicious or buggy agent-generated code** — exfiltration, resource exhaustion, escape
   attempts.
2. **Prompt-injected agents** invoking tools with attacker-chosen code or arguments.
   sandboxio cannot prevent the injection; it bounds what the injected code can reach.
3. **Cross-tenant leakage** — tenant A's code, files or state reaching tenant B.
4. **Credential leakage** into sandboxes, logs, traces or audit events.
5. **Supply-chain compromise of sandboxio itself** — a tiny dependency surface, lazy
   adapter imports, and a release path with no long-lived token.

## What is explicitly out of scope

Stated plainly, because a security tool that is vague about its limits is worse than none:

- **Making untrusted code safe on the `CONTAINER` tier.** A shared kernel is not a boundary
  against hostile code. Docker is for trusted, dev and CI workloads.
- **Defending against prompt injection.** That is your agent's problem, upstream of the
  sandbox. sandboxio assumes the injection already succeeded.
- **Tenant identity and authorization.** sandboxio labels and separates sandboxes; deciding
  who may ask for one is your application's job.

## The five defaults that do the work

| Default | What it stops | Escape hatch |
|---------|---------------|--------------|
| **Egress denied** on `create()` with no arguments | exfiltration, second-stage fetches, calls to APIs with found credentials | `NetworkPolicy(egress="allow")`, or an allowlist where the backend enforces one |
| **Mandatory timeouts** on `create()`, `run()` and `run_code()` | runaway cost, hung executions, denial of service | raise the value; `None` means *inherit*, never *unbounded* |
| **Resource caps always applied** — CPU, memory bounded together with swap, and a process ceiling where the backend has one | fork bombs, memory exhaustion of the host | a caller may raise a cap, never unset one |
| **Guaranteed teardown**, shielded and bounded by a grace period, on exception and on cancellation | sandboxes and bills that outlive the process | `sandboxio reap` for whatever still survives, with a warning naming it |
| **Isolation tier reported and enforceable** | a silent downgrade between environments | `require_isolation=`, checked *before* provisioning |

## The rule that makes them trustworthy

**A backend that cannot enforce what you asked for raises.** It does not approximate, warn
and continue, or degrade to something weaker.

A `NetworkPolicy(allow=[...])` against Docker raises `CapabilityNotSupported` instead of
granting full bridge access, because Docker has no per-host egress filtering. `egress="learn"`
raises in v0.1 rather than falling back to `deny`. `Resources(disk_mb=...)` on Docker is
refused rather than ignored. A security control that appears to apply and does not is the
highest-severity bug this project can ship
([H1](../hazards.md#h1--a-security-default-silently-does-not-apply)), and the contract suite
proves deny-by-default against a canary host on every real backend.

## Choosing a tier

The tier measures one property: resistance to kernel escape by an adversarial tenant
([isolation tiers](isolation-tiers.md)).

| Your code is | Use | Why |
|--------------|-----|-----|
| yours, reviewed, or CI's own | `CONTAINER` (Docker) | a shared kernel is fine when nothing in the sandbox is trying to leave it |
| agent-generated, single-tenant, low-value data | `CONTAINER` with egress denied, or better | the network default is doing most of the work here |
| untrusted, multi-tenant, or touching other people's data | `MICROVM` (E2B) as the floor | a dedicated guest kernel; a kernel bug is not immediately a host compromise |

Make it enforceable rather than documented:

```python
import sandboxio
from sandboxio import IsolationTier

sb = await sandboxio.create("e2b://", require_isolation=IsolationTier.MICROVM)
```

A weaker backend fails before anything is provisioned or billed. An `UNKNOWN`-tier backend
satisfies no requirement at all, and creating on one warns.

## What the container tier does and does not harden

Everything that costs no compatibility is applied: all capabilities dropped,
`no-new-privileges`, a process ceiling, and swap bounded together with memory
([ADR-0028](../adr/0028-docker-container-hardening.md)).

Two things are **not** applied, because both break ordinary images: running as a non-root
user, and a read-only root filesystem. So a Docker sandbox runs as root on a writable
rootfs inside the container ([H16](../hazards.md#h16--docker-sandboxes-run-as-root-on-a-writable-rootfs)).
That gap is recorded rather than papered over, and it is one more reason `CONTAINER` is not
the tier for hostile code.

## Secrets

`secrets=` is a separate parameter from `env=` so that redaction has something to act on.
Values passed there are removed from messages, notes, reprs, audit events, spans and CLI
output before anything is rendered, which means an exception you log is safe to log.

sandboxio persists no credential anywhere. Secrets in a DSN are refused with a
`ConfigurationError` pointing at the environment-variable convention — a DSN carries a
backend, a template and `timeout`, and is safe to put in a config file. For your own
provider credentials, use short-lived, least-privilege keys.

## Tenancy

One sandbox per session or tenant-run, labelled with your own metadata:

```python
import sandboxio

sb = await sandboxio.create(metadata={"tenant_id": "acme", "session_id": "s-1"})
```

Labels propagate to provider-native labels where the backend supports them, which is what
makes an orphan findable later by `sandboxio reap --label tenant_id=acme`. **sandboxio will
not silently share a sandbox across tenants under any circumstance.** Warm pools and
fork-per-tenant are opt-in patterns you choose, never a default you get.

## Your side of the contract

Before running untrusted code:

- [ ] Pick the tier deliberately, and state it in code with `require_isolation=`.
- [ ] Leave egress denied, or allowlist specific hosts — not `egress="allow"` because a
      dependency was missing ([the dependency patterns are here](../how-to/docker.md#getting-dependencies-into-a-deny-egress-sandbox)).
- [ ] Pass credentials as `secrets=`, and only the ones that sandbox actually needs.
- [ ] Label sandboxes with tenant and session, so an orphan is attributable.
- [ ] Turn on an audit sink, so what ran is a record rather than a memory
      ([audit and tracing](../how-to/observability.md)).
- [ ] Put your own authorization in front of sandbox creation. sandboxio does not do it.

## What this project does not claim

- No third-party security audit has been performed.
- It is **pre-alpha**, with nothing released; the API is not stable yet.
- No v0.1 backend provides the `GVISOR` tier — the tier exists in the model, not in what
  shipped.
- Isolation tiers are claims about someone else's infrastructure, published only with a
  dated link to the provider's own documentation and re-verified quarterly
  ([ADR-0006](../adr/0006-isolation-tiers-first-class.md)).

Vulnerabilities go privately through the Security tab, never an issue
([SECURITY.md](https://github.com/bit-agents/sandboxio/blob/main/SECURITY.md)).
