# ADR-0015 — Python floor 3.11; develop on 3.14

**Status:** Accepted
**Date:** 2026-09-19
**Resolves:** [Q2](../open-questions.md#q2--python-version-floor)
**Related:** [ADR-0002](0002-async-first-anyio.md), [ADR-0004](0004-thin-core-lazy-adapters.md)

## Context

The input design set never stated a floor, though the API as written needs at least 3.10
(`X | Y` in runtime-evaluated signatures, anyio, PEP 702 `@deprecated`).

A floor is an adoption gate, not a style choice: a team on an older interpreter cannot
install us at all. sandboxio's pitch is "drop this into your existing agent stack", and
those stacks are existing codebases that move slowly.

**Ecosystem floors.** Every backend SDK and framework we target already sits at `>=3.10`:
`e2b`, `modal`, `langgraph`, `openai-agents`, `pydantic-ai`, `crewai`, `typer`, `anyio`.
Two carry upper caps: **`crewai` requires `<3.14`** and `modal` requires `<3.15`.

**Reachable install base**, by share of the last 180 days of downloads:

| Floor | langgraph | e2b | openai-agents |
|-------|-----------|-----|---------------|
| 3.11 | 90.1% | 94.9% | 90.4% |
| 3.12 | 67.2% | 81.8% | 56.6% |
| 3.13 | 26.4% | 27.0% | 19.3% |
| 3.14 | 7.5% | 5.9% | 5.0% |

**What newer floors would buy us** is thin. 3.13 adds stdlib PEP 702 `@deprecated`, which
`typing-extensions` — already a base dependency — provides anyway. 3.14 adds PEP 649
deferred annotations, pleasant for a heavily-typed protocol library but not load-bearing,
and official free-threading, which is irrelevant to an I/O-bound async library.

A 3.14 floor would additionally make sandboxio and CrewAI **mutually uninstallable**,
contradicting the four-framework coverage claim in [spec/09](../spec/09-integrations.md).

## Decision

- **`requires-python = ">=3.11"`.**
- **CI matrix: 3.11, 3.12, 3.13, 3.14.** Default CI job and local development on **3.14**,
  so we find deprecations early and ship on a modern toolchain.
- Support the newest release within one month of its final; drop a version only when it
  reaches upstream EOL, and treat the drop as a minor bump with a changelog entry.
- **`from __future__ import annotations` repo-wide.** On 3.11-3.13 it keeps annotations
  unevaluated, which measurably helps the import budget
  ([ADR-0004](0004-thin-core-lazy-adapters.md)); on 3.14 PEP 649 makes it a no-op. Any code
  needing annotations at runtime uses `typing.get_type_hints`, never `__annotations__`
  directly.
- Upper caps: we declare **none**. Capping `requires-python` is how a dependency becomes
  the thing blocking a user's upgrade.

**Why 3.11 and not 3.12:** the 3.11 cohort is still 13-34% of downloads depending on
ecosystem — a third of OpenAI Agents users. PEP 695 generics syntax does not pay for that.

**Why 3.11 and not 3.10:** 3.11 unified `asyncio.TimeoutError` with the builtin
`TimeoutError`, which is what lets [Q4](../open-questions.md#q4--timeouterror-shadows-the-builtin)
resolve cleanly rather than with a compatibility shim. 3.11 also brings `Self`, `StrEnum`
and `ExceptionGroup`. It is supported upstream until October 2027, beyond any horizon this
project currently plans for.

## Consequences

- We develop on 3.14 and ship for 3.11, so **CI, not the local interpreter, is what proves
  the floor.** A 3.11 job is a required check; without it, 3.12+ syntax leaks in silently.
- Reviewers must actually know the floor. `AGENTS.md` and `CONTRIBUTING.md` state it, since
  coding agents will otherwise generate whatever the newest interpreter allows.
- No PEP 695 type-parameter syntax, no t-strings, no `concurrent.interpreters` in core
  until the floor moves.
- The floor is revisited at the [quarterly review](../runbook.md#quarterly-review) against
  the same download-share data, not on the appeal of new syntax.
- `crewai`'s `<3.14` cap is a **third-party** constraint on our integration matrix, not on
  our floor. It is documented in the framework matrix and re-checked quarterly; if it
  persists it becomes a note in the CrewAI integration docs.
