#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Fabian Koerner <mail@fabiankoerner.com>
# SPDX-License-Identifier: MIT
#
# Regression tests for the CI helpers (ci-wait.sh, fetch-pr-feedback.sh) against
# a stubbed `gh`: stale results from a previous head, late check registration
# and superseded workflow attempts. No external shell test framework required.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CI_WAIT="$REPO_ROOT/scripts/ci-wait.sh"
FEEDBACK="$REPO_ROOT/.github/skills/pr-review/fetch-pr-feedback.sh"
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

TEST_DIR="$(mktemp -d)"
trap 'rm -rf "$TEST_DIR"' EXIT

# The stub answers from files in $GH_FIXTURE. `heads` and `checks` hold one
# response per line, consumed in order; the last line repeats once exhausted.
mkdir -p "$TEST_DIR/bin"
cat > "$TEST_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
next() {
    local file="$GH_FIXTURE/$1" n total
    n=$(( $(cat "$file.n" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$file.n"
    total=$(wc -l < "$file")
    sed -n "$(( n < total ? n : total ))p" "$file"
}
jq_filter() { if [[ -n "$1" ]]; then jq -rc "$1"; else cat; fi; }
args="$*"
jq_expr=""
for ((i = 1; i <= $#; i++)); do
    [[ "${!i}" == --jq ]] && { j=$((i + 1)); jq_expr="${!j}"; }
done
case "$args" in
    "pr view"*headRefOid*) next heads ;;
    "pr view"*headRefName*) echo "not-the-current-branch" ;;
    "pr checks"*)
        out=$(next checks)
        if [[ "$out" == "["* ]]; then echo "$out"; else echo "$out" >&2; exit 1; fi ;;
    "repo view"*) echo "o/r" ;;
    "api "*/check-runs*) jq_filter "$jq_expr" < "$GH_FIXTURE/check-runs.json" ;;
    "api "*/actions/runs*) jq_filter "$jq_expr" < "$GH_FIXTURE/workflow-runs.json" ;;
    "api "*/status*) jq_filter "$jq_expr" <<<'{"state": "pending", "statuses": []}' ;;
    "api repos/o/r/pulls/1 "*) jq_filter "$jq_expr" <<<'{"head": {"sha": "new"}}' ;;
    "api "*) echo "[]" ;;
    *) echo "unexpected gh call: $args" >&2; exit 99 ;;
esac
EOF
chmod +x "$TEST_DIR/bin/gh"

fixture() {
    GH_FIXTURE="$TEST_DIR/$1"
    mkdir -p "$GH_FIXTURE"
    export GH_FIXTURE
}

run_ci_wait() {
    OUTPUT=$(cd "$TEST_DIR" && PATH="$TEST_DIR/bin:$PATH" CI_WAIT_INTERVAL=0 \
        CI_WAIT_TIMEOUT="${TIMEOUT:-10}" CI_WAIT_EXPECTED_SHA="${EXPECTED:-}" \
        bash "$CI_WAIT" 1 2>&1)
    RC=$?
}

ok='[{"name":"ci-gate","state":"SUCCESS","link":"u"}]'

echo "ci-wait: ignores checks until the PR head reaches the expected SHA"
fixture head-lag
printf 'old\nold\nnew\n' > "$GH_FIXTURE/heads"
printf 'no checks reported on the branch\n%s\n' "$ok" > "$GH_FIXTURE/checks"
EXPECTED=new run_ci_wait
assert_eq "exit code" 0 "$RC"
assert_contains "waits for new head" "PR head is old, waiting for new" "$OUTPUT"
assert_eq "checks polled only once head matched" 3 "$(cat "$GH_FIXTURE/checks.n")"

echo "ci-wait: never reports a stale head's results as success"
fixture head-stuck
echo old > "$GH_FIXTURE/heads"
echo "$ok" > "$GH_FIXTURE/checks"
EXPECTED=new TIMEOUT=1 run_ci_wait
assert_eq "times out" 1 "$RC"
assert_contains "timeout message" "Timed out" "$OUTPUT"

echo "ci-wait: waits for workflows that register after the first finished poll"
fixture late-registration
echo new > "$GH_FIXTURE/heads"
printf '%s\n%s\n' '[{"name":"detect","state":"SUCCESS","link":"u"}]' \
    '[{"name":"detect","state":"SUCCESS","link":"u"},{"name":"ci-gate","state":"FAILURE","link":"u"}]' \
    > "$GH_FIXTURE/checks"
run_ci_wait
assert_eq "late failure is reported" 1 "$RC"
assert_contains "failed check listed" "ci-gate" "$OUTPUT"

echo "ci-wait: pins the first observed head when none is expected"
fixture first-head
echo new > "$GH_FIXTURE/heads"
echo "$ok" > "$GH_FIXTURE/checks"
run_ci_wait
assert_eq "exit code" 0 "$RC"
assert_contains "head in summary" "PR #1 @ new" "$OUTPUT"

run_feedback() {
    OUTPUT=$(cd "$TEST_DIR" && PATH="$TEST_DIR/bin:$PATH" bash "$FEEDBACK" 1 2>/dev/null)
    RC=$?
}

write_runs() {
    # Two attempts of ci.yml on the same SHA: suite 1 (older) and suite 2.
    cat > "$GH_FIXTURE/check-runs.json" <<EOF
{"total_count": 3, "check_runs": [
  {"name": "ci-gate", "status": "completed", "conclusion": "failure", "html_url": "u", "check_suite": {"id": 1}, "output": {}},
  {"name": "ci-gate", "status": "completed", "conclusion": "$1", "html_url": "u", "check_suite": {"id": 2}, "output": {}},
  {"name": "CodeQL", "status": "completed", "conclusion": "success", "html_url": "u", "check_suite": {"id": 9}, "output": {}}
]}
EOF
    cat > "$GH_FIXTURE/workflow-runs.json" <<'EOF'
{"workflow_runs": [
  {"check_suite_id": 1, "path": ".github/workflows/ci.yml", "event": "pull_request", "created_at": "2026-10-03T15:54:53Z"},
  {"check_suite_id": 2, "path": ".github/workflows/ci.yml", "event": "pull_request", "created_at": "2026-10-03T15:54:55Z"}
]}
EOF
}

echo "pr:feedback: superseded workflow attempts do not fail the aggregate"
fixture superseded
write_runs success
run_feedback
assert_eq "exit code" 0 "$RC"
assert_eq "state" success "$(jq -r '.ci_status.state' <<<"$OUTPUT")"
assert_eq "superseded flags" "true,false,false" \
    "$(jq -r '[.ci_status.check_runs[].superseded] | map(tostring) | join(",")' <<<"$OUTPUT")"
assert_eq "history retained" 3 "$(jq '.ci_status.check_runs | length' <<<"$OUTPUT")"
assert_eq "head sha" new "$(jq -r '.ci_status.head_sha' <<<"$OUTPUT")"

echo "pr:feedback: a failing latest attempt still fails the aggregate"
fixture latest-failure
write_runs failure
run_feedback
assert_eq "state" failure "$(jq -r '.ci_status.state' <<<"$OUTPUT")"

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
