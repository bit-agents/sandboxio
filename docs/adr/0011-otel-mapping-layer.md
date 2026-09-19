# ADR-0011 — OTel GenAI semconv isolated behind one mapping module

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0012](0012-no-telemetry-no-import-side-effects.md), [ADR-0005](0005-secure-by-default.md)
**Related:** [ADR-0021](0021-observability-record.md) — the shared operation record

## Context

OpenTelemetry's GenAI semantic conventions are the emerging standard for agent
observability — sandbox operations map naturally to `execute_tool` spans nesting under a
caller's `invoke_agent` span. They are also pre-1.0, were re-homed mid-2026, and attribute
names have changed more than once.

Scattering attribute string literals across adapters means a spec rename becomes a
multi-file, multi-adapter change, and stale names silently produce unqueryable telemetry.

## Decision

- **All semconv attribute strings live in one module**, `sandboxio/otel.py`. No adapter and no
  core module writes a span attribute name directly. A rename is then a one-file change.
- The semconv version we target is **pinned and documented**, and bumping it is a changelog
  entry.
- **Zero-config participation:** if the host application has configured a tracer provider,
  sandboxio emits spans; otherwise it is a no-op. sandboxio never installs an exporter, never starts a
  provider, and never adds an OTel SDK to the base dependency set.
- **Content capture is opt-in**, per the spec's privacy modes. Code and file contents are
  never on spans by default; secrets never, under any setting.
- Spans, audit events and `ExecResult.meter` are three renderings of **one** internal
  operation record, with redaction applied once at close
  ([ADR-0021](0021-observability-record.md)). The span starts when the record opens, so a
  long execution is visible while it runs.

## Consequences

- A pre-1.0 upstream is a standing maintenance cost; the mapping module bounds it to a
  known, small blast radius.
- Users on an older semconv see attribute names they do not expect after a bump. Hence the
  changelog entry and the pinned, documented version.
- The single-record design means adding a field is one change in three renderers rather than
  three independent changes, and makes "secrets never reach any sink" a single testable
  claim.
