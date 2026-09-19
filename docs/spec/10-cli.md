# 10 — CLI

Typer app. The CLI is the only place allowed to be pretty: `rich` tracebacks, colour and
progress bars are installed at the CLI entry point, never at library import
([ADR-0012](../adr/0012-no-telemetry-no-import-side-effects.md)).

## Commands

| Command | Purpose | Ships |
|---------|---------|-------|
| `sbx doctor` | Per-backend availability, credentials found (**names only**), Docker reachability, versions — with a fix hint per failure. Also programmatic as `sbx.doctor()`. | v0.1 |
| `uvx sbx demo` | Self-contained Docker-backed demo — create sandbox, run code, stream output, teardown — in under 60 s with no account and no config. | v0.1 |
| `sbx replay <trace>` | Deterministic replay of a recorded execution trace; local static HTML viewer. | v0.2 |
| `sbx bench` | Backend comparison: latency, cost where known. | v0.2 |

## Behaviour requirements

- `--json` on **every** command, rendering the same payload as the human output. Not a
  second code path.
- Respect `NO_COLOR`; detect non-TTY and degrade cleanly.
- Examples inside `--help`, not only in the docs.
- Documented exit codes, stable across releases.
- Progress bars for genuinely long operations only: image pull, sandbox boot.
- `doctor` MUST print credential **variable names**, never values, and MUST NOT make a
  provider API call that costs money.
- Shell completions and `sbx upgrade` self-check: v0.2.

## `doctor` output contract

For each backend: installed (yes/no + install command), credentials (which variables are
set, by name), reachability (e.g. Docker daemon responding), SDK version, and the isolation
tier it would provide. Every failure line carries a fix hint
([04](04-errors.md#hint-quality)).

This is the first thing a user runs when something is wrong, and the first thing a
maintainer asks for in a bug report — so its output SHOULD be paste-friendly and MUST be
free of secrets.
