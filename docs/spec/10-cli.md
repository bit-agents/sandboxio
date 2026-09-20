# 10 — CLI

Stdlib `argparse`, in core, at `sandboxio.cli`. `uvx sandboxio demo` MUST work from the bare
distribution, and core takes no dependency beyond `anyio` + `typing-extensions`
([ADR-0004](../adr/0004-thin-core-lazy-adapters.md)), so a CLI framework is out. The CLI is
the only place allowed to be pretty: `rich` tracebacks are installed at the CLI entry point
when `rich` is importable and `SBX_DEBUG=1`, never at library import
([ADR-0012](../adr/0012-no-telemetry-no-import-side-effects.md)). Colour is plain ANSI,
only on a TTY, and `NO_COLOR` wins.

## Commands

| Command | Purpose | Ships |
|---------|---------|-------|
| `sandboxio doctor` | Per-backend availability, credentials found (**names only**), Docker reachability, versions — with a fix hint per failure. Also programmatic as `sandboxio.doctor()`. | v0.1 |
| `uvx sandboxio demo` | Self-contained Docker-backed demo — create sandbox, run code, stream output, teardown — with no account and no config. Runs stdlib-only code under the default deny-egress policy. The **under-60 s** budget is measured **warm**: a first run also pulls ~130 MB of image, which is host-side and unaffected by the sandbox's network policy. | v0.1 |
| `sandboxio reap` | List and kill orphaned sandboxes by `metadata` label — the operator-facing backstop when shielded teardown could not finish ([ADR-0020](../adr/0020-cancellation-semantics.md)). Dry-run by default; `--kill` to act. | v0.1 |
| `sandboxio replay <trace>` | Deterministic replay of a recorded execution trace; local static HTML viewer. | v0.2 |
| `sandboxio bench` | Backend comparison: latency. | v0.2 |
| `sandboxio costs` | Post-hoc cost attribution by `metadata` label, e.g. `--since 2026-09-01 --label tenant_id=acme`. Requires `Capability.COST_REPORTING`; reports the provider's own resolution rather than interpolating ([06](06-observability.md#cost-reconciliation-capability-gated-v02)). | v0.2 |

The primary console script is `sandboxio`. A short `sbx` alias script is installed as a
convenience, but **copy-paste examples always use the full name** — `uvx` resolves by
distribution name, and the three-letter name belongs to an unrelated PyPI package
([ADR-0014](../adr/0014-project-name.md)).

## Behaviour requirements

- `--json` on **every** command, rendering the same payload as the human output. Not a
  second code path.
- Respect `NO_COLOR`; detect non-TTY and degrade cleanly.
- Examples inside `--help`, not only in the docs.
- Documented exit codes, stable across releases: `0` success · `1` a problem was found or
  the command failed (`doctor`: an installed backend has a failing check; `reap --kill`: a
  kill failed; `demo`: a step failed, including the egress probe reaching the network) ·
  `2` usage error · `130` interrupted. A dry-run `reap` that lists sandboxes exits `0`.
- Progress bars for genuinely long operations only: image pull, sandbox boot.
- `doctor` MUST print credential **variable names**, never values, and MUST NOT make a
  provider API call that costs money.
- `reap` MUST default to listing only. Killing requires an explicit flag, because the tool
  operates on live infrastructure and a label filter can be wrong.
- Shell completions and `sandboxio upgrade` self-check: v0.2.

## `doctor` output contract

For each backend: installed (yes/no + install command), credentials (which variables are
set, by name), reachability (e.g. Docker daemon responding), SDK version, and the isolation
tier it would provide. Every failure line carries a fix hint
([04](04-errors.md#hint-quality)).

This is the first thing a user runs when something is wrong, and the first thing a
maintainer asks for in a bug report — so its output SHOULD be paste-friendly and MUST be
free of secrets.

## `reap` contract

`reap` asks each backend for the sandboxes it labelled through the optional
[`ReapableBackend`](02-ports.md#reapablebackend-optional) port. Docker MUST list **every**
`io.sandboxio.managed` container, running or stopped — a lifetime-expired container is left
stopped by Docker, and `reap` is its cleanup path. E2B lists every running or paused sandbox
with `sandboxio_managed=true`. `--label key=value` narrows by `metadata`; `--backend` narrows
by backend and defaults to `docker` and `e2b`, reporting *not installed* rather than failing
for a missing extra.

## `demo` contract

Five steps, each timed and reported: create · `run_code` · stream · egress probe · teardown.
The egress probe MUST attempt a real connection from inside the sandbox and MUST fail the
demo if it succeeds — a demo that shows deny-by-default not applying is a bug report, not a
pass ([H1](../hazards.md#h1--a-security-default-silently-does-not-apply)). Without the Docker
extra the demo prints the exact install command from `BackendNotInstalled` and exits `1`.
