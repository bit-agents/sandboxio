# Contributing to sandboxio

## Licensing and the DCO

Contributions are accepted under the [Developer Certificate of Origin](https://developercertificate.org/).
There is **no CLA** and no copyright assignment.

Sign off every commit:

```bash
git commit -s -m "fix: ..."
```

That adds `Signed-off-by: Your Name <you@example.com>`, which certifies you wrote the patch
or have the right to submit it under the project's license.

**Inbound equals outbound.** Code you contribute is licensed under the MIT License in
[`LICENSE`](LICENSE); prose you contribute to `docs/` is licensed under CC BY 4.0 in
[`LICENSE-DOCS`](LICENSE-DOCS). Code samples inside `docs/` are MIT, not CC BY
([ADR-0026](docs/adr/0026-docs-license-cc-by.md)).

## Before you open a PR

**Read [`docs/spec/`](docs/spec/) first.** It is the normative contract, in RFC-2119
language, and it wins over every other document. Where the spec is silent or marked `OPEN`,
**ask** — do not invent. A decision that will outlive the PR needs an
[ADR](docs/adr/README.md), not a comment.

Architectural decisions already made are in [`docs/adr/`](docs/adr/). A requirement that
looks arbitrary usually has an ADR explaining what it is preventing.

## Development

```bash
uv sync --all-extras          # core + docker + e2b + modal + dev
uv run pytest                 # unit + fake contract suite; no Docker, no network
```

Python 3.14 for development; the floor is 3.11 and is proven by CI, not by your local
interpreter.

Before pushing, run what CI runs:

```bash
uv run pytest -q                        # fast: fake backend only
uv run pytest -m docker                 # Docker contract suite (needs Docker)
uv run --env-file .env pytest -m e2b    # E2B contract suite; E2B_API_KEY in a git-ignored .env
uv run ruff check . && uv run ruff format --check .
uv run pyright && uv run mypy
uv run python scripts/check_doc_links.py
```

Full loop and release process: [`docs/runbook.md`](docs/runbook.md).

## What gets a PR merged

- **A new adapter passes 100% of the contract suite** for every capability it declares.
  Declaring a capability you do not implement is the one unforgivable bug
  ([ADR-0007](docs/adr/0007-contract-suite-as-spec.md)).
- **A bug fix comes with the test that would have caught it.** If the contract suite should
  have caught it, the test goes in the suite and the PR gets a `spec-gap` label.
- **A security fix is not finished without a regression test.**
- **No new base dependency** without an ADR. Core is `anyio` + `typing-extensions`
  ([ADR-0004](docs/adr/0004-thin-core-lazy-adapters.md)).
- **No import-time side effects**, no sockets at import, nothing that pushes the import
  budget over 150 ms ([ADR-0012](docs/adr/0012-no-telemetry-no-import-side-effects.md)).
- **A public-API change updates the examples.** Every script in [`examples/`](examples/)
  is executed by CI against the fake, so a stale example fails the build, not a stranger.
- **Never widen the API to the lowest common denominator.** One-backend features go behind
  `Capability` flags and `.native` ([ADR-0003](docs/adr/0003-no-lowest-common-denominator.md)).

Commit subjects follow [Conventional Commits](https://www.conventionalcommits.org/).

CI gates block merge and are not overridden. If a gate is wrong, change the gate in its own
PR, with a reason.

## Reporting bugs

**Issue templates require a reproduction. No repro, no triage** — stated up front and
applied without debate. Include `sandboxio doctor --json` output for anything
environment-related.

Questions go to GitHub Discussions, not issues.

**Security bugs do not go in issues at all** — see [`SECURITY.md`](SECURITY.md).

## AI-assisted contributions

They are welcome, and much of this project is built that way. The bar is the same either
way: **you understand the change, you can defend it in review, and you have reproduced the
bug it claims to fix.**

A plausible-looking report or patch that turns out to be fabricated is closed without
debate. This is not hostility to the tooling; it is what keeps the issue queue survivable
for a security-adjacent project.
