# Deny by default

`sandboxio.create()` with no arguments gives a sandbox that cannot open a single outbound
connection. Not "a sandbox with a firewall you can configure" — one that starts closed, and
opens only where you say so.

[`examples/04_egress_denied.py`](https://github.com/bit-agents/sandboxio/blob/main/examples/04_egress_denied.py) proves this on a real
sandbox in about twenty lines, then shows the explicit opt-out.

## The threat this answers

An agent's code is at best buggy and at worst attacker-chosen through prompt injection.
sandboxio cannot prevent the injection. It bounds the blast radius: whatever runs in the
sandbox cannot exfiltrate the data it was given, cannot fetch a second stage, and cannot
call an API with credentials it found lying around. Egress is the channel for all three, so
egress is off ([spec/05](../spec/05-security-policy.md#threat-model)).

Mandatory timeouts and resource caps sit beside it for the same reason: an unbounded
execution is a cost and a denial-of-service waiting to happen, so `timeout=None` is refused
rather than interpreted as "forever".

## What the default costs, honestly

Dependencies. `pip install` from inside the sandbox does not work, and this project's own
first draft carried a streaming example that did exactly that. The answer is not a setup
window with the network open — a policy that varies over a sandbox's life makes "the policy
in effect" a time-varying fact the audit record cannot state. The answers are images with
dependencies baked in and offline wheelhouses uploaded through `files`
([Docker how-to](../how-to/docker.md#getting-dependencies-into-a-deny-egress-sandbox)), or an
allowlist on a backend that can enforce one ([E2B how-to](../how-to/e2b.md#network-allowlists)).

Image pulls are unaffected: `docker pull` runs on the host daemon, outside the container's
network namespace. That confusion generated an open question in this project's history, and
is worth stating plainly.

## The rule that makes it trustworthy

**A backend that cannot enforce a requested policy raises `CapabilityNotSupported`.** It
does not approximate, it does not warn and continue. Docker has no per-host egress filtering,
so a `NetworkPolicy(allow=...)` against Docker raises instead of quietly granting full bridge
access ([ADR-0023](../adr/0023-docker-network-and-dependencies.md)). Accepting and ignoring a
network policy is the single most dangerous bug this library could have
([hazard H1](../hazards.md#h1--a-security-default-silently-does-not-apply)), and the contract
suite proves deny against a canary host on every real backend.

The same rule covers every typed argument: `Resources(disk_mb=...)` on Docker and
`Resources(cpu=...)` on E2B are refused, not ignored. Never silently no-op.

## Seeing it

`uvx sandboxio demo` runs an outbound request from inside a fresh sandbox and reports that it
was denied — and would fail the demo if it were not. Where a backend reports blocked
attempts, the count is in every audit event as `network_denials`.
