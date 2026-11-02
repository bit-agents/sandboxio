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
FROM python:3.15-slim@sha256:94d3426f1def7db4a106a232ac121bfd975393e5dfd40a619b955fae45fe7913 AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE LICENSE-DOCS ./
COPY src ./src
COPY packages ./packages
RUN pip install --no-cache-dir --prefix=/install ./packages/sandboxio-e2b "./[mcp,e2b]"

FROM python:3.15-slim@sha256:94d3426f1def7db4a106a232ac121bfd975393e5dfd40a619b955fae45fe7913
COPY --from=build /install /usr/local
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin sandboxio
USER 10001
WORKDIR /home/sandboxio
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "sandboxio.mcp"]
CMD ["--backend", "e2b://code-interpreter-v1"]
