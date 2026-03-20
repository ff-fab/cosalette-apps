# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

FROM python:3.14-alpine

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

WORKDIR /app

# Copy monorepo root lockfile and workspace config for reproducible builds.
# Build context must be the repository root (docker build -f apps/vito2mqtt/Dockerfile .)
COPY pyproject.toml uv.lock ./
COPY apps/vito2mqtt/pyproject.toml apps/vito2mqtt/
COPY apps/vito2mqtt/README.md apps/vito2mqtt/
COPY apps/vito2mqtt/LICENSE apps/vito2mqtt/
COPY apps/vito2mqtt/packages/src/ apps/vito2mqtt/packages/src/

# Install the application using locked dependencies (no cache to keep image small)
RUN uv pip install --system --no-cache ./apps/vito2mqtt

# Run as non-root
RUN adduser -D -G dialout vito
RUN mkdir -p /app/data && chown vito:vito /app/data
USER vito

# Persistent state directory
VOLUME /data

# Entry point — reads config from environment / .env
ENTRYPOINT ["vito2mqtt"]
CMD ["--help"]
