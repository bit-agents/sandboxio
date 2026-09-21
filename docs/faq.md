# FAQ

Short answers with a link to the long one. If your question is "why does X fail", start at
[troubleshooting](how-to/troubleshooting.md) instead.

## What it is

**Is this a framework?**
No. It is a library with no runtime of its own, no server and no opinion about how you
build your agent — one async API over sandbox providers, plus a sync facade
([ADR-0009](adr/0009-library-first-server-later.md)).

**Does it replace the provider SDKs?**
It sits in front of them and keeps them reachable. Provider-specific features stay
available through `Capability` flags and `sb.native`, so using sandboxio is not a decision
to give up the E2B or Docker API ([ADR-0003](adr/0003-no-lowest-common-denominator.md)).

**Why not just Docker plus `subprocess`?**
For one provider and one script, that is the right answer. The case for this library starts
when you need a second backend, a security default you can prove, or tests that run without
Docker — laid out with the counter-cases in
[why sandboxio and not something else](explanation/comparisons.md).

**How does it relate to OpenAI's `SandboxClient`?**
Complement, not competitor: framework sandbox layers are a distribution channel for this
one ([ADR-0013](adr/0013-complement-openai-sandboxclient.md)).

## Using it

**Which backends exist?**
Docker, E2B and an in-process fake in v0.1; Modal in v0.1.1
([ADR-0025](adr/0025-v01-scope-cut.md)). Third-party adapters install as
`sandboxio-<name>` and register under the same entry-point group as the first-party ones.

**Do I have to write async code?**
No. `create_sync()` gives the same API, blocking — it is a thin facade over the async core,
not a second implementation. Each sync sandbox holds one portal thread for its lifetime, so
heavy concurrency is a reason to use the async API ([ADR-0022](adr/0022-sync-facade.md)).

**How do I install dependencies if the sandbox has no network?**
Bake them into the image, or upload an offline wheelhouse — both work under the default
policy ([Docker how-to](how-to/docker.md#getting-dependencies-into-a-deny-egress-sandbox)).
On E2B you can also allowlist the hosts you need.

**Can I turn the network on?**
Yes, explicitly: `NetworkPolicy(egress="allow")`. What you cannot do is get it by accident
([deny by default](explanation/deny-by-default.md)).

**Can I run without a timeout?**
No. `timeout=None` on a call means *inherit the sandbox timeout*; on `create()` it is
refused. Unbounded execution is a cost and an availability problem, not only a security one
([spec/05](spec/05-security-policy.md#mandatory-timeouts)).

**How do I test code that uses sandboxio?**
`fake://` and the `sbx_fake` fixture, which ship with the base package: no Docker, no
network, no provider account ([offline testing](how-to/offline-testing.md)).

**Does it work with LangGraph, the OpenAI Agents SDK or MCP?**
Yes, with the supported version ranges published and proven by a weekly CI matrix
([integrations](how-to/integrations.md#supported-framework-versions)).

## Security

**Is a Docker sandbox safe for untrusted code?**
No. `CONTAINER` shares the host kernel and is not a boundary against hostile code — it is
for trusted, dev and CI code. `MICROVM` is the recommended floor for untrusted or
multi-tenant work ([the security model](explanation/security-model.md),
[isolation tiers](explanation/isolation-tiers.md)).

**Then what does sandboxio actually give me?**
A blast radius you chose on purpose, and defaults that fail loudly rather than silently:
egress denied, timeouts mandatory, caps always applied, teardown guaranteed, and the
isolation tier reported and enforceable. The full in-scope and out-of-scope list is on
[the security model page](explanation/security-model.md).

**What happens if a backend cannot honour a security argument?**
It raises. Accepting and ignoring a network policy is the single most dangerous bug this
library could ship, so an unsupported allowlist or cap is refused, never approximated
([H1](hazards.md#h1--a-security-default-silently-does-not-apply)).

**Are my secrets safe in logs?**
Values passed as `secrets=` are redacted from messages, reprs, audit events, spans and CLI
output before rendering, and sandboxio persists no credential anywhere. Secrets in a DSN are
refused ([spec/05](spec/05-security-policy.md#secrets)).

**How do I report a vulnerability?**
Privately, through the Security tab — never an issue
([SECURITY.md](https://github.com/bit-agents/sandboxio/blob/main/SECURITY.md)).

## The project

**Is it production-ready?**
v0.1 is released, the contract suite gates every backend, and the behaviour you build
against is the normative, CI-enforced [specification](spec/README.md). What v0.1 does not
give you is a frozen API: a minor release may break the covered surface until 1.0
([version policy](explanation/version-policy.md)), so pin a minor. It is also young — judge
the code, not the adjective.

**What does it depend on?**
`anyio` and `typing-extensions`, and nothing else. Every provider SDK sits behind an extra
and is imported the first time that backend is used; `import sandboxio` has a 150 ms budget
that CI enforces ([ADR-0004](adr/0004-thin-core-lazy-adapters.md)).

**Does it phone home?**
No telemetry, ever, not even opt-out — and no import side effects at all: no sockets, no
logging configuration, no global state ([ADR-0012](adr/0012-no-telemetry-no-import-side-effects.md)).

**Which Python versions?**
3.11 and newer ([ADR-0015](adr/0015-python-version-floor.md)).

**What counts as a breaking change?**
More than you would expect, because there are two audiences: callers and adapter authors. A
new required contract-suite test breaks adapter authors even though callers see nothing, and
the version number takes the stricter verdict. `sb.native` is outside the contract by design
([version policy](explanation/version-policy.md)).

**What happens when a provider ships a breaking change?**
A nightly canary installs every provider SDK unpinned and opens an issue when it breaks;
what was absorbed is written down in the [churn log](churn-log.md). Absorbing that churn
publicly is the point of the project, not a chore beside it.

**What is the licence?**
MIT for code, CC BY 4.0 for the prose in `docs/`. Contributions are under the DCO, with no
CLA ([ADR-0016](adr/0016-license-mit.md), [ADR-0026](adr/0026-docs-license-cc-by.md)).

**Why `sandboxio` and not `sbx`?**
`sbx` on PyPI is an unrelated package. `SBX` survives as the short code — error codes,
`SBX_` environment variables, the `sbx_fake` fixture — and copy-paste commands always use
the full name ([ADR-0014](adr/0014-project-name.md)).

**Where do I ask something that is not here?**
[Discussions](https://github.com/bit-agents/sandboxio/discussions) for questions and ideas,
[issues](https://github.com/bit-agents/sandboxio/issues/new/choose) for a bug you can
reproduce ([SUPPORT.md](https://github.com/bit-agents/sandboxio/blob/main/SUPPORT.md)).
