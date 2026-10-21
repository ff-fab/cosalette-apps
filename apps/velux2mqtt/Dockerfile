# ── lgpio wheel ──────────────────────────────────────────────
# gpiozero needs a pin factory that talks to /dev/gpiochip*; without one it falls
# back to NativeFactory, which needs /dev/gpiomem and fails in this container.
# lgpio publishes no cp314 or musllinux wheels, so the locked sdist is built here
# and only the finished wheel reaches the runtime image. This is the same build as
# apps/geiger2mqtt/Dockerfile (see apps/geiger2mqtt/docs/adr/ADR-002).
# PYPI=1 makes setup.py compile the bundled lg C sources statically instead of
# linking a system liblgpio. swig is pinned to 4.2.1 because 4.3 removed the
# PyInt_* aliases lgpio.i still uses. The lg sources predate C23 (GCC 15 default)
# and GCC 14 strict pointer checks, so CFLAGS selects gnu17 and keeps the
# pointer mismatch a warning. The root pyproject applies the same settings to uv sync.
FROM python:3.14-alpine AS lgpio-build

RUN apk add --no-cache build-base linux-headers

WORKDIR /build
RUN --mount=from=ghcr.io/astral-sh/uv:0.6,source=/uv,target=/bin/uv \
    --mount=type=bind,source=pyproject.toml,target=/build/pyproject.toml \
    --mount=type=bind,source=uv.lock,target=/build/uv.lock \
    --mount=type=bind,source=apps/velux2mqtt/pyproject.toml,target=/build/apps/velux2mqtt/pyproject.toml \
    uv export --frozen --no-dev --no-emit-workspace --package velux2mqtt \
      --format requirements-txt >/tmp/requirements.txt \
    && sed -n '/^lgpio==/,/^[^ ]/{/^lgpio==\|^ /p}' /tmp/requirements.txt >/tmp/lgpio.txt \
    && pip install --no-cache-dir swig==4.2.1.post0 setuptools==80.9.0 \
    && PYPI=1 CFLAGS="-std=gnu17 -Wno-error=incompatible-pointer-types" pip wheel --no-cache-dir --no-deps --no-build-isolation \
      --no-binary lgpio --require-hashes -r /tmp/lgpio.txt -w /wheels

# ── runtime ──────────────────────────────────────────────────
FROM python:3.14-alpine

WORKDIR /app

# Build context must be the repository root (docker build -f apps/velux2mqtt/Dockerfile .)
COPY apps/velux2mqtt/pyproject.toml apps/velux2mqtt/
COPY apps/velux2mqtt/README.md apps/velux2mqtt/
COPY apps/velux2mqtt/packages/src/ apps/velux2mqtt/packages/src/

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
# the latest rich back in behind --prune). lgpio is taken out of the export and
# installed from the wheel the build stage made from the same locked, hash-checked
# sdist; the wheel is bind-mounted, not copied.
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
# this app builds no Typer CLI of its own, so it needs no TYPER_USE_RICH=0
# (docs/adr/ADR-013).
#
# uv is bind-mounted for this step only and pip is uninstalled: the app needs
# neither at runtime, and together they would add about 53 MB to the image.
# The workspace pyproject.toml and uv.lock are bind-mounted too, so they stay
# out of the image (about 0.5 MB).
RUN --mount=from=ghcr.io/astral-sh/uv:0.6,source=/uv,target=/bin/uv \
    --mount=from=lgpio-build,source=/wheels,target=/wheels \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml \
    --mount=type=bind,source=uv.lock,target=/app/uv.lock \
    uv export --frozen --no-dev --no-emit-workspace --prune rich --package velux2mqtt \
      --no-emit-package lgpio --format requirements-txt >/tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode --no-deps -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode --no-deps /wheels/lgpio-*.whl \
    && uv pip install --system --no-cache --compile-bytecode --no-deps ./apps/velux2mqtt \
    && uv pip uninstall --system pip \
    && python -m compileall -q -j0 -x '/(idlelib|tkinter|turtledemo|pydoc_data)/|/turtle\.py$' "$(python -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')" \
    && rm /tmp/requirements.txt

# gpiozero picks lgpio explicitly instead of probing every pin factory. lgpio
# writes its notification pipes to LG_WD, which must be writable by appuser.
ENV GPIOZERO_PIN_FACTORY=lgpio \
    LG_WD=/tmp

# Fail the build if the compiled extension does not load. Importing lgpio as root
# creates a root-owned notification FIFO in LG_WD that appuser could not open at
# runtime, so remove it again.
RUN python -c "import lgpio, gpiozero.pins.lgpio" \
    && rm -f /tmp/.lgd-nfy*

# Prepare persistence directory and non-root user
RUN adduser -D appuser \
    && mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser

VOLUME /app/data

# Health: MQTT is the primary signal; the probe only makes it visible on the host.
# An unhealthy status restarts nothing. Exits 1, 3 and 4 heal through
# restart: unless-stopped (docs/adr/ADR-011); velux2mqtt has no telemetry, so it
# sets no exit_after_stale. Covers are independent devices, so the probe checks
# health-file freshness only (--fail-on ""). The start period allows for the
# Pi 4 startup proxy measured for airthings2mqtt 0.3.0 (28.6 s at --cpus 0.5),
# giving roughly 2x margin. velux2mqtt startup has not been measured on a Pi.
ENV COSALETTE_HEALTH_FILE=/tmp/velux2mqtt-health.json
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
  CMD ["cosalette-health", "--fail-on", ""]

ENTRYPOINT ["velux2mqtt"]
