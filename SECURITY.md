# Security Policy

sandboxio runs untrusted code and sits next to credentials. A bug here is worse than a bug in
most libraries, so this process exists from day one rather than from the first report.

## Reporting a vulnerability

**Report privately through GitHub Security Advisories** — the repository's *Security* tab,
*Report a vulnerability*. Do not open a public issue, and do not disclose before a fix is
released.

You will get an acknowledgement **within 48 hours**.

Useful in a report: affected version, backend (Docker / E2B / Modal), whether a declared
security control did not apply, and a reproduction. `sandboxio doctor --json` output is
designed to be pasted and carries no secrets.

### Especially wanted

A report that a **declared control did not apply** is the highest-severity class this
project has — for example:

- `NetworkPolicy(egress="deny")` accepted, but the sandbox reached the network.
- A `Resources` cap accepted and silently dropped.
- `require_isolation=` not actually enforced, or a reported `IsolationTier` that the backend
  does not provide.
- A secret reaching a log, trace, `repr` or audit event.

These are treated as security bugs even when no exploit is demonstrated: the user made a
trust decision on our word.

## Supported versions

Pre-1.0, only the latest released minor is supported. There are no backports.

## Our process

1. **Intake** — private advisory, acknowledged within 48 hours.
2. **Triage** — severity assessed, with particular weight on the policy-enforcement path.
3. **Fix in private** — advisory drafted, fix written, and a regression test added to the
   contract suite. A security fix without a test is not finished.
4. **Coordinate** — if the root cause is a provider's, disclosure is coordinated with them.
5. **Release and disclose** — patch release, published advisory with a CVE where warranted,
   changelog entry. We do not bury it.
6. **Post-incident** — which gate should have caught it, and adding that gate.

For a policy-enforcement bug we state plainly which control did not apply, from which
version, and what users should check.

Full operator detail: [`docs/runbook.md`](docs/runbook.md#security-advisories).

## Scope

**In scope:** the `sandboxio` library, its adapters, the bundled MCP server, and the release
pipeline.

**Out of scope:** vulnerabilities in Docker, E2B, Modal or another provider's
infrastructure — report those to the provider. We will help coordinate, and we will
document the impact on sandboxio users.

**Not a vulnerability:** code escaping a sandbox on a backend whose reported
`IsolationTier` is `CONTAINER`. Container isolation is not a security boundary against
hostile code, the tier reports that honestly, and choosing a stronger tier is the documented
remedy. A *misreported* tier is very much a vulnerability.
