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
port_file=.beads/dolt-server.port
term_attempts="${BEADS_RECOVER_TERM_ATTEMPTS:-20}"
term_interval="${BEADS_RECOVER_TERM_INTERVAL:-0.5}"
dolt_command="$(command -v dolt)"
dolt_executable="$(readlink -f "$dolt_command")"

pid_is_live() {
    [[ "$1" =~ ^[0-9]+$ ]] && kill -0 "$1" 2>/dev/null
}

server_is_healthy() {
    local pid="$1" port
    [[ -f "$port_file" ]] || return 1
    port="$(<"$port_file")"
    [[ "$port" =~ ^[0-9]+$ ]] || return 1
    pid_is_live "$pid" && bd dolt status >/dev/null 2>&1
}

if [[ -f "$pid_file" ]]; then
    tracked_pid="$(<"$pid_file")"
    if server_is_healthy "$tracked_pid"; then
        echo "✓ bd tracks a healthy dolt server (PID $tracked_pid); nothing to recover"
        exit 0
    fi
fi

orphans=()
for proc in /proc/[0-9]*; do
    [[ "$(readlink "$proc/cwd" 2>/dev/null)" == "$dolt_dir" ]] || continue
    [[ "$(readlink -f "$proc/exe" 2>/dev/null)" == "$dolt_executable" ]] || continue
    mapfile -d '' -t argv <"$proc/cmdline" 2>/dev/null || continue
    [[ "$(basename "${argv[0]:-}")" == "$(basename "$dolt_command")" ]] || continue
    [[ "${argv[1]:-}" == "sql-server" ]] || continue
    orphans+=("${proc#/proc/}")
done

for pid in "${orphans[@]}"; do
    echo "Stopping orphaned dolt sql-server (PID $pid)…"
    kill -TERM "$pid"
done
for pid in "${orphans[@]}"; do
    for ((attempt = 0; attempt < term_attempts; attempt++)); do
        kill -0 "$pid" 2>/dev/null || continue 2
        sleep "$term_interval"
    done
    echo "✗ dolt sql-server (PID $pid) did not exit within $((term_attempts)) attempts" >&2
    exit 1
done

rm -f "$pid_file" "$port_file"
bd dolt start
bd dolt status
