#!/bin/bash
# Post-start cleanup script for devcontainer
# Runs on every container start (including restarts) to clean stale artifacts
# from the previous session.
set -euo pipefail

cd /workspace

if ! command -v bd >/dev/null 2>&1; then
    echo "⚠️  bd not found on PATH; skipping beads startup cleanup"
    exit 0
fi

if [ ! -d ".beads" ]; then
    exit 0
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

# Ensure Dolt sql-server is running (required for beads operations).
# bd manages the Dolt lifecycle (port, PID, logs) — never start dolt directly.
if command -v bd >/dev/null 2>&1 && command -v dolt >/dev/null 2>&1 && [ -d ".beads/dolt" ]; then
    if ! bd dolt test --quiet 2>/dev/null; then
        echo "🔮 Starting Dolt server..."
        if bd dolt start; then
            echo "✅ Dolt server started"
        else
            echo "⚠️  Dolt server failed to start (check bd dolt logs)"
        fi
    fi
fi
