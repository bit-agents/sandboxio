# The sandboxio MCP server as a container: ghcr.io/bit-agents/sandboxio-mcp
#
# Rootless; no Docker socket is mounted or reachable — the sandbox backend inside this
# image is a cloud one (E2B by default). Configuration is fixed at process start through
# arguments and environment; there is no runtime config tool (spec/09, ADR-0009).
#
#   docker build -f docker/mcp/Dockerfile -t sandboxio-mcp .
#   docker run -i --rm -e E2B_API_KEY sandboxio-mcp --backend e2b://code-interpreter-v1

# Both stages pin the base image by digest; Dependabot raises the bump, so a pinned
# digest does not mean an unpatched base.
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE LICENSE-DOCS ./
COPY src ./src
COPY packages ./packages
RUN pip install --no-cache-dir --prefix=/install ./packages/sandboxio-e2b "./[mcp,e2b]"

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
COPY --from=build /install /usr/local
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin sandboxio
USER 10001
WORKDIR /home/sandboxio
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "sandboxio.mcp"]
CMD ["--backend", "e2b://code-interpreter-v1"]
