#!/bin/bash
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
