# isabelle-mcp container image.
#
# NOTE: this image is large (Isabelle + a prebuilt HOL heap are multi-GB) and is
# not built in CI here; it is provided for users who want a turnkey server.
# Build:  docker build -t isabelle-mcp .
# Run  :  docker run --rm -i isabelle-mcp        # stdio MCP server
#
# The build downloads Isabelle2025-2 and its components (Poly/ML, JDK) and
# builds the HOL session image, so it needs network access and time.

FROM python:3.12-slim AS base

ARG ISABELLE_VERSION=Isabelle2025-2
ARG ISABELLE_URL=https://isabelle.in.tum.de/website-Isabelle2025-2/dist/Isabelle2025-2_linux.tar.gz

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates git less libgomp1 fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Install Isabelle into /opt and put it on PATH.
RUN curl -fsSL "$ISABELLE_URL" -o /tmp/isabelle.tar.gz \
    && tar -xzf /tmp/isabelle.tar.gz -C /opt \
    && rm /tmp/isabelle.tar.gz
ENV ISABELLE_HOME=/opt/${ISABELLE_VERSION}
ENV PATH=${ISABELLE_HOME}/bin:${PATH}

# Fetch components and build the HOL heap (slow, cached in the image layer).
RUN isabelle components -a \
    && isabelle build -b HOL

# Install uv (Python package manager).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY . /app
RUN uv sync --frozen --no-dev

ENV ISABELLE_MCP_SESSION=HOL
# Default to stdio; override ISABELLE_MCP_TRANSPORT=streamable-http for HTTP.
CMD ["uv", "run", "--no-dev", "isabelle-mcp"]
