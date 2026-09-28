# Proposal 0001 — Egress allowlist and DNS control on every backend

**Status:** Proposed
**Created:** 2026-09-27
**Discussion:** [#40](https://github.com/bit-agents/sandboxio/issues/40)
**Spec:** [05](../spec/05-security-policy.md#network-policy), [06](../spec/06-observability.md), [08](../spec/08-adapter-contract.md#coverage-map)
**Related:** [ADR-0023](../adr/0023-docker-network-and-dependencies.md), [ADR-0028](../adr/0028-docker-container-hardening.md), [H1](../hazards.md#h1--a-security-default-silently-does-not-apply)

A proposal is how a change to the public API, the specification or the security surface is
designed in the open before it is built. When accepted, its normative text moves into
`docs/spec/` and its decisions into ADRs; the proposal stays as the record. It carries no
release date.

## Summary

`NetworkPolicy(egress="deny", allow=("pypi.org",))` works the same way on every backend that
supports it: hostnames are matched at connection time, everything else fails whether or not
the client honours a proxy, and DNS answers only the names on the list. On Docker this is
done by an optional proxy sidecar. Every refused connection and DNS query is recorded, and
the operation record says who enforced the policy.

## Motivation

Today the only portable policies are "no network" and "all network". An allowlist raises
`CapabilityNotSupported` on Docker ([ADR-0023](../adr/0023-docker-network-and-dependencies.md)),
so a workload that needs one package index or one API ends up with `egress="allow"`, which
gives up the default that does most of the work
([security model](../explanation/security-model.md#the-five-defaults-that-do-the-work)).

Three gaps sit under that:

- **Allowlist semantics are backend-defined.** [spec/05](../spec/05-security-policy.md#network-policy)
  says an allowlist exists, not what an entry means. Whether a hostname is matched per
  connection or resolved once, whether wildcards and ports are allowed, and whether private
  addresses are reachable through an allowlisted name are all left to the backend. A hostname
  pinned to the IPs it had at create time breaks on CDNs within minutes.
- **DNS is not governed.** Nothing in the spec says what `deny` or an allowlist means for DNS.
  A resolver that forwards any name upstream is a channel out of the sandbox even when every
  TCP connection is refused: data travels in the names looked up.
- **Refusals are not recorded.** `AuditEvent.network_denials` is a count, filled only "where
  the backend reports them" ([06](../spec/06-observability.md)). Docker reports none, and no
  backend says *what* was refused, so a failing allowlist cannot be debugged from the record.

## Goals and non-goals

**Goals**

- One meaning for an allowlist entry on every backend that accepts it.
- An allowlist on Docker, without a new base dependency.
- DNS covered by the same policy as connections.
- Every refusal visible in the operation record, with its destination.
- The enforcement point reported, so a caller can tell a provider control from ours.

**Non-goals**

- TLS interception. Decisions are made on the destination, the TLS SNI and the HTTP `Host`,
  never on content.
- Rules on methods, paths or headers.
- Ingress and port exposure.
- A proxy inside the guest of a microVM backend (see [Alternatives](#alternatives-considered)).

## Specification

- **R1** — `NetworkPolicy.allow` MUST accept hostnames (`api.github.com`), wildcard
  subdomains (`*.pythonhosted.org`, see R9), a hostname with a port (`api.github.com:443`)
  and CIDRs (`10.20.0.0/16`). An entry without a port allows 80 and 443.
- **R2** — An allowlisted hostname MUST be matched at connection time, not resolved once at
  sandbox creation.
- **R3** — A connection to a destination not on the list MUST fail, whether or not the client
  is proxy-aware: raw sockets, clients that ignore `HTTP(S)_PROXY`, UDP, ICMP and IPv6
  included.
- **R4** — A connection to a loopback, link-local, private (RFC 1918, RFC 4193) or cloud
  metadata address (`169.254.169.254`, `fd00:ec2::254`) MUST fail even when an allowlisted
  name resolves to it. A CIDR listed explicitly in `allow` is the only exception.
- **R5** — Under `egress="deny"` with an empty allowlist, no DNS query from the sandbox MUST
  get an answer from outside it.
- **R6** — With an allowlist, the sandbox's resolver MUST answer only allowlisted names and
  MUST return `NXDOMAIN` for every other name without forwarding the query.
- **R7** — If the enforcing component stops, the sandbox MUST lose egress. It MUST NOT gain it.
- **R8** — Every refused connection and every refused DNS query MUST add its destination to
  the operation record. Redaction applies as for every other field.
- **R9** — A wildcard entry lets the sandbox send arbitrary subdomain queries to that domain's
  authoritative servers, which is itself a channel out. Wildcards MUST be written explicitly
  (`*.` prefix) and MUST emit a `SandboxWarning` that says so.
- **R10** — The operation record MUST state the enforcement point: `provider` for a backend's
  native control, `sandboxio-proxy` for the sidecar.
- **R11** — The core distribution MUST NOT depend on the proxy. Without the `proxy` extra, an
  allowlist on Docker raises `CapabilityNotSupported` as it does today.
- **R12** — Where the proxy exempts its own traffic by uid, no sandbox process MUST run as
  that uid. `create()` MUST refuse an image or `user` that maps to it with
  `ConfigurationError`, and the sandbox MUST keep `no-new-privileges` and no `CAP_SETUID`.
- **R13** — A sandbox whose proxy has stopped MUST be reported as gone (`SandboxGone`) on its
  next operation, not left running without a network.

## API

No new type. `NetworkPolicy` keeps its shape; the entry grammar in R1 becomes normative.

```python
import sandboxio
from sandboxio import NetworkPolicy

policy = NetworkPolicy(egress="deny", allow=("pypi.org", "files.pythonhosted.org"))

async with await sandboxio.create("docker://python:3.12-slim", network=policy) as sb:
    await sb.run(["pip", "install", "requests"], timeout=120)   # allowed
    res = await sb.run(["curl", "-sS", "https://example.com"])  # refused, exit != 0
```

Install: `uv add "sandboxio[docker,proxy]"`. The extra carries the orchestration code and the
proxy image reference, pinned by digest; the image is pulled like any other.

## Backend support

| Backend | How it is enforced | If it cannot be |
| --- | --- | --- |
| Docker | Proxy sidecar, one per sandbox (below) | Without the `proxy` extra, a non-empty `allow` raises `CapabilityNotSupported` |
| E2B | Native `network={deny_out, allow_out}`. Domain rules match per connection on TLS SNI (443) and HTTP `Host` (80) ([E2B docs](https://docs.e2b.dev/sandbox/internet-access), read 2026-09-27). Plain `deny` is expected to meet R5, which its contract test verifies | R6 is not met natively: once `allow_out` contains a domain, E2B allows its upstream resolver, `8.8.8.8`, which answers any name ([security model](../explanation/security-model.md#what-an-allowlist-does-not-close)). See [open question 1](#open-questions) |
| Modal (adapter not yet shipped) | Native `outbound_cidr_allowlist` | CIDRs only: the adapter MUST raise `CapabilityNotSupported` for a hostname entry. On acceptance, spec/05's "E2B/Modal capability" wording is amended to match |
| Fake | Recorded, not enforced | — |

**Docker sidecar.** The sandbox runs with `network_mode: container:<proxy>` and shares the
proxy's network namespace. The proxy container holds `CAP_NET_ADMIN`, installs nftables rules
at start, then runs as a dedicated uid:

- nat, output hook: traffic of the proxy's uid and to loopback passes; UDP and TCP port 53 are
  redirected to the local resolver; all other TCP is redirected to the local transparent
  proxy.
- filter, output hook, policy drop: accept loopback, redirected connections (`ct status
  dnat`) and the proxy's uid. Everything else, including UDP to other ports, ICMP and IPv6,
  is dropped.

The resolver answers allowlisted names by forwarding them and every other name with a local
`NXDOMAIN` (R5, R6); CoreDNS does this with configuration only. The transparent proxy reads
the original destination (`SO_ORIGINAL_DST`), peeks the TLS SNI or HTTP `Host`, checks it
against the list, resolves it at that moment (R2), refuses private and metadata addresses
(R4), and records every refusal (R8).

The sandbox keeps the hardening of [ADR-0028](../adr/0028-docker-container-hardening.md): with
all capabilities dropped it cannot alter the rules (`nft` and `iptables` fail with `EPERM`),
and with `no-new-privileges` it cannot switch to the proxy's uid. The uid is fixed and
documented, chosen outside ranges common images use as their default user (65532, for
example, is the distroless `nonroot` user) — R12.

When the proxy container stops, the shared namespace keeps only its loopback interface, so
the sandbox has no route (R7). Restarting the proxy does not bring the interface back into
the sandbox, which is why R13 reports the sandbox as gone rather than degraded.

Starting the sidecar adds one container start to `create()`, before the sandbox's own. The
Docker CI job in [Testing](#testing) MUST report that added latency.

## Security considerations

- **Addressed:** exfiltration and second-stage fetches through unlisted hosts, including by
  clients that ignore proxy settings (R3); DNS as a channel out (R5, R6); DNS rebinding to
  private and metadata addresses (R4).
- **Residual:** an exact allowlisted name still sends its queries to that domain's
  authoritative servers, which matters only if the attacker controls them. A wildcard entry
  hands the attacker the whole subdomain space of that domain (R9).
- **Introduced:** a new component with network reach. The proxy image MUST be built
  reproducibly, signed, pinned by digest in the extra and attested like the wheels. It runs
  with `CAP_NET_ADMIN` only for rule setup, exposes no management API, keeps no state, and
  listens only on the ports its rules redirect to. In the shared namespace the sandbox can
  connect to those ports, so the proxy MUST NOT listen on anything else.
- **Failure mode:** fails closed (R7, R13).

## Observability

In the operation record, and therefore `AuditEvent`, spans and `Meter`
([06](../spec/06-observability.md)):

| Field | Type | Meaning |
| --- | --- | --- |
| `egress_enforced_by` | `Literal["provider", "sandboxio-proxy"] \| None` | R10; `None` when egress is `allow` with no proxy |
| `network_denied` | `tuple[str, ...]` | R8; each refused destination as `host:port`, `ip:port` or `dns:<name>` |
| `network_denials` | `int` | unchanged; equals `len(network_denied)` where the backend reports destinations |

No new error code: R12 uses `ConfigurationError`, R13 `SandboxGone`, R11 `CapabilityNotSupported`.

## Compatibility

- **Callers:** an allowlist on Docker stops raising once the `proxy` extra is installed.
  Without it, nothing changes. On E2B, the outcome of open question 1 may change how an
  allowlist with a domain entry is accepted.
- **Adapter authors:** new contract-suite rows. An adapter declares allowlist support only if
  it passes all of them, or declares the ones it does not meet.
- The R1 grammar is additive; existing entries keep their meaning.

## Testing

| Requirement | Contract test |
| --- | --- |
| R1, R2 | Allowlisted host reachable; changing its DNS record mid-sandbox keeps it reachable |
| R3 | Raw TCP to an unlisted IP, `curl --noproxy '*'`, UDP to an outside port, ICMP and IPv6 all fail. A TCP connect alone is not proof: the test exchanges data |
| R3, R6 | The unlisted canary is a real, resolvable host (for example `example.org`), never a reserved name that fails to resolve anyway |
| R4 | An allowlisted name resolving to `169.254.169.254` or `10.0.0.1` is refused |
| R5 | Under plain `deny`, `getaddrinfo("example.com")` fails and a direct query to `8.8.8.8` gets no answer |
| R6 | An unlisted name returns `NXDOMAIN`; a capture on the proxy's uplink shows no query for it |
| R7, R13 | Stopping the proxy fails every egress test and the next operation raises `SandboxGone` |
| R8 | Each refusal appears once in `network_denied` |
| R9 | A wildcard entry emits the warning |
| R10 | `egress_enforced_by` matches the backend |
| R11 | The core import graph has no proxy dependency; without the extra an allowlist on Docker raises |
| R12 | `create()` with the proxy's uid raises `ConfigurationError`; a root sandbox cannot `setresuid` to it |

The Docker rows need a CI job with the proxy image built from the same commit.

## Alternatives considered

- **Internal network with an explicit proxy (Docker).** The sandbox sits on a
  `--internal` network, the proxy on it and on a bridge, `HTTP(S)_PROXY` set. Direct
  connections fail by topology. Rejected: clients that ignore proxy variables break instead
  of being filtered, and Docker's embedded resolver on an `--internal` network is not
  documented to refuse external names, so R5 would rest on engine behaviour the engine does
  not promise.
- **A CONNECT-only proxy** (smokescreen, for example). It handles hostname allowlists and
  private-address refusal well, but has no transparent mode, so it cannot serve the redirect
  above.
- **Envoy** as the transparent proxy. It can do it (`original_dst`, `tls_inspector`), at a
  much larger image and configuration surface. Rejected: at this scope that surface outweighs
what it adds.
- **Resolving the allowlist once at create time** and filtering by IP. Breaks on CDNs and
  any record change (R2).
- **A proxy inside a microVM guest.** It shares the kernel with the code it polices, so it is
  no stronger than the guest code's privilege separation.
- **A host-side forward proxy for cloud backends** that the provider allows as the only
  destination. Strong, but the user must run a reachable service; out of scope for a library.

## Open questions

1. E2B's native allowlist does not meet R6. Should an allowlist with a domain entry on E2B
   raise `CapabilityNotSupported`, as
   [H1](../hazards.md#h1--a-security-default-silently-does-not-apply) suggests, or be accepted
   with a warning and `egress_enforced_by="provider"` recording which requirements the
   provider meets?
2. One proxy per sandbox (isolation, more containers) or one per tenant (cheaper, shared
   failure domain)? This proposal assumes per sandbox.
3. Should `egress="allow"` also run through the proxy, so R8 records everything?
4. [ADR-0023](../adr/0023-docker-network-and-dependencies.md) says a proxy sidecar earns its
   own ADR. That ADR is written on acceptance and amends ADR-0023.

## History

- 2026-09-27 — Proposed.
