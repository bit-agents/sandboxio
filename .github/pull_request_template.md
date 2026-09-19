<!-- Conventional Commits subject on the PR title. Every commit signed off: `git commit -s`. -->

## What and why

<!-- Link the issue, spec section or ADR this implements. -->

## Checklist

- [ ] `uv run pytest` · `uv run ruff check . && uv run ruff format --check .` · `uv run mypy && uv run pyright`
- [ ] A bug fix carries the test that would have caught it
- [ ] A new capability is implemented everywhere it is declared (ADR-0007)
- [ ] No new base dependency, no new eager import (ADR-0004)
- [ ] A decision that outlives this PR has an ADR
