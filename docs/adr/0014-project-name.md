# ADR-0014 — Project name: `sandboxio`, short code `SBX`

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q1](../open-questions.md#q1--project-name)
**Amended by:** [ADR-0025](0025-v01-scope-cut.md) — `sandboxio[modal]` lands in v0.1.1
**Related:** [ADR-0010](0010-stable-error-codes.md), [ADR-0004](0004-thin-core-lazy-adapters.md)

## Context

The original three-letter working name was load-bearing: module paths, the entry-point group, error codes
(semver-covered API), env vars, CLI name, extras, third-party package convention and docs
URLs all embed the project name. Renaming after launch breaks all of them, so the name had
to be fixed before commit one.

That working name is **not available on PyPI**. It is held by *StudyBox (SBX) — Terminal
Flashcards* (MIT, two releases, last published 2020-12-09). The project is dormant, but
PEP 541 name transfer is slow and not reliably granted, so we treated the name as taken
rather than block the project on an appeal.

Criteria from the original brief: short, neutral, generic (fsspec-style), pip-available,
signals "substrate" rather than "framework".

Candidates checked on PyPI — available: `sandboxio`, `execbox`, `isobox`, `anysandbox`,
`sandkit`, `boxrun`, `sandbx`, `sandboxpy`, `boxen`. Taken: `runbox`, `anybox`, `enclave`,
`sbox`, `cage`, `warden`, `vessel`, `codebox`, `sandboxlib`. `pysandbox` is available but
rejected: Victor Stinner's `pysandbox` was publicly abandoned as "broken by design" for
Python sandboxing, which is the worst possible association for a security library.

## Decision

**The project is `sandboxio`. The short code is `SBX`.**

| Surface | Value |
|---------|-------|
| Distribution / import | `sandboxio` · `import sandboxio` |
| Extras | `sandboxio[docker]`, `sandboxio[e2b]`, `sandboxio[modal]` |
| Entry-point group | `sandboxio.backends` |
| Third-party adapters | `sandboxio-fly`, `sandboxio-<name>` |
| Error codes | `SBX_E1002` |
| Env vars | `SBX_DEBUG` |
| Pytest fixture | `sbx_fake` |
| CLI | `sandboxio` (primary), `sbx` (alias script) |
| MCP module / image | `python -m sandboxio.mcp` · `ghcr.io/<org>/sandboxio-mcp` |
| Routing file | `sandboxio-routing.yaml` |
| Phase-2 server | `sandboxio-server` |

Supporting choices:

- **One long name, one short code.** `SBX` is the project's short code, used where brevity
  is worth more than explicitness: error codes, env vars, the CLI alias, the pytest
  fixture. It is documented as such, not treated as a second name. Anything new picks a
  side by this rule, not by taste.
- **Canonical usage is `import sandboxio`, unaliased.** Docs and examples never teach an
  alias. Callers may alias; we do not show it. Two spellings in the docs would defeat both
  the one-obvious-way rule and greppability, and sandbox creation is not frequent enough to
  earn a `numpy as np`-style alias.
- **`uvx sandboxio demo` is the documented form.** `uvx` resolves by distribution name, so
  invoking the short alias there would install the unrelated flashcards package. Copy-paste
  examples therefore always use the full name.
- The short alias console script is a convenience only, and may collide locally with the
  flashcards package. Acceptable; it is not the documented entry point.
- The GitHub organisation `sandboxio` is taken. The repo lives under a suffixed org or a
  personal account; the org name is not part of the public contract the way the PyPI name
  is.

## Consequences

- Error codes, env vars and the fixture name written before this ADR remain valid — the
  short code preserves them. Only distribution, import and CLI surfaces changed.
- Two spellings exist in the project's vocabulary. The long/short rule above is what keeps
  that from becoming ambiguity.
- `sandboxio` reads as async infrastructure (`asyncio`, `anyio`, `trio`), which suits the
  positioning. It may also read as a company domain — acceptable, and arguably useful.
- The dormant PyPI package under the old working name is a standing minor hazard: docs must
  never instruct a user to `pip install` or `uvx` that name.
- If PEP 541 ever frees it, we do **not** rename. We may claim it as a defensive
  placeholder pointing at `sandboxio`.
