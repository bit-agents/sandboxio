---
name: docs-consistency
description: Audit the public documentation for prose that contradicts the build, the spec or another page. Use before a release or a public announcement, after a scope cut or a dependency-bound change, or when asked to check whether the docs still match the code. Not a link checker — CI already owns that.
---

# Docs consistency

Every consistency bug this project has shipped was the same shape: **prose restating a
decision that lives somewhere else**, left behind when the decision moved. A tier, a scope
cut, a dependency bound, an exit code. Nothing in CI sees that class, because each half is
individually valid.

Audit for that. Do not re-derive what a gate already proves.

## Rules that decide every finding

- **`docs/spec/` is normative and wins over every other document.** When a page disagrees
  with the spec, the page is wrong — *unless* the spec disagrees with `src/` or
  `pyproject.toml`, in which case the spec is wrong and it is the most authoritative wrong
  answer in the repo. Say which it is.
- **Never write a security claim to close a finding.** An isolation tier is published only
  with a dated link to the provider's own documentation ([ADR-0006](../../../docs/adr/0006-isolation-tiers-first-class.md)).
  Reuse an existing dated link; never invent a date or a mechanism.
- **Never hand-edit a generated file.** `docs/llms-full.txt` comes from
  `scripts/gen_llms_full.py` (`--check` is a gate) and `docs/errors/` from
  `scripts/gen_error_catalog.py`. Edit the source, then regenerate.
- **A fix arrives with the test that would have caught it**, whenever the check is
  mechanical. Half of what this skill finds is a string comparison; that half belongs in
  `tests/`, not in a future audit.

## The four checks

### 1. Scope — does a page imply something ships that does not?

Source of truth: [ADR-0025](../../../docs/adr/0025-v01-scope-cut.md) and
`[project.optional-dependencies]` in `pyproject.toml`.

Modal is v0.1.1 and the docs must not imply it is available; no shipped backend provides the
`GVISOR` tier. Read every list of backends, every extras list and every install command in
prose, including the ones in comments (`uv sync --all-extras  # core + docker + e2b + ...`)
and in `AGENTS.md`, which seeds future agent-written PRs. An extra named in prose that
`pyproject.toml` does not declare is a failed install for a reader.

### 2. Tier claims — is one stronger than the security model allows, or unsourced?

Source of truth: `docs/explanation/security-model.md`, `docs/explanation/isolation-tiers.md`
and the dated table in `README.md`.

Two failure modes, both real here before:

- A page restates a mechanism ("Firecracker microVM") without the dated link ADR-0006
  requires. This includes the `packages/*/README.md` files, which are **PyPI long
  descriptions** — the widest-read prose the project has.
- A page hands the reader code execution without naming the tier. Hazard H16's tripwire is
  *any* doc or example implying Docker is safe for untrusted code; the disclosed weakness is
  that a Docker sandbox runs as root on a writable rootfs. Wherever a doc shows a model or
  an MCP client running chosen code, the tier belongs next to it.

### 3. Spec versus build — does the normative document match what ships?

Compare `docs/spec/` against `pyproject.toml`, `src/`, `packages/` and
`.github/workflows/`: dependency bounds, extras, error codes, CLI flags and exit codes, the
CI matrix table in `docs/spec/08-adapter-contract.md`, and DSN template names.

A bound in the spec that is looser than `pyproject.toml` is the worst finding available — an
adapter author trusting it installs a version the CHANGELOG records as broken. Mechanical,
so it wants a gate.

### 4. Prose versus `src/` — behavioural claims no test executes

README blocks and `examples/` are CI-executed, so a claim there cannot rot silently. The
how-to and explanation pages are **not**. Read every sentence that states what the code
does — exit codes, defaults, what raises, what a flag means, what is retried — and check it
against `src/`. Weight operator-facing tools (`doctor`, `reap`) highest: someone scripts
against those sentences.

## Do not spend effort here

These came back clean in the 2026-09-26 audit because a machine already guards each one.
Re-checking them is how an audit produces nothing.

| Guarded by | Covers |
|------------|--------|
| `scripts/gen_error_catalog.py --check` | every `SBX_Ennnn` code and its docs page |
| `scripts/check_doc_links.py` | every relative link and anchor |
| `tests/test_readme_examples.py`, `tests/test_examples.py` | every README block and `examples/` program, executed |
| `tests/test_otel.py` | every span attribute string |
| `tests/test_docs_site.py` | every error code resolving at its printed URL |
| `tests/test_release_state.py` | prose claiming the project is unreleased |
| `tests/test_placeholders.py` | unfilled `{{MARKER}}` and `TODO(placeholder)` |

Env var names, the `FakeBackend` surface, timeout semantics and import identity
(`import sandboxio`, never aliased) were also clean; check them only if something nearby
moved.

## Reporting

Rank by what a skeptical reader does with it, not by how many files it touches. The question
is whether someone evaluating the project would use the finding to dismiss it — a security
page that breaks the rule it states outranks twenty stale line numbers.

For each finding give the file and line, the exact text, what it contradicts **with that
file and line too**, and a one-line fix. Do not propose rewrites of whole pages.

If a check comes back clean, say so explicitly. That is a result, and it stops the next run
from re-deriving it.
