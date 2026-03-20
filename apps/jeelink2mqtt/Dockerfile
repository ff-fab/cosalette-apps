FROM python:3.14-alpine

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

WORKDIR /app

# Copy monorepo root lockfile and workspace config for reproducible builds.
# Build context must be the repository root (docker build -f apps/jeelink2mqtt/Dockerfile .)
COPY pyproject.toml uv.lock ./
COPY apps/jeelink2mqtt/pyproject.toml apps/jeelink2mqtt/
COPY apps/jeelink2mqtt/README.md apps/jeelink2mqtt/
COPY apps/jeelink2mqtt/packages/src/ apps/jeelink2mqtt/packages/src/

# Install the application using locked dependencies (no cache to keep image small)
RUN uv pip install --system --no-cache ./apps/jeelink2mqtt

# Prepare persistence directory and non-root user
RUN adduser -D appuser && addgroup appuser dialout \
    && mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

VOLUME /app/data

ENTRYPOINT ["jeelink2mqtt"]
