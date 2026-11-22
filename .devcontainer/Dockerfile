# cosalette-apps development container
# Python 3.14 + uv + common dev tools

FROM mcr.microsoft.com/devcontainers/python:3.14-bookworm

# bash with pipefail, so a failing curl/echo piped into sha256sum fails the RUN.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install uv (fast Python package manager)
# renovate: datasource=docker depName=ghcr.io/astral-sh/uv
COPY --from=ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 /uv /uvx /bin/



# Install additional system dependencies
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        jq \
        httpie \
        fzf \
        ripgrep \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install go-task (task runner — https://taskfile.dev)
# renovate: datasource=github-releases depName=go-task/task
ARG TASK_VERSION=v3.54.0
ARG TASK_SHA256_AMD64=680859dbb4d881a9c72d4d9a8f510825450849af8567deacd7302c01124416fb
ARG TASK_SHA256_ARM64=d7189d439d4a6058e39e1b2acd7c8b27acd4856691b408f23b242e4294e1df5b
RUN set -eux; \
    ARCH="$(dpkg --print-architecture)"; \
    case "${ARCH}" in \
        amd64) TASK_ARCH='amd64' ;; \
        arm64) TASK_ARCH='arm64' ;; \
        *) echo "Unsupported architecture: ${ARCH}" >&2; exit 1 ;; \
    esac; \
    TASK_TARBALL="task_linux_${TASK_ARCH}.tar.gz"; \
    TASK_URL="https://github.com/go-task/task/releases/download/${TASK_VERSION}/${TASK_TARBALL}"; \
    case "${ARCH}" in \
      amd64) EXPECTED_SHA="${TASK_SHA256_AMD64}" ;; \
      arm64) EXPECTED_SHA="${TASK_SHA256_ARM64}" ;; \
      *) echo "Unsupported architecture: ${ARCH}" >&2; exit 1 ;; \
    esac; \
    for i in 1 2 3; do \
        curl -fsSL "${TASK_URL}" -o /tmp/task.tar.gz && break || sleep 5; \
    done; \
    echo "${EXPECTED_SHA}  /tmp/task.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/task.tar.gz -C /tmp task; \
    install -m 755 /tmp/task /usr/local/bin/task; \
    rm -f /tmp/task /tmp/task.tar.gz

# Install dolt (versioned SQL database backend for the beads/bd issue tracker).
# Baked into the image so the container starts reliably without a runtime download.
# This project runs bd in server mode (`bd init --server` in post-create.sh,
# `bd dolt start` in post-start.sh), which requires an external dolt binary.
# Verified against beads v1.1.2.
# renovate: datasource=github-releases depName=dolthub/dolt
ARG DOLT_VERSION=v2.2.3
# SHA-256 digests for supply-chain integrity verification (update on version bump)
ARG DOLT_SHA256_AMD64=ffafa7cc172cada5f77ca3fb96306545ddac44a111625f75f870306c7f197301
ARG DOLT_SHA256_ARM64=5e8f4dbe61931c36f8359022ee32337e5daf65aba06a29791a066e50677c8b3a
RUN set -eux; \
    ARCH=$(dpkg --print-architecture); \
    case "${ARCH}" in \
      amd64) EXPECTED_SHA="${DOLT_SHA256_AMD64}" ;; \
      arm64) EXPECTED_SHA="${DOLT_SHA256_ARM64}" ;; \
      *) echo "Unsupported architecture: ${ARCH}" >&2; exit 1 ;; \
    esac; \
    TARBALL="/tmp/dolt-linux-${ARCH}.tar.gz"; \
    curl -fsSL \
      "https://github.com/dolthub/dolt/releases/download/${DOLT_VERSION}/dolt-linux-${ARCH}.tar.gz" \
      -o "${TARBALL}"; \
    echo "${EXPECTED_SHA}  ${TARBALL}" | sha256sum -c -; \
    tar -xzf "${TARBALL}" -C /tmp; \
    install "/tmp/dolt-linux-${ARCH}/bin/dolt" /usr/local/bin/; \
    rm -rf "/tmp/dolt-linux-${ARCH}" "${TARBALL}"; \
    dolt version

# Install beads (bd) — git-backed issue tracker for AI agents.
# Baked into the image so the VS Code extension (planet57.vscode-beads) can
# discover the project during activation, before any lifecycle scripts run.
# The tarball ships a single binary that links only libc and the loader
# (verified with `readelf -d` on both linux/amd64 and linux/arm64 at v1.1.2).
# renovate: datasource=github-releases depName=gastownhall/beads
ARG BD_VERSION=v1.1.2
# SHA-256 digests for supply-chain integrity verification (update on version bump)
ARG BD_SHA256_AMD64=a72d71ed374955dc9f83a0f90b54bd7b6a0016709dd1676ae2e368651ed401c2
ARG BD_SHA256_ARM64=a134015faf4be0a43f8681a8d602eaf0b7c255c957f09d3c933257c8c92fdd10
RUN set -eux; \
    ARCH=$(dpkg --print-architecture); \
    case "${ARCH}" in \
      amd64) EXPECTED_SHA="${BD_SHA256_AMD64}" ;; \
      arm64) EXPECTED_SHA="${BD_SHA256_ARM64}" ;; \
      *) echo "Unsupported architecture: ${ARCH}" >&2; exit 1 ;; \
    esac; \
    VER_NO_V="${BD_VERSION#v}"; \
    TARBALL="/tmp/beads_${VER_NO_V}_linux_${ARCH}.tar.gz"; \
    curl -fsSL \
      "https://github.com/gastownhall/beads/releases/download/${BD_VERSION}/beads_${VER_NO_V}_linux_${ARCH}.tar.gz" \
      -o "${TARBALL}"; \
    echo "${EXPECTED_SHA}  ${TARBALL}" | sha256sum -c -; \
    tar -xzf "${TARBALL}" -C /tmp; \
    install -m 755 /tmp/bd /usr/local/bin/bd; \
    rm -f /tmp/bd "${TARBALL}"; \
    bd version

# Install Kilo CLI (AI coding agent — https://kilocode.ai)
# renovate: datasource=github-releases depName=Kilo-Org/kilocode
ARG KILO_VERSION=v7.8.27
# SHA-256 digests for supply-chain integrity verification (update on version bump)
ARG KILO_SHA256_AMD64=4c08aa46dd87453a329f48b0f00d34d0fa7b8f0ac910fe8937814d4e8582de08
ARG KILO_SHA256_ARM64=65491b899f62b07beafb3ce89b88b987a03197c88563afbf976d38fb78df5ff6
# Kilo releases use x64/arm64 naming (not amd64) — ARCH_NAME remaps from dpkg convention
RUN set -eux; \
    ARCH=$(dpkg --print-architecture); \
    case "${ARCH}" in \
      amd64) ARCH_NAME='x64';   EXPECTED_SHA="${KILO_SHA256_AMD64}" ;; \
      arm64) ARCH_NAME='arm64'; EXPECTED_SHA="${KILO_SHA256_ARM64}" ;; \
      *) echo "Unsupported architecture: ${ARCH}" >&2; exit 1 ;; \
    esac; \
    TARBALL="/tmp/kilo-linux-${ARCH_NAME}.tar.gz"; \
    curl -fsSL \
      "https://github.com/Kilo-Org/kilocode/releases/download/${KILO_VERSION}/kilo-linux-${ARCH_NAME}.tar.gz" \
      -o "${TARBALL}"; \
    echo "${EXPECTED_SHA}  ${TARBALL}" | sha256sum -c -; \
    tar -xzf "${TARBALL}" -C /tmp kilo; \
    install -m 755 /tmp/kilo /usr/local/bin/kilo; \
    rm -f /tmp/kilo "${TARBALL}"; \
    kilo --version

# Install Claude Code CLI (Anthropic — https://claude.com/claude-code)
# The installer downloads the CLI binary and verifies it against a SHA-256
# checksum from Anthropic's release manifest before installing. We pin the CLI
# version (passed through to the installer) so builds are reproducible; bump via
# Renovate. The bootstrap script itself is fetched over TLS from claude.ai and
# is trusted rather than checksum-pinned — unlike task/dolt/bd/kilo above,
# which all verify a SHA-256 digest of the downloaded tarball before use.
# Accepted gap: Anthropic does not publish a stable checksum for install.sh,
# and this stage never runs in CI (INSTALL_CLAUDE_CODE=false there), so blast
# radius is limited to local/interactive devcontainer builds. Revisit if a
# pinned checksum becomes available upstream.
# renovate: datasource=npm depName=@anthropic-ai/claude-code
ARG CLAUDE_CODE_VERSION=2.1.330
# Claude Code is a local/interactive dev tool only — CI never invokes `claude`.
# Default to installing it (local devcontainer builds via VS Code / `devcontainer
# up` get it out of the box); the CI devcontainer-build workflows set
# INSTALL_CLAUDE_CODE=false (via devcontainer.json's build.args + localEnv, see
# .devcontainer/devcontainer.json) so CI image builds skip it entirely, which
# also sidesteps this whole class of PATH bug in CI.
ARG INSTALL_CLAUDE_CODE=true
RUN set -eux; \
    if [ "${INSTALL_CLAUDE_CODE}" = "true" ]; then \
      INSTALLER="/tmp/claude-install.sh"; \
      curl -fsSL https://claude.ai/install.sh -o "${INSTALLER}"; \
      # Install as the container user, not root: the installer writes to
      # "$HOME/.local", and root's /root is mode 0700, so a root install left
      # /usr/local/bin/claude dangling for vscode. The binary is vscode-owned
      # by design (vscode has passwordless sudo anyway); root should not run
      # claude. DISABLE_AUTOUPDATER below keeps the pinned version authoritative.
      runuser -u vscode -- bash "${INSTALLER}" "${CLAUDE_CODE_VERSION}"; \
      rm -f "${INSTALLER}"; \
      # The installer only advises adding ~/.local/bin to PATH via shell rc
      # files, which non-interactive shells never source. Symlink into
      # /usr/local/bin, already on PATH everywhere, matching how
      # task/dolt/bd/kilo are installed above.
      ln -sf /home/vscode/.local/bin/claude /usr/local/bin/claude; \
    fi
# Stay on the Renovate-reviewed CLAUDE_CODE_VERSION instead of self-updating.
ENV DISABLE_AUTOUPDATER=1

# Configure uv to use project-local virtual environments
ENV UV_PROJECT_ENVIRONMENT="/workspaces/cosalette-apps/.venv"

# Create .vscode-server directory with proper ownership
# This prevents permission issues when volumes are mounted
RUN mkdir -p /home/vscode/.vscode-server /home/vscode/.vscode-server/extensions \
    && chown -R vscode:vscode /home/vscode/.vscode-server

# Verify installations
RUN set -eux; \
    uv --version && python --version && task --version && fzf --version && dolt version && bd version && kilo --version; \
    if [ "${INSTALL_CLAUDE_CODE}" = "true" ]; then runuser -u vscode -- claude --version; fi
