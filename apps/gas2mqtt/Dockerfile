FROM python:3.14-alpine

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

WORKDIR /app

# Copy project files and lockfile for reproducible builds
COPY pyproject.toml uv.lock README.md ./
COPY packages/src/ packages/src/

# Install the application using locked dependencies (no cache to keep image small)
RUN uv pip install --system --no-cache .

# Run as non-root
RUN adduser -D appuser
RUN mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

# Entry point — reads config from environment / .env
CMD ["gas2mqtt"]
