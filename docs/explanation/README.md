# Explanation

Why the defaults are what they are. Read the isolation tiers page before running untrusted
code.

| Page | Question it answers |
|------|---------------------|
| [The security model](security-model.md) | What sandboxio protects you from, what it does not, and what stays your job |
| [Isolation tiers](isolation-tiers.md) | What a container does and does not protect you from, and what the floor is for untrusted code |
| [Deny by default](deny-by-default.md) | Why egress is off, and what that costs |
| [Why errors have codes](error-codes.md) | Why every failure carries a stable `SBX_E` code and a hint that is a fix |
| [Version policy](version-policy.md) | What counts as a breaking change, how long a deprecation lives, and why `.native` is exempt |
| [Why sandboxio and not something else](comparisons.md) | When a provider SDK, a framework's sandbox layer or plain Docker is the better answer — and when it is not |
