# ADR-0024 — Docker declares `STATEFUL_CODE` off in v0.1

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q11](../open-questions.md#q11--stateful_code-on-docker)
**Related:** [ADR-0003](0003-no-lowest-common-denominator.md), [ADR-0007](0007-contract-suite-as-spec.md)

## Context

`run_code(code, context_id=...)` implies a persistent interpreter per context. E2B gets this
from its code-interpreter template; Docker does not. Three implementations were considered,
plus declaring the capability off.

Baking an exec server into an image — whether a bespoke one or a Jupyter kernel — fails on a
point that matters more than convenience: **`docker://python:3.12-slim` is the documented
zero-config path, and users bring arbitrary images.** An approach that works only with our
image is not a Docker adapter; it is a Docker-image adapter, and it would quietly break the
one-line-swap promise for everyone with a custom base.

The approach that avoids that is injecting a small bootstrap at runtime: upload a script,
`docker exec` it, and speak a framed protocol over stdin. It requires only that the image
contain Python — which `run_code(language="python")` already requires. It is the right
long-term answer.

It is also a second execution path, with its own framing protocol, partial-output handling,
per-statement timeouts and error surfacing, landing in a step whose exit criterion is
already "100% of the contract suite against real Docker."

## Decision

- **Docker declares `STATEFUL_CODE` off in v0.1.** `run_code(context_id=...)` raises
  `CapabilityNotSupported`, naming the backends that do support it
  ([spec/04](../spec/04-errors.md#hint-quality)).
- `run_code` without `context_id` is a one-shot `exec` and is fully supported.
- **`results` stays `None`** on Docker. It MUST NOT be synthesised from parsed stdout
  ([ADR-0003](0003-no-lowest-common-denominator.md)).
- **The runtime-injected bootstrap is the intended path**, recorded here so the option is
  not rediscovered from scratch. It is revisited after the E2B adapter lands, when we know
  what stateful contexts and rich outputs actually need to look like — building it before
  that risks designing the protocol against a guess.
- Approaches requiring a purpose-built image are **rejected outright**, not deferred.

## Consequences

- Portable code using `context_id` works on E2B and fails loudly on Docker. That is
  capability discovery doing its job, and it is a better outcome than a silently emulated
  context — but it is a visible asymmetry in the launch narrative, and the docs should own
  it rather than hide it.
- Local development and CI cover stateless `run_code` only. A team whose agent depends on
  stateful contexts cannot fully test offline against Docker, and the fake backend is the
  answer for that case.
- Keeping the Docker adapter small protects the Step 4 exit criterion, which is the gate the
  whole build order hangs on.
- When B′ is built, it changes a capability flag from false to true — additive, not
  breaking, and the contract suite already has the tests waiting.
