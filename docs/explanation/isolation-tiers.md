# Isolation tiers

"Sandbox" spans radically different guarantees, and every abstraction in this space presents
them behind one word. sandboxio does not. Every backend and every sandbox reports an
`IsolationTier`, it appears in reprs, audit events and spans, and you can require one.

## What the tier measures

One property: **resistance to kernel escape by an adversarial tenant**. Not performance,
not features, not cost. The rank orders that property only
([ADR-0018](../adr/0018-isolation-tier-ordering.md)).

| Tier | Mechanism | Honest position |
|------|-----------|-----------------|
| `CONTAINER` | a Linux container sharing the host kernel (runc) | **Not a security boundary against hostile code.** For trusted, dev and CI code only. A kernel exploit is a host compromise. |
| `GVISOR` | a user-space kernel interposed between the container and the host | Defence in depth, not hardware-VM equivalence. No v0.1 backend provides it; the tier is a property of the model, not of what shipped. |
| `MICROVM` | a dedicated guest kernel in a hardware-virtualised VM (Firecracker) | The recommended floor for untrusted, multi-tenant code. |
| `UNKNOWN` | the adapter has not verified its mechanism | Satisfies **no** requirement. Creating on it warns once per backend. |

Docker is `CONTAINER`. E2B is `MICROVM`. The fake reports `CONTAINER` while isolating nothing,
because it is for tests.

## Why `CONTAINER` is still in the product

Because most agent code is not hostile, and local Docker is where development happens. The
point is not to forbid it; the point is that code reviewed against local Docker and deployed
against a cloud backend — or the reverse — should never *silently* change its security
assumption. The tier makes the change visible.

## Making it enforceable

```python
import sandboxio
from sandboxio import IsolationTier

sb = await sandboxio.create("e2b://", require_isolation=IsolationTier.MICROVM)
```

`require_isolation` is checked **before** anything is provisioned. A weaker backend fails
with `ConfigurationError` and nothing was created or billed. `require_isolation=UNKNOWN` is
meaningless and raises. This one line is the most valuable security affordance in the API:
it turns a silent downgrade into a failed deployment.

## Why the README's tier cells are blank

A tier is a claim about someone else's infrastructure. This project publishes one only with
a dated link to the provider's own documentation, re-verified quarterly
([ADR-0006](../adr/0006-isolation-tiers-first-class.md),
[hazard H4](../hazards.md#h4--isolation-claims-we-cannot-defend)). A provider changing its
isolation mechanism is a breaking change in this project's public data, not a footnote.
