#!/usr/bin/env bash
# scripts/pre-pr.sh — Pre-PR quality gate (ADR-012)
#
# Change-scoped by default: scripts/pre-pr-scope.sh picks the apps (changed
# apps, or every app when a shared path changed) and the changed files. Steps
# that cannot be affected by the change are reported as [SKP]. CI still runs
# its own full checks and `ci-gate` stays the required status check.
#
# Shows concise live progress while routing detailed command output to
# PRE_PR_LOG. On failure or timeout, tails the log automatically.
# Always prints pre-pr-exit=<rc> so agents can parse the final status.
#
# Env vars (with defaults):
#   PRE_PR_LOG          path to the detailed log  (default: /tmp/cosalette-pre-pr.log)
#   PRE_PR_TAIL_LINES   lines to tail on failure  (default: 120)
#   PRE_PR_FULL=1       check everything          (task pre-pr:full)
#   PRE_PR_APPS="a b"   check exactly these apps  (task pre-pr APPS="a b")
#   PRE_PR_BASE_REF     ref to diff against       (default: origin/main)
#
# Invoked by: task pre-pr, task pre-pr:full

# Note: -e intentionally omitted; rc is captured explicitly so the
# EXIT trap always runs and pre-pr-exit=<rc> is always printed.
set -uo pipefail

PRE_PR_LOG="${PRE_PR_LOG:-/tmp/cosalette-pre-pr.log}"
PRE_PR_TAIL_LINES="${PRE_PR_TAIL_LINES:-120}"

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

_script_start=$(date +%s)
_final_rc=0

# shellcheck disable=SC2329  # invoked by the EXIT trap below
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

skip_step() {
    printf '  [SKP] %s  (%s)\n' "$1" "$2"
}

# ── Steps (first failure stops the chain) ─────────────────────────────────────

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

_security() {
    if [ "$SCOPE_MODE" = full ]; then
        run_step "security:audit" "$TIMEOUT_SECURITY" task security:audit
        return
    fi
    run_step "security:python" "$TIMEOUT_SECURITY" task security:python || return
    if scope_touches '.github/workflows/*' '.github/actions/*'; then
        run_step "security:actions" "$TIMEOUT_SECURITY" task security:actions || return
    else
        skip_step "security:actions" "no workflow change"
    fi
    if scope_touches uv.lock pyproject.toml 'apps/*/pyproject.toml'; then
        run_step "security:deps" "$TIMEOUT_SECURITY" task security:deps
    else
        skip_step "security:deps" "no uv.lock or pyproject.toml change"
    fi
}

_steps() {
    local apps="$SCOPE_APPS"

    _precommit                                                              || return
    run_step "reuse:lint"   "$TIMEOUT_LINT"      task reuse:lint            || return
    run_step "lint (root)"  "$TIMEOUT_LINT"      task lint                  || return
    if [ -n "$apps" ]; then
        run_step "lint:all"      "$TIMEOUT_LINT"      task lint:all ONLY_APPS="$apps"      || return
        run_step "typecheck:all" "$TIMEOUT_TYPECHECK" task typecheck:all ONLY_APPS="$apps" || return
    else
        skip_step "lint:all, typecheck:all" "no app selected"
    fi
    run_step "test:unit (root)" "$TIMEOUT_TEST"  task test:unit             || return
    if [ -n "$apps" ]; then
        run_step "test:apps"     "$TIMEOUT_TEST"      task test:apps ONLY_APPS="$apps"     || return
    else
        skip_step "test:apps" "no app selected"
    fi
    if scope_touches 'scripts/*' '.github/*' Taskfile.yml 'taskfiles/*' \
        REUSE.toml uv.lock release-please-config.json; then
        run_step "test:scripts" "$TIMEOUT_TEST"  task test:scripts          || return
    else
        skip_step "test:scripts" "no scripts or tooling change"
    fi
    if scope_touches 'packages/*' pyproject.toml uv.lock .flake8 Taskfile.yml; then
        run_step "complexity (root)" "$TIMEOUT_COMPLEXITY" task complexity  || return
    else
        skip_step "complexity (root)" "no root package change"
    fi
    if [ -n "$apps" ]; then
        run_step "complexity:all" "$TIMEOUT_COMPLEXITY" task complexity:all ONLY_APPS="$apps" || return
    else
        skip_step "complexity:all" "no app selected"
    fi
    _docker_lint                                                            || return
    _security
}

_steps || _final_rc=$?

exit "$_final_rc"
