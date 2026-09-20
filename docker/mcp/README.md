# sandboxio MCP server image

Builds `ghcr.io/{{ORG}}/sandboxio-mcp` from this repository: `python -m sandboxio.mcp`
in a rootless `python:3.12-slim` image with the E2B adapter installed.

```bash
docker build -f docker/mcp/Dockerfile -t sandboxio-mcp .
docker run -i --rm -e E2B_API_KEY sandboxio-mcp                 # stdio, E2B backend
docker run -i --rm -e E2B_API_KEY sandboxio-mcp --backend e2b://my-template --timeout 600
```

`server.yaml` and `tools.json` are the Docker MCP Catalog metadata, in the shape
`docker/mcp-registry` expects under `servers/sandboxio/`. Publication needs the image pushed
and a pull request to the registry, both blocked on the org name
([README placeholders](../../README.md#license)). Usage and client configuration:
[docs/how-to/integrations.md](../../docs/how-to/integrations.md#mcp-server).
