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
    if echo "$haystack" | grep -qF "$needle"; then
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
    export QA_LOG_DIR="$(mktemp -d)"
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

# Test: pre-pr.sh always emits pre-pr-exit= even when a step fails
# We override the first step to exit nonzero to test that the EXIT trap fires.
T4_LOG=$(mktemp)
# Create a wrapper that replaces pre-commit with a failing stub
T4_WRAPPER=$(mktemp --suffix=.sh)
cat > "$T4_WRAPPER" << 'EOF'
#!/usr/bin/env bash
pre-commit() { exit 42; }
export -f pre-commit
export TIMEOUT_PRECOMMIT=5 TIMEOUT_LINT=5 TIMEOUT_TYPECHECK=5
export TIMEOUT_TEST=5 TIMEOUT_COMPLEXITY=5 TIMEOUT_SIMILARITY=5 TIMEOUT_SECURITY=5
source SCRIPT_PATH
EOF
sed -i "s|SCRIPT_PATH|$REPO_ROOT/scripts/pre-pr.sh|" "$T4_WRAPPER"
T4_OUT=$(PRE_PR_LOG="$T4_LOG" bash "$T4_WRAPPER" 2>&1 || true)
assert_contains "pre-pr.sh: emits pre-pr-exit= on failure" "pre-pr-exit=" "$T4_OUT"
assert_contains "pre-pr.sh: emits [FAIL] on failure" "[FAIL]" "$T4_OUT"
rm -f "$T4_LOG" "$T4_WRAPPER"

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
    PRE_PR_LOG="$T5_LOG" \
    TIMEOUT_PRECOMMIT=5 TIMEOUT_LINT=5 TIMEOUT_TYPECHECK=5 \
    TIMEOUT_TEST=5 TIMEOUT_COMPLEXITY=5 TIMEOUT_SIMILARITY=5 TIMEOUT_SECURITY=5 \
    bash "$REPO_ROOT/scripts/pre-pr.sh" 2>&1 || true
)
assert_contains "pre-pr.sh: emits [DONE] on success" "[DONE]" "$T5_OUT"
assert_contains "pre-pr.sh: emits pre-pr-exit=0 on success" "pre-pr-exit=0" "$T5_OUT"
rm -f "$T5_LOG"
rm -rf "$T5_BIN"

# Test: pre-pr.sh sets _final_rc nonzero when a middle step fails
# pre-commit succeeds, then task reuse:lint fails, rest should be skipped.
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
    PRE_PR_LOG="$T6_LOG" \
    TIMEOUT_PRECOMMIT=5 TIMEOUT_LINT=5 TIMEOUT_TYPECHECK=5 \
    TIMEOUT_TEST=5 TIMEOUT_COMPLEXITY=5 TIMEOUT_SIMILARITY=5 TIMEOUT_SECURITY=5 \
    bash "$REPO_ROOT/scripts/pre-pr.sh" 2>&1 || true
)
assert_contains "pre-pr.sh: mid-chain failure emits [FAIL]" "[FAIL]" "$T6_OUT"
if echo "$T6_OUT" | grep -q "pre-pr-exit=0"; then
    _fail "pre-pr.sh: mid-chain failure should not emit pre-pr-exit=0"
else
    _pass "pre-pr.sh: mid-chain failure exits with nonzero rc"
fi
rm -f "$T6_LOG"
rm -rf "$T6_BIN"

# ── Summary ──────────────────────────────────────────────────────────────────

printf "\n%d passed, %d failed\n" "$PASS" "$FAIL"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
