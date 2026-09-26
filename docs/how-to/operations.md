# How to operate sandboxio

The `sandboxio` command ships with the base package (`sbx` is a local alias; copy-paste
examples always use the full name, because `uvx` resolves by distribution name).

## `sandboxio doctor`

The first thing to run when something is wrong, and what a bug report asks for.

```bash
sandboxio doctor
sandboxio doctor --json
```

Per backend: installed (with the install command if not), package versions, credential
variables by **name** with set/unset, reachability (Docker: a local daemon ping; E2B: not
probed, because that would be an API call), and the isolation tier it would provide. Every
failing line carries a fix. The same report is available in Python as
`sandboxio.doctor()`, returning a frozen `DoctorReport` with `as_dict()`.

Exit `0` when every installed backend is healthy, `1` otherwise.

## `sandboxio reap`

The operator-facing backstop for sandboxes that outlived their process: a crash with the
reaper disabled, a teardown that exceeded its grace and warned, a Docker container left
stopped when its lifetime ended.

```bash
sandboxio reap                              # dry run: docker and e2b, every managed sandbox
sandboxio reap --backend docker             # one backend
sandboxio reap --label tenant_id=acme       # narrowed by your metadata
sandboxio reap --kill                       # remove what is listed
sandboxio reap --json
```

Listing is the default because the tool operates on live infrastructure and a label filter
can be wrong. A backend whose extra is not installed is reported as *not installed*, not an
error. Exit `1` when a backend could not be listed — even on a dry run, because the orphan
list is then incomplete — and, with `--kill`, when a kill failed. A dry run that listed
every requested backend exits `0`, however many sandboxes it found
([spec/10](../spec/10-cli.md#behaviour-requirements)).

## `sandboxio demo`

`uvx sandboxio demo` is the zero-config proof that the install works; `--backend fake://`
runs the same five steps in-process. See the [quickstart](../quickstart.md).

## Environment variables

All `SBX_`-prefixed. Provider credentials use the provider's own names (`E2B_API_KEY`).

| Variable | Effect | Default |
|----------|--------|---------|
| `SBX_DEBUG` | `1` shows full tracebacks in the CLI | off |
| `SBX_TEARDOWN_GRACE` | seconds a kill may take before `OrphanedSandboxWarning` | `5` |
| `SBX_AUDIT_TIMEOUT` | seconds an audit sink's `emit` may take | `5` |
| `SBX_DOCKER_REAPER` | `0` disables the Docker reaper sidecar | on |
| `SBX_DOCKER_THREADS` | worker threads the Docker adapter may hold; each live stream parks one ([ADR-0027](../adr/0027-adapter-thread-budget.md)) | `64` |
| `NO_COLOR` | disables colour in the CLI | — |

Nothing else changes behaviour from the environment, and nothing is read from a dotfile.

## Exit codes

`0` success · `1` a problem was found or the command failed · `2` usage error · `130`
interrupted. Stable across releases ([spec/10](../spec/10-cli.md)).
