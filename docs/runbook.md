# Runbook

How to operate the project: develop, verify, release, and respond when something upstream
breaks or someone reports a vulnerability.

Commands below assume `uv` and the decisions from
[Step 0](build-order.md#step-0--lock-the-p0-decisions-½-day). Anything marked *(planned)*
does not exist yet.

---

## Dev setup

One command, and it stays one command — a contributor who cannot get running in five
minutes does not become a contributor.

```bash
uv sync --all-extras          # core + docker + e2b + modal + dev
uv run pytest                 # unit + fake contract suite; no Docker, no network
```

Requirements: **Python 3.14 for development** (floor is 3.11 —
[ADR-0015](adr/0015-python-version-floor.md)), Docker for the Docker contract job, and
provider credentials only for cloud jobs. `uv python install 3.14` if you do not have it;
the floor is proven by CI, not by your local interpreter.

## Daily loop

```bash
uv run pytest -q                        # fast: fake backend only
uv run pytest -m docker                 # Docker contract suite (needs Docker)
uv run ruff check . && uv run ruff format --check .
uv run pyright && uv run mypy src/
uv run python -X importtime -c "import sandboxio" 2>&1 | tail -1    # import budget
```

Before pushing, run what CI runs on PRs: unit + fake + docker contract + lint + types +
import budget.

---

## CI gates

Full matrix in [spec/08](spec/08-adapter-contract.md#ci-matrix). The gates that **block
merge**:

| Gate | Threshold | Why it exists |
|------|-----------|---------------|
| Import budget | <150 ms, hard fail >200 ms | agents cold-start this on every run ([H8](hazards.md#h8--import-bloat-and-eager-imports)) |
| No network at import | zero sockets under `pytest-socket` | offline and air-gapped CI must work |
| Wheel contents | base install pulls no adapter code; extras resolve | supply-chain surface ([H10](hazards.md#h10--a-litellm-class-incident-in-sandboxio-itself)) |
| Types | pyright + mypy strict on public API; `py.typed` in wheel | without `py.typed`, downstream mypy sees `Any` |
| Contract suite | 100% for every declared capability | [ADR-0007](adr/0007-contract-suite-as-spec.md) |
| No leaked containers | zero sandboxio-labelled containers after Docker jobs | [H2](hazards.md#h2--leaked-sandboxes) |
| Error catalog | every code has a page, every page a code | [spec/04](spec/04-errors.md#catalog-is-generated) |
| Doc samples | every YAML/JSON sample in `spec/` parses; every Python sample compiles | the input set shipped a config that was not valid YAML |

A red gate is not overridden. If a gate is wrong, change the gate in its own PR, with a
reason.

---

## Provider churn response

The nightly latest-SDK canary is the early-warning system, and absorbing what it catches is
the core value proposition ([H5](hazards.md#h5--provider-churn-outpaces-maintenance)).

**When the canary goes red:**

1. It auto-opens a `provider-churn` issue. Triage within one working day — silence here is
   the failure mode.
2. Reproduce against the pinned SDK version to confirm it is upstream, not us.
3. Classify:
   - **Breaking API change** → absorb it in the adapter. Users should not need to change
     code. If they must, it is a minor bump with a migration note.
   - **Behaviour change** → check whether the contract suite caught it. If it did not, the
     suite has a gap; add the test in the same PR.
   - **New capability** → `Capability` flag if ≥2 backends have it, otherwise `.native`.
   - **Removed capability** → capability flag goes false for that backend; document it as a
     provider change, not an sandboxio regression.
4. **Write the churn-log entry.** Date, provider, versions affected, what broke, what we
   did, whether users need to act.
5. Release. Churn absorption should ship in days, not at the next milestone.

### Churn-absorption log

A public docs page, maintained per absorbed break. It is the marketing for the core value
prop — the evidence that the abstraction pays for itself — so it is written for users, not
as a changelog dump. Never let it go stale; an empty churn log and a busy one both tell a
story.

---

## Release

1. Green CI on `main`, including nightly cloud contract jobs.
2. `CHANGELOG.md` updated (keep-a-changelog). Note every absorbed provider break.
3. Verify the semver contract: error codes, DSN grammar, protocols, `ExecResult` shape,
   `Capability`/`IsolationTier` members, contract suite
   ([spec/03](spec/03-public-api.md#stability-contract)). `.native` is excluded — changes
   there are not breaking.
4. Deprecations landing in this release carry `DeprecationWarning` with correct
   `stacklevel`, PEP 702 `@deprecated`, a changelog entry, and a stated removal window.
5. Tag; publish via **PyPI Trusted Publishing** with PEP 740 attestations. No token-based
   publishing, no local `twine upload`.
6. Publish the MCP container image; update the Docker MCP Catalog entry.
7. Verify the install path a user actually takes: `uvx sandboxio demo` on a clean machine.

**Never:** publish from a laptop, hard-pin a provider SDK to force a green build, or ship a
release with a skipped contract test.

---

## Security advisories

`SECURITY.md` and this process exist from day one, not from the first report.

1. **Intake** — private report via GitHub Security Advisory. Acknowledge within 48 hours.
2. **Triage** — assess severity, with particular weight on anything in the policy
   enforcement path ([H1](hazards.md#h1--a-security-default-silently-does-not-apply)) or, in
   Phase 2, the server auth path
   ([server hazards](hazards.md#server-mode-hazards-phase-2)).
3. **Fix in private** — draft advisory, fix, and a regression test in the contract suite.
   A security fix without a test is not finished.
4. **Coordinate** — if the root cause is a provider's, coordinate disclosure with them.
5. **Release and disclose** — patch release, published advisory with a CVE where warranted,
   changelog entry. Do not bury it.
6. **Post-incident** — what class of bug was it, and which gate should have caught it? Add
   the gate.

For a policy-enforcement bug specifically: state plainly which control did not apply, from
which version, and what users should check. Users made trust decisions on our word.

---

## Issue triage

Weekly, or as they arrive for anything security-adjacent.

- Issue templates **require** reproduction. No repro, no triage — stated up front, applied
  without debate ([H11](hazards.md#h11--ai-slop-issues-and-prs)).
- Ask for `sandboxio doctor --json` output on any environment report; it is designed to be pasted
  and carries no secrets ([spec/10](spec/10-cli.md#doctor-output-contract)).
- Labels: `provider-churn` (auto from canary), `adapter:<name>`, `security`, `spec-gap`,
  `good-first-issue`.
- A bug that the contract suite should have caught gets a `spec-gap` label and a suite test
  in the fix PR. That loop is what keeps the suite meaningful.
- Q&A goes to GitHub Discussions — searchable and indexed, unlike chat.
- PRs need a DCO `Signed-off-by` line ([ADR-0016](adr/0016-license-mit.md)); there is no CLA.

---

## Quarterly review

The market facts in [`input/02-market-landscape.md`](input/02-market-landscape.md) were a
Q3 2026 snapshot. This space moves monthly; a stale snapshot silently becomes a wrong
strategy.

Every quarter:

- [ ] Re-verify competitor state: ComputeSDK, VibeKit, llm-sandbox, LangChain sandbox
      backends, OpenAI Agents SDK `SandboxConfig`.
- [ ] Re-verify each backend's **isolation tier** against current provider docs; update the
      dated sources ([H4](hazards.md#h4--isolation-claims-we-cannot-defend)).
- [ ] Check every [pre-committed gate](hazards.md#pre-committed-engineering-gates) against
      reality, and write down the answer even when it is "no change".
- [ ] Review [hazards.md](hazards.md): any tripwire fired? any hazard now stale?
- [ ] Review [open-questions.md](open-questions.md): anything DEFERRED whose trigger fired?
- [ ] Check the OTel GenAI semconv version for renames
      ([ADR-0011](adr/0011-otel-mapping-layer.md)).
- [ ] Daytona: isolation tier, SDK state, license state — `UNKNOWN` until proven.
- [ ] Any backend still reporting `UNKNOWN`: can it be verified and promoted this quarter?

The point of pre-committing the thresholds is that this review is mechanical. Do not
renegotiate a threshold during the review in which it fires.
