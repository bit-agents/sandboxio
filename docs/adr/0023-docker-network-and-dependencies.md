# ADR-0023 — Docker cannot filter egress; dependencies come from images or wheelhouses

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q10](../open-questions.md#q10--deny-by-default-vs-the-demo)
**Related:** [ADR-0005](0005-secure-by-default.md), [ADR-0003](0003-no-lowest-common-denominator.md)

## Context

Deny-by-default egress appeared to conflict with the zero-config demo and with the input
set's `pip install -r requirements.txt` streaming example.

**Half of that conflict was a misreading.** `network_mode: none` governs the *sandbox's*
egress; `docker pull python:3.12-slim` runs on the *host* daemon, outside the container. The
demo therefore works under deny-by-default: the host fetches the image, the sandbox runs
stdlib-only code with no network interfaces. There was never a problem there, and the
confusion is itself worth documenting.

The real question is narrower: how a user gets dependencies into a deny-egress sandbox. And
here Docker imposes a hard limit — **Docker Engine has no per-host egress filtering.**
`docker run --network` accepts `none | bridge | host | container | <custom>`;
`docker network create` exposes no allow, deny or egress options. Verified against the local
Docker CLI, not assumed.

So the Docker adapter can express `egress="deny"` (network `none`) and unrestricted egress
(bridge), but **cannot** honour `NetworkPolicy(allow=(...))` without a sidecar proxy or
iptables machinery that is out of scope for v0.1.

## Decision

### Capability honesty over convenience

The Docker adapter **MUST raise `CapabilityNotSupported` when `allow` is non-empty.**
Silently granting full bridge access because a host allowlist was requested would be
[hazard H1](../hazards.md#h1--a-security-default-silently-does-not-apply) — a security
control that appears to apply and does not. Allowlists remain available on E2B and Modal,
which have native support.

### Two documented dependency patterns for Docker

1. **Image prep** — dependencies baked into the image ahead of time. The primary pattern.
2. **Offline wheelhouse** — `files.upload()` the wheels, then
   `uv pip install --offline --find-links /wheels`. Fits deny-by-default exactly and needs
   no network at all.

Both work under the default policy. Neither weakens it.

### Rejected: a mutable setup window

A two-phase "install with egress, then lock down" was rejected. E2B's `update_network` could
support it, but Docker cannot change a running container's network mode, and — more
importantly — a policy that varies over a sandbox's life makes "the policy in effect"
time-varying in the audit record. A security claim that is only true for part of a
sandbox's life is not a claim worth making. Revisit only with an audit model that can
express it.

### Documentation requirements

- The spec states plainly that **image pull is host-side**, since that misreading generated
  this question.
- The `<60 s` demo budget includes a first-run image pull of roughly 130 MB. It is stated as
  measured warm, or the demo moves to a smaller image.

## Consequences

- `NetworkPolicy(allow=...)` is a backend-differentiated feature, not a portable one. That
  is the design working as intended, but the per-backend docs must be explicit so nobody
  writes an allowlist against Docker and assumes it applies.
- Docker users doing dependency-heavy work must build images or ship wheelhouses. More
  friction than `pip install`, and the honest cost of the default.
- If the Docker allowlist gap becomes a real adoption blocker, a proxy sidecar is the
  implementation — a substantial piece of work that earns its own ADR.
