FROM python:3.14-alpine

# bluez provides `bluetoothctl`, which bleak uses to detect the host BlueZ
# version over D-Bus. Without it bleak warns and blindly assumes BlueZ 5.55+,
# which could select an incompatible code path against an older host stack.
# Small image-size cost in exchange for reliable BlueZ version detection.
RUN apk add --no-cache bluez

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

WORKDIR /app

# Copy monorepo root lockfile and workspace config for reproducible builds.
# Build context must be the repository root (docker build -f apps/airthings2mqtt/Dockerfile .)
COPY pyproject.toml uv.lock ./
COPY apps/airthings2mqtt/pyproject.toml apps/airthings2mqtt/
COPY apps/airthings2mqtt/README.md apps/airthings2mqtt/
COPY apps/airthings2mqtt/packages/src/ apps/airthings2mqtt/packages/src/

# Install dependencies from the committed lockfile, then the app itself.
#
# `uv pip install ./apps/<app>` on its own does NOT read uv.lock — it re-resolves
# every requirement against PyPI at build time, so the pins this repo maintains
# reach CI and developer machines but not the shipped image. Exporting the locked
# graph first and installing it with --require-hashes closes that gap: the image
# gets exactly the versions in uv.lock, verified by hash.
#
# --no-emit-workspace omits the workspace members themselves (they are not on
# PyPI); --no-deps on the second step keeps uv from re-resolving what step one
# already pinned.
#
# No --require-hashes: the root pyproject's [tool.uv] constraint-dependencies are
# security floors (aiohttp>=3.14.3 and friends), and uv rejects any unpinned
# requirement in that mode. The exported file still pins every version with == and
# carries every hash, so the image gets the locked graph either way.
RUN uv export --frozen --no-dev --no-emit-workspace --package airthings2mqtt \
      --format requirements-txt >/tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --no-deps ./apps/airthings2mqtt \
    && rm /tmp/requirements.txt

# Prepare persistence directory and non-root user
RUN adduser -D appuser \
    && mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

VOLUME /app/data

ENTRYPOINT ["airthings2mqtt"]
