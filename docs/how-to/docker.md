# How to run on Docker

Install the extra, have a Docker daemon running, and `create()` with no arguments — or
`docker://<image>` — gives you a container per sandbox with `network: none`.

```bash
uv add "sandboxio[docker]"
sandboxio doctor          # confirms the daemon is reachable and prints the engine version
```

```python
import sandboxio
from sandboxio_docker import DockerConfig

sb = await sandboxio.create("docker://python:3.12-slim")
sb = await sandboxio.create(DockerConfig(template="ghcr.io/acme/agent-runtime:1.4"))
```

The isolation tier is `CONTAINER`: a shared kernel. Use it for trusted, dev and CI code;
for untrusted multi-tenant code pick a `MICROVM` backend
([isolation tiers](../explanation/isolation-tiers.md)).

## What the adapter does

- One container per sandbox, `docker exec` per operation, working directory `/work`.
  A relative path means the same file to `files.read`/`write` and to `run` — both resolve
  under `/work`.
- `network_mode: none` by default. `NetworkPolicy(egress="allow")` gives the bridge network.
  **Allowlists are refused** with `CapabilityNotSupported`: Docker has no per-host egress
  filtering, and granting bridge access because an allowlist was requested would be a
  security control that appears to apply and does not
  ([ADR-0023](../adr/0023-docker-network-and-dependencies.md)). Allowlists are an E2B capability.
- CPU and memory caps apply on every sandbox (1 CPU, 512 MB unless you raise them), and
  swap is capped with memory so the limit is the limit.
  `Resources(disk_mb=...)` is refused rather than ignored — Docker cannot enforce it.
- Every container drops all capabilities, runs with `no-new-privileges` and a 512-process
  ceiling ([ADR-0028](../adr/0028-docker-container-hardening.md)). It still runs **as root
  on a writable rootfs** ([H16](../hazards.md#h16--docker-sandboxes-run-as-root-on-a-writable-rootfs)):
  `CONTAINER` is for trusted, dev and CI code, not for untrusted multi-tenant code — use
  E2B for that. An image needing a dropped capability back is a
  `.native` case.
- The container's PID 1 is `sleep <timeout>`: the provider-side lifetime backstop. When it
  fires, Docker leaves the container **stopped**; `sandboxio reap` removes it.
- A call timeout or a cancellation kills **every** process in the container (Docker cannot
  signal one `exec`); the filesystem survives.
- `run_code(context_id=...)` raises: Docker declares `STATEFUL_CODE` off in v0.1
  ([ADR-0024](../adr/0024-stateful-code-on-docker.md)).
- The filesystem port relies on `find`, `mkdir` and `rm` in the image, as in `python:*-slim`.

## Getting dependencies into a deny-egress sandbox

The sandbox cannot `pip install` from the internet, by design. Two patterns work under the
default policy; neither weakens it.

### Pattern 1 — bake them into the image (primary)

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir pandas==2.2.3 numpy==2.1.3
WORKDIR /work
```

```bash
docker build -t agent-runtime:1 .
```

```python
import sandboxio

async with await sandboxio.create("docker://agent-runtime:1") as sb:
    print((await sb.run_code("import pandas; print(pandas.__version__)")).stdout)
```

### Pattern 2 — ship an offline wheelhouse

Download the wheels on the host, upload them, install with no index. This needs no network
inside the sandbox at all.

```bash
pip download --dest wheels --only-binary=:all: --platform manylinux2014_x86_64 \
  --python-version 3.12 pandas==2.2.3
```

```python
from pathlib import Path

import sandboxio

async with await sandboxio.create("docker://python:3.12-slim", timeout=600) as sb:
    await sb.files.mkdir("/work/wheels", parents=True)
    for wheel in Path("wheels").glob("*.whl"):
        await sb.files.upload(wheel, f"/work/wheels/{wheel.name}")
    res = await sb.run(
        ["python", "-m", "pip", "install", "--no-index", "--find-links", "/work/wheels", "pandas"],
        timeout=300,
    )
    res.raise_for_status()
```

Match the wheel platform to the image (`manylinux2014_x86_64` for `python:3.12-slim` on
x86-64; `manylinux2014_aarch64` on Apple Silicon and Graviton). If the image has `uv`,
`uv pip install --offline --find-links /work/wheels pandas` does the same.

A mutable "install with egress, then lock down" window is deliberately not offered: the
policy in effect would then vary over the sandbox's life, and the audit record could not
say which policy an operation ran under.

## Leaked containers and the reaper

Every container carries `io.sandboxio.managed=true`, `io.sandboxio.session=<process id>`,
`io.sandboxio.timeout=<seconds>` and one `io.sandboxio.meta.<key>` label per `metadata`
entry. A Ryuk-style sidecar (one per process, image `testcontainers/ryuk`) removes the
session's containers if the process dies without teardown. `SBX_DOCKER_REAPER=0` disables
it, for hosts that forbid privileged containers.

Whatever survives — a crashed process with the reaper disabled, a lifetime-expired
container left stopped — is visible to:

```bash
sandboxio reap                          # lists, running and stopped
sandboxio reap --label tenant_id=acme   # narrows by your metadata
sandboxio reap --kill                   # removes
```

## Configuring the backend object

`AuditConfig`, the default image and the interpreter name live on the backend instance.
Construct it yourself and either use it directly or register it under the `docker` name so
DSNs pick it up:

```python
import sandboxio
from sandboxio.audit import AuditConfig, LoggingSink
from sandboxio_docker import DockerBackend

backend = DockerBackend(image="agent-runtime:1", audit=AuditConfig(sinks=(LoggingSink(),)))
sandboxio.register("docker", lambda: backend)

sb = await sandboxio.create()   # now uses `backend`
```
