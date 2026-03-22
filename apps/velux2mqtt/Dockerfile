FROM python:3.14-alpine

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

WORKDIR /app

# Copy monorepo root lockfile and workspace config for reproducible builds.
# Build context must be the repository root (docker build -f apps/velux2mqtt/Dockerfile .)
COPY pyproject.toml uv.lock ./
COPY apps/velux2mqtt/pyproject.toml apps/velux2mqtt/
COPY apps/velux2mqtt/README.md apps/velux2mqtt/
COPY apps/velux2mqtt/packages/src/ apps/velux2mqtt/packages/src/

# Install the application using locked dependencies (no cache to keep image small)
RUN uv pip install --system --no-cache ./apps/velux2mqtt

# Prepare persistence directory and non-root user
RUN adduser -D appuser \
    && mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

VOLUME /app/data

ENTRYPOINT ["velux2mqtt"]
