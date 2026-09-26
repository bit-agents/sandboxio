# sandboxio-e2b

The E2B adapter for [sandboxio](../../README.md). Install it as the extra:

```bash
uv pip install "sandboxio[e2b]"
export E2B_API_KEY=...
```

Isolation tier: `MICROVM` — [a Firecracker microVM with its own kernel](https://e2b.dev/security),
E2B's own description, read on **2026-09-20**; that page carries no revision date of its
own, so that is the date it was read
([ADR-0006](../../docs/adr/0006-isolation-tiers-first-class.md)). It is the documented floor
for untrusted, multi-tenant code.

Egress is denied by default
(`allow_internet_access=False`); `NetworkPolicy(allow=...)` maps to E2B's native allowlist.
`STATEFUL_CODE` is declared: `run_code(context_id=...)` keeps a live interpreter per
context, and rich outputs arrive in `ExecResult.results`.

CPU and memory come from the template, so `Resources(cpu=..., memory_mb=...)` is refused
rather than silently ignored — pick a template with the resources you need. PTY,
pause/resume, snapshots and forks are reachable through `.native` (the SDK's
`AsyncSandbox`) and are outside the semver contract.

A `list[str]` command is `shlex`-quoted into E2B's bash, so nothing is expanded or split.
