# ADR-0005 — Secure by default, enforced in v0.1

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0006](0006-isolation-tiers-first-class.md), [ADR-0003](0003-no-lowest-common-denominator.md)
**Open questions:** [Q10 deny-by-default vs. the demo](../open-questions.md#q10--deny-by-default-vs-the-demo)

## Context

The differentiator against every existing sandbox wrapper is security posture, and the
target buyer treats a cross-tenant leak as a contract violation rather than a bug. Defaults
decide outcomes: a security control that must be switched on is off in most deployments.

Threats in scope: malicious or buggy agent-generated code, prompt-injected agents invoking
tools with attacker-chosen arguments, cross-tenant leakage, and credential leakage into
sandboxes, logs or traces.

## Decision

Enforced in v0.1, not deferred:

1. **No network by default.** `NetworkPolicy(egress="deny")`. Opt-in allowlists of hosts and
   CIDRs. Each adapter maps this to the provider's real control (E2B
   `allow_internet_access=False`, Modal empty `outbound_cidr_allowlist`, Docker network mode
   `none`). A backend that cannot enforce it must raise, never accept-and-ignore.
2. **Mandatory timeouts.** `create()`, `run()` and `run_code()` refuse unbounded execution.
   Default 300 s.
3. **Resource caps always applied.** Modest CPU/memory/disk defaults. Callers may raise
   them; they may not unset them.
4. **Guaranteed teardown.** Context-manager exit kills the sandbox even on exception or
   cancellation, and a reaper cleans up what a crashed process left behind.
5. **Secrets are not env.** A separate `secrets=` parameter, redacted from logs, exceptions,
   audit events, reprs and spans. Never in a DSN, never baked into an image.
6. **Per-tenant isolation by default.** One sandbox per session or tenant-run, labelled via
   `metadata`. Sharing and warm pools are opt-in and documented, never implicit.

We will also state plainly what sandboxio does **not** do: it does not make untrusted code safe on
the `CONTAINER` tier, it does not defend against prompt injection, and it does not manage
tenant identity or authorization.

## Consequences

- The defaults break the obvious first thing a user tries — installing a package inside the
  sandbox. This tension with the zero-config demo is unresolved
  ([Q10](../open-questions.md#q10--deny-by-default-vs-the-demo)) and must be answered by
  documentation and image design, not by weakening the default.
- Every default above is a contract test. "Deny actually denies" is verified by egress to a
  canary host failing, per adapter, against the real backend.
- Redaction happens in one place, at record close, upstream of all renderings — otherwise it
  would be implemented three times and get it wrong once
  ([ADR-0021](0021-observability-record.md)).
- Mandatory timeouts will annoy someone with a legitimately long job. They can raise the cap;
  they cannot remove it.
