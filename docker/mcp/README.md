# sandboxio MCP server image

Builds `ghcr.io/bit-agents/sandboxio-mcp` from this repository: `python -m sandboxio.mcp`
in a rootless `python:3.12-slim` image with the E2B adapter installed.

```bash
docker build -f docker/mcp/Dockerfile -t sandboxio-mcp .
docker run -i --rm -e E2B_API_KEY sandboxio-mcp                 # stdio, E2B backend
docker run -i --rm -e E2B_API_KEY sandboxio-mcp --backend e2b://my-template --timeout 600
```

The `image` job in `release.yml` pushes `amd64` and `arm64` on every `v*` tag, `latest` only
for a final version. Usage and client configuration:
[docs/how-to/integrations.md](../../docs/how-to/integrations.md#mcp-server).

## The catalog entry

`server.yaml` and `tools.json` are the Docker MCP Catalog metadata. They are the source the
registry pull request is copied from, byte for byte, into `servers/sandboxio/` of a
`docker/mcp-registry` fork — first submitted as
[docker/mcp-registry#5258](https://github.com/docker/mcp-registry/pull/5258).

`tools.json` is generated; never edit it by hand. `tests/test_mcp_catalog_entry.py` fails if
it is stale, or if the entry loses the two properties the registry rejects on:

```bash
uv run python scripts/gen_mcp_tools.py
```

**`source.commit` is the revision a Docker reviewer audits, so it has to move with the
release.** Bump it to the new tag's commit and open the registry pull request — the release
runbook lists this as the step after the image is pushed.

To submit, in a fork of the registry:

```bash
cp docker/mcp/server.yaml docker/mcp/tools.json <fork>/servers/sandboxio/
cd <fork> && npx prettier --write servers/sandboxio/   # house style; only server.yaml is gated
task validate -- --name sandboxio
task build -- --tools --pull-community sandboxio       # --pull-community: the image is not in mcp/
```
