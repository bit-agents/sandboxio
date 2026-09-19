# 04 — Errors

Errors are a product surface for two audiences: humans who want the fix, and coding
assistants that need a stable token. See [ADR-0010](../adr/0010-stable-error-codes.md).

## Tree

```
SandboxError                    base; carries .code, .hint, .url
├── ConfigurationError          SBX_E10xx
│   ├── BackendNotFound         SBX_E1001   hint: installed backends + install command
│   └── BackendNotInstalled     SBX_E1002   hint: uv pip install "sandboxio[e2b]"
├── CapabilityNotSupported      SBX_E1101   hint: which backends do support it
├── CreationError               SBX_E1201
├── ConnectError                SBX_E1202
├── ExecutionError              SBX_E1301   non-zero exit via raise_for_status()
├── SandboxTimeout              SBX_E1302   OPEN (Q4) — naming and builtin inheritance
├── NetworkPolicyViolation      SBX_E1401
├── ResourceLimitExceeded       SBX_E1402
├── AuthError                   SBX_E1501   hint: names the exact missing env var
└── RateLimitError              SBX_E1502
```

**OPEN ([Q4](../open-questions.md#q4--timeouterror-shadows-the-builtin))** — whether the
canonical name is `SandboxTimeout` with a `TimeoutError` alias, and whether it inherits the
builtin. Applies to any other builtin-shadowing name added later.

## Required attributes

Every `SandboxError` MUST carry:

| Attribute | Rule |
|-----------|------|
| `.code` | Stable `SBX_Ennnn`. Semver-covered. Renaming or repurposing is breaking. |
| `.hint` | The **exact fix**, as a command where one exists. Not a restatement of the problem. |
| `.url` | Redirect-stable docs page, one per code: `https://<docs>/errors/SBX_E1002`. |
| `__cause__` | Preserved when wrapping a provider exception. |

## Rendering

```
sandboxio.errors.BackendNotInstalled: [SBX_E1002] The 'e2b' backend is not installed.
  Fix:  uv pip install "sandboxio[e2b]"
  Docs: https://<docs-domain>/errors/SBX_E1002
```

- The library MUST NOT install `rich` tracebacks; the CLI entry point MAY
  ([ADR-0012](../adr/0012-no-telemetry-no-import-side-effects.md)).
- Messages MUST NOT contain secrets, credentials, env values or full user code
  ([06](06-observability.md#redaction)).

## Hint quality

Hints are specific, which means errors are constructed with context rather than raised bare:

- `AuthError` names the exact missing environment variable for that backend.
- `BackendNotFound` lists the backends actually installed **and** the install command for a
  known-but-missing one.
- `CapabilityNotSupported` names the capability and which backends provide it.
- `ResourceLimitExceeded` names the limit that was hit and its current value.

## Mapping rules (adapters)

1. Every provider exception crossing an adapter boundary MUST be mapped into this tree.
   A raw provider exception escaping is a bug, checked by the contract suite.
2. `raise ... from e` always — `__cause__` is how users debug provider-specific failures.
3. Do not invent codes per provider. If a provider failure has no good home, that is a
   signal to add a code to this catalog, with a docs page, in the same change.
4. Transient provider failures MUST map to `RateLimitError` or `CreationError` rather than
   being retried silently. sandboxio does not retry on the caller's behalf in v0.1.

## Catalog is generated

The per-code docs pages MUST be generated from the in-code catalog, so codes, hints and docs
cannot drift. Adding an error means adding code, hint and page in one change; CI MUST fail
if a code exists without a page or a page without a code.
