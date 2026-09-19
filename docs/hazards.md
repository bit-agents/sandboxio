# Hazards

What can kill this project, or its users. Each hazard has a **tripwire** — the observable
signal that it is happening — and a response. Hazards are reviewed quarterly
([runbook](runbook.md#quarterly-review)); market facts date fast in this space.

Unresolved *decisions* live in [open-questions.md](open-questions.md). This file is about
risks that persist after the decisions are made.

---

## Product hazards (users get hurt)

### H1 — A security default silently does not apply

**The worst possible bug in this library.** An adapter accepts `NetworkPolicy(egress="deny")`
and provisions a sandbox with full internet access; or a resource cap is dropped; or
`require_isolation` is not checked. The user believes they have a control they do not have,
and only finds out from an exfiltration.

- **Tripwire:** a contract test for policy enforcement is skipped, xfailed, or absent for a
  declared capability.
- **Response:** policy enforcement tests hit a real canary host against the real backend.
  Never mock the thing that proves the control works. A backend that cannot enforce a
  requested policy raises `CapabilityNotSupported`
  ([spec/05](spec/05-security-policy.md#network-policy)).

### H2 — Leaked sandboxes

A cancelled task, a crashed process, or a cancellation during `create()` leaves cloud
sandboxes running and billing. At agent scale this is a runaway cost, not an untidiness.

- **Tripwire:** CI reports non-zero sandboxio-labelled containers after a Docker job; a provider
  console shows sandboxes with no corresponding run.
- **Response:** shielded teardown bounded by `TEARDOWN_GRACE`, a Ryuk-style reaper for
  Docker, `metadata` labels propagated to provider-native labels so orphans are findable,
  `sandboxio reap` for operators, and a CI assertion on every Docker job
  ([ADR-0020](adr/0020-cancellation-semantics.md)). The mandatory `create(timeout=...)` is
  the guaranteed backstop — it bounds the worst case at ~300 s of billing even when every
  other mechanism fails.

### H3 — A secret reaches a log, trace, repr or audit event

Three observability sinks plus exceptions plus reprs means five chances to leak. Redaction
implemented per-sink will be wrong in at least one.

- **Tripwire:** any sink constructed downstream of its own formatting rather than from the
  shared record.
- **Response:** one operation record, one redaction pass upstream of all sinks, one test
  asserting a canary secret appears in none of them
  ([spec/06](spec/06-observability.md#redaction)).

### H4 — Isolation claims we cannot defend

Publishing "MICROVM" or "GVISOR" for a third party's infrastructure is a security claim
about someone else's system. If it is wrong, or becomes wrong, users made a trust decision
on our word.

- **Tripwire:** a tier in the table with no dated source; a provider changing its runtime.
- **Response:** every tier above `CONTAINER` carries a dated provider-documentation source;
  Daytona stays unverified; a provider's mechanism change is a **changelog entry**, not a
  footnote ([ADR-0006](adr/0006-isolation-tiers-first-class.md)).

---

## Technical hazards (the project gets hurt)

### H5 — Provider churn outpaces maintenance

E2B shipped v0→v1→v2 in about a year, with `beta_` methods and yanked releases. Daytona
rebuilt product, SDK and license. Modal enforces pre-1.0 deprecations. Absorbing this is the
value proposition; failing to absorb it is the death of the value proposition.

- **Tripwire:** the nightly latest-SDK canary red for more than one week; `provider-churn`
  issues accumulating unclosed.
- **Response:** canary in CI from the start, loose lower bounds rather than hard pins, and
  the **public churn-absorption log** — which is simultaneously the mitigation and the
  marketing ([runbook](runbook.md#provider-churn-response)).

### H6 — Core stops being provider-ignorant

A provider concept leaks into core — E2B's context semantics, Modal's Volume model — and
the one-file-per-provider containment quietly stops holding.

- **Tripwire:** a provider name, or a provider-shaped concept, appearing in a core module;
  an adapter needing more than a thin mapping.
- **Response:** core imports nothing provider-specific, enforced by an import-linter rule.
  Widening core is deliberate and goes through an ADR.

### H7 — Abstraction drifts toward the lowest common denominator

Each individual "let's just not support that, only one backend has it" is reasonable. Fifty
of them is `apache-libcloud`.

- **Tripwire:** a capability removed rather than flagged; `.native` usage growing in our own
  examples; a feature request closed as "not portable".
- **Response:** `Capability` + `.native` is the answer, never removal. Promotion into the
  typed API at **two** stable backends ([ADR-0003](adr/0003-no-lowest-common-denominator.md)).

### H8 — Import bloat and eager imports

A slow or side-effecting import is fatal for a library agents load on every cold start, and
disqualifying in offline or air-gapped CI.

- **Tripwire:** import budget over 150 ms.
- **Response:** hard CI fail over 200 ms; **feature freeze until fixed** — this is one of
  the pre-committed thresholds.

### H9 — FakeBackend diverges from reality

Users test against the fake, ship, and discover real backends behave differently. The fake
then actively costs trust instead of building it.

- **Tripwire:** a bug that the fake could not have caught, twice in the same area.
- **Response:** the fake passes the same contract suite. Divergence is a **suite gap** — fix
  the shared test, never special-case the fake
  ([ADR-0007](adr/0007-contract-suite-as-spec.md)).

---

## Supply-chain hazards

### H10 — A litellm-class incident in sandboxio itself

sandboxio is a credential-adjacent dependency that executes untrusted code. A compromise here is
maximally bad, and the enterprise accounts we are targeting are exactly the ones that will
never come back.

- **Tripwire:** any new base dependency; any transitive tree growth; a maintainer account
  without hardware 2FA.
- **Response:** `typing-extensions` + `anyio` only in core, adapters isolated and lazy,
  Trusted Publishing with PEP 740 attestations, `SECURITY.md` and an advisory process from
  day one, OpenSSF Scorecard tracked
  ([ADR-0004](adr/0004-thin-core-lazy-adapters.md), [runbook](runbook.md#security-advisories)).

### H11 — AI-slop issues and PRs

The curl project's experience: plausible-looking, wholly fabricated reports consuming
maintainer attention until the maintainers burn out. A security-adjacent project attracts
more of it.

- **Tripwire:** unreproducible reports rising as a share of the issue queue.
- **Response:** issue templates requiring reproduction, a stated and enforced triage policy,
  and closing without debate — from day one, not after it hurts.

---

## Market hazards

### H12 — Framework absorption — **highest likelihood**

LangChain's sandbox backends and OpenAI Agents SDK's `SandboxConfig` become good enough that
framework-agnosticism stops being worth a dependency.

- **Tripwire:** `SandboxClient` gaining non-OpenAI adopters; framework sandbox layers adding
  security policy depth.
- **Response:** complement rather than fight — ship adapters **into** them, in both
  directions ([ADR-0013](adr/0013-complement-openai-sandboxclient.md)). If it wins, we are
  already inside it.

### H13 — Provider consolidation

The sandbox market collapses to one or two providers and the abstraction loses its point.

- **Tripwire:** a major backend shutting down or being acquired; new projects defaulting to
  one provider without evaluation.
- **Response:** shift weight to the security-policy layer, the local/CI story (which
  survives consolidation intact), and Stage 2 orchestration.

### H14 — "Yet another abstraction layer" fatigue

- **Tripwire:** adoption conversations spent justifying the layer's existence rather than
  discussing features.
- **Response:** thin core, visible escape hatches, substrate positioning. The fsspec
  comparison does a lot of work here; earn it rather than claim it.

### H15 — A hyperscaler or standards body ships the standard

AWS AgentCore going self-hostable, or the Kubernetes agent-sandbox CRD reaching 1.0 with
broad adoption.

- **Tripwire:** `agents.x-k8s.io` leaving alpha with multi-vendor backing; an AgentCore OSS
  edition.
- **Response:** become the best adapter into it. This is a planned pivot, not a defeat.

---

## Server-mode hazards (Phase 2)

Only live if `sandboxio-server` is triggered, but the constraints are decided now. The server
holds cloud credentials **and** executes untrusted code — a tier-1 credential surface. The
LiteLLM 2026 failure chain, not to be repeated:

| Their failure | Our rule |
|---------------|----------|
| CVE-2026-42208 — pre-auth SQLi in the API-key verification path, exploited within ~36h of advisory, CISA KEV | Parameterize **everything** in the auth path |
| CVE-2026-42271 + Starlette BadHost chain — assessed CVSS 10.0 unauth RCE via MCP *test* endpoints | No unauthenticated endpoints at all; role-gate every management and test endpoint; validate Host headers |
| `/config/update` without a role check → runtime config rewrite → RCE | No config hot-reload without authz; prefer immutable config at boot |
| JWT cache keyed on `token[:20]` | No clever auth caching |

Plus: rootless container, least-privilege per-backend credentials, bind localhost unless
configured otherwise, and **never** a Docker socket reachable from sandboxed code.
