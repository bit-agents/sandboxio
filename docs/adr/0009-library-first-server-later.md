# ADR-0009 — Library first; MCP is the first server; `sbx-server` is gated

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0004](0004-thin-core-lazy-adapters.md)

## Context

The recurring pattern in this space — LiteLLM SDK then Proxy, OTel SDK then Collector,
Docker client then daemon, DBOS-as-library versus Temporal-as-server — is that the service
becomes the product only when the concern shifts from ergonomics to governance:
multi-tenant routing, central auth, spend control, central audit.

Building the server first means paying for an ops-grade artifact before adoption exists, and
inheriting a tier-1 credential surface that also executes untrusted code. LiteLLM's 2026 CVE
run shows what that surface costs when it is not treated as the primary product.

## Decision

Three phases, each with an explicit trigger:

| Phase | Deliverable | Trigger |
|-------|-------------|---------|
| 0 | Library only | now |
| 1 | `sbx.mcp`, containerized MCP server | launch |
| 2 | `sbx-server`, separate package, REST + SSE gateway | >30% of adopters ask for multi-tenant routing or a deployable service, **or** enterprise buyers demand SSO/JWT with central audit |

- The MCP server is the first server surface. Containerized, single-tenant, config fixed at
  process start, **no runtime config-mutation tool**, nothing ever executed on the host.
- `sbx-server` is a **separate distribution** when it happens, so its dependency tree and
  attack surface never reach library users.
- The **routing config format is designed now and loadable by the library**, so teams can
  adopt declarative routing before adopting any server. Which backend and isolation class a
  tool or tenant gets must be a YAML change, not a code change.

## Consequences

- We defer the enterprise revenue surface. Deliberate: the library is the adoption wedge and
  fsspec proved library-only can become default infrastructure.
- The routing format must be got right early even though its main consumer does not exist
  yet. Cost is bounded: it is a config schema, and the library uses it too.
- If the trigger fires, the server's security posture is a build-order item of its own — no
  unauthenticated endpoints, parameterized queries in the auth path, host-header validation,
  immutable config at boot, rootless container, and never a Docker socket reachable from
  sandboxed code ([hazards](../hazards.md#server-mode-hazards-phase-2)).
