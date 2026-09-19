# ADR-0016 — MIT license; DCO for contributions

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q3](../open-questions.md#q3--license)
**Related:** [ADR-0004](0004-thin-core-lazy-adapters.md), [ADR-0009](0009-library-first-server-later.md)

## Context

The input set never chose a license, despite positioning sandboxio as self-hostable and
enterprise-supply-chain friendly, and despite citing Daytona's license changes and
closed-sourcing as a market risk.

This is a personally-owned project with a single copyright holder today. The immediate
neighbourhood is overwhelmingly permissive: `anyio` MIT, `pydantic` MIT, `langgraph` MIT,
`e2b` MIT, `openai-agents` MIT, `fsspec` BSD-3, `httpx` BSD-3, `modal` Apache-2.0. Both
base dependencies are permissive and compatible (`anyio` MIT, `typing-extensions` PSF-2.0).

The realistic alternative was Apache-2.0, whose distinguishing feature is an explicit
patent grant protecting users from a contributor later asserting a patent, plus §5 making
contributions inbound-equals-outbound without a separate agreement. Both licenses clear
enterprise review; neither is a differentiator for adoption.

## Decision

- **MIT** for the `sandboxio` library and everything in this repository.
- **DCO** (`Signed-off-by`) for contributions, not a CLA. A CLA is friction that a project
  this size cannot spend, and DCO plus an explicit inbound-equals-outbound statement in
  `CONTRIBUTING.md` is sufficient for a permissive project.
- `LICENSE` at the repo root, SPDX `MIT` in package metadata, and the license stated in
  `README.md` and on the docs site.
- **The Phase-2 `sandboxio-server` license is deliberately left open**
  ([ADR-0009](0009-library-first-server-later.md)). It is a separate distribution that does
  not exist yet, and its license is decided when it is created — not implicitly inherited
  from this decision.
- We do **not** relicense opportunistically. Changing the library license later requires
  consent from every copyright holder, and attempting it after adoption is how projects
  lose their communities.

## Consequences

- No patent grant. A contributor could in principle assert a patent against users. Accepted:
  the risk is small for a solo permissive project, and MIT is the ecosystem norm around us.
- **The window to choose Apache-2.0 instead closes as soon as outside contributions land.**
  This is the one asymmetry in the decision, and it is why it is being made now rather than
  deferred.
- MIT permits anyone, including a competitor or a framework vendor, to fold sandboxio into
  their product. That is consistent with the strategy — being absorbed into the framework
  layers is a planned outcome, not a threat
  ([ADR-0013](0013-complement-openai-sandboxclient.md)).
- Keeping the server's license open preserves the optionality the roadmap contemplates
  without weakening the library's permissive promise. If the server is ever licensed
  differently, that split must be stated plainly and early, not discovered by users.
- DCO means no copyright assignment, so a future commercial relicensing of *this* code
  would need contributor consent. If that optionality matters later, the answer is a
  separately-licensed package, not a retroactive CLA.
