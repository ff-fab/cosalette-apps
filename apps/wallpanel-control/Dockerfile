FROM python:3.14-alpine

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

WORKDIR /app

# Copy monorepo root lockfile and workspace config for reproducible builds.
# Build context must be the repository root (docker build -f apps/wallpanel-control/Dockerfile .)
COPY pyproject.toml uv.lock ./
COPY apps/wallpanel-control/pyproject.toml apps/wallpanel-control/
COPY apps/wallpanel-control/README.md apps/wallpanel-control/
COPY apps/wallpanel-control/packages/src/ apps/wallpanel-control/packages/src/

# Install the application using locked dependencies (no cache to keep image small)
RUN uv pip install --system --no-cache ./apps/wallpanel-control

# Prepare persistence directory and non-root user
RUN adduser -D appuser \
    && mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

VOLUME /app/data

ENTRYPOINT ["wallpanel-control"]
