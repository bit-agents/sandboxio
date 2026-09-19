# ADR-0026 — Documentation under CC BY 4.0; code stays MIT

**Status:** Accepted
**Date:** 2026-09-19
**Amends:** [ADR-0016](0016-license-mit.md)
**Related:** [ADR-0007](0007-contract-suite-as-spec.md), [ADR-0014](0014-project-name.md)

## Context

[ADR-0016](0016-license-mit.md) placed "the `sandboxio` library and everything in this
repository" under MIT. That sentence was written when the repository was expected to be
mostly code. It is currently the opposite: `docs/spec/` is a normative, RFC-2119
specification, and `docs/adr/` is a decision record, both intended to be read, cited and
re-implemented by people writing third-party adapters ([ADR-0007](0007-contract-suite-as-spec.md)
makes the contract suite the adapter spec, and `spec/08` is written as instructions to an
outside implementer).

MIT applied to prose is not wrong, but it is a software license doing a job it was not
drafted for: its operative terms speak of "the Software", and its warranty disclaimer is
noise on a specification. More practically, it gives no clear answer to what a third party
must do when they quote a section of the spec in their own documentation.

The ecosystem convention for exactly this split is permissive code plus CC BY for prose —
Kubernetes, Godot and the Rust book all separate them.

The trap in the split is code samples. `docs/spec/` is full of illustrative signatures that
readers are expected to paste, and a copyleft-adjacent attribution requirement on pasted
snippets would be a hazard rather than a protection.

## Decision

- **Code is MIT**, in `LICENSE`. Unchanged from [ADR-0016](0016-license-mit.md).
- **Prose in `docs/` is CC BY 4.0**, in `LICENSE-DOCS`.
- **Code samples inside `docs/` are MIT**, not CC BY. The boundary is mechanical: anything
  in a fenced code block is code, everything else is prose.
- Package metadata keeps `SPDX: MIT`. The wheel ships no prose from `docs/`, so the
  distribution a user installs is MIT-only and the supply-chain answer stays one word.
- **DCO covers both.** Inbound equals outbound per surface: code contributions in under
  MIT, prose contributions in under CC BY 4.0. Stated in `CONTRIBUTING.md`; still no CLA.
- The Phase-2 `sandboxio-server` license stays open
  ([ADR-0009](0009-library-first-server-later.md)). This ADR does not decide it.

## Consequences

- Every new file raises a boundary question. The fenced-block rule is what keeps that from
  becoming a judgement call, and it is stated in `LICENSE-DOCS` and `CONTRIBUTING.md`.
- A third party can lift the spec into their own docs, or fork it for a competing
  implementation, provided they credit it. That is the intended outcome: a spec nobody may
  quote is not a spec, it is a manual.
- Two license files is a visible complication on a repository this small, and some automated
  license scanners will report the repo as multi-licensed. Accepted — the alternative is a
  specification whose reuse terms are borrowed from a software license.
- Relicensing the docs later needs contributor consent, exactly as for code. Nothing about
  this split is easier to undo than the MIT decision it amends.
- CC BY 4.0 is one-way compatible with CC BY-SA 4.0: downstream may impose share-alike on
  their adaptation, and we cannot pull that adaptation back without their permission.
