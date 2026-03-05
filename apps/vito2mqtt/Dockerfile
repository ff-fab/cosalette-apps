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

# Multi-stage Docker build for vito2mqtt
# Stages:
#   1. builder: compile Python package and dependencies
#   2. runtime: minimal image with only runtime dependencies

# ============================================================================
# STAGE 1: Builder
# ============================================================================
# Purpose: Compile Python package, install dependencies, create wheel.
# This stage includes build tools and is discarded after compilation.

FROM python:3.14-slim AS builder

# Install system build dependencies required for compiling Python packages
# - build-essential: C compiler and build tools
# - libffi-dev: FFI library for ctypes, used by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create build directory
WORKDIR /build

# Copy project files for building
COPY pyproject.toml README.md LICENSE ./
COPY packages/ ./packages/

# Build the Python wheel using pip (project uses hatchling backend)
# Omit --no-deps to ensure all dependencies are included
# This creates .whl files for the app and all of its dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels .

# ============================================================================
# STAGE 2: Runtime
# ============================================================================
# Purpose: Minimal production image with only runtime dependencies.
# Only includes Python runtime, app code, and runtime-required system libs.

FROM python:3.14-slim AS runtime

# Install only runtime dependencies
# Most runtime libraries (libffi, libssl, etc.) are automatically pulled as
# transitive dependencies of Python packages. Keeping this minimal.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create application user (non-root for security)
# Run as UID 1000 (standard unprivileged user)
# This prevents container breakout exploits that assume root access
RUN useradd -m -u 1000 vito

# Set working directory and change ownership to vito user
WORKDIR /app
RUN chown -R vito:vito /app

# Copy wheels from builder and requirements
COPY --from=builder /build/wheels /tmp/wheels

# Install application and dependencies from wheels
# --no-cache-dir: don't store pip cache (saves image size)
# --no-index --find-links: use only local wheels, no PyPI download
RUN pip install --no-cache-dir --no-index --find-links /tmp/wheels vito2mqtt && \
    rm -rf /tmp/wheels

# Switch to non-root user
USER vito

# Expose health check port (if cosalette supports it; otherwise remove)
# Default MQTT doesn't expose a port in the container, broker is external
# This is a placeholder for future health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Entry point: run vito2mqtt CLI
# Accepts dynamic environment variables with VITO2MQTT_ prefix (pydantic-settings)
# Required vars:
#   VITO2MQTT_SERIAL_PORT: e.g., /dev/ttyUSB0
#   VITO2MQTT_MQTT__HOST: e.g., mosquitto (docker-compose service name)
ENTRYPOINT ["vito2mqtt"]
CMD ["--help"]
