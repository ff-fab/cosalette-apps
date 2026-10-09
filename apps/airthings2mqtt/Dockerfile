FROM python:3.14-alpine

# No bluez package. bleak runs `bluetoothctl --version` only to refuse BlueZ
# older than 5.55, and inside the image that reports the image's bluez, not the
# host bluetoothd it talks to over D-Bus. Without it bleak logs one warning and
# assumes 5.55+, which saves about 11 MB. The host requirement is documented in
# docs/getting-started.md.

WORKDIR /app

# Build context must be the repository root (docker build -f apps/airthings2mqtt/Dockerfile .)
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
# The workspace pyproject.toml and uv.lock are bind-mounted too, so they stay
# out of the image (about 0.5 MB).
RUN --mount=from=ghcr.io/astral-sh/uv:0.6,source=/uv,target=/bin/uv \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml \
    --mount=type=bind,source=uv.lock,target=/app/uv.lock \
    uv export --frozen --no-dev --no-emit-workspace --prune rich --package airthings2mqtt \
      --format requirements-txt >/tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode --no-deps -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode --no-deps ./apps/airthings2mqtt \
    && uv pip uninstall --system pip \
    && python -m compileall -q -j0 -x '/(idlelib|tkinter|turtledemo|pydoc_data)/|/turtle\.py$' "$(python -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')" \
    && rm /tmp/requirements.txt

# Plain Click help and errors: rich is not installed (see --prune rich above).
ENV TYPER_USE_RICH=0

# Prepare persistence directory and a dedicated non-root user. The fixed UID/GID
# 10001 is deliberately not 1000 (usually the host login user), so a host D-Bus
# policy can target this app alone. dbus-daemon refuses connections from a UID
# without a host account, so the host needs a matching system user: see
# docs/host-setup.md. Keep in sync with deploy/airthings2mqtt-bluez.conf.
RUN addgroup -g 10001 appuser \
    && adduser -D -H -u 10001 -G appuser appuser \
    && mkdir -p /app/data && chown 10001:10001 /app/data
USER 10001:10001

VOLUME /app/data

# The user has no home directory, so the framework default store path
# (~/.local/state/...) is not writable. Keep the device store on the volume.
ENV AIRTHINGS2MQTT_STORE_PATH=/app/data/store.json

# Health: MQTT is the primary signal; the probe only makes it visible on the host.
# An unhealthy status restarts nothing. Exits 1, 3, 4, 5 and 6 heal through
# restart: unless-stopped (docs/adr/ADR-011). One instance reads one sensor, so
# the default --fail-on stale applies: a stale sensor means the app is not doing
# its job. The start period allows for the measured Pi 4 startup of
# airthings2mqtt 0.3.0 (28.6 s at --cpus 0.5), giving roughly 2x margin.
ENV COSALETTE_HEALTH_FILE=/tmp/airthings2mqtt-health.json
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
  CMD ["cosalette-health"]
ENTRYPOINT ["airthings2mqtt"]
