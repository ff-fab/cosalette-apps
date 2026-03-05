# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra hardware

COPY packages/src/ packages/src/

FROM python:3.14-slim-bookworm

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/packages/src/ packages/src/

ENV PATH="/app/.venv/bin:$PATH"

# Persistence volume
VOLUME /app/data

ENTRYPOINT ["jeelink2mqtt"]
