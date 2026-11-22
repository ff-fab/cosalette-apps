#!/bin/bash
# Post-start hook: runs tooling startup tasks on every container start.
set -euo pipefail

cd /workspaces/cosalette-apps

# Beads startup: only runs when bd is available.
if command -v bd >/dev/null 2>&1; then
    if [ -d ".beads" ]; then
        # Fix permissions: Docker bind-mounts (especially on WSL/NTFS) may set group-
        # readable bits that bd warns about. Best effort only: startup must continue
        # even when stat/chmod is unsupported or the directory is not writable.
        beads_mode=""
        if beads_mode="$(stat -c '%a' .beads 2>/dev/null)"; then
            if [ "$beads_mode" != "700" ]; then
                chmod 700 .beads 2>/dev/null || true
            fi
        fi

        removed=0
        if [ -S ".beads/bd.sock" ]; then
            rm -f .beads/bd.sock
            removed=1
        fi

        if [ -f ".beads/daemon.pid" ]; then
            rm -f .beads/daemon.pid
            removed=1
        fi

        if [ -f ".beads/daemon.lock" ]; then
            rm -f .beads/daemon.lock
            removed=1
        fi

        if [ "$removed" -eq 1 ]; then
            echo "✅ Cleaned legacy Beads daemon artifacts"
        fi
    fi

    # Start the beads dolt SQL server on the port pinned by BEADS_DOLT_SERVER_PORT
    # (see devcontainer.json, cap-fp5u). bd does not auto-start dolt on a pinned
    # port, so this start is what gives bd and the VSCode extension a server.
    # `bd dolt start` is idempotent, so a failure here is real; warn, never block.
    if command -v dolt >/dev/null 2>&1; then
        if bd dolt start >/dev/null 2>&1; then
            echo "✅ Beads dolt server running"
        else
            echo "⚠️  bd dolt start failed; check 'bd dolt status' (recover: task beads:recover)"
        fi
    fi
else
    echo "⚠️  bd not found on PATH; skipping beads startup cleanup"
fi

# Check GitHub CLI auth — inform but never block startup.
if command -v gh >/dev/null 2>&1; then
    if ! gh auth status >/dev/null 2>&1; then
        echo "ℹ️ GitHub CLI is not authenticated."
        echo "   Run: gh auth login"
    fi
fi
