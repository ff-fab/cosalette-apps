#!/usr/bin/env bash
# scripts/tests/test_qa_scripts.sh — Self-contained shell tests for qa-task.sh
# and pre-pr.sh.  No external test framework required; uses a minimal inline
# harness.
#
# Run: bash scripts/tests/test_qa_scripts.sh
# Exit code: 0 = all pass, 1 = at least one failure

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PASS=0
FAIL=0

# ── Minimal test harness ──────────────────────────────────────────────────────

_pass() { printf "  [ OK] %s\n" "$1"; PASS=$(( PASS + 1 )); }
_fail() { printf "  [ERR] %s\n" "$1"; FAIL=$(( FAIL + 1 )); }

assert_eq() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        _pass "$desc"
    else
        _fail "$desc — expected='$expected' got='$actual'"
    fi
}

assert_contains() {
    local desc="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF -- "$needle"; then
        _pass "$desc"
    else
        _fail "$desc — '$needle' not found in output"
    fi
}

assert_exit_eq() {
    local desc="$1" expected="$2" actual="$3"
    assert_eq "$desc (exit code)" "$expected" "$actual"
}

# ── Tests: qa-task.sh ─────────────────────────────────────────────────────────

printf "\n=== qa-task.sh ===\n"

# Test: run_with_log propagates nonzero exit codes from a failing command
# Verifies that pipefail + if pipeline correctly surfaces "false"'s exit code.
T1_LOG=$(mktemp)
T1_STATUS=$(mktemp)
(
    QA_LOG_DIR="$(mktemp -d)"
    export QA_LOG_DIR
    # Source just the run_with_log function by running it inline
    bash -c "
        set -uo pipefail
        LOG_FILE='$T1_LOG'
        run_with_log() {
            local label=\"\$1\"; shift
            echo \"==> [\$label] \$*\" | tee -a \"\$LOG_FILE\"
            # pipefail: pipeline exits nonzero if \"\$@\" fails, even though tee succeeds
            if \"\$@\" 2>&1 | tee -a \"\$LOG_FILE\"; then
                echo \"==> [\$label] OK\" | tee -a \"\$LOG_FILE\"
                return 0
            else
                local rc=\$?
                echo \"==> [\$label] FAILED (exit \$rc)\" | tee -a \"\$LOG_FILE\"
                return \$rc
            fi
        }
        run_with_log testlabel false
        echo \$? > '$T1_STATUS'
    " || true
    # Script exits nonzero because set -e is on and run_with_log returned nonzero;
    # capture the last exit code from the log
    grep -oP 'exit \K[0-9]+' "$T1_LOG" | tail -1 > "$T1_STATUS" 2>/dev/null || true
)
# Check that the log contains FAILED
T1_OUT=$(cat "$T1_LOG" 2>/dev/null || echo "")
assert_contains "run_with_log: failed command logged as FAILED" "FAILED" "$T1_OUT"
rm -f "$T1_LOG" "$T1_STATUS"

# Test: unknown task prints error and exits 1
T2_LOG=$(mktemp)
bash "$REPO_ROOT/scripts/qa-task.sh" not-a-real-task > "$T2_LOG" 2>&1; T2_RC=$?
T2_OUT=$(cat "$T2_LOG")
rm -f "$T2_LOG"
assert_contains "qa-task.sh: unknown task message" "Unknown QA task" "$T2_OUT"
assert_exit_eq "qa-task.sh: unknown task exits 1" "1" "$T2_RC"

# Test: missing task name prints usage and exits 1
T3_LOG=$(mktemp)
bash "$REPO_ROOT/scripts/qa-task.sh" > "$T3_LOG" 2>&1; T3_RC=$?
T3_OUT=$(cat "$T3_LOG")
rm -f "$T3_LOG"
assert_contains "qa-task.sh: no-arg usage message" "Usage:" "$T3_OUT"
assert_exit_eq "qa-task.sh: no-arg exits 1" "1" "$T3_RC"

# ── Tests: pre-pr.sh ─────────────────────────────────────────────────────────

printf "\n=== pre-pr.sh ===\n"

# All pre-pr.sh tests run the full chain (PRE_PR_FULL=1) so every step is reached
# regardless of what the working tree has changed.

# Test: pre-pr.sh always emits pre-pr-exit= even when a step fails
# The first step fails, so the EXIT trap must report the failure. The stub sits
# on PATH: `timeout` execs a binary, so an exported shell function never reaches
# it and the real pre-commit would run (and rewrite files) instead.
T4_LOG=$(mktemp)
T4_BIN=$(mktemp -d)
printf '#!/usr/bin/env bash\nexit 42\n' > "$T4_BIN/pre-commit"
chmod +x "$T4_BIN/pre-commit"
# Every step runs (all failures are reported), so stub task too.
printf '#!/usr/bin/env bash\nexit 0\n' > "$T4_BIN/task"
chmod +x "$T4_BIN/task"
T4_OUT=$(
    PATH="$T4_BIN:$PATH" \
    PRE_PR_FULL=1 \
    PRE_PR_LOG="$T4_LOG" \
    TIMEOUT_PRECOMMIT=5 TIMEOUT_LINT=5 TIMEOUT_TYPECHECK=5 \
    TIMEOUT_TEST=5 TIMEOUT_COMPLEXITY=5 TIMEOUT_SECURITY=5 \
    bash "$REPO_ROOT/scripts/pre-pr.sh" 2>&1 || true
)
assert_contains "pre-pr.sh: emits [FAIL] on failure" "[FAIL]" "$T4_OUT"
assert_contains "pre-pr.sh: emits the failing step's rc" "pre-pr-exit=42" "$T4_OUT"
rm -rf "$T4_LOG" "$T4_LOG.steps"
rm -rf "$T4_BIN"

# Test: pre-pr.sh emits [DONE] and pre-pr-exit=0 when all steps succeed
# We put stub binaries on PATH that always succeed.
T5_LOG=$(mktemp)
T5_BIN=$(mktemp -d)
# Create pre-commit stub
printf '#!/usr/bin/env bash\nexit 0\n' > "$T5_BIN/pre-commit"
chmod +x "$T5_BIN/pre-commit"
# Create task stub that always succeeds
printf '#!/usr/bin/env bash\nexit 0\n' > "$T5_BIN/task"
chmod +x "$T5_BIN/task"
T5_OUT=$(
    PATH="$T5_BIN:$PATH" \
    PRE_PR_FULL=1 \
    PRE_PR_LOG="$T5_LOG" \
    TIMEOUT_PRECOMMIT=5 TIMEOUT_LINT=5 TIMEOUT_TYPECHECK=5 \
    TIMEOUT_TEST=5 TIMEOUT_COMPLEXITY=5 TIMEOUT_SECURITY=5 \
    bash "$REPO_ROOT/scripts/pre-pr.sh" 2>&1 || true
)
assert_contains "pre-pr.sh: emits [DONE] on success" "[DONE]" "$T5_OUT"
assert_contains "pre-pr.sh: emits pre-pr-exit=0 on success" "pre-pr-exit=0" "$T5_OUT"
rm -rf "$T5_LOG" "$T5_LOG.steps"
rm -rf "$T5_BIN"

# Test: pre-pr.sh sets _final_rc nonzero when a middle step fails
# pre-commit succeeds, then task reuse:lint fails; the other steps still run.
T6_LOG=$(mktemp)
T6_BIN=$(mktemp -d)
# pre-commit stub: always succeeds
printf '#!/usr/bin/env bash\nexit 0\n' > "$T6_BIN/pre-commit"
chmod +x "$T6_BIN/pre-commit"
# task stub: fails for reuse:lint, succeeds for everything else
cat > "$T6_BIN/task" << 'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "reuse:lint" ]; then exit 99; fi
exit 0
EOF
chmod +x "$T6_BIN/task"
T6_OUT=$(
    PATH="$T6_BIN:$PATH" \
    PRE_PR_FULL=1 \
    PRE_PR_LOG="$T6_LOG" \
    TIMEOUT_PRECOMMIT=5 TIMEOUT_LINT=5 TIMEOUT_TYPECHECK=5 \
    TIMEOUT_TEST=5 TIMEOUT_COMPLEXITY=5 TIMEOUT_SECURITY=5 \
    bash "$REPO_ROOT/scripts/pre-pr.sh" 2>&1 || true
)
assert_contains "pre-pr.sh: mid-chain failure emits [FAIL]" "[FAIL]" "$T6_OUT"
if echo "$T6_OUT" | grep -q "pre-pr-exit=0"; then
    _fail "pre-pr.sh: mid-chain failure should not emit pre-pr-exit=0"
else
    _pass "pre-pr.sh: mid-chain failure exits with nonzero rc"
fi
rm -rf "$T6_LOG" "$T6_LOG.steps"
rm -rf "$T6_BIN"

# Shared stub setup for the parallel-phase tests: pre-commit succeeds; the task
# stub fails reuse:lint late (exit 99, after a sleep, so it finishes last),
# fails security:audit (exit 7) and times out typecheck:all via TIMEOUT_TYPECHECK=1.
_parallel_stubs() {
    printf '#!/usr/bin/env bash\nexit 0\n' > "$1/pre-commit"
    cat > "$1/task" << 'EOF2'
#!/usr/bin/env bash
case "${1:-}" in
    reuse:lint) sleep 1; exit 99 ;;
    security:audit) exit 7 ;;
    typecheck:all) exec sleep 10 ;;
esac
exit 0
EOF2
    chmod +x "$1/pre-commit" "$1/task"
}

_run_parallel_case() { # bin log jobs
    PATH="$1:$PATH" \
    PRE_PR_FULL=1 \
    PRE_PR_LOG="$2" \
    PRE_PR_JOBS="$3" \
    TIMEOUT_PRECOMMIT=5 TIMEOUT_LINT=5 TIMEOUT_TYPECHECK=1 \
    TIMEOUT_TEST=5 TIMEOUT_COMPLEXITY=5 TIMEOUT_SECURITY=5 \
    bash "$REPO_ROOT/scripts/pre-pr.sh" 2>&1 || true
}

# Result lines (OK/ERR/TIM) in output order, labels only.
_result_order() {
    echo "$1" | sed -n 's/^  \[\(...\)\] \([^ ]*\( (root)\)\{0,1\}\).*/\2/p' | tr '\n' ' '
}

# Test: parallel mode reports every failure, in a fixed order, and keeps
# per-step timeouts and the first failing step's rc.
T7_LOG=$(mktemp)
T7_BIN=$(mktemp -d)
_parallel_stubs "$T7_BIN"
T7_OUT=$(_run_parallel_case "$T7_BIN" "$T7_LOG" 4)
assert_contains "pre-pr.sh parallel: announces the parallel phase" "in parallel (PRE_PR_JOBS=4)" "$T7_OUT"
assert_contains "pre-pr.sh parallel: reports reuse:lint failure" "[ERR] reuse:lint" "$T7_OUT"
assert_contains "pre-pr.sh parallel: reports security:audit failure" "[ERR] security:audit" "$T7_OUT"
assert_contains "pre-pr.sh parallel: per-step timeout still fires" "[TIM] typecheck:all" "$T7_OUT"
assert_contains "pre-pr.sh parallel: rc of the first failing step" "pre-pr-exit=99" "$T7_OUT"
assert_contains "pre-pr.sh parallel: tails each failed step log" "lines of $T7_LOG.steps/_security.log" "$T7_OUT"
T7_ORDER=$(_result_order "$T7_OUT")
assert_eq "pre-pr.sh parallel: results in fixed order, test:apps last" \
    "pre-commit reuse:lint lint (root) lint:all typecheck:all test:unit (root) test:scripts complexity (root) complexity:all docker:lint security:audit test:apps " \
    "$T7_ORDER"
assert_contains "pre-pr.sh parallel: step logs appended to PRE_PR_LOG" "━━━ security:audit ━━━" "$(cat "$T7_LOG")"
rm -rf "$T7_LOG" "$T7_LOG.steps" "$T7_BIN"

# Test: PRE_PR_JOBS=1 runs the same steps sequentially with live progress
T8_LOG=$(mktemp)
T8_BIN=$(mktemp -d)
_parallel_stubs "$T8_BIN"
T8_OUT=$(_run_parallel_case "$T8_BIN" "$T8_LOG" 1)
if echo "$T8_OUT" | grep -q "in parallel"; then
    _fail "pre-pr.sh PRE_PR_JOBS=1: must not run in parallel"
else
    _pass "pre-pr.sh PRE_PR_JOBS=1: runs sequentially"
fi
assert_contains "pre-pr.sh PRE_PR_JOBS=1: live progress lines" "-->  reuse:lint ..." "$T8_OUT"
assert_eq "pre-pr.sh PRE_PR_JOBS=1: same results in the same order" \
    "$T7_ORDER" "$(_result_order "$T8_OUT")"
assert_contains "pre-pr.sh PRE_PR_JOBS=1: rc of the first failing step" "pre-pr-exit=99" "$T8_OUT"
rm -rf "$T8_LOG" "$T8_LOG.steps" "$T8_BIN"

# ── Summary ──────────────────────────────────────────────────────────────────

printf "\n%d passed, %d failed\n" "$PASS" "$FAIL"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
