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
uv sync --all-extras          # core + docker + e2b + dev
uvx pre-commit install        # ruff, whitespace and uv.lock, on every commit
uv run pytest                 # unit + fake contract suite; no Docker, no network
```

The hooks are deliberately fast. Types, tests and the contract suites are not in them —
a hook slow enough to skip protects nothing.

Python 3.14 for development; the floor is 3.11 and is proven by CI, not by your local
interpreter.

Before pushing, run what CI runs:

```bash
make check                              # lint, types, tests, Docker suite, Actions lint, links
make coverage                           # the same measurement CI gates on, plus htmlcov/
make test-e2b                           # nightly in CI; needs E2B_API_KEY in a git-ignored .env
make site                               # the docs site, built exactly as Pages publishes it
```

`make demo-cast` re-records the terminal capture in `README.md` and the quickstart. It needs
`asciinema`, `agg` and a Docker daemon, and it runs the real command — so the timings in the
GIF are the machine's, not a target. Run it when the demo's output changes, and take the
median of a few runs rather than the fastest.

Coverage is a floor, not a target: CI fails under the `fail_under` in `pyproject.toml`,
measured over the default selection plus the Docker suite. Raise the floor once the real
number has held above the next step; never lower it to make a red run green.

`make help` lists every target, and each one is a single line you can run by hand instead.

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

Commit subjects follow [Conventional Commits](https://www.conventionalcommits.org/), and CI
checks every commit in the PR as well as the PR title.

**Every PR is squash-merged** and its branch is deleted on merge, so the PR title becomes
the subject on `main`. The squashed commit keeps the full commit messages, which is what
carries your `Signed-off-by` into the history.

CI gates block merge and are not overridden. If a gate is wrong, change the gate in its own
PR, with a reason.

## Changelog entries

Every change a user could notice gets one line under `## [Unreleased]` in
[`CHANGELOG.md`](CHANGELOG.md), in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
heading that fits: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.

Write it for somebody deciding whether to upgrade, not as a summary of your diff:

```markdown
### Fixed

- `CapabilityNotSupported` now names the backends that do support the capability, instead of
  a generic "check `capabilities`" hint.
```

- **No entry needed** for refactors, tests, CI or docs that change nothing observable. When
  in doubt, write one; a redundant line is cheaper than a silent behaviour change.
- **Breaking changes open with `**Breaking:**`** and say what to do instead. What counts as
  breaking, and what window a deprecation gets, is
  [the version policy](docs/explanation/version-policy.md).
- **A deprecation names its replacement and its removal version.** "Deprecated" without both
  is an entry that helps nobody.
- **An absorbed provider break is written twice**: here, and in the
  [churn-absorption log](docs/churn-log.md) with the detail. The changelog says a version
  bump is all you need; the churn log is the evidence for that claim.

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
