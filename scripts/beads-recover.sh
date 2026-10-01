#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Fabian Koerner <mail@fabiankoerner.com>
# SPDX-License-Identifier: MIT
#
# Recover bd from an orphaned dolt sql-server (cap-bqfr).
#
# bd can lose .beads/dolt-server.pid while the server it started keeps the
# database lock. bd then auto-starts a new server on every call, and each one
# fails with 'database "dolt" is locked by another dolt process'. This script
# stops the orphan (never touching the database or its lock files) and lets bd
# start a server it tracks again.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
dolt_dir="$PWD/.beads/dolt"
pid_file=.beads/dolt-server.pid

if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "✓ bd tracks a live dolt server (PID $(cat "$pid_file")); nothing to recover"
    exit 0
fi

orphans=()
for proc in /proc/[0-9]*; do
    [[ "$(readlink "$proc/cwd" 2>/dev/null)" == "$dolt_dir" ]] || continue
    tr '\0' ' ' <"$proc/cmdline" 2>/dev/null | grep -q 'sql-server' || continue
    orphans+=("${proc#/proc/}")
done

for pid in "${orphans[@]}"; do
    echo "Stopping orphaned dolt sql-server (PID $pid)…"
    kill -TERM "$pid"
done
for pid in "${orphans[@]}"; do
    for _ in {1..20}; do
        kill -0 "$pid" 2>/dev/null || continue 2
        sleep 0.5
    done
    echo "✗ dolt sql-server (PID $pid) did not exit within 10 s" >&2
    exit 1
done

bd dolt start
bd dolt status
