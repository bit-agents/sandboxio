# ADR-0008 — Dual configuration: DSN strings and typed config objects

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0010](0010-stable-error-codes.md)

## Context

Two audiences with opposed needs. The five-minute evaluation and the "swap one line" demo
want a string: `sandboxio.create("e2b://code-interpreter")`. Production wants typed, reviewable,
autocompleting configuration with no stringly-typed policy hidden in a URL.

Prior art: SQLAlchemy and fsspec both carry a URL form alongside a structured form, and both
survive on it.

## Decision

Both, with a clear division:

- **DSN strings** for quick swaps and demos: `docker://python:3.12-slim`,
  `e2b://code-interpreter?timeout=600`, `fake://`. The grammar is public API under semver.
- **Typed config objects** for production: `sandboxio.create(E2BConfig(template=...,
  network=NetworkPolicy(allow=("api.openai.com",))))`.
- **Credentials never appear in a DSN.** They come from per-provider environment variables
  by that provider's own convention (`E2B_API_KEY`, …). sandboxio never persists credentials and
  never logs them.
- DSN query parameters are limited to simple scalars. Anything structured — network
  allowlists, resource shapes, secrets — is object-only. A DSN must not be able to express a
  security policy ambiguously.
- An unknown scheme raises `BackendNotFound` listing installed backends, and, for a
  known-but-missing backend, the exact install command.

## Consequences

- Two parse paths to keep in sync; the DSN parser is a thin front end that constructs the
  same typed objects, never a second code path.
- DSN grammar under semver means adding a scheme is fine, changing the meaning of an existing
  query parameter is breaking.
- Users will try to put API keys in DSNs. The parser should detect obvious credential-looking
  parameters and raise a `ConfigurationError` that explains the env-var convention, rather
  than silently accepting them into logs.
