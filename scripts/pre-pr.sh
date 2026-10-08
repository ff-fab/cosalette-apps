#!/usr/bin/env bash
# scripts/pre-pr.sh — Pre-PR quality gate (ADR-012)
#
# Change-scoped by default: scripts/pre-pr-scope.sh picks the apps (changed
# apps, or every app when a shared path changed) and the changed files. Steps
# that cannot be affected by the change are reported as [SKP]. CI still runs
# its own full checks and `ci-gate` stays the required status check.
#
# Runs in two phases: every cheap or I/O-bound check in parallel, then
# test:apps alone so the app tests never share the CPU with heavy steps.
# Every step runs, so all failures are reported. Result lines print in a
# fixed order; each step group logs to its own file under PRE_PR_LOG.steps/,
# and those logs are appended to PRE_PR_LOG in the same order. On failure or
# timeout, tails the log of every failed step group automatically.
# Always prints pre-pr-exit=<rc> so agents can parse the final status.
#
# Env vars (with defaults):
#   PRE_PR_LOG          path to the detailed log  (default: /tmp/cosalette-pre-pr.log)
#   PRE_PR_TAIL_LINES   lines to tail on failure  (default: 120)
#   PRE_PR_FULL=1       check everything          (task pre-pr:full)
#   PRE_PR_APPS="a b"   check exactly these apps  (task pre-pr APPS="a b")
#   PRE_PR_BASE_REF     ref to diff against       (default: origin/main)
#   PRE_PR_JOBS         parallel step groups      (default: nproc; 1 = sequential)
#
# Invoked by: task pre-pr, task pre-pr:full

# Functions run indirectly (the EXIT trap, run_phase "$g"):
# shellcheck disable=SC2329

# Note: -e intentionally omitted; rc is captured explicitly so the
# EXIT trap always runs and pre-pr-exit=<rc> is always printed.
set -uo pipefail

PRE_PR_LOG="${PRE_PR_LOG:-/tmp/cosalette-pre-pr.log}"
PRE_PR_TAIL_LINES="${PRE_PR_TAIL_LINES:-120}"
PRE_PR_JOBS="${PRE_PR_JOBS:-$(nproc 2>/dev/null || echo 4)}"
STEP_LOG_DIR="${PRE_PR_LOG}.steps"

TIMEOUT_PRECOMMIT="${TIMEOUT_PRECOMMIT:-300}"   # 5 min
TIMEOUT_LINT="${TIMEOUT_LINT:-120}"             # 2 min
TIMEOUT_TYPECHECK="${TIMEOUT_TYPECHECK:-180}"   # 3 min
TIMEOUT_TEST="${TIMEOUT_TEST:-600}"             # 10 min
TIMEOUT_COMPLEXITY="${TIMEOUT_COMPLEXITY:-120}" # 2 min
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
rm -rf "$STEP_LOG_DIR"
mkdir -p "$STEP_LOG_DIR"

_script_start=$(date +%s)
_final_rc=0
declare -a _failed_logs=()
_LIVE=0

_on_exit() {
    local elapsed=$(( $(date +%s) - _script_start ))
    echo ""
    if [ "$_final_rc" -eq 0 ]; then
        printf '[DONE] All pre-PR checks passed  (%ds)\n' "$elapsed"
    else
        printf '[FAIL] pre-PR gate failed  (%ds) -- see %s\n' "$elapsed" "$PRE_PR_LOG"
        echo ""
        local log
        for log in "${_failed_logs[@]:-$PRE_PR_LOG}"; do
            echo "--- last $PRE_PR_TAIL_LINES lines of $log ---"
            tail -n "$PRE_PR_TAIL_LINES" "$log"
            echo "--- end log ---"
        done
    fi
    printf '\npre-pr-exit=%s\n' "$_final_rc"
}
trap '_on_exit' EXIT

printf 'pre-pr  log=%s\n' "$PRE_PR_LOG"

# ── Scope ─────────────────────────────────────────────────────────────────────

# shellcheck source=scripts/pre-pr-scope.sh
. "$(dirname "$0")/pre-pr-scope.sh"
pre_pr_scope || { _final_rc=$?; exit "$_final_rc"; }

printf 'scope   %s: %s\n' "$SCOPE_MODE" "$SCOPE_REASON"
printf 'apps    %s\n' "${SCOPE_APPS:-(none)}"
[ -n "$SCOPE_BASE" ] && printf 'base    %s\n' "$(git rev-parse --short "$SCOPE_BASE")"
echo ""

# ── Step runner ───────────────────────────────────────────────────────────────

# run_step writes to STEP_LOG, the log of the step group it belongs to.
# _LIVE=1 (sequential mode) prints a "-->" line before each step starts.
run_step() {
    local label="$1"
    local timeout_secs="$2"
    shift 2
    local t0
    t0=$(date +%s)
    [ "$_LIVE" = 1 ] && printf '  -->  %s ...\n' "$label"
    printf '\n%s\n' "━━━ $label ━━━" >> "$STEP_LOG"

    local rc=0
    if command -v timeout >/dev/null 2>&1; then
        timeout "${_TIMEOUT_EXTRA[@]}" "$timeout_secs" "$@" >> "$STEP_LOG" 2>&1 || rc=$?
    else
        "$@" >> "$STEP_LOG" 2>&1 || rc=$?
    fi

    local elapsed=$(( $(date +%s) - t0 ))
    if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
        printf '  [TIM] %s  (%ds)  TIMED OUT after %ss\n' "$label" "$elapsed" "$timeout_secs"
        printf '==> [%s] TIMED OUT after %ss (exit %s)\n' "$label" "$timeout_secs" "$rc" >> "$STEP_LOG"
    elif [ "$rc" -ne 0 ]; then
        printf '  [ERR] %s  (%ds)\n' "$label" "$elapsed"
    else
        printf '  [ OK] %s  (%ds)\n' "$label" "$elapsed"
    fi

    return "$rc"
}

skip_step() {
    printf '  [SKP] %s  (%s)\n' "$1" "$2"
}

# run_phase GROUP... runs every step group, PRE_PR_JOBS at a time, and prints
# each group's result lines in the order given (not completion order). Every
# group runs even after a failure, so all failures are reported; the phase
# returns the rc of the first failing group in that order. Each group logs to
# its own file under STEP_LOG_DIR, appended to PRE_PR_LOG in the same order.
run_phase() {
    local -a groups=("$@")
    local g rc
    if [ "$PRE_PR_JOBS" -le 1 ] || [ "${#groups[@]}" -eq 1 ]; then
        for g in "${groups[@]}"; do
            rc=0
            _LIVE=1 STEP_LOG="$STEP_LOG_DIR/$g.log" "$g" || rc=$?
            echo "$rc" > "$STEP_LOG_DIR/$g.rc"
        done
    else
        printf '  -->  %d step groups in parallel (PRE_PR_JOBS=%s) ...\n' "${#groups[@]}" "$PRE_PR_JOBS"
        for g in "${groups[@]}"; do
            while [ "$(jobs -rp | wc -l)" -ge "$PRE_PR_JOBS" ]; do wait -n || true; done
            # No --foreground: the job has no TTY, and its own process group
            # lets timeout kill the whole step tree.
            (
                [ "${#_TIMEOUT_EXTRA[@]}" -gt 0 ] && _TIMEOUT_EXTRA=(--kill-after=30s)
                rc=0
                STEP_LOG="$STEP_LOG_DIR/$g.log" "$g" || rc=$?
                echo "$rc" > "$STEP_LOG_DIR/$g.rc"
            ) > "$STEP_LOG_DIR/$g.out" 2>&1 < /dev/null &
        done
        wait
        for g in "${groups[@]}"; do cat "$STEP_LOG_DIR/$g.out"; done
    fi
    local first=0
    for g in "${groups[@]}"; do
        rc=$(cat "$STEP_LOG_DIR/$g.rc" 2>/dev/null || echo 1)  # no rc: the group crashed
        [ -f "$STEP_LOG_DIR/$g.log" ] && cat "$STEP_LOG_DIR/$g.log" >> "$PRE_PR_LOG"
        if [ "$rc" -ne 0 ]; then
            _failed_logs+=("$STEP_LOG_DIR/$g.log")
            [ "$first" -eq 0 ] && first="$rc"
        fi
    done
    return "$first"
}

# ── Step groups (each one a unit of the parallel phase) ───────────────────────

# ruff/ruff-format and reuse run below as check-only tasks with the locked
# tool versions CI uses, so pre-commit skips its copies (and its ruff --fix
# never rewrites files here). The full run scans secrets in security:audit.
_precommit() {
    local skip="ruff,ruff-format,reuse"
    [ "$SCOPE_MODE" = full ] && skip="$skip,detect-secrets"
    skip="${SKIP:+$SKIP,}$skip"
    if scope_touches .pre-commit-config.yaml; then
        run_step "pre-commit (all files)" "$TIMEOUT_PRECOMMIT" \
            env SKIP="$skip" pre-commit run --all-files
        return
    fi
    local files
    mapfile -t files < <(scope_existing_files)
    if [ "${#files[@]}" -eq 0 ]; then
        skip_step "pre-commit" "no changed files"
        return 0
    fi
    run_step "pre-commit (${#files[@]} changed files, incl. detect-secrets)" "$TIMEOUT_PRECOMMIT" \
        env SKIP="$skip" pre-commit run --files "${files[@]}"
}

_reuse()     { run_step "reuse:lint"       "$TIMEOUT_LINT" task reuse:lint; }
_lint()      { run_step "lint (root)"      "$TIMEOUT_LINT" task lint; }
_test_unit() { run_step "test:unit (root)" "$TIMEOUT_TEST" task test:unit; }

_lint_apps() {
    run_step "lint:all" "$TIMEOUT_LINT" task lint:all ONLY_APPS="$SCOPE_APPS"
}

_typecheck_apps() {
    run_step "typecheck:all" "$TIMEOUT_TYPECHECK" task typecheck:all ONLY_APPS="$SCOPE_APPS"
}

_complexity_apps() {
    run_step "complexity:all" "$TIMEOUT_COMPLEXITY" task complexity:all ONLY_APPS="$SCOPE_APPS"
}

_test_apps() {
    run_step "test:apps" "$TIMEOUT_TEST" task test:apps ONLY_APPS="$SCOPE_APPS"
}

_test_scripts() {
    if scope_touches 'scripts/*' '.github/*' Taskfile.yml 'taskfiles/*' \
        REUSE.toml uv.lock release-please-config.json; then
        run_step "test:scripts" "$TIMEOUT_TEST" task test:scripts
    else
        skip_step "test:scripts" "no scripts or tooling change"
    fi
}

_complexity() {
    if scope_touches 'packages/*' pyproject.toml uv.lock .flake8 Taskfile.yml; then
        run_step "complexity (root)" "$TIMEOUT_COMPLEXITY" task complexity
    else
        skip_step "complexity (root)" "no root package change"
    fi
}

_docker_lint() {
    if scope_touches .hadolint.yaml; then
        run_step "docker:lint" "$TIMEOUT_LINT" task docker:lint
        return
    fi
    local files
    mapfile -t files < <(scope_existing_files .devcontainer/Dockerfile 'apps/*/Dockerfile')
    if [ "${#files[@]}" -eq 0 ]; then
        skip_step "docker:lint" "no Dockerfile changed"
        return 0
    fi
    run_step "docker:lint (${#files[@]} changed)" "$TIMEOUT_LINT" task docker:lint -- "${files[@]}"
}

# Runs every security step and returns the first failure's rc.
_security() {
    if [ "$SCOPE_MODE" = full ]; then
        run_step "security:audit" "$TIMEOUT_SECURITY" task security:audit
        return
    fi
    local rc=0 r
    run_step "security:python" "$TIMEOUT_SECURITY" task security:python || { r=$?; rc=$r; }
    if scope_touches '.github/workflows/*' '.github/actions/*'; then
        run_step "security:actions" "$TIMEOUT_SECURITY" task security:actions || { r=$?; [ "$rc" -eq 0 ] && rc=$r; }
    else
        skip_step "security:actions" "no workflow change"
    fi
    if scope_touches uv.lock pyproject.toml 'apps/*/pyproject.toml'; then
        run_step "security:deps" "$TIMEOUT_SECURITY" task security:deps || { r=$?; [ "$rc" -eq 0 ] && rc=$r; }
    else
        skip_step "security:deps" "no uv.lock or pyproject.toml change"
    fi
    return "$rc"
}

# ── Phases ────────────────────────────────────────────────────────────────────

# Phase 1: every cheap or I/O-bound check, in parallel.
# Phase 2: test:apps alone, so CPU-sensitive app tests (e.g. caldates2mqtt
# integration, cap-zh2o) never share the CPU with the heavy phase-1 steps.
_steps() {
    local -a phase1=(_precommit _reuse _lint)
    if [ -n "$SCOPE_APPS" ]; then
        phase1+=(_lint_apps _typecheck_apps)
    else
        skip_step "lint:all, typecheck:all, complexity:all, test:apps" "no app selected"
    fi
    phase1+=(_test_unit _test_scripts _complexity)
    [ -n "$SCOPE_APPS" ] && phase1+=(_complexity_apps)
    phase1+=(_docker_lint _security)

    local rc=0 r
    run_phase "${phase1[@]}" || rc=$?
    if [ -n "$SCOPE_APPS" ]; then
        run_phase _test_apps || { r=$?; [ "$rc" -eq 0 ] && rc=$r; }
    fi
    return "$rc"
}

_steps || _final_rc=$?

exit "$_final_rc"
