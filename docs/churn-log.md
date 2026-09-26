# Churn-absorption log

Every provider break this library absorbed on your behalf, newest first.

The point of a sandbox abstraction is that a provider's breaking change costs you a version
bump instead of a migration. That claim is only worth as much as its evidence, so each
absorbed break is written down here — including the ones that were not absorbed cleanly.

Each entry records the date, the provider and the versions affected, what broke, what
changed here, and whether you need to act. An entry lands in the same release as the fix,
and in [`CHANGELOG.md`](https://github.com/bit-agents/sandboxio/blob/main/CHANGELOG.md) as well. The procedure is
[*Provider churn* in the runbook](runbook.md).

## Entries

*None yet — no provider break absorbed since 0.1.0.*

An empty log and a busy one tell different stories, and both are honest. This one is empty
because there is nothing to report, not because nothing is being watched: the nightly
latest-SDK canary runs every provider SDK unpinned, and the weekly framework matrix runs each
integration at its oldest supported version and at the newest release.
