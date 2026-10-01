#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Fabian Koerner <mail@fabiankoerner.com>
# SPDX-License-Identifier: MIT
#
# Self-contained regression tests for beads-recover.sh and release-please lock
# version selectors. No external shell test framework is required.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RECOVER_SCRIPT="$REPO_ROOT/scripts/beads-recover.sh"
PASS=0
FAIL=0

_pass() { printf '  [ OK] %s\n' "$1"; PASS=$((PASS + 1)); }
_fail() { printf '  [ERR] %s\n' "$1"; FAIL=$((FAIL + 1)); }

assert_eq() {
    if [[ "$2" == "$3" ]]; then _pass "$1"; else _fail "$1 — expected=$2 got=$3"; fi
}

assert_contains() {
    if grep -qF "$2" <<<"$3"; then _pass "$1"; else _fail "$1 — missing '$2'"; fi
}

lock_package_count() {
    awk -v package="$1" '
        /^\[\[package\]\]/ {
            if (matches && has_version) count++
            matches = has_version = 0
        }
        $1 == "name" && $2 == "=" && split($0, fields, "\"") && fields[2] == package { matches = 1 }
        matches && /^version = "/ { has_version = 1 }
        END { if (matches && has_version) count++ }
        END { print count + 0 }
    ' "$REPO_ROOT/uv.lock"
}

TEST_DIR="$(mktemp -d)"
PIDS=()
cleanup() {
    local pid
    for pid in "${PIDS[@]}"; do
        kill -KILL "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT

make_fixture() {
    local name="$1"
    FIXTURE="$TEST_DIR/$name"
    BIN="$FIXTURE/bin"
    LOG="$FIXTURE/bd.log"
    mkdir -p "$BIN" "$FIXTURE/.beads/dolt"
    git -C "$FIXTURE" init -q
    ln -s /usr/bin/bash "$BIN/dolt"
    cat > "$FIXTURE/.beads/dolt/sql-server" <<'EOF'
trap 'exit 0' TERM
while :; do sleep 1; done
EOF
    chmod +x "$FIXTURE/.beads/dolt/sql-server"
    cat > "$BIN/bd" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$BD_LOG"
case "$*" in
  'dolt status') exit "${BD_STATUS_RC:-0}" ;;
  'dolt start') exit 0 ;;
esac
EOF
    chmod +x "$BIN/bd"
}

start_server() {
    local mode="${1:-exit}"
    if [[ "$mode" == ignore ]]; then
        sed -i "s/trap 'exit 0' TERM/trap '' TERM/" "$FIXTURE/.beads/dolt/sql-server"
    fi
    (
        cd "$FIXTURE/.beads/dolt" || exit
        PATH="$BIN:$PATH" exec -a dolt "$BIN/dolt" sql-server
    ) &
    SERVER_PID=$!
    PIDS+=("$SERVER_PID")
    sleep 0.05
}

run_recover() {
    (
        cd "$FIXTURE" || exit
        PATH="$BIN:$PATH" BD_LOG="$LOG" "$RECOVER_SCRIPT"
    ) 2>&1
}

start_count() {
    if [[ -f "$LOG" ]]; then
        grep -c '^dolt start$' "$LOG" || true
    else
        printf '0\n'
    fi
}

printf '\n=== beads-recover.sh ===\n'

make_fixture healthy
start_server
printf '%s\n' "$SERVER_PID" > "$FIXTURE/.beads/dolt-server.pid"
printf '3306\n' > "$FIXTURE/.beads/dolt-server.port"
OUT=$(run_recover); RC=$?
assert_eq 'healthy tracked server exits successfully' 0 "$RC"
assert_contains 'healthy tracked server does not restart' 'nothing to recover' "$OUT"
assert_eq 'healthy tracked server does not call start' 0 "$(start_count)"
kill -0 "$SERVER_PID" 2>/dev/null && _pass 'healthy tracked server remains running' || _fail 'healthy tracked server was stopped'

make_fixture orphan
start_server
ORPHAN_PID="$SERVER_PID"
(
    cd "$FIXTURE/.beads/dolt" || exit
    PATH="$BIN:$PATH" exec -a unrelated "$BIN/dolt" sql-server
) &
UNRELATED_PID=$!
PIDS+=("$UNRELATED_PID")
printf '999999\n' > "$FIXTURE/.beads/dolt-server.pid"
printf 'invalid\n' > "$FIXTURE/.beads/dolt-server.port"
OUT=$(run_recover); RC=$?
assert_eq 'stale metadata recovers successfully' 0 "$RC"
kill -0 "$ORPHAN_PID" 2>/dev/null && _fail 'matching orphan was stopped' || _pass 'matching orphan was stopped'
kill -0 "$UNRELATED_PID" 2>/dev/null && _pass 'non-dolt process was not stopped' || _fail 'non-dolt process was stopped'
assert_eq 'recovery starts a new server once' 1 "$(start_count)"
[[ ! -e "$FIXTURE/.beads/dolt-server.pid" && ! -e "$FIXTURE/.beads/dolt-server.port" ]] && _pass 'stale metadata is removed' || _fail 'stale metadata remains'

make_fixture timeout
start_server ignore
printf '999999\n' > "$FIXTURE/.beads/dolt-server.pid"
printf '3306\n' > "$FIXTURE/.beads/dolt-server.port"
OUT=$(BEADS_RECOVER_TERM_ATTEMPTS=2 BEADS_RECOVER_TERM_INTERVAL=0.01 run_recover); RC=$?
assert_eq 'TERM timeout fails recovery' 1 "$RC"
assert_contains 'TERM timeout is reported' 'did not exit' "$OUT"
assert_eq 'TERM timeout does not restart server' 0 "$(start_count)"

printf '\n=== release-please lock selectors ===\n'
mapfile -t apps < <(jq -r '.packages | to_entries[] | [.key, .value.component, (.value["extra-files"][] | select(.path == "/uv.lock") | .jsonpath)] | @tsv' "$REPO_ROOT/release-please-config.json")
for entry in "${apps[@]}"; do
    IFS=$'\t' read -r path component selector <<<"$entry"
    expected="$.package[?(@.name.value=='$component')].version"
    assert_eq "$path targets its own lock package" "$expected" "$selector"
    assert_eq "$component has exactly one versioned lock package" 1 "$(lock_package_count "$component")"
done
assert_eq 'each app has one distinct lock selector' "${#apps[@]}" "$(printf '%s\n' "${apps[@]}" | cut -f3 | sort -u | wc -l | tr -d ' ')"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
