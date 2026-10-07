FROM python:3.14-alpine

WORKDIR /app

# Copy monorepo root lockfile and workspace config for reproducible builds.
# Build context must be the repository root (docker build -f apps/gas2mqtt/Dockerfile .)
COPY pyproject.toml uv.lock ./
COPY apps/gas2mqtt/pyproject.toml apps/gas2mqtt/
COPY apps/gas2mqtt/README.md apps/gas2mqtt/
COPY apps/gas2mqtt/packages/src/ apps/gas2mqtt/packages/src/

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
#
# --compile-bytecode writes the .pyc files at build time. The app runs as a
# non-root user that cannot write into root-owned site-packages, so without them
# every start and every CLI call recompiles all imports. compileall does the
# same for the standard library, whose .pyc the python:alpine base image strips.
#
# uv is bind-mounted for this step only and pip is uninstalled: the app needs
# neither at runtime, and together they would add about 53 MB to the image.
RUN --mount=from=ghcr.io/astral-sh/uv:0.6,source=/uv,target=/bin/uv \
    uv export --frozen --no-dev --no-emit-workspace --package gas2mqtt \
      --format requirements-txt >/tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode --no-deps ./apps/gas2mqtt \
    && uv pip uninstall --system pip \
    && python -m compileall -q -j0 "$(python -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')" \
    && rm /tmp/requirements.txt

# Run as non-root with persistent data directory
RUN adduser -D appuser \
    && mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

VOLUME /app/data

# Health: MQTT is the primary signal; the probe only makes it visible on the host.
# An unhealthy status restarts nothing. Exits 1, 3, 4, 5 and 6 heal through
# restart: unless-stopped (docs/adr/ADR-011). One sensor feeds every entity, so
# the default --fail-on stale applies. The start period allows for the Pi 4
# startup proxy measured for airthings2mqtt 0.3.0 (28.6 s at --cpus 0.5), giving
# roughly 2x margin. The native probe does not measure gas2mqtt startup, which
# has not been measured on a Pi.
ENV COSALETTE_HEALTH_FILE=/tmp/gas2mqtt-health.json
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
  CMD ["cosalette-health"]

ENTRYPOINT ["gas2mqtt"]
