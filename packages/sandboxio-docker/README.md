# sandboxio-docker

The Docker adapter for [sandboxio](../../README.md). Install it as the extra:

```bash
uv pip install "sandboxio[docker]"
```

Isolation tier: `CONTAINER` — a shared kernel, for trusted, dev and CI code only. Egress is
denied by default (`network_mode: none`); allowlists are not supported on Docker and raise
`CapabilityNotSupported` ([ADR-0023](../../docs/adr/0023-docker-network-and-dependencies.md)).
`run_code(context_id=...)` raises: Docker declares `STATEFUL_CODE` off in v0.1
([ADR-0024](../../docs/adr/0024-stateful-code-on-docker.md)).

A timeout or cancellation kills **every** process in the sandbox (Docker cannot signal one
`exec`); the filesystem survives. The filesystem port relies on `find`, `mkdir` and `rm`
being present in the image, as they are in `python:*-slim`.
