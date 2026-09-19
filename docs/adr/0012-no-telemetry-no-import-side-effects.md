# ADR-0012 — No telemetry, no import side effects

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0004](0004-thin-core-lazy-adapters.md), [ADR-0011](0011-otel-mapping-layer.md)

## Context

sbx sits in the path of untrusted code execution for teams whose dependency review is a
gate. Every behaviour that is surprising at import time — a network call, a mutated global,
a configured logger, a printed banner — is both a review finding and a real failure mode in
sandboxed, offline and air-gapped CI.

Opt-out telemetry has produced sustained backlash for Next.js, Homebrew and Scarf. For a
security library the calculus is worse: phoning home from the component that runs untrusted
code is disqualifying in exactly the accounts we are targeting.

## Decision

Hard bans, enforced in CI where mechanically possible:

- **No telemetry.** None by default and none opt-out. If usage data is ever collected it is
  opt-in, loudly documented, and gets its own ADR.
- **No network at import**, verified with sockets blocked in CI.
- **No import side effects:** no global mutable state, no logging configuration, no
  `rich` traceback installation, no provider SDK import. `rich` tracebacks are installed in
  the CLI entry point only.
- **The library never prints.** The library logger uses `NullHandler` and is quiet unless
  the host application asks. `SBX_DEBUG=1` or `debug=True` raises verbosity; nothing else
  does.
- **Import budget under 150 ms**, hard fail over 200 ms.

## Consequences

- We will not know how many people use which backend, and we accept that. Signal comes from
  issues, discussions and stars.
- Debugging is worse without a default handler. The answer is high-quality `__repr__`s, a
  `doctor` command and an explicit debug switch — not ambient logging.
- CI gates must exist from commit one; retrofitting an import budget after an accidental
  eager import has spread is far more expensive than starting with it red.
