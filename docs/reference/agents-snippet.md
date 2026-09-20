# AGENTS.md snippet for projects that use sandboxio

Paste the block below into your repository's `AGENTS.md` (or `CLAUDE.md`, `.cursorrules`,
…). It gives a coding assistant the handful of facts it needs to write correct sandboxio
code without reading this repository.

````markdown
## sandboxio

Sandboxed code execution goes through `sandboxio` (`import sandboxio`, never aliased).

- Create: `async with await sandboxio.create("docker://python:3.12-slim") as sb:`. Sync code
  uses `sandboxio.create_sync(...)` with `with`. `create()` never guesses; `None` means local
  Docker. Other DSNs: `e2b://<template>`, `fake://` (tests).
- Run: `await sb.run(["cmd", "arg"], timeout=60)` → `ExecResult(exit_code, stdout, stderr)`;
  `await sb.run_code("print(1)")`; `async with sb.stream([...]) as proc: async for chunk in proc`.
  Files: `sb.files.read/write/upload/download/ls/mkdir/remove` (paths are sandbox-internal).
- Defaults are security controls: egress denied, 300 s timeout, modest CPU/memory caps.
  Do not loosen them to make something work; bake dependencies into the image or upload a
  wheelhouse. `timeout=None` means "inherit", never "unbounded".
- Secrets go in `secrets={...}`, never `env=` and never in a DSN. They are redacted everywhere.
- Check `Capability.X in sb.capabilities` before a backend-specific call; Docker has no
  `STATEFUL_CODE` and refuses network allowlists; E2B refuses `Resources(cpu/memory_mb)`.
- Errors: catch `sandboxio.SandboxError` (base) or a subclass; every one has `.code`
  (`SBX_E1302`), `.hint` (the fix) and `.url`. `except TimeoutError` does NOT catch sandbox
  timeouts — use `sandboxio.SandboxTimeout`.
- Tests use the `sbx_fake` pytest fixture (installed with the package) or
  `sandboxio.register("docker", lambda: FakeBackend())` so `docker://` resolves to the fake.
  Never require Docker or a provider account in unit tests.
- `sb.native` and `sandboxio.experimental.*` are outside semver; say so when you use them.
- Diagnose the environment with `sandboxio doctor --json`; clean up with `sandboxio reap`.
````

The snippet is kept current with the public API: the doc-sample and README gates in this
repository run against the same surface it describes.
