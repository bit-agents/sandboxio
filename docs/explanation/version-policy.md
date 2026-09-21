# Version policy

[spec/03](../spec/03-public-api.md#stability-contract) names the surface semver covers. This
page says what that means in practice: what counts as a break, how long a deprecation lives,
and why the answer sometimes differs depending on whether you *call* sandboxio or *implement*
a backend for it.

## What the number promises today

sandboxio is `0.x`. Until `1.0`:

- **A patch release never breaks the covered surface.**
- **A minor release may**, and every such break gets a changelog entry and a migration note.

That is the ordinary `0.x` bargain, and it is the honest one while adapters are still being
written against the contract. After `1.0` the usual rule applies: breaks land in a major.

## Two audiences, one version number

Most libraries have callers. This one also has **adapter authors**, and the same change can
be additive for one and breaking for the other. The verdict below is always the stricter of
the two, because the version number cannot say "breaking, but only for some of you".

| Change | Callers | Adapter authors |
|--------|---------|-----------------|
| New error code | additive | additive |
| Renaming or repurposing an error code ([ADR-0010](../adr/0010-stable-error-codes.md)) | **breaking** | **breaking** |
| New DSN scheme or parameter ([spec/07](../spec/07-configuration.md)) | additive | additive |
| Changing what an existing DSN parameter means | **breaking** | **breaking** |
| New `Capability` or `IsolationTier` member | additive | additive |
| Removing or renaming one | **breaking** | **breaking** |
| New method on a port protocol | additive | **breaking** — every adapter must grow it |
| Changing a port method's signature | **breaking** | **breaking** |
| New required test in the contract suite ([ADR-0007](../adr/0007-contract-suite-as-spec.md)) | additive | **breaking** — a passing adapter can start failing |
| A backend's reported `IsolationTier` changes ([ADR-0006](../adr/0006-isolation-tiers-first-class.md)) | **breaking** | **breaking** |
| A default becoming stricter | **breaking** | **breaking** |

The last two are the ones people are surprised by.

A **reported isolation tier is public data**, not an implementation detail: code branches on
it, and `require_isolation=` refuses to provision below it. Correcting a tier downward can
stop a program that used to run — which is the point, but it is still a break.

A **stricter default breaks behaviour without breaking any signature**. Everything still
type-checks and the call still compiles; it just refuses work it used to accept. Tightening
security defaults is not exempt: it ships in a minor before `1.0`, in a major after, always
with the changelog entry saying what now gets refused.

## How the spec versions

[`docs/spec/`](../spec/README.md) ships with the package and versions with it; there is no
separate spec version to track. A spec edit is breaking when it turns something an adapter
was allowed to do into something it MUST NOT, or adds a MUST it did not carry. Clarifying
wording that changes no requirement is not a break, and says so in its changelog entry.

Where the spec is silent or marked `OPEN (Qn)`, nothing is promised yet. Building on an open
question is building on sand — ask, and the answer becomes normative.

## Deprecations

A symbol on its way out carries all four of these, not whichever is convenient:

1. `DeprecationWarning` with a correct `stacklevel`, so the warning points at *your* line.
2. PEP 702 `@typing_extensions.deprecated`, so the type-checker says it before runtime does.
3. A changelog entry naming the replacement.
4. A window of **at least one minor release and at least 90 days**, whichever ends later.

Removal happens only in a release that is allowed to break. Warnings alone do not reach
people — most CI hides them — which is why the type-checker annotation is the half that
actually works.

## `.native` is outside the contract

`.native` hands you the provider's own object, and the provider's surface is not ours to
promise. Concretely: **anything reached through `.native` can change in a patch release**,
because it changes when the provider ships, not when we do.

What is still promised is that `.native` exists and returns the underlying object. Reaching
through it is opting out of semver deliberately, and
[ADR-0003](../adr/0003-no-lowest-common-denominator.md) is why that escape hatch exists
rather than sanding the feature off.

## An upstream break is not our breaking change

When a provider ships an incompatible SDK, absorbing it is the job — see the
[churn-absorption log](../churn-log.md). The default outcome is a patch release in which your
code does not change.

If a provider break genuinely cannot be absorbed, it becomes a minor with a migration note
and a churn-log entry saying so plainly. "The provider changed it" is an explanation, never
an excuse for a silent break.

## Security releases and yanking

A security fix lands in a patch on the current minor, with an advisory
([SECURITY.md](https://github.com/bit-agents/sandboxio/blob/main/SECURITY.md)). A release is
yanked only when installing it is actively harmful — a broken build, a leaked credential, a
declared control that does not apply. A yank hides a version from resolution; it never
deletes it, and PyPI filenames are never reused.
