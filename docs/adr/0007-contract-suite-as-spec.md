# ADR-0007 — The contract suite is the adapter specification

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0001](0001-ports-and-adapters.md), [ADR-0003](0003-no-lowest-common-denominator.md)

## Context

Structural protocols mean a wrong adapter still type-checks. Prose in a spec document does
not stop an adapter from swallowing a timeout, leaking a container on exception, or claiming
a capability it fakes. The ecosystem lever — third parties shipping adapters without a PR —
only works if "is this adapter correct?" has a mechanical answer.

Prior art: SQLAlchemy's dialect compliance suite, fsspec's shared tests, and the `moto` /
`responses` / `vcrpy` family for offline testing of the layer below.

## Decision

- **`sandboxio.testing.suite` is normative.** Where the suite and prose disagree, the suite wins;
  a behaviour not covered by the suite is not guaranteed.
- Adapter authors subclass one class: `class TestFlyAdapter(BackendContractSuite)`.
- The suite covers lifecycle and teardown-under-exception, cancellation and shielded
  cleanup, `run` semantics, `run_code`, streaming order and termination, filesystem
  round-trips including binary safety, policy enforcement (deny actually denies, caps
  applied), error mapping with `__cause__` preserved, and **capability honesty** — every
  declared flag tested, every undeclared flag raising.
- **`FakeBackend` must pass the same suite** and ships in v0.1 as a supported product
  surface, with a pytest fixture, for users testing their own agent tools with no Docker and
  no cloud.
- The suite is written **before** the adapters (see [build-order](../build-order.md)), so it
  specifies behaviour rather than describing whatever Docker happened to do.

## Consequences

- Expanding the port contract means expanding the suite first; adapters then fail until
  updated. That is the intended pressure.
- Some contract tests need real network and real credentials (egress denial, provider error
  mapping). Those run nightly and on release, gated on secrets, not on every PR.
- The suite is a public API of its own. Breaking it breaks third-party adapters' CI, so it
  falls under the semver policy.
- `FakeBackend` passing the suite is what makes it trustworthy as a test double: if it
  diverges from real backends, that is a suite gap, and the fix is a new shared test.
