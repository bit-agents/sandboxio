# ADR-0001 — Ports and adapters (hexagonal) architecture

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0003](0003-no-lowest-common-denominator.md), [ADR-0004](0004-thin-core-lazy-adapters.md), [ADR-0007](0007-contract-suite-as-spec.md)

## Context

sbx spans backends with genuinely different shapes: a local Docker daemon, E2B's Firecracker
microVMs with a code-interpreter protocol, Modal's gVisor sandboxes with Volumes and GPUs.
Their SDKs churn independently and fast — E2B shipped v0→v1→v2 in roughly a year; Modal
changed its Sandbox filesystem API at V2.

Two failure modes in prior art bound the design. `apache-libcloud` reduced every provider to
their intersection and became useless for anything real. Framework-coupled layers
(`langchain_e2b`, OpenAI Agents SDK's `SandboxConfig`) are usable only inside their host
framework.

## Decision

We will structure sbx as ports and adapters:

- **Core** defines protocols (`Backend`, `AsyncSandbox`, `AsyncFileSystem`, `Process`) and
  value objects (`Resources`, `NetworkPolicy`, `ExecResult`, `Capability`, `IsolationTier`).
  It contains no backend-specific code, no provider imports and no I/O beyond what the
  protocols require.
- **Adapters** implement the protocols per backend and live behind extras or third-party
  packages. All provider-specific behaviour, quirks and exception mapping lives there.
- **Dependency direction is inward only.** Core never imports an adapter; adapters are
  resolved at runtime through the registry ([ADR-0004](0004-thin-core-lazy-adapters.md)).

Protocols are `typing.Protocol`, structural rather than inherited, so third parties can
implement them without importing a base class.

## Consequences

- A third party can ship `sbx-fly` without a PR, and the contract suite tells them whether
  it is correct ([ADR-0007](0007-contract-suite-as-spec.md)).
- Provider churn is contained to one file per provider. This is the moat, and it only holds
  if core stays genuinely provider-ignorant — any provider concept leaking into core
  (E2B's `context_id` semantics, Modal's Volume model) erodes it.
- Core must be widened deliberately when a real backend cannot be expressed. The escape
  valve is `Capability` + `.native`, not a special case in core.
- Structural protocols mean a broken adapter type-checks. The contract suite, not the type
  system, is what proves conformance.
