# ADR-0010 — Error codes are public, semver-covered API

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0003](0003-no-lowest-common-denominator.md), [ADR-0008](0008-dsn-and-typed-config.md)
**Related:** [ADR-0017](0017-timeout-error-naming.md) — timeout naming and the no-builtin-shadowing rule

## Context

Two consumers read errors here, and both benefit from the same thing. Humans want the fix,
not a stack trace: the models are Rust's error codes, Pydantic v2's per-error URLs, Ruff's
rule pages. LLM coding assistants want a stable, greppable token they can map to a known
remedy — an error string that changes wording between releases is useless to them.

Adapters also sit on top of provider SDKs whose exceptions are unstable and
provider-specific. Leaking those through is the same lock-in the library exists to remove.

## Decision

- Every exception derives from `SandboxError` and carries `.code` (`SBX_E1002`), a one-line
  cause, `.hint` with the **exact fix command**, and `.url` to a per-code docs page.
- **Codes are semver-covered API.** Renaming or repurposing a code is a breaking change. One
  docs page per code, at a redirect-stable path.
- **Adapters map native exceptions into the sandboxio tree, preserving `__cause__`.** A raw
  provider exception escaping an adapter is a bug, and the contract suite checks for it.
- Hints are specific, not generic: auth errors name the exact missing environment variable;
  unknown-backend errors list what is installed and how to install what is not;
  `CapabilityNotSupported` names which backends do support the feature.
- Error-catalog docs pages are **generated from the catalog in code**, so codes, hints and
  docs cannot drift.
- No exception inherits from a builtin, and no name shadows one ([ADR-0017](0017-timeout-error-naming.md)).

## Consequences

- The catalog is a design artifact maintained alongside the code, not a docs afterthought.
  Adding an error means adding a code, a hint and a page.
- Stable codes constrain refactoring: merging two error conditions is breaking even when the
  class hierarchy would allow it.
- Good hints require knowing the user's situation — which backends are installed, which env
  var is missing. That argues for errors constructed with context rather than raised bare,
  and is worth the plumbing.
