#!/usr/bin/env bash
# scripts/tests/test_gpl_headers.sh — Focused tests for add_gpl_headers.py --check.
# Creates temporary git repos to exercise GPL and non-GPL path detection.
#
# Run: bash scripts/tests/test_gpl_headers.sh
# Exit code: 0 = all pass, 1 = at least one failure

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/add_gpl_headers.py"
PASS=0
FAIL=0

# ── Minimal test harness ──────────────────────────────────────────────────────

_pass() { printf "  [ OK] %s\n" "$1"; PASS=$(( PASS + 1 )); }
_fail() { printf "  [ERR] %s\n" "$1"; FAIL=$(( FAIL + 1 )); }

assert_exit_eq() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        _pass "$desc"
    else
        _fail "$desc — expected exit=$expected got=$actual"
    fi
}

assert_contains() {
    local desc="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF "$needle"; then
        _pass "$desc"
    else
        _fail "$desc — '$needle' not found in output"
    fi
}

assert_not_contains() {
    local desc="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF "$needle"; then
        _fail "$desc — '$needle' unexpectedly found in output"
    else
        _pass "$desc"
    fi
}

# ── Helpers ───────────────────────────────────────────────────────────────────

# Write a minimal REUSE.toml with gpl-app (GPL) and mit-app (MIT).
_write_reuse_toml() {
    local dir="$1"
    cat > "$dir/REUSE.toml" << 'TOML'
version = 1

[[annotations]]
path = ["apps/gpl-app/**"]
SPDX-FileCopyrightText = "2026 Test"
SPDX-License-Identifier = "GPL-3.0-or-later"

[[annotations]]
path = ["apps/mit-app/**"]
SPDX-FileCopyrightText = "2026 Test"
SPDX-License-Identifier = "MIT"
TOML
}

_run_check() {
    local repo="$1"
    local out rc
    out=$(uv run --project "$REPO_ROOT" "$repo/scripts/add_gpl_headers.py" --check 2>&1)
    rc=$?
    printf '%s\nEXIT:%d\n' "$out" "$rc"
}

_exit_code() {
    echo "$1" | grep -oE 'EXIT:[0-9]+' | tail -1 | cut -d: -f2
}

# ── Tests ─────────────────────────────────────────────────────────────────────

printf "\n=== add_gpl_headers.py --check ===\n"

GPL_MARKER="# This program is free software: you can redistribute it and/or modify"

# ── Test 1: GPL-path file missing header → exit 1, message about missing ─────
printf "\n-- Test 1: GPL file without header fails --\n"
T1=$(mktemp -d)
git init "$T1" -q
git -C "$T1" config user.email "test@test.com"
git -C "$T1" config user.name "Test"
mkdir -p "$T1/scripts" "$T1/apps/gpl-app"
cp "$SCRIPT" "$T1/scripts/add_gpl_headers.py"
_write_reuse_toml "$T1"
printf 'x = 1\n' > "$T1/apps/gpl-app/main.py"
git -C "$T1" add .
git -C "$T1" commit -m "init" -q
OUT1=$(_run_check "$T1")
RC1=$(_exit_code "$OUT1")
[ -z "$RC1" ] && { _fail "Test 1: _run_check produced no EXIT code"; rm -rf "$T1"; } ||
assert_exit_eq "GPL file missing header: exits 1" "1" "$RC1"
assert_contains "GPL file missing header: names the file" "apps/gpl-app/main.py" "$OUT1"
rm -rf "$T1"

# ── Test 2: non-GPL-path file with GPL marker → exit 1, contamination msg ────
printf "\n-- Test 2: non-GPL file with GPL marker fails --\n"
T2=$(mktemp -d)
git init "$T2" -q
git -C "$T2" config user.email "test@test.com"
git -C "$T2" config user.name "Test"
mkdir -p "$T2/scripts" "$T2/apps/mit-app"
cp "$SCRIPT" "$T2/scripts/add_gpl_headers.py"
_write_reuse_toml "$T2"
# Write a GPL header into a non-GPL file
printf '%s\n\nx = 1\n' "$GPL_MARKER" > "$T2/apps/mit-app/oops.py"
git -C "$T2" add .
git -C "$T2" commit -m "init" -q
OUT2=$(_run_check "$T2")
RC2=$(_exit_code "$OUT2")
[ -z "$RC2" ] && { _fail "Test 2: _run_check produced no EXIT code"; rm -rf "$T2"; } ||
assert_exit_eq "non-GPL file with GPL marker: exits 1" "1" "$RC2"
assert_contains "non-GPL file with GPL marker: names the file" "apps/mit-app/oops.py" "$OUT2"
rm -rf "$T2"

# ── Test 3: non-GPL-path file without GPL marker → exit 0 ────────────────────
printf "\n-- Test 3: non-GPL file without GPL marker passes --\n"
T3=$(mktemp -d)
git init "$T3" -q
git -C "$T3" config user.email "test@test.com"
git -C "$T3" config user.name "Test"
mkdir -p "$T3/scripts" "$T3/apps/gpl-app" "$T3/apps/mit-app"
cp "$SCRIPT" "$T3/scripts/add_gpl_headers.py"
_write_reuse_toml "$T3"
# GPL file with proper header
printf '%s\n\nx = 1\n' "$GPL_MARKER" > "$T3/apps/gpl-app/main.py"
# non-GPL file without GPL header
printf 'x = 1\n' > "$T3/apps/mit-app/clean.py"
git -C "$T3" add .
git -C "$T3" commit -m "init" -q
OUT3=$(_run_check "$T3")
RC3=$(_exit_code "$OUT3")
[ -z "$RC3" ] && { _fail "Test 3: _run_check produced no EXIT code"; rm -rf "$T3"; } ||
assert_exit_eq "non-GPL file without GPL marker: exits 0" "0" "$RC3"
assert_not_contains "non-GPL file without GPL marker: not listed" "apps/mit-app/clean.py" "$OUT3"
rm -rf "$T3"

# ── Test 4: _version.py skipped even in GPL path or with GPL marker ───────────
printf "\n-- Test 4: _version.py files are skipped --\n"
T4=$(mktemp -d)
git init "$T4" -q
git -C "$T4" config user.email "test@test.com"
git -C "$T4" config user.name "Test"
mkdir -p "$T4/scripts" "$T4/apps/gpl-app" "$T4/apps/mit-app"
cp "$SCRIPT" "$T4/scripts/add_gpl_headers.py"
_write_reuse_toml "$T4"
# _version.py in GPL path without header → should be skipped (not flagged missing)
printf 'x = 1\n' > "$T4/apps/gpl-app/_version.py"
# _version.py in non-GPL path with GPL marker → should be skipped (not flagged contaminated)
printf '%s\n\nx = 1\n' "$GPL_MARKER" > "$T4/apps/mit-app/_version.py"
git -C "$T4" add .
git -C "$T4" commit -m "init" -q
OUT4=$(_run_check "$T4")
RC4=$(_exit_code "$OUT4")
[ -z "$RC4" ] && { _fail "Test 4: _run_check produced no EXIT code"; rm -rf "$T4"; } ||
assert_exit_eq "_version.py files skipped: exits 0" "0" "$RC4"
assert_not_contains "_version.py in GPL path not flagged" "_version.py" "$OUT4"
rm -rf "$T4"

# ── Test 5: MIT-only REUSE.toml + non-GPL app file with GPL marker → exit 1 ──
printf "\n-- Test 5: MIT-only REUSE.toml with GPL marker in app file fails --\n"
T5=$(mktemp -d)
git init "$T5" -q
git -C "$T5" config user.email "test@test.com"
git -C "$T5" config user.name "Test"
mkdir -p "$T5/scripts" "$T5/apps/mit-app"
cp "$SCRIPT" "$T5/scripts/add_gpl_headers.py"
cat > "$T5/REUSE.toml" << 'TOML'
version = 1

[[annotations]]
path = ["apps/mit-app/**"]
SPDX-FileCopyrightText = "2026 Test"
SPDX-License-Identifier = "MIT"
TOML
printf '%s\n\nx = 1\n' "$GPL_MARKER" > "$T5/apps/mit-app/oops.py"
git -C "$T5" add .
git -C "$T5" commit -m "init" -q
OUT5=$(_run_check "$T5")
RC5=$(_exit_code "$OUT5")
[ -z "$RC5" ] && { _fail "Test 5: _run_check produced no EXIT code"; rm -rf "$T5"; } ||
assert_exit_eq "MIT-only REUSE.toml with GPL marker: exits 1" "1" "$RC5"
assert_contains "MIT-only REUSE.toml with GPL marker: names the file" "apps/mit-app/oops.py" "$OUT5"
rm -rf "$T5"

# ── Test 6: GPL-path .sh file missing header → exit 1, message about missing ──
printf "\n-- Test 6: GPL .sh file without header fails --\n"
T6=$(mktemp -d)
git init "$T6" -q
git -C "$T6" config user.email "test@test.com"
git -C "$T6" config user.name "Test"
mkdir -p "$T6/scripts" "$T6/apps/gpl-app"
cp "$SCRIPT" "$T6/scripts/add_gpl_headers.py"
_write_reuse_toml "$T6"
printf '#!/usr/bin/env bash\necho hello\n' > "$T6/apps/gpl-app/run.sh"
git -C "$T6" add .
git -C "$T6" commit -m "init" -q
OUT6=$(_run_check "$T6")
RC6=$(_exit_code "$OUT6")
[ -z "$RC6" ] && { _fail "Test 6: _run_check produced no EXIT code"; rm -rf "$T6"; } ||
assert_exit_eq "GPL .sh file missing header: exits 1" "1" "$RC6"
assert_contains "GPL .sh file missing header: names the file" "apps/gpl-app/run.sh" "$OUT6"
rm -rf "$T6"

# ── Test 7: non-GPL-path .sh file with GPL marker → exit 1, contamination msg ─
printf "\n-- Test 7: non-GPL .sh file with GPL marker fails --\n"
T7=$(mktemp -d)
git init "$T7" -q
git -C "$T7" config user.email "test@test.com"
git -C "$T7" config user.name "Test"
mkdir -p "$T7/scripts" "$T7/apps/mit-app"
cp "$SCRIPT" "$T7/scripts/add_gpl_headers.py"
_write_reuse_toml "$T7"
printf '#!/usr/bin/env bash\n%s\necho hello\n' "$GPL_MARKER" > "$T7/apps/mit-app/oops.sh"
git -C "$T7" add .
git -C "$T7" commit -m "init" -q
OUT7=$(_run_check "$T7")
RC7=$(_exit_code "$OUT7")
[ -z "$RC7" ] && { _fail "Test 7: _run_check produced no EXIT code"; rm -rf "$T7"; } ||
assert_exit_eq "non-GPL .sh file with GPL marker: exits 1" "1" "$RC7"
assert_contains "non-GPL .sh file with GPL marker: names the file" "apps/mit-app/oops.sh" "$OUT7"
rm -rf "$T7"

# ── Summary ───────────────────────────────────────────────────────────────────

printf "\n%d passed, %d failed\n" "$PASS" "$FAIL"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
