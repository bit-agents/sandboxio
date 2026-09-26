# sandboxio-docker

The Docker adapter for [sandboxio](../../README.md). Install it as the extra:

```bash
uv pip install "sandboxio[docker]"
```

Isolation tier: `CONTAINER` — [a container shares the host kernel](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/),
Docker's own description, read on **2026-09-20**; that page carries no revision date of its
own, so that is the date it was read
([ADR-0006](../../docs/adr/0006-isolation-tiers-first-class.md)). Use it for trusted, dev
and CI code. `MICROVM` — `sandboxio[e2b]` — is the documented floor for untrusted,
multi-tenant code.

Sandboxes run **as root on a writable rootfs**. Every container drops all capabilities and
runs with `no-new-privileges` and a 512-process ceiling
([ADR-0028](../../docs/adr/0028-docker-container-hardening.md)), but neither a non-root
`user` nor `read_only=True` is set, because both break ordinary images. That is an accepted
gap, not an oversight
([H16](../../docs/hazards.md#h16--docker-sandboxes-run-as-root-on-a-writable-rootfs)).

Egress is denied by default (`network_mode: none`); allowlists are not supported on Docker
and raise `CapabilityNotSupported`
([ADR-0023](../../docs/adr/0023-docker-network-and-dependencies.md)).
`run_code(context_id=...)` raises: Docker declares `STATEFUL_CODE` off in v0.1
([ADR-0024](../../docs/adr/0024-stateful-code-on-docker.md)).

A timeout or cancellation kills **every** process in the sandbox (Docker cannot signal one
`exec`); the filesystem survives. The filesystem port relies on `find`, `mkdir` and `rm`
being present in the image, as they are in `python:*-slim`.
