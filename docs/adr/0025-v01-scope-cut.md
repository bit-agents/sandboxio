# ADR-0025 — v0.1 ships Docker + E2B + Fake; Modal moves to v0.1.1

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q12](../open-questions.md#q12--v01-scope-cut)
**Related:** [ADR-0007](0007-contract-suite-as-spec.md), [ADR-0003](0003-no-lowest-common-denominator.md)

## Context

The roadmap scoped v0.1 at weeks 2-10 with three real adapters (Docker, E2B, Modal) plus
FakeBackend, the contract suite, the CI matrix, an MCP server, two framework adapters, OTel,
audit, a CLI and a full Diátaxis documentation set.

That is not an eight-week scope. The relevant question is not whether it slips but *what*
slips — and under time pressure the things that go are documentation and test depth, which
are precisely the two things this project's differentiation rests on. The contract suite is
normative ([ADR-0007](0007-contract-suite-as-spec.md)) and the offline-testing story is a
primary adoption hook; neither survives being the last thing built.

The launch narrative needs **two** backends, not three. "Swap Docker↔E2B with one line" is
the same claim as "swap Docker↔E2B↔Modal with one line" — a third backend does not make the
demo more convincing, it makes it later.

Docker and E2B are also the pair that stresses the abstraction hardest: the widest possible
gap between local runc with no rich outputs and a Firecracker microVM with a code
interpreter. Modal sits between them on almost every axis, so it is the least informative
of the three to build first.

## Decision

**v0.1 ships Docker, E2B and FakeBackend. Modal moves to v0.1.1.**

Unchanged in v0.1: the contract suite, the pytest fixture and fake, the CI matrix, the MCP
server, **one** framework adapter (LangGraph), OTel spans, audit, `doctor` / `demo` / `reap`,
full typing, and the Diátaxis documentation set with a generated error reference.

Everything else in the roadmap's v0.1 list stays as written.

Modal in v0.1.1 also serves a purpose beyond coverage: GPU, Volumes with per-tenant
`sub_path` and the gVisor tier re-test the abstraction against a genuinely different
filesystem and resource model, after the ports have settled rather than while they are still
moving.

## Consequences

- The isolation-tier table ships with `GVISOR` unrepresented by any v0.1 backend. The tier
  stays in the enum — it is a property of the model, not of what we happen to have shipped —
  but the docs must not imply Modal is available.
- "Works with all four frameworks" is a v0.2 claim, not a launch claim. v0.1 says LangGraph,
  and says it accurately.
- A team that specifically needs Modal waits one release. Acceptable: they can reach it via
  `.native` on no backend at all, so the honest answer is "not yet", and the release is
  weeks, not quarters.
- The Step 4 exit criterion — Docker passing 100% of the contract suite — remains the gate
  everything hangs on. Cutting scope does not relax it.
- If Docker and E2B together reveal that the abstraction needs widening, that happens before
  a third adapter is written against it, which is the cheaper ordering.
