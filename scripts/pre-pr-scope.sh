#!/usr/bin/env bash
# scripts/pre-pr-scope.sh — Decide what `task pre-pr` checks (ADR-012)
#
# Sourced by scripts/pre-pr.sh. Run it directly to print the scope:
#   bash scripts/pre-pr-scope.sh
#
# Changed files = commits since `git merge-base <base> HEAD`, plus staged,
# unstaged and untracked files. The rules match CI (.github/workflows/ci.yml):
#   - a change under apps/<app>/ selects that app;
#   - a change to any shared path selects every app. The shared list lives in
#     .github/ci-shared-paths.txt, which CI's paths-filter reads too.
#
# Inputs (env):
#   PRE_PR_FULL=1      check every app and every file (task pre-pr:full)
#   PRE_PR_APPS="a b"  check exactly these apps (task pre-pr APPS="a b")
#   PRE_PR_BASE_REF    ref to diff against (default: origin/main). When it is
#                      missing and cannot be fetched, the run falls back to full.
#
# Outputs (globals set by pre_pr_scope):
#   SCOPE_MODE    full | scoped
#   SCOPE_REASON  one line explaining the selection
#   SCOPE_APPS    space-separated app names (empty: no app changed)
#   SCOPE_BASE    merge-base commit (scoped mode only)
#   SCOPE_FILES   array of changed paths, deletions included (scoped mode only)

SHARED_PATHS_FILE=".github/ci-shared-paths.txt"

scope_all_apps() {
    local pyproject
    for pyproject in apps/*/pyproject.toml; do
        [ -f "$pyproject" ] && basename "$(dirname "$pyproject")"
    done
}

scope_shared_patterns() {
    sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^$/d' "$SHARED_PATHS_FILE"
}

# Print the first changed file matching any glob argument; fail when none does.
# Globs use bash [[ == ]] semantics, where `*` also matches `/`.
scope_match() {
    local file pattern
    for file in "${SCOPE_FILES[@]}"; do
        for pattern in "$@"; do
            # shellcheck disable=SC2053  # unquoted on purpose: glob match
            if [[ "$file" == $pattern ]]; then
                printf '%s\n' "$file"
                return 0
            fi
        done
    done
    return 1
}

# True when the run is full or a changed file matches any glob argument.
scope_touches() {
    [ "$SCOPE_MODE" = full ] || scope_match "$@" >/dev/null
}

# These files can change how hooks validate every file, so pre-commit must
# scan the whole tree when any of them changes.
precommit_config_changed() {
    scope_touches .pre-commit-config.yaml '.prettierrc*' .prettierignore \
        .editorconfig .editorconfig-checker.json
}

# Print changed files that still exist and match any glob argument (all
# changed files when called without arguments).
scope_existing_files() {
    local file pattern
    for file in "${SCOPE_FILES[@]}"; do
        [ -f "$file" ] || continue
        if [ "$#" -eq 0 ]; then
            printf '%s\n' "$file"
            continue
        fi
        for pattern in "$@"; do
            # shellcheck disable=SC2053
            if [[ "$file" == $pattern ]]; then
                printf '%s\n' "$file"
                break
            fi
        done
    done
}

pre_pr_scope() {
    SCOPE_MODE=scoped
    SCOPE_REASON=""
    SCOPE_APPS=""
    SCOPE_BASE=""
    SCOPE_FILES=()

    local all_apps app
    all_apps=$(scope_all_apps | tr '\n' ' ')
    all_apps=${all_apps% }

    if [ -n "${PRE_PR_APPS:-}" ]; then
        for app in $PRE_PR_APPS; do
            if [[ " $all_apps " != *" $app "* ]]; then
                echo "ERROR: APPS names unknown app '$app' (known: $all_apps)" >&2
                return 2
            fi
        done
    fi

    if [ "${PRE_PR_FULL:-}" = 1 ]; then
        SCOPE_MODE=full
        SCOPE_REASON="full run requested (task pre-pr:full)"
        SCOPE_APPS=$all_apps
        return 0
    fi

    local ref="${PRE_PR_BASE_REF:-origin/main}"
    if ! git rev-parse --verify --quiet "${ref}^{commit}" >/dev/null && [ "$ref" = origin/main ]; then
        timeout 30 git fetch --quiet origin main >/dev/null 2>&1 || true
    fi
    if ! SCOPE_BASE=$(git merge-base "$ref" HEAD 2>/dev/null); then
        SCOPE_MODE=full
        SCOPE_BASE=""
        SCOPE_APPS=${PRE_PR_APPS:-$all_apps}
        SCOPE_REASON="no merge-base with $ref, falling back to the full run"
        return 0
    fi

    mapfile -t SCOPE_FILES < <(
        {
            git diff --name-only --no-renames "$SCOPE_BASE" HEAD
            git diff --name-only --no-renames HEAD
            git ls-files --others --exclude-standard
        } | sort -u
    )

    if [ -n "${PRE_PR_APPS:-}" ]; then
        SCOPE_APPS=$(printf '%s' "$PRE_PR_APPS" | tr -s ' ')
        SCOPE_REASON="APPS override"
        return 0
    fi

    local shared_hit patterns
    mapfile -t patterns < <(scope_shared_patterns)
    if shared_hit=$(scope_match "${patterns[@]}"); then
        SCOPE_APPS=$all_apps
        SCOPE_REASON="shared path changed ($shared_hit), so every app runs"
        return 0
    fi

    local selected=""
    for app in $all_apps; do
        if scope_match "apps/$app/*" >/dev/null; then
            selected="$selected $app"
        fi
    done
    SCOPE_APPS=${selected# }
    if [ -n "$SCOPE_APPS" ]; then
        SCOPE_REASON="${#SCOPE_FILES[@]} changed file(s) under the selected apps"
    else
        SCOPE_REASON="${#SCOPE_FILES[@]} changed file(s), none under apps/ or a shared path"
    fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    set -uo pipefail
    pre_pr_scope || exit $?
    printf 'mode=%s\nreason=%s\napps=%s\nbase=%s\nfiles=%s\n' \
        "$SCOPE_MODE" "$SCOPE_REASON" "$SCOPE_APPS" "$SCOPE_BASE" "${#SCOPE_FILES[@]}"
fi
