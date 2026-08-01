# cosalette-apps development container
# Python 3.14 + uv + common dev tools

FROM mcr.microsoft.com/devcontainers/python:3.14-bookworm

# Install uv (fast Python package manager)
# renovate: datasource=docker depName=ghcr.io/astral-sh/uv
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /bin/



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
ARG TASK_VERSION=v3.52.0
ARG TASK_SHA256_AMD64=02c679ffae53dca791804847d78b31731615894e292948397c971c87ac9e95bd
ARG TASK_SHA256_ARM64=7e0044108830cec0534577b289564e3b7c83e6df276feb631a1edc63d04e4ebe
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
    cd /tmp && tar -xzf task.tar.gz task && \
    mv task /usr/local/bin/ && \
    chmod +x /usr/local/bin/task && \
    rm -f /tmp/task.tar.gz

# Install dolt (versioned SQL database backend for the beads/bd issue tracker).
# Baked into the image so the container starts reliably without a runtime download.
# bd on Linux requires an external dolt binary; the embedded dolt in the bd binary
# is macOS-only as of beads v1.0.0.
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
# The tarball ships a single static-ish binary; an ICU compatibility symlink
# is created when the binary links against a different ICU than the OS provides.
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
    # ICU compatibility shim: the prebuilt bd binary may link against a \
    # different ICU major version than the base image provides. Create \
    # version-specific symlinks so the dynamic loader resolves them. \
    # CAUTION: this spoofs SONAMEs — acceptable here because bd is the \
    # only consumer, but do not apply this pattern system-wide. \
    if ! bd version >/dev/null 2>&1; then \
      MULTIARCH="$(dpkg-architecture -qDEB_HOST_MULTIARCH 2>/dev/null || echo x86_64-linux-gnu)"; \
      LOCAL_ICU=$(ldconfig -p | grep -oP 'libicui18n\.so\.\K[0-9]+' | head -1); \
      NEEDED_ICU=$(ldd /usr/local/bin/bd 2>/dev/null | grep -oP 'libicui18n\.so\.\K[0-9]+' || true); \
      if [ -n "$LOCAL_ICU" ] && [ -n "$NEEDED_ICU" ] && [ "$LOCAL_ICU" != "$NEEDED_ICU" ]; then \
        for lib in libicui18n libicuuc libicudata; do \
          ln -sf "/lib/${MULTIARCH}/${lib}.so.${LOCAL_ICU}" \
                  "/lib/${MULTIARCH}/${lib}.so.${NEEDED_ICU}"; \
        done; \
        ldconfig; \
      fi; \
    fi; \
    bd version

# Install opencode (AI coding agent — https://opencode.ai)
# renovate: datasource=github-releases depName=anomalyco/opencode
ARG OPENCODE_VERSION=v1.18.10
# SHA-256 digests for supply-chain integrity verification (update on version bump)
ARG OPENCODE_SHA256_AMD64=6b1113da704253fb4da12b41e4236acecb9f2b62949c945f6eeacaa15111b976
ARG OPENCODE_SHA256_ARM64=41ae3041e91b894e4c0dc06a73a9a2796254bf390ffb99626a43af5e2912d170
RUN set -eux; \
    ARCH=$(dpkg --print-architecture); \
    case "${ARCH}" in \
      amd64) ARCH_NAME='x64';   EXPECTED_SHA="${OPENCODE_SHA256_AMD64}" ;; \
      arm64) ARCH_NAME='arm64'; EXPECTED_SHA="${OPENCODE_SHA256_ARM64}" ;; \
      *) echo "Unsupported architecture: ${ARCH}" >&2; exit 1 ;; \
    esac; \
    TARBALL="/tmp/opencode-linux-${ARCH_NAME}.tar.gz"; \
    curl -fsSL \
      "https://github.com/anomalyco/opencode/releases/download/${OPENCODE_VERSION}/opencode-linux-${ARCH_NAME}.tar.gz" \
      -o "${TARBALL}"; \
    echo "${EXPECTED_SHA}  ${TARBALL}" | sha256sum -c -; \
    tar -xzf "${TARBALL}" -C /tmp opencode; \
    install -m 755 /tmp/opencode /usr/local/bin/opencode; \
    rm -f /tmp/opencode "${TARBALL}"; \
    opencode --version

# Install Claude Code CLI (Anthropic — https://claude.com/claude-code)
# The installer downloads the CLI binary and verifies it against a SHA-256
# checksum from Anthropic's release manifest before installing. We pin the CLI
# version (passed through to the installer) so builds are reproducible; bump via
# Renovate. The bootstrap script itself is fetched over TLS from claude.ai and
# is trusted rather than checksum-pinned — unlike task/dolt/bd/opencode above,
# which all verify a SHA-256 digest of the downloaded tarball before use.
# Accepted gap: Anthropic does not publish a stable checksum for install.sh,
# and this stage never runs in CI (INSTALL_CLAUDE_CODE=false there), so blast
# radius is limited to local/interactive devcontainer builds. Revisit if a
# pinned checksum becomes available upstream.
# renovate: datasource=npm depName=@anthropic-ai/claude-code
ARG CLAUDE_CODE_VERSION=2.1.220
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
      bash "${INSTALLER}" "${CLAUDE_CODE_VERSION}"; \
      rm -f "${INSTALLER}"; \
      # The installer places the binary at "${HOME}/.local/bin/claude" and only
      # advises adding that dir to PATH via shell rc files (~/.bashrc etc).
      # Non-interactive Docker RUN layers never source those, so `claude` is
      # not found in later RUN steps (or in non-login CI/devcontainer shells).
      # Symlink into /usr/local/bin, already on PATH everywhere, matching how
      # task/dolt/bd/opencode are installed above.
      ln -sf "${HOME}/.local/bin/claude" /usr/local/bin/claude; \
    fi

# Configure uv to use project-local virtual environments
ENV UV_PROJECT_ENVIRONMENT="/workspaces/cosalette-apps/.venv"

# Create .vscode-server directory with proper ownership
# This prevents permission issues when volumes are mounted
RUN mkdir -p /home/vscode/.vscode-server /home/vscode/.vscode-server/extensions \
    && chown -R vscode:vscode /home/vscode/.vscode-server

# Verify installations
RUN set -eux; \
    uv --version && python --version && task --version && fzf --version && dolt version && bd version && opencode --version; \
    if [ "${INSTALL_CLAUDE_CODE}" = "true" ]; then claude --version; fi
