# ADR-0028 — Docker containers ship hardened, minus the flags that break images

**Status:** Accepted
**Date:** 2026-09-20
**Related:** [ADR-0005](0005-secure-by-default.md) — secure by default · [ADR-0006](0006-isolation-tiers-first-class.md) — the tier is reported, not claimed · [ADR-0023](0023-docker-network-and-dependencies.md) — what Docker can and cannot enforce

## Context

`containers.create` passed `nano_cpus`, `mem_limit`, `network_mode`, `environment` and
`labels` and nothing else. Agent code therefore ran as root, with the default capability
set, no PID ceiling, and swap available past the stated memory cap. Resource exhaustion is
named in the threat model ([spec/05](../spec/05-security-policy.md#threat-model)), and the
resource-cap rule there says a caller "MUST NOT be able to unset" a cap — which a memory
limit that swap silently extends does not satisfy.

None of this is a declared `Capability`, so no contract was broken. Nor does any of it make
the `CONTAINER` tier safe for untrusted code; spec/05 puts that explicitly out of scope.
These are the cheap holes an escape does not even need.

Every candidate flag was run against a real daemon on `python:3.12-slim`, exercising
`mkdir`, a write to `WORKDIR`, a Python run and `tempfile`:

| Flag | Result |
|------|--------|
| `security_opt=["no-new-privileges"]` | everything passes |
| `cap_drop=["ALL"]` | everything passes |
| `pids_limit` | everything passes |
| `memswap_limit == mem_limit` | everything passes |
| `user="nobody"` | **write to `/work` fails** — the directory is root-owned |
| `read_only=True` | **write and `tempfile` fail** |
| `read_only=True` + tmpfs on `/work` and `/tmp` | passes, but `/work` becomes RAM |

## Decision

We will apply the four flags that cost nothing, to every container, with no opt-out:

- `security_opt=["no-new-privileges"]`
- `cap_drop=["ALL"]`
- `pids_limit=512` — a constant, not a `Resources` field. Generous enough for test runners
  and compilers, low enough that a fork bomb never reaches host PID exhaustion.
- `memswap_limit` equal to the effective `mem_limit`, which disables swap, so the memory
  cap is the cap.

We will **not** set `user` or `read_only`. Both break the images people already run, and
neither has a migration that fits inside a hardening change: a non-root user needs `/work`
chowned, and a read-only rootfs needs tmpfs mounts that turn `/work` into RAM and collide
with the `Resources.disk_mb` refusal ADR-0023 settled.

This adds no `Capability`, no config field and no env var. An image that genuinely needs a
dropped capability back is a `.native` case, not an API we widen.

## Consequences

A fork bomb is contained, a setuid binary cannot escalate, and the memory cap stops being
advisory — all without a version of the adapter that refuses to run ordinary images. The
Docker contract suite asserts the flags on a live container and asserts that ordinary code
still runs under them, so a future regression is a red gate rather than a silent loss.

The cost: an image that relied on a capability in the default set — raw sockets, `mount`,
`chown` across users — stops working, and the failure surfaces as the image's own error
rather than as a sandboxio one. Running as root inside the container remains the default,
which is the larger of the two gaps we are leaving open; closing it needs its own change
with an image contract behind it, not a flag.
