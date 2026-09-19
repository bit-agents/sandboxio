# ADR-0004 — Thin core; adapters behind extras, lazily imported

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0001](0001-ports-and-adapters.md), [ADR-0012](0012-no-telemetry-no-import-side-effects.md)

## Context

The target buyer is a B2B SaaS team whose dependency review is a gate. Two 2026 events set
the bar: the litellm supply-chain incident, where a broad dependency tree on a
credential-handling package became everyone's problem, and the general expectation of SBOMs
and build attestations in enterprise review.

Separately, a library that agents import on every cold start cannot afford a slow import,
and nobody should pay for the E2B SDK to use Docker locally.

## Decision

- **Core depends on `typing-extensions` and `anyio` only.** Any further base dependency
  requires an ADR.
- **First-party adapters live in the monorepo behind extras** (`sbx[docker]`, `sbx[e2b]`,
  `sbx[modal]`). Third parties ship separate distributions (`sbx-fly`).
- **Resolution is by entry point**, group `sbx.backends`, read lazily via
  `importlib.metadata`. Plus runtime `sbx.register(name, "pkg:Class")` for dynamic cases.
- **Importing `sbx` never imports an adapter, and never imports a provider SDK.** The
  adapter module is imported on first use of that backend.
- Enforced in CI, not by convention: import budget under 150 ms (hard fail over 200 ms), no
  sockets at import, and a wheel-contents test asserting the base install pulls no adapter
  code.

## Consequences

- A missing backend is a common, recoverable error rather than an ImportError at the top of
  the file. `BackendNotInstalled` must name the exact install command
  ([ADR-0010](0010-stable-error-codes.md)).
- Entry-point scanning has a measurable cost and must be lazy and cached; it counts against
  the import budget.
- The monorepo means first-party adapters version in lockstep with core. Accepted for v0.1;
  revisit if an adapter needs to ship on a provider's cadence rather than ours.
- We cannot vendor convenience helpers into core "just for one adapter". Shared adapter
  utilities need an explicit internal home with its own stability stance.
