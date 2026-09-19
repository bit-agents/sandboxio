# sandboxio

**One secure Python API for running AI-agent code in any sandbox.** Swap Docker ↔ E2B ↔
Modal with one line; no network by default; test your agent tools offline with the built-in
fake.

<!-- TODO(placeholder): badges — CI, PyPI version, Python versions, OpenSSF Scorecard, license.
     Blocked on the GitHub org/repo being chosen (ADR-0014) and CI existing (build-order Step 1). -->
<!-- {{BADGES}} -->

> [!WARNING]
> **Pre-alpha. There is no code in this repository yet — only the specification.**
>
> The public API is not stable, nothing is published to PyPI, and no version is suitable for
> any use. What *is* stable enough to build against is [`docs/spec/`](docs/spec/), which is
> normative and CI-enforced.
>
> Watch the repo if you want the v0.1 announcement. Do not depend on this yet.

## Why this exists

Every sandbox provider ships its own SDK with its own shape, so agent code that runs on one
is rewritten for the next. The framework layers each solve it captively — LangChain's
backends only help inside LangChain. sandboxio is the framework-agnostic substrate
underneath, with the security posture that agent execution actually needs.

- **Security is the headline, not an add-on.** Deny-by-default egress, mandatory timeouts,
  isolation-tier reporting and audit hooks are all in v0.1 — not a later hardening pass.
- **No lowest common denominator.** One-backend features stay reachable through `Capability`
  flags and `.native` instead of being sanded off.
- **Tiny, auditable core.** `anyio` and `typing-extensions` only; every backend SDK sits
  behind an extra and is imported lazily.
- **Offline-testable.** `FakeBackend` and a pytest fixture, so your agent's tools have tests
  that need no Docker, no network and no provider account.
- **Provider churn is absorbed publicly.** Upstream breaking changes are tracked, absorbed
  and written down.

## Quickstart

<!-- TODO(placeholder): replace with the real install line once the package is published.
     `uvx sandboxio demo` is the documented entry point — never the `sbx` alias, which
     resolves to an unrelated PyPI package (ADR-0014). -->

```bash
# {{INSTALL}} — not yet published
uv add sandboxio            # planned
```

```python
import sandboxio

async with await sandboxio.create() as sb:                      # zero-config, local Docker
    res = await sb.run_code("print('hello')")
    print(res.stdout)

sb = await sandboxio.create("docker://python:3.12-slim")        # one-line backend swap
sb = await sandboxio.create("e2b://code-interpreter")
sb = await sandboxio.create("modal://base?gpu=T4")

res = await sb.run(["pytest", "-q"], timeout=120)
```

Full surface, including the sync facade, streaming, filesystem and capability discovery:
[`docs/spec/03-public-api.md`](docs/spec/03-public-api.md).

## Backends

| Backend | Status | Isolation tier |
|---------|--------|----------------|
| Docker | planned for v0.1 | <!-- {{TIER}} --> |
| E2B | planned for v0.1 | <!-- {{TIER}} --> |
| `FakeBackend` | planned for v0.1 | n/a — in-process, for tests |
| Modal | planned for v0.1.1 | <!-- {{TIER}} --> |

<!-- TODO(placeholder): isolation tiers stay blank until every tier above CONTAINER carries a
     dated link to the provider's own documentation. Publishing a tier is a security claim
     about someone else's infrastructure — see hazards H4 and ADR-0006. Do not fill these in
     from memory. -->

Third-party adapters are first-class: the adapter contract is
[specified](docs/spec/08-adapter-contract.md) and enforced by a shared contract suite.

## Documentation

<!-- TODO(placeholder): link the published docs site once it exists (Diátaxis, generated from docs/). -->
<!-- {{DOCS_URL}} -->

Until then, read the repository:

- [`docs/spec/`](docs/spec/) — the normative specification. This is the contract.
- [`docs/adr/`](docs/adr/) — why each decision was made, including the ones that look arbitrary.
- [`docs/hazards.md`](docs/hazards.md) — what can go wrong, for you and for this project, with tripwires.
- [`docs/build-order.md`](docs/build-order.md) — what is being built, in what order.
- [`docs/runbook.md`](docs/runbook.md) — how the project is operated and released.

## Security

Isolation tiers are reported, not assumed: `CONTAINER` is not a security boundary against
hostile code, and sandboxio says so rather than implying otherwise.

Report vulnerabilities privately — see [`SECURITY.md`](SECURITY.md). A report that a
*declared control did not apply* is the highest-severity class this project has.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md). Contributions need a DCO `Signed-off-by` line;
there is no CLA.

## License

Code is [MIT](LICENSE). Prose in `docs/` is [CC BY 4.0](LICENSE-DOCS); code samples inside
those documents are MIT ([ADR-0026](docs/adr/0026-docs-license-cc-by.md)).
