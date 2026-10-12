#!/usr/bin/env bash
# scripts/ci-scope.sh — Decide which fixed-cost CI jobs a change needs
# (cap-2ydw, ADR-012 amendment of 2026-10-12)
#
# Reads changed paths (one per line) on stdin, prints `key=value` lines for
# $GITHUB_OUTPUT. Run from the repo root; .github/workflows/ci.yml calls it in
# the `detect` job.
#   CI_SCOPE_FULL=1   select every job (push to main: full coverage)
#
# Each job runs when a changed path is in its input surface. A shared path
# (.github/ci-shared-paths.txt, which also covers every workflow under
# .github/**) selects every job.
#   root_tests   lint + repo-root unit and script tests. These import every
#                app and read its Dockerfile, compose.yml, .env.example and
#                pyproject.toml, and shellcheck every *.sh, so they run unless
#                every changed path is inert: Markdown, docs, beads state, or an
#                app's own tests and docs (app CI covers those). A *.sh is never
#                inert.
#   docker_lint  hadolint: any Dockerfile or .hadolint.yaml.
#
# security (any app or shared change) and app-ci (per app) stay in ci.yml's
# paths-filter. Globs use bash [[ == ]] semantics, where `*` also matches `/`;
# `*Dockerfile*` relies on that.

set -euo pipefail

# shellcheck source=scripts/pre-pr-scope.sh
source "$(dirname "${BASH_SOURCE[0]}")/pre-pr-scope.sh"

# Anchored regex: a bash glob `*` would also cross `/`, so `apps/*/docs/*`
# would wrongly treat apps/x/packages/src/x/docs/y.py as inert.
INERT_RE='^(docs/|\.beads/|apps/[^/]+/(docs|packages/tests)/)|\.md$'

mapfile -t SCOPE_FILES
mapfile -t shared < <(scope_shared_patterns)

if [ "${CI_SCOPE_FULL:-}" = 1 ] || scope_match "${shared[@]}" >/dev/null; then
    printf 'root_tests=true\ndocker_lint=true\n'
    exit 0
fi

root_tests=false
for file in "${SCOPE_FILES[@]}"; do
    if [[ "$file" == *.sh || ! "$file" =~ $INERT_RE ]]; then
        root_tests=true
        break
    fi
done

docker_lint=false
scope_match '*Dockerfile*' .hadolint.yaml >/dev/null && docker_lint=true

printf 'root_tests=%s\ndocker_lint=%s\n' "$root_tests" "$docker_lint"
