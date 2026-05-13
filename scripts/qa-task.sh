#!/usr/bin/env bash
# scripts/qa-task.sh — Durable QA task wrapper
#
# Runs a named QA task with per-task logging, status capture, and optional
# timeouts. Delegates to existing Taskfile tasks for orchestration; runs
# security tools directly for atomic leaf operations.
#
# Usage: bash scripts/qa-task.sh <task-name> [args...]
#
# Built-in tasks:
#   lint              Delegate to: task lint
#   typecheck         Delegate to: task typecheck
#   test              Delegate to: task test
#   complexity        Delegate to: task complexity
#   pre-pr            Delegate to: bash scripts/pre-pr.sh
#   security:audit    Orchestrate: deps + secrets + python + actions
#   security:deps     Run pip-audit on the workspace
#   security:secrets  Run detect-secrets audit against .secrets.baseline
#   security:python   Run ruff --select S on root + all app source directories
#   security:actions  Run actionlint + zizmor on .github/workflows

set -euo pipefail

TASK_NAME="${1:-}"
if [ -z "$TASK_NAME" ]; then
    echo "Usage: $0 <task-name>" >&2
    exit 1
fi

LOG_DIR="${QA_LOG_DIR:-.qa-logs}"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)_$$
SAFE_TASK="${TASK_NAME//:/--}"
LOG_FILE="$LOG_DIR/${SAFE_TASK}_${TIMESTAMP}.log"
STATUS_FILE="$LOG_DIR/${SAFE_TASK}.status"

run_with_log() {
    local label="$1"
    shift
    echo "==> [$label] $*" | tee -a "$LOG_FILE"
    # pipefail: pipeline exits nonzero if "$@" fails, even though tee succeeds
    if "$@" 2>&1 | tee -a "$LOG_FILE"; then
        echo "==> [$label] OK" | tee -a "$LOG_FILE"
        return 0
    else
        local rc=$?
        echo "==> [$label] FAILED (exit $rc)" | tee -a "$LOG_FILE"
        return $rc
    fi
}

run_task() {
    local rc=0
    run_with_log "$@" || rc=$?
    echo "$rc" > "$STATUS_FILE"
    return $rc
}

# ── Security leaf helpers ──────────────────────────────────────────────────────

_do_security_deps() {
    local cache="${PIP_AUDIT_CACHE_DIR:-.cache/pip-audit}"
    mkdir -p "$cache"
    uv export --format requirements-txt --all-packages --all-extras --all-groups --no-emit-workspace --no-hashes \
        | uv run pip-audit -r /dev/stdin --progress-spinner off --timeout 10 --cache-dir "$cache"
}

_do_security_secrets() {
    local baseline=.secrets.baseline
    if [ ! -f "$baseline" ]; then
        echo "ERROR: .secrets.baseline not found — create it with: uv run detect-secrets scan > .secrets.baseline" >&2
        return 1
    fi
    { git ls-files -z; git ls-files --others --exclude-standard -z; } | \
        xargs -0 uv run detect-secrets-hook --baseline "$baseline" --
}

_do_security_python() {
    local src_dirs=()
    [ -d "packages/src" ] && src_dirs+=("packages/src")
    for app_src in apps/*/packages/src; do
        [ -d "$app_src" ] && src_dirs+=("$app_src")
    done
    if [ ${#src_dirs[@]} -eq 0 ]; then
        echo "No source directories found — skipping"
        return 0
    fi
    uv run ruff check --select S --no-config "${src_dirs[@]}"
}

_do_security_actions() {
    local rc=0
    uv run actionlint .github/workflows/*.yml || rc=$?
    uv run zizmor \
        --min-severity high \
        --min-confidence high \
        --no-progress \
        .github/workflows \
        .github/actions || rc=$?
    return $rc
}

# ──────────────────────────────────────────────────────────────────────────────

case "$TASK_NAME" in
    lint)
        run_task lint task lint
        ;;

    typecheck)
        run_task typecheck task typecheck
        ;;

    test)
        run_task test task test
        ;;

    complexity)
        run_task complexity task complexity
        ;;

    pre-pr)
        run_task pre-pr bash scripts/pre-pr.sh
        ;;

    security:deps)
        run_task security:deps _do_security_deps
        ;;

    security:secrets)
        run_task security:secrets _do_security_secrets
        ;;

    security:python)
        run_task security:python _do_security_python
        ;;

    security:actions)
        run_task security:actions _do_security_actions
        ;;

    security:audit)
        echo "==> [security:audit] Running full security audit (parallel)..." | tee -a "$LOG_FILE"
        # Run all four checks in parallel; collect exit codes via PIDs
        _do_security_deps    >> "$LOG_FILE" 2>&1 & PID_DEPS=$!
        _do_security_secrets >> "$LOG_FILE" 2>&1 & PID_SEC=$!
        _do_security_python  >> "$LOG_FILE" 2>&1 & PID_PY=$!
        _do_security_actions >> "$LOG_FILE" 2>&1 & PID_ACT=$!

        AUDIT_FAILURES=()
        wait $PID_DEPS    || AUDIT_FAILURES+=(security:deps)
        wait $PID_SEC     || AUDIT_FAILURES+=(security:secrets)
        wait $PID_PY      || AUDIT_FAILURES+=(security:python)
        wait $PID_ACT     || AUDIT_FAILURES+=(security:actions)

        if [ ${#AUDIT_FAILURES[@]} -gt 0 ]; then
            echo "==> [security:audit] FAILED: ${AUDIT_FAILURES[*]}" | tee -a "$LOG_FILE"
            echo "1" > "$STATUS_FILE"
            exit 1
        fi
        echo "==> [security:audit] All checks passed" | tee -a "$LOG_FILE"
        echo "0" > "$STATUS_FILE"
        ;;

    *)
        echo "Unknown QA task: '$TASK_NAME'" >&2
        echo "Available: lint typecheck test complexity pre-pr security:audit security:deps security:secrets security:python security:actions" >&2
        exit 1
        ;;
esac
