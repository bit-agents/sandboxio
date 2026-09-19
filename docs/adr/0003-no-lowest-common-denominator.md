# ADR-0003 — No lowest common denominator: capabilities + `.native`

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0001](0001-ports-and-adapters.md), [ADR-0007](0007-contract-suite-as-spec.md)

## Context

`apache-libcloud` is the cautionary tale: a portable API narrowed to the intersection of all
providers, plus `ex_`-prefixed provider extensions that were undiscoverable and untyped.
Users who needed anything distinctive dropped to the raw SDK, and the abstraction became a
liability.

The distinctive features here are exactly the reasons people pick a backend: E2B's rich
interpreter outputs and PTY, Modal's GPUs, Volumes with per-tenant `sub_path`, memory
snapshots and tunnels, Daytona's LSP and git operations. An abstraction that hides them is
not worth installing.

## Decision

We will never narrow the API to the common subset. Three mechanisms:

1. **`Capability` flags.** Every optional behaviour is a flag on the backend and on the
   sandbox. Callers branch on `Capability.GPU in sb.capabilities` rather than on backend
   name.
2. **`CapabilityNotSupported`, never a silent no-op.** A typed argument a backend cannot
   honour raises. Accepting and ignoring `network=` on a backend without network policy is
   the single worst thing this library could do — it turns a security control into a lie.
3. **`.native` escape hatch.** Every sandbox exposes the raw provider client or sandbox
   object. Nothing is hidden and nothing is wrapped for the sake of wrapping.

**Capability honesty is testable:** every declared flag must have a passing contract test,
and every undeclared flag must raise. An adapter cannot claim a capability it does not have.

`.native` is explicitly outside the semver contract and must be documented as such at every
mention.

## Consequences

- Portable code and native code are visibly different at the call site, which is the point.
- Users who reach for `.native` lose portability knowingly, and can come back when the
  capability is promoted into core.
- Promotion rule: a feature moves from `.native` into the typed API once **at least two
  backends** support it stably. This is why pause/resume and snapshot/fork are deferred —
  E2B's is beta and Modal's model differs.
- The `Capability` flag set will grow. It is a `Flag` enum, so additions are backwards
  compatible; removals are breaking.
