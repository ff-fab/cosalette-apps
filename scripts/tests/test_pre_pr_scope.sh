#!/usr/bin/env bash
# scripts/tests/test_pre_pr_scope.sh — Scope detection of the pre-pr gate
# (scripts/pre-pr-scope.sh, ADR-012), exercised in throwaway git repos.
#
# Run: bash scripts/tests/test_pre_pr_scope.sh
# Exit code: 0 = all pass, 1 = at least one failure

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCOPE_SH="$REPO_ROOT/scripts/pre-pr-scope.sh"
# Run under `task pre-pr:full` too: never inherit the outer gate's scope.
unset PRE_PR_FULL PRE_PR_APPS PRE_PR_BASE_REF
PASS=0
FAIL=0

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

# A repo with apps a and b, the real shared-path list and origin/main at the
# first commit. No remote is configured, so a missing ref cannot be fetched.
make_repo() {
    local dir
    dir=$(mktemp -d)
    git -C "$dir" init --quiet --initial-branch=main
    git -C "$dir" config user.email t@example.invalid
    git -C "$dir" config user.name test
    mkdir -p "$dir/apps/a/src" "$dir/apps/b/src" "$dir/.github"
    touch "$dir/apps/a/pyproject.toml" "$dir/apps/b/pyproject.toml" "$dir/README.md"
    cp "$REPO_ROOT/.github/ci-shared-paths.txt" "$dir/.github/"
    git -C "$dir" add -A
    git -C "$dir" commit --quiet -m init
    git -C "$dir" update-ref refs/remotes/origin/main HEAD
    printf '%s\n' "$dir"
}

# Print "<field>" from the scope script run in <dir> with extra env.
scope_field() {
    local dir="$1" field="$2"
    shift 2
    (cd "$dir" && env "$@" bash "$SCOPE_SH") | sed -n "s/^$field=//p"
}

printf "\n=== pre-pr-scope.sh ===\n"

# App-only change: a committed change under apps/a selects only a.
R=$(make_repo)
echo x > "$R/apps/a/src/m.py"
git -C "$R" add -A && git -C "$R" commit --quiet -m change
assert_eq "app-only change: mode" "scoped" "$(scope_field "$R" mode)"
assert_eq "app-only change: selects that app" "a" "$(scope_field "$R" apps)"
# Uncommitted and untracked files count too.
echo y > "$R/apps/b/src/new.py"
assert_eq "untracked file under apps/b: selects both" "a b" "$(scope_field "$R" apps)"
rm -rf "$R"

# Non-app, non-shared change selects no app.
R=$(make_repo)
echo z >> "$R/README.md"
assert_eq "docs-only change: no app" "" "$(scope_field "$R" apps)"
rm -rf "$R"

# Hook configuration can invalidate unchanged files, so it must select the
# all-files pre-commit path. Check every configured pattern independently so a
# missing pattern cannot be hidden by an earlier match.
R=$(make_repo)
for config in .pre-commit-config.yaml .prettierrc.json .prettierrc.js \
    .prettierignore .editorconfig .editorconfig-checker.json; do
    (
        cd "$R" || exit
        # shellcheck disable=SC1090 # The script is sourced by absolute path from the checkout.
        . "$SCOPE_SH"
        SCOPE_MODE=scoped
        SCOPE_FILES=("$config")
        precommit_config_changed
    )
    assert_eq "hook configuration $config: pre-commit scans all files" "0" "$?"
done
(
    cd "$R" || exit
    # shellcheck disable=SC1090 # The script is sourced by absolute path from the checkout.
    . "$SCOPE_SH"
    # shellcheck disable=SC2034 # The sourced function reads these temporary scope globals.
    SCOPE_MODE=scoped
    # shellcheck disable=SC2034 # The sourced function reads these temporary scope globals.
    SCOPE_FILES=(README.md)
    precommit_config_changed
)
assert_eq "ordinary file change: pre-commit remains scoped" "1" "$?"
rm -rf "$R"

# Shared change: uv.lock selects every app.
R=$(make_repo)
touch "$R/uv.lock"
assert_eq "shared change: selects every app" "a b" "$(scope_field "$R" apps)"
assert_eq "shared change: reason names the file" \
    "shared path changed (uv.lock), so every app runs" "$(scope_field "$R" reason)"
rm -rf "$R"

# APPS override wins over a shared change; an unknown app is rejected.
R=$(make_repo)
touch "$R/uv.lock"
assert_eq "APPS override: selects only the named app" "b" \
    "$(scope_field "$R" apps PRE_PR_APPS=b)"
(cd "$R" && PRE_PR_APPS=nope bash "$SCOPE_SH" >/dev/null 2>&1)
assert_eq "APPS override: unknown app (exit code)" "2" "$?"
rm -rf "$R"

# Missing origin/main falls back to the full run over every app.
R=$(make_repo)
git -C "$R" update-ref -d refs/remotes/origin/main
assert_eq "missing origin/main: mode" "full" "$(scope_field "$R" mode)"
assert_eq "missing origin/main: every app" "a b" "$(scope_field "$R" apps)"
rm -rf "$R"

# pre-pr:full checks every app regardless of the diff.
R=$(make_repo)
assert_eq "PRE_PR_FULL=1: mode" "full" "$(scope_field "$R" mode PRE_PR_FULL=1)"
assert_eq "PRE_PR_FULL=1: every app" "a b" "$(scope_field "$R" apps PRE_PR_FULL=1)"
rm -rf "$R"

# Drift guard: CI builds its shared filter from the same file and hardcodes none.
CI_YML="$REPO_ROOT/.github/workflows/ci.yml"
if grep -qF ".github/ci-shared-paths.txt" "$CI_YML"; then
    _pass "ci.yml reads .github/ci-shared-paths.txt"
else
    _fail "ci.yml no longer reads .github/ci-shared-paths.txt"
fi
if grep -qE "^[[:space:]]*-[[:space:]]*'(uv\.lock|pyproject\.toml|scripts/\*\*)'" "$CI_YML"; then
    _fail "ci.yml hardcodes a shared path; keep them in .github/ci-shared-paths.txt"
else
    _pass "ci.yml hardcodes no shared path"
fi

printf "\n%d passed, %d failed\n" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
