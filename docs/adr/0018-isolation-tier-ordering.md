# ADR-0018 — `IsolationTier` ordering via an explicit rank; `UNKNOWN` is the default

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q5](../open-questions.md#q5--isolationtier-needs-ordering)
**Related:** [ADR-0006](0006-isolation-tiers-first-class.md), [ADR-0005](0005-secure-by-default.md)

## Context

`require_isolation=IsolationTier.MICROVM` must fail if the resolved backend is "weaker",
which implies a comparison a plain `Enum` does not provide. Whether
`CONTAINER < GVISOR < MICROVM` is even a legitimate total order is the harder half of the
question: gVisor is documented as defence-in-depth, explicitly not hardware-VM equivalent.

Kubernetes `RuntimeClass` — which [spec/07](../spec/07-configuration.md) already borrows as
the mental model for `isolation_classes` — deliberately does **not** rank its handlers.
`runc`, `gvisor` and `kata` are named and selected by name; the ordering judgement is left
to the cluster operator.

The discriminating scenario is what happens when a stronger tier is added later
(confidential VM, Kata, bare metal):

| Design | On adding a stronger tier | Arithmetic leaks | Serialization |
|--------|---------------------------|------------------|---------------|
| `IntEnum`, spaced values | fine | **yes** — members equal bare ints | magic numbers |
| **Plain enum + rank map** | **fine, correct semantics** | no | string values |
| Set of acceptable tiers | **rejects the stronger backend** | no | string values |
| Order by declaration index | fragile — reordering changes semantics | no | string values |

The set-based design is the most honest about gVisor not being microVM-equivalent, but it
fails the discriminator: an existing `require_isolation={MICROVM}` would reject a newly
added `CONFIDENTIAL_VM` backend. Fail-closed, but wrong, and silently so.

Separately, [spec/01](../spec/01-domain-model.md) said an unverified backend "must not be
claimed above `CONTAINER`". But reporting `CONTAINER` **is itself a claim** — it asserts
at-least-container-grade isolation we have not verified.

## Decision

Plain `Enum` with string values and an **explicit internal rank map**:

```python
class IsolationTier(Enum):
    UNKNOWN   = "unknown"
    CONTAINER = "container"
    GVISOR    = "gvisor"
    MICROVM   = "microvm"

_RANK = {UNKNOWN: 0, CONTAINER: 10, GVISOR: 20, MICROVM: 30}
```

- **The rank is a documented policy claim, not a property of the member values.** It ranks
  exactly one thing: *resistance to kernel escape by an adversarial tenant*, under the
  threat model in [spec/05](../spec/05-security-policy.md). It is **not** a general
  "more secure" scale, and the docs must say so wherever the ordering appears.
- Rich comparisons (`<`, `<=`, `>`, `>=`) are derived from the rank. Arithmetic is not
  available — this is why a plain `Enum` is used rather than `IntEnum`.
- `tier.satisfies(minimum)` is the intent-revealing form and the one the docs teach;
  `require_isolation` is evaluated with it.
- **Ranks are spaced by 10** so a tier can be inserted between two existing ones without
  renumbering. Adding a tier is additive; `require_isolation=MICROVM` automatically accepts
  anything stronger, which is the correct semantics and the reason ordering beat sets.
- **Every member must have a rank**, asserted by a test that enumerates the class. A member
  without one is a `KeyError` at runtime, which is not an acceptable failure mode for a
  security control.

### `UNKNOWN`

- **`UNKNOWN` is the default for any adapter that does not declare a tier.** Not
  `CONTAINER`. An adapter author who says nothing has claimed nothing.
- It ranks 0, so it satisfies **no** requirement — `require_isolation=CONTAINER` against an
  `UNKNOWN` backend fails, which is the point.
- `require_isolation=UNKNOWN` is meaningless and MUST raise `ConfigurationError`.
- Creating a sandbox on an `UNKNOWN`-tier backend emits `UnverifiedIsolationWarning` once
  per backend per process. A warning, not a print — the library stays quiet otherwise
  ([ADR-0012](0012-no-telemetry-no-import-side-effects.md)).
- Daytona is `UNKNOWN` until its mechanism is verified from provider documentation with a
  date ([ADR-0006](0006-isolation-tiers-first-class.md)).

## Consequences

- We assert a total order over security mechanisms, which K8s declined to do. Scoping it to
  one property — escape resistance — is what makes it defensible; it is the industry
  consensus ordering for that property specifically. If isolation ever needs more
  dimensions (side channels, co-tenancy, confidential computing), the escape route is a
  policy object (`IsolationPolicy(min_tier=..., …)`), not more enum members.
- The rank map is internal state that must track the members. That is a test, not a
  convention.
- `UNKNOWN` as the adapter default means a third-party adapter is unusable under any
  `require_isolation` until its author declares a tier. That friction is deliberate and
  points in the safe direction.
- Inserting a tier between existing ones changes what an existing `require_isolation`
  accepts — always toward accepting more, never fewer. Not breaking, but it is a changelog
  entry.
- One overstatement remains: `FakeBackend` reports `CONTAINER` while providing no isolation
  at all, since it executes nothing. A `NONE` tier would be the honest fix if that label
  ever reaches somewhere it matters; it is not worth the member today.
