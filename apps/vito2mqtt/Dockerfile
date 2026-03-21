FROM python:3.14-alpine

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

WORKDIR /app

# Copy monorepo root lockfile and workspace config for reproducible builds.
# Build context must be the repository root (docker build -f apps/vito2mqtt/Dockerfile .)
COPY pyproject.toml uv.lock ./
COPY apps/vito2mqtt/pyproject.toml apps/vito2mqtt/
COPY apps/vito2mqtt/README.md apps/vito2mqtt/
COPY apps/vito2mqtt/LICENSE apps/vito2mqtt/
COPY apps/vito2mqtt/packages/src/ apps/vito2mqtt/packages/src/

# Install the application using locked dependencies (no cache to keep image small)
RUN uv pip install --system --no-cache ./apps/vito2mqtt

# Run as non-root (dialout group for serial device access)
RUN adduser -D appuser && addgroup appuser dialout \
    && mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

VOLUME /app/data

ENTRYPOINT ["vito2mqtt"]
