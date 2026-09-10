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
RUN uv export --frozen --no-dev --no-emit-workspace --package wallpanel-control \
      --format requirements-txt >/tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --no-deps ./apps/wallpanel-control \
    && rm /tmp/requirements.txt

# Prepare persistence directory and non-root user
RUN adduser -D appuser \
    && mkdir -p /app/data /home/appuser/.ssh \
    && chown appuser:appuser /app/data /home/appuser/.ssh \
    && chmod 700 /home/appuser/.ssh
USER appuser

VOLUME /app/data

ENTRYPOINT ["wallpanel-control"]
