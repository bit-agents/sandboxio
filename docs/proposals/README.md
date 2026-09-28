# Proposals

A proposal designs a change to the public API, the specification or the security surface in
the open, before it is built. A change that touches none of those needs only an issue.

When a proposal is accepted, its normative text moves into [`docs/spec/`](../spec/README.md)
and its decisions into [ADRs](../adr/README.md). The proposal stays as the record of why. It
carries no release date.

**Lifecycle:** `Proposed` → `Accepted` → `Implemented`, or `Rejected` · `Withdrawn` ·
`Superseded by NNNN`. At most five proposals are `Proposed` at a time.

A number is assigned when the proposal is published, in order. Discussion happens on the
issue linked from the proposal's header.

| Proposal | Title | Status |
|----------|-------|--------|
| [0001](0001-egress-allowlist-and-dns.md) | Egress allowlist and DNS control on every backend | Proposed |
