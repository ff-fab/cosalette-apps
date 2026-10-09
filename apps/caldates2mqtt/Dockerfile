FROM python:3.14-alpine

WORKDIR /app

# Copy monorepo root lockfile and workspace config for reproducible builds.
# Build context must be the repository root (docker build -f apps/caldates2mqtt/Dockerfile .)
COPY pyproject.toml uv.lock ./
COPY apps/caldates2mqtt/pyproject.toml apps/caldates2mqtt/
COPY apps/caldates2mqtt/README.md apps/caldates2mqtt/
COPY apps/caldates2mqtt/packages/src/ apps/caldates2mqtt/packages/src/

# Install dependencies from the committed lockfile, then the app itself.
#
# `uv pip install ./apps/<app>` on its own does NOT read uv.lock — it re-resolves
# every requirement against PyPI at build time, so the pins this repo maintains
# reach CI and developer machines but not the shipped image. Exporting the locked
# graph first and installing it with --require-hashes closes that gap: the image
# gets exactly the versions in uv.lock, verified by hash.
#
# --no-emit-workspace omits the workspace members themselves (they are not on
# PyPI); --no-deps on both steps keeps uv from re-resolving the locked graph (the
# export already lists every transitive dependency, and re-resolving would pull
# the latest rich back in behind --prune).
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
# -x skips the GUI, turtle and pydoc help modules no app imports (about 3.5 MB of
# .pyc); Python still runs them, it just compiles them in memory.
#
# --prune rich drops rich and the packages only it needs (pygments,
# markdown-it-py, mdurl): about 14 MB that typer loads only to colour --help and
# usage errors. cosalette 0.11.1+ falls back to plain Click help without them;
# TYPER_USE_RICH=0 below does the same for Typer apps the app builds itself
# (docs/adr/ADR-013).
#
# uv is bind-mounted for this step only and pip is uninstalled: the app needs
# neither at runtime, and together they would add about 53 MB to the image.
RUN --mount=from=ghcr.io/astral-sh/uv:0.6,source=/uv,target=/bin/uv \
    uv export --frozen --no-dev --no-emit-workspace --prune rich --package caldates2mqtt \
      --format requirements-txt >/tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode --no-deps -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode --no-deps ./apps/caldates2mqtt \
    && uv pip uninstall --system pip \
    && python -m compileall -q -j0 -x '/(idlelib|tkinter|turtledemo|pydoc_data)/|/turtle\.py$' "$(python -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')" \
    && rm /tmp/requirements.txt

# Plain Click help and errors: rich is not installed (see --prune rich above).
ENV TYPER_USE_RICH=0

# Prepare persistence directory and non-root user
RUN adduser -D appuser \
    && mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

VOLUME /app/data

# Health: MQTT is the primary signal; the probe only makes it visible on the host.
# An unhealthy status restarts nothing. Exits 1, 3, 4 and 6 heal through
# restart: unless-stopped (docs/adr/ADR-011); caldates2mqtt sets no
# exit_after_stale. Calendars are independently configured, so one stale
# calendar must not make the whole container unhealthy.
# The first health-file write came 2.5 to 2.8 s after start on amd64 at
# --cpus 0.5; ADR-011's Pi 4 factor (about 3.5x) gives about 10 s, so the 60 s
# start period leaves a wide margin. Not measured on a Pi.
ENV COSALETTE_HEALTH_FILE=/tmp/caldates2mqtt-health.json
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
  CMD ["cosalette-health", "--fail-on", ""]

ENTRYPOINT ["caldates2mqtt"]
