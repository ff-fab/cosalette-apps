FROM python:3.14-alpine AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./

# Phase 1: install dependencies only (cached unless pyproject.toml/uv.lock change)
RUN uv sync --frozen --no-dev --extra hardware --no-install-project --no-editable --no-cache

# Phase 2: copy source and install the project itself
COPY packages/src/ packages/src/
RUN uv sync --frozen --no-dev --extra hardware --no-editable --no-cache

FROM python:3.14-alpine

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Prepare persistence directory and non-root user
RUN adduser -D appuser && addgroup appuser dialout \
    && mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

VOLUME /app/data

ENTRYPOINT ["jeelink2mqtt"]
