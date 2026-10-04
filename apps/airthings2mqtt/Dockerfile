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
#
# --compile-bytecode writes the .pyc files at build time. The app runs as a
# non-root user that cannot write into root-owned site-packages, so without them
# every start and every CLI call recompiles all imports. compileall does the
# same for the standard library, whose .pyc the python:alpine base image strips.
RUN uv export --frozen --no-dev --no-emit-workspace --package airthings2mqtt \
      --format requirements-txt >/tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode --no-deps ./apps/airthings2mqtt \
    && python -m compileall -q -j0 "$(python -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')" \
    && rm /tmp/requirements.txt

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

# No HEALTHCHECK (docs/adr/ADR-010): MQTT carries health (heartbeat, availability,
# LWT), and a stale sensor exits with code 5 for the restart policy.
ENTRYPOINT ["airthings2mqtt"]
