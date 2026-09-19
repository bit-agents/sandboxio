# ADR-0011 — OTel GenAI semconv isolated behind one mapping module

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0012](0012-no-telemetry-no-import-side-effects.md), [ADR-0005](0005-secure-by-default.md)
**Open questions:** [Q9 audit / OTel / meter overlap](../open-questions.md#q9--one-event-three-sinks-audit--otel--meter)

## Context

OpenTelemetry's GenAI semantic conventions are the emerging standard for agent
observability — sandbox operations map naturally to `execute_tool` spans nesting under a
caller's `invoke_agent` span. They are also pre-1.0, were re-homed mid-2026, and attribute
names have changed more than once.

Scattering attribute string literals across adapters means a spec rename becomes a
multi-file, multi-adapter change, and stale names silently produce unqueryable telemetry.

## Decision

- **All semconv attribute strings live in one module**, `sbx/otel.py`. No adapter and no
  core module writes a span attribute name directly. A rename is then a one-file change.
- The semconv version we target is **pinned and documented**, and bumping it is a changelog
  entry.
- **Zero-config participation:** if the host application has configured a tracer provider,
  sbx emits spans; otherwise it is a no-op. sbx never installs an exporter, never starts a
  provider, and never adds an OTel SDK to the base dependency set.
- **Content capture is opt-in**, per the spec's privacy modes. Code and file contents are
  never on spans by default; secrets never, under any setting.
- Spans, audit events and `ExecResult.meter` are three renderings of **one** internal
  operation record, with redaction applied once upstream
  ([Q9](../open-questions.md#q9--one-event-three-sinks-audit--otel--meter)).

## Consequences

- A pre-1.0 upstream is a standing maintenance cost; the mapping module bounds it to a
  known, small blast radius.
- Users on an older semconv see attribute names they do not expect after a bump. Hence the
  changelog entry and the pinned, documented version.
- The single-record design means adding a field is one change in three renderers rather than
  three independent changes, and makes "secrets never reach any sink" a single testable
  claim.
