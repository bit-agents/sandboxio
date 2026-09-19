# Specification

Normative specification for sbx. Derived from [`../input/`](../input/), constrained by
[`../adr/`](../adr/). Where this spec and any other document disagree, **this spec wins**.

## Conventions

- **MUST / MUST NOT / SHOULD / MAY** are used in the RFC 2119 sense. MUST is a contract-suite
  test; SHOULD is a reviewable default; MAY is genuinely optional.
- Code blocks are **illustrative signatures**, not copy-paste implementations, unless marked
  otherwise.
- `**OPEN (Qn)**` marks a requirement that is not yet decided. An implementation MUST NOT
  guess at an OPEN item — resolve it in [`../open-questions.md`](../open-questions.md) first.
- A behaviour that appears nowhere in this spec and nowhere in the contract suite is **not
  guaranteed**, and callers MUST NOT rely on it.

## Contents

| File | Scope |
|------|-------|
| [01-domain-model.md](01-domain-model.md) | Entities, value objects, capabilities, isolation tiers, lifecycle |
| [02-ports.md](02-ports.md) | Protocol interfaces adapters implement |
| [03-public-api.md](03-public-api.md) | `sbx.*` surface, `create()`, results, sync facade, stability contract |
| [04-errors.md](04-errors.md) | Error tree, code catalog, rendering, mapping rules |
| [05-security-policy.md](05-security-policy.md) | Defaults, network policy, secrets, tenancy, isolation enforcement |
| [06-observability.md](06-observability.md) | The operation record, audit sinks, OTel spans, meter, redaction |
| [07-configuration.md](07-configuration.md) | DSN grammar, typed config, credentials, routing file |
| [08-adapter-contract.md](08-adapter-contract.md) | What every adapter MUST do; contract suite coverage map |
| [09-integrations.md](09-integrations.md) | Framework adapters and the MCP server |
| [10-cli.md](10-cli.md) | CLI surface and behaviour |

## Scope fences

sbx is not an agent framework, not a memory system, not a durable-execution engine, not a
managed cloud, and not a lowest-common-denominator wrapper. These are permanent, not
"not yet".
