# sandboxio MCP server image

Builds `ghcr.io/bit-agents/sandboxio-mcp` from this repository: `python -m sandboxio.mcp`
in a rootless `python:3.12-slim` image with the E2B adapter installed.

```bash
docker build -f docker/mcp/Dockerfile -t sandboxio-mcp .
docker run -i --rm -e E2B_API_KEY sandboxio-mcp                 # stdio, E2B backend
docker run -i --rm -e E2B_API_KEY sandboxio-mcp --backend e2b://my-template --timeout 600
```

`server.yaml` and `tools.json` are the Docker MCP Catalog metadata, in the shape
`docker/mcp-registry` expects under `servers/sandboxio/`. The `image` job in `release.yml`
pushes `amd64` and `arm64` on every `v*` tag, `latest` only for a final version; the pull
request to the registry stays manual. Usage and client configuration:
[docs/how-to/integrations.md](../../docs/how-to/integrations.md#mcp-server).
