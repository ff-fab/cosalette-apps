FROM python:3.14-alpine

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

# System deps for CairoSVG (optional PNG rendering)
RUN apk add --no-cache cairo libffi

WORKDIR /app

# Copy monorepo root lockfile and workspace config for reproducible builds.
# Build context must be the repository root (docker build -f apps/suncast/Dockerfile .)
COPY pyproject.toml uv.lock ./
COPY apps/suncast/pyproject.toml apps/suncast/
COPY apps/suncast/README.md apps/suncast/
COPY apps/suncast/packages/src/ apps/suncast/packages/src/

# Install the application with optional PNG and HTTP support
RUN uv pip install --system --no-cache "./apps/suncast[png,http]"

# Prepare output and data directories, run as non-root
RUN adduser -D appuser \
    && mkdir -p /app/data /output \
    && chown -R appuser:appuser /app/data /output
USER appuser

VOLUME /app/data
VOLUME /output

ENTRYPOINT ["suncast"]
