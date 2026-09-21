# Why sandboxio and not something else

Three things already solve part of this problem. Each is the right answer sometimes, and this
page says when — including the cases where the answer is "not sandboxio".

## A single provider's SDK

**Use theirs when** you have picked one provider, you are using what makes it distinctive,
and you are not planning to move.

The provider's own SDK is always the shortest path to that provider's best features, and
sandboxio does not try to beat it there. What it does is stop that choice from being
load-bearing:

- **Local and cloud are the same code.** Docker on a laptop, a microVM in production, one
  call site.
- **Distinctive features stay reachable.** `Capability` flags and `.native` keep E2B's rich
  interpreter output, Modal's GPUs or Daytona's LSP available instead of sanded off. This is
  the whole of [ADR-0003](../adr/0003-no-lowest-common-denominator.md), written against
  `apache-libcloud` — a portable API narrowed to the intersection of every provider, whose
  users dropped to the raw SDK the moment they needed anything real.
- **Your tests stop needing an account.** `FakeBackend` records and asserts without a
  network, and passes the same contract suite the real backends do.

The cost is one more dependency between you and the provider, and you can always reach
through it.

## A framework's sandbox layer

LangChain ships sandbox backends; the OpenAI Agents SDK ships `SandboxConfig` with clients
for several providers. Both are good, and **neither is a competitor here** — that is a
decision, not a slogan ([ADR-0013](../adr/0013-complement-openai-sandboxclient.md)).

**Use theirs when** you are inside that framework, intend to stay, and its provider list
covers you. Fewer moving parts wins.

**Use sandboxio when** the sandbox has to outlive the framework choice: a library used from
more than one framework, a service with no framework at all, or a migration where the agent
layer changes and the execution layer should not.

You are not choosing between them. `sandboxio.integrations` returns each framework's **native**
tool object, so sandboxio runs *inside* those ecosystems rather than beside them.

## Docker and `subprocess`, yourself

This is the real alternative for most people, and for a script it is the right one.

It stops being right at the point where the list below becomes yours to maintain. Every item
is something this project already had to get wrong once:

- A timeout that actually **bounds** the work, including a hung stream, and that raises
  something other than the builtin `TimeoutError` so your retry loop can tell them apart.
- **Teardown that survives cancellation.** A `Ctrl-C` during cleanup must not strand a
  container; shielded teardown with a bounded grace is a surprising amount of care.
- **No network unless asked**, and a way to prove it is off rather than assume it.
- **Honest capability reporting**, so a control you set is never quietly ignored — the one
  failure mode that turns a security setting into a lie.
- A **leak check** you trust, because the container you forgot is billed either way.

## When not to use sandboxio

- **You need a real security boundary against hostile code, and you are on Docker.**
  Containers share the host kernel. sandboxio reports `CONTAINER` rather than implying
  otherwise, but reporting a risk does not remove it — read
  [isolation tiers](isolation-tiers.md) and pick `MICROVM`, or do not run that code.
- **One provider, one feature, one script.** The abstraction earns nothing and costs a
  dependency.
- **You are all-in on one agent framework** whose sandbox layer already covers your
  providers.
- **You need it today.** Nothing is released yet.

## What is actually different

Not features — anyone can ship features. These are the things that are *checkable*:

| | How you can check it |
|---|---|
| Adapters cannot lie about capabilities | Every declared flag has a passing [contract-suite](../spec/08-adapter-contract.md) test; every undeclared one must raise |
| Isolation is reported, never assumed | Tiers are dated and sourced to the provider's own documentation, re-verified quarterly ([runbook](../runbook.md)) |
| Deny-by-default is the default | An example in CI proves egress is denied, rather than a sentence saying so |
| Provider churn is absorbed in public | The [churn-absorption log](../churn-log.md), plus a nightly canary and a weekly framework matrix that produced the bounds in `pyproject.toml` |
| Errors are an API | Stable `SBX_E` codes under semver ([ADR-0010](../adr/0010-stable-error-codes.md)) |

## A note on dates

The descriptions of other projects above are deliberately general, because specifics go stale
fastest. The snapshot behind them is from **2026-09-19**
([ADR-0013](../adr/0013-complement-openai-sandboxclient.md)), and re-reading it is a quarterly
item in the [runbook](../runbook.md). If something here is out of date, that is a bug worth an
issue.
