# How to run on E2B

E2B runs each sandbox in a Firecracker microVM with a live code interpreter. It is the
`MICROVM` tier and the backend to pick for untrusted, multi-tenant code
([isolation tiers](../explanation/isolation-tiers.md)).

## API key

```bash
uv add "sandboxio[e2b]"
export E2B_API_KEY=e2b_...        # from the E2B dashboard; use a key scoped to one team
sandboxio doctor                  # shows "E2B_API_KEY set" — never the value
```

The key is read from the environment when a sandbox is created, never from a DSN and never
from a dotfile. A missing key raises `AuthError` (`SBX_E1501`) naming `E2B_API_KEY`. Keep
keys short-lived and least-privilege; sandboxio never persists them and redacts them from
every log, exception, repr, audit event and span.

```python
import sandboxio
from sandboxio_e2b import E2BConfig

sb = await sandboxio.create("e2b://")                          # default template
sb = await sandboxio.create("e2b://code-interpreter-v1?timeout=600")
sb = await sandboxio.create(E2BConfig(template="my-team-template"))
```

## Network allowlists

E2B is the backend where `NetworkPolicy(allow=...)` is a real control: it maps to the
provider's native deny-all-then-allow rules at create time.

```python
import sandboxio
from sandboxio import NetworkPolicy

async with await sandboxio.create(
    "e2b://", network=NetworkPolicy(allow=("api.openai.com", "pypi.org", "files.pythonhosted.org"))
) as sb:
    res = await sb.run(["pip", "install", "-q", "httpx"], timeout=120)
```

`egress="deny"` (the default) blocks everything; `egress="allow"` opens everything. Hosts
and CIDRs are both accepted. The policy is fixed for the sandbox's life.

## Stateful code contexts and rich outputs

E2B declares `STATEFUL_CODE`: pass any `context_id` string and the adapter keeps one live
interpreter per id, so variables survive between calls. A timeout or cancellation restarts
that context — the only way to stop a running cell — and the next call starts clean.

```python
import sandboxio

async with await sandboxio.create("e2b://") as sb:
    await sb.run_code("import pandas as pd; df = pd.DataFrame({'a': [1, 2, 3]})", context_id="s1")
    res = await sb.run_code("df.describe()", context_id="s1")
    for output in res.results or ():
        print(output.mime_type, output.data[:80])      # text/plain, text/html, image/png (base64)
```

`ExecResult.results` carries the interpreter's display outputs as `RichOutput(mime_type,
data)` in Jupyter's format; binary payloads are base64 text.

## Resources come from the template

CPU, memory and disk are properties of an E2B template, so `Resources(cpu=..., memory_mb=...)`
is **refused** with `ConfigurationError` instead of being silently ignored. Build a template
with the resources you need and name it in the DSN or `E2BConfig`.

## Labels and reaping

`metadata` becomes sandbox metadata on E2B, plus `sandboxio_managed=true` and
`sandboxio_session=<process id>`. `sandboxio reap --backend e2b` lists every running or
paused sandbox carrying the managed flag; `--kill` ends them. `connect()` refuses a sandbox
that does not carry the flag.

## Behind `.native`

PTY, pause/resume, snapshots and the SDK's own methods are reachable as `sb.native`, the
SDK's `AsyncSandbox`. Everything reached through `.native` is outside the semver contract:
it changes when E2B changes it.
