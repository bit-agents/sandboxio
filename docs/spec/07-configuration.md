# 07 — Configuration

See [ADR-0008](../adr/0008-dsn-and-typed-config.md).

## DSN grammar

```
<backend>://[<template>][?<param>=<value>&…]
```

Examples: `docker://python:3.12-slim`, `e2b://code-interpreter?timeout=600`,
`modal://base?gpu=T4`, `fake://`.

Rules:

- The grammar is **public API under semver**. Adding a scheme or parameter is additive;
  changing the meaning of an existing parameter is breaking.
- Query parameters are **simple scalars only**. Anything structured — network allowlists,
  resource shapes, secrets, metadata — is typed-object-only. A DSN MUST NOT be able to
  express a security policy ambiguously.
- An unknown scheme raises `BackendNotFound` listing installed backends, plus the install
  command for a known-but-missing one.
- An unknown parameter MUST raise `ConfigurationError`, never be ignored.
- The DSN parser is a **front end that constructs the same typed objects**, never a second
  configuration code path.

## Typed configuration

```python
sandboxio.create(E2BConfig(
    template="code-interpreter",
    network=NetworkPolicy(allow=("api.openai.com",)),
    resources=Resources(memory_mb=2048),
))
```

Production usage SHOULD prefer typed config: reviewable, autocompleting, no stringly-typed
policy.

## Credentials

- Credentials come from **per-provider environment variables** by that provider's own
  convention (`E2B_API_KEY`, `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET`, …).
- Credentials MUST NOT appear in a DSN. The parser SHOULD detect credential-looking
  parameters and raise `ConfigurationError` naming the correct env var.
- sandboxio MUST NOT persist credentials, and MUST NOT log them even at debug verbosity.
- A missing credential MUST raise `AuthError` naming the exact variable
  ([04](04-errors.md#hint-quality)).

## Backend resolution

1. Explicit `sandboxio.register(name, "pkg:Class")` registrations.
2. Entry points in group `sandboxio.backends`, read lazily via `importlib.metadata`.
3. Nothing found → `BackendNotFound` / `BackendNotInstalled`.

Resolution MUST be lazy and cached. Entry-point scanning counts against the import budget
([ADR-0004](../adr/0004-thin-core-lazy-adapters.md)).

## Routing file

Designed now, loadable by the **library** before any server exists
([ADR-0009](../adr/0009-library-first-server-later.md)). Mental model: Kubernetes
`RuntimeClass` for isolation classes, LiteLLM `config.yaml` for the policy surface.

```yaml
# sandboxio-routing.yaml
backends:
  docker-local: { adapter: docker, image: "python:3.12-slim" }
  e2b-fast:     { adapter: e2b, template: code-interpreter, api_key: os.environ/E2B_API_KEY }
  modal-gpu:    { adapter: modal, gpu: T4, api_key: os.environ/MODAL_TOKEN }

isolation_classes:            # cf. Kubernetes RuntimeClass
  standard:  { backend: docker-local }    # trusted / dev
  sandboxed: { backend: modal-gpu }       # gVisor tier
  isolated:  { backend: e2b-fast }        # microVM tier — untrusted multi-tenant

routes:                       # first match wins
  - match: { tool: run_python }
    class: isolated
  - match: { tool: data_transform }
    class: sandboxed
  - match: { tenant_tier: enterprise }
    class: isolated

default_class: standard       # mandatory

policy:
  network: { egress: deny }
  limits:  { timeout_s: 300, memory_mb: 1024 }
  spend:   { per_tenant_daily_usd: 50 }    # server-mode only
```

Rules:

- Secrets **only** as `os.environ/NAME` references. A literal secret in this file MUST be a
  load-time error, not a warning.
- First-match routing. `default_class` is a **top-level, mandatory** key — a config without
  it MUST fail to load. It is deliberately not a pseudo-route in the `routes` list: a
  default is not a match rule, and encoding it as one made the list heterogeneous.
- Every route entry has exactly the keys `match` and `class`. An unknown key MUST be a
  load-time error.
- The example above is **parse-tested in CI**. The input-set version of this config was not
  valid YAML at all ([readme errata](../readme.md#known-errors-in-input)); every config
  sample in this spec MUST be machine-verified, not eyeballed.
- Library use: `sandboxio.create(route_for(tool="run_python", tenant_tier="enterprise"))`.
- Which backend or isolation class a tool or tenant gets MUST be a YAML change, never a code
  change.
- `spend` is meaningful only in server mode; the library MUST reject it with a clear message
  rather than ignoring it.
