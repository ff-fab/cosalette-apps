#!/usr/bin/env bash
# scripts/pre-pr.sh — Pre-PR quality gate
#
# Shows concise live progress while routing detailed command output to
# PRE_PR_LOG. On failure or timeout, tails the log automatically.
# Always prints pre-pr-exit=<rc> so agents can parse the final status.
#
# Env vars (with defaults):
#   PRE_PR_LOG          path to the detailed log  (default: /tmp/cosalette-pre-pr.log)
#   PRE_PR_TAIL_LINES   lines to tail on failure  (default: 120)
#
# Invoked by: task pre-pr

# Note: -e intentionally omitted; rc is captured explicitly so the
# EXIT trap always runs and pre-pr-exit=<rc> is always printed.
set -uo pipefail

PRE_PR_LOG="${PRE_PR_LOG:-/tmp/cosalette-pre-pr.log}"
PRE_PR_TAIL_LINES="${PRE_PR_TAIL_LINES:-120}"

TIMEOUT_PRECOMMIT="${TIMEOUT_PRECOMMIT:-300}"   # 5 min
TIMEOUT_LINT="${TIMEOUT_LINT:-120}"             # 2 min
TIMEOUT_TYPECHECK="${TIMEOUT_TYPECHECK:-180}"   # 3 min
TIMEOUT_TEST="${TIMEOUT_TEST:-600}"             # 10 min
TIMEOUT_COMPLEXITY="${TIMEOUT_COMPLEXITY:-60}"  # 1 min
TIMEOUT_SIMILARITY="${TIMEOUT_SIMILARITY:-60}"  # 1 min
TIMEOUT_SECURITY="${TIMEOUT_SECURITY:-300}"     # 5 min

# Detect GNU timeout --foreground support once
declare -a _TIMEOUT_EXTRA=()
if command -v timeout >/dev/null 2>&1; then
    if timeout --foreground --kill-after=30s 1 true 2>/dev/null; then
        _TIMEOUT_EXTRA=(--foreground --kill-after=30s)
    fi
else
    echo "WARN: 'timeout' command not found — per-step timeouts are disabled" >&2
fi

# ── Logging setup ─────────────────────────────────────────────────────────────

mkdir -p "$(dirname "$PRE_PR_LOG")"
: > "$PRE_PR_LOG"

_script_start=$(date +%s)
_final_rc=0

_on_exit() {
    local elapsed=$(( $(date +%s) - _script_start ))
    echo ""
    if [ "$_final_rc" -eq 0 ]; then
        printf '[DONE] All pre-PR checks passed  (%ds)\n' "$elapsed"
    else
        printf '[FAIL] pre-PR gate failed  (%ds) -- see %s\n' "$elapsed" "$PRE_PR_LOG"
        echo ""
        echo "--- last $PRE_PR_TAIL_LINES lines of $PRE_PR_LOG ---"
        tail -n "$PRE_PR_TAIL_LINES" "$PRE_PR_LOG"
        echo "--- end log ---"
    fi
    printf '\npre-pr-exit=%s\n' "$_final_rc"
}
trap '_on_exit' EXIT

printf 'pre-pr  log=%s\n\n' "$PRE_PR_LOG"

# ── Step runner ───────────────────────────────────────────────────────────────

run_step() {
    local label="$1"
    local timeout_secs="$2"
    shift 2
    local t0
    t0=$(date +%s)
    printf '  -->  %s ...\n' "$label"
    printf '\n%s\n' "━━━ $label ━━━" >> "$PRE_PR_LOG"

    local rc=0
    if command -v timeout >/dev/null 2>&1; then
        timeout "${_TIMEOUT_EXTRA[@]}" "$timeout_secs" "$@" >> "$PRE_PR_LOG" 2>&1 || rc=$?
    else
        "$@" >> "$PRE_PR_LOG" 2>&1 || rc=$?
    fi

    local elapsed=$(( $(date +%s) - t0 ))
    if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
        printf '  [TIM] %s  (%ds)  TIMED OUT after %ss\n' "$label" "$elapsed" "$timeout_secs"
        printf '==> [%s] TIMED OUT after %ss (exit %s)\n' "$label" "$timeout_secs" "$rc" >> "$PRE_PR_LOG"
    elif [ "$rc" -ne 0 ]; then
        printf '  [ERR] %s  (%ds)\n' "$label" "$elapsed"
    else
        printf '  [ OK] %s  (%ds)\n' "$label" "$elapsed"
    fi

    return "$rc"
}

# ── Steps (first failure stops the chain) ─────────────────────────────────────

run_step "pre-commit (all files)"  "$TIMEOUT_PRECOMMIT"  pre-commit run --all-files &&
run_step "reuse:lint"              "$TIMEOUT_LINT"        task reuse:lint            &&
run_step "lint:all"                "$TIMEOUT_LINT"        task lint:all              &&
run_step "typecheck:all"           "$TIMEOUT_TYPECHECK"   task typecheck:all         &&
run_step "test:all"                "$TIMEOUT_TEST"        task test:all              &&
run_step "complexity"              "$TIMEOUT_COMPLEXITY"  task complexity            &&
run_step "similarity"              "$TIMEOUT_SIMILARITY"  task similarity            &&
run_step "security:audit"          "$TIMEOUT_SECURITY"    task security:audit        ||
_final_rc=$?

exit "$_final_rc"
