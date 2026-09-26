# How to run sandboxio in CI

Two jobs: your tool tests against the fake on every pull request (no Docker, no network,
seconds), and the same tests against real Docker on `main`. Copy this into
`.github/workflows/sandboxio.yml` and change the two `run` lines that are yours.

```yaml
name: agent tools

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  fake:
    name: tests against the fake (every PR)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10
        with:
          enable-cache: true
      - run: uv sync
      - run: uv run pytest -q            # your tests, using the sbx_fake fixture

  docker:
    name: tests against Docker (main only)
    if: github.ref == 'refs/heads/main'
    needs: fake
    runs-on: ubuntu-latest              # ships a Docker daemon
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10
        with:
          enable-cache: true
      - run: uv sync --extra docker
      - run: docker pull python:3.12-slim
      - run: uv run pytest -q -m docker  # your tests that create real sandboxes
      - name: zero leaked sandboxes
        run: test "$(docker ps -aq --filter label=io.sandboxio.managed | wc -l)" -eq 0
```

Mark the tests that need a daemon so the PR job skips them:

```python
import pytest

import sandboxio


@pytest.mark.docker
@pytest.mark.anyio
async def test_tool_on_real_docker() -> None:
    async with await sandboxio.create("docker://python:3.12-slim", timeout=60) as sb:
        assert (await sb.run(["echo", "ok"])).stdout == "ok\n"
```

```toml
[tool.pytest.ini_options]
markers = ["docker: needs a Docker daemon"]
addopts = "-m 'not docker'"      # PRs run the fake; `-m docker` opts in
```

The leak check at the end is the same one this repository runs: a sandbox left behind by a
test is a bug, and the label makes it visible. `sandboxio reap --kill` cleans up a runner
that is reused between jobs.

For E2B, add a job gated on the secret and run it nightly rather than on every PR — the suite
creates real sandboxes and costs real money:

```yaml
  e2b:
    if: github.event_name == 'schedule'
    runs-on: ubuntu-latest
    env:
      E2B_API_KEY: ${{ secrets.E2B_API_KEY }}
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10
      - run: uv sync --extra e2b
      - run: uv run pytest -q -m e2b
```
