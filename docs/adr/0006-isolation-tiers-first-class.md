# ADR-0006 — Isolation tier is a first-class, reported property

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0005](0005-secure-by-default.md), [ADR-0003](0003-no-lowest-common-denominator.md)
**Related:** [ADR-0018](0018-isolation-tier-ordering.md) — rank semantics and the `UNKNOWN` default

## Context

"Sandbox" spans radically different guarantees. A runc container shares the host kernel; a
gVisor sandbox interposes a user-space kernel; a Firecracker microVM gives a dedicated guest
kernel. Against a fully adversarial tenant these are not interchangeable, yet every
abstraction in this space presents them behind one word.

A portable API that hides this difference actively misleads: code written and reviewed
against local Docker gets deployed against a cloud backend, or vice versa, with no signal
that the security assumption changed.

## Decision

- `IsolationTier` (`CONTAINER`, `GVISOR`, `MICROVM`) is a **required property of every
  backend and every sandbox**, reported at runtime and present in reprs, audit events and
  spans.
- `create(require_isolation=...)` is an **enforceable precondition**: if the resolved backend
  is weaker, creation fails with `ConfigurationError` before anything is provisioned.
  "Weaker" is defined by the rank in [ADR-0018](0018-isolation-tier-ordering.md).
- Docs state the honest position: gVisor is defence-in-depth and not hardware-VM equivalent;
  `CONTAINER` is for trusted, dev and CI code only; `MICROVM` is the recommended floor for
  untrusted multi-tenant code.
- **A tier is a claim we must be able to defend.** A backend whose mechanism is not
  verified from the provider's own documentation reports `UNKNOWN`, not `CONTAINER` —
  reporting `CONTAINER` is itself an unearned claim
  ([ADR-0018](0018-isolation-tier-ordering.md)). Daytona is `UNKNOWN`.

## Consequences

- We are publishing security claims about third-party infrastructure. Each one needs a dated
  source, and re-verification is a standing item ([runbook](../runbook.md#quarterly-review)).
- A provider changing its isolation mechanism is a **breaking change in our public data**,
  not a footnote — it goes in the changelog and the churn log.
- `require_isolation` gives users a one-line way to make a deployment fail closed rather than
  silently downgrade. This is the single most valuable security affordance in the API.
