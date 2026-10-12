#!/usr/bin/env bash
# scripts/tests/test_ci_scope.sh — Fixed-cost CI job selection
# (scripts/ci-scope.sh, cap-2ydw) for representative pull request diffs.
#
# Run: bash scripts/tests/test_ci_scope.sh
# Exit code: 0 = all pass, 1 = at least one failure

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
unset CI_SCOPE_FULL
PASS=0
FAIL=0

_pass() { printf "  [ OK] %s\n" "$1"; PASS=$(( PASS + 1 )); }
_fail() { printf "  [ERR] %s\n" "$1"; FAIL=$(( FAIL + 1 )); }

# expect <description> <expected output, one line> <changed path>...
expect() {
    local desc="$1" expected="$2" actual
    shift 2
    actual=$(cd "$REPO_ROOT" && printf '%s\n' "$@" | sed '/^$/d' \
        | bash scripts/ci-scope.sh | paste -sd' ')
    if [ "$expected" = "$actual" ]; then
        _pass "$desc"
    else
        _fail "$desc — expected='$expected' got='$actual'"
    fi
}

ALL="root_tests=true docker_lint=true"
NONE="root_tests=false docker_lint=false"
ROOT="root_tests=true docker_lint=false"

printf "\n=== ci-scope.sh ===\n"

expect "app source change runs root tests (they import every app)" "$ROOT" \
    apps/wallpanel-control/packages/src/wallpanel_control/main.py
expect "app compose change runs root tests (TLS/MQTT 5 posture)" "$ROOT" \
    apps/gas2mqtt/compose.yml
expect "app Dockerfile change adds Docker lint" "$ALL" apps/gas2mqtt/Dockerfile
expect "devcontainer Dockerfile change adds Docker lint" "$ALL" .devcontainer/Dockerfile
expect "hadolint config change adds Docker lint" "$ALL" .hadolint.yaml
expect "app-only PR like #398: app source, docs, beads" "$ROOT" \
    apps/wallpanel-control/packages/src/wallpanel_control/probe.py \
    apps/wallpanel-control/docs/configuration.md \
    docs/adr/ADR-005-foo.md .beads/issues.jsonl
expect "app tests and docs only skip both jobs" "$NONE" \
    apps/gas2mqtt/packages/tests/unit/test_x.py apps/gas2mqtt/docs/index.md \
    apps/gas2mqtt/CHANGELOG.md
expect "docs-only change skips both jobs" "$NONE" docs/index.md README.md
expect "beads-only change skips both jobs" "$NONE" .beads/issues.jsonl
expect "a shell script is never inert (shellcheck)" "$ROOT" \
    apps/gas2mqtt/packages/tests/run.sh
expect "a docs/ directory inside app source is not inert" "$ROOT" \
    apps/gas2mqtt/packages/src/gas2mqtt/docs/x.py
expect "devcontainer script runs root tests" "$ROOT" .devcontainer/post-create.sh
expect "unknown root file runs root tests" "$ROOT" .dockerignore
expect "shared path selects every job" "$ALL" uv.lock
expect "workflow-only change selects every job" "$ALL" .github/workflows/ci.yml
expect "shared fixture selects every job" "$ALL" packages/tests/fixtures/x.py
expect "shared path among docs selects every job" "$ALL" docs/index.md taskfiles/PythonApp.yml
expect "no changed files skip both jobs" "$NONE"

actual=$(cd "$REPO_ROOT" && printf 'docs/index.md\n' | CI_SCOPE_FULL=1 bash scripts/ci-scope.sh | paste -sd' ')
if [ "$actual" = "$ALL" ]; then
    _pass "CI_SCOPE_FULL=1 selects every job"
else
    _fail "CI_SCOPE_FULL=1 selects every job — got='$actual'"
fi

printf "\n%d passed, %d failed\n" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
