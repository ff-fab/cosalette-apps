#!/bin/bash
# Wait for all CI checks on a PR to complete, then report results.
# Called by: task ci:wait -- <pr-number>
#
# Polls `gh pr checks` every INTERVAL seconds until no checks are
# IN_PROGRESS / PENDING / QUEUED. Then prints a summary table with
# pass/fail status and links to failed runs for easy debugging.
#
# Stale-result guards:
#   - The wait is pinned to an expected head SHA: CI_WAIT_EXPECTED_SHA if set,
#     else the local branch's pushed commit (@{push}) when the current branch is
#     the PR head, else the first head observed. Until the PR head matches it,
#     checks are ignored — they would belong to the previous revision.
#   - After checks finish, their signature must remain unchanged for the
#     registration grace period. Changes and pending checks restart the timer.
#
# Exit codes:
#   0 — all checks passed (or skipped)
#   1 — one or more checks failed
#   2 — usage error (missing PR number or gh not available)
#   3 — persistent API failure (e.g. expired token)
#   4 — PR is merged/closed and its head can never reach the expected SHA

set -euo pipefail

INTERVAL="${CI_WAIT_INTERVAL:-5}"
TIMEOUT="${CI_WAIT_TIMEOUT:-1800}"  # 30 minutes default
REGISTRATION_GRACE="${CI_WAIT_REGISTRATION_GRACE:-60}"

# ── Prerequisite checks ─────────────────────────────────────────────

if ! command -v gh &>/dev/null; then
    echo "Error: gh CLI not found on PATH" >&2
    exit 2
fi

if ! command -v jq &>/dev/null; then
    echo "Error: jq not found on PATH" >&2
    exit 2
fi

# ── Argument handling ────────────────────────────────────────────────

PR="${1:-}"
if [ -z "$PR" ]; then
    # Auto-detect: use the PR associated with the current branch
    PR=$(gh pr view --json number --jq '.number' 2>/dev/null || true)
    if [ -z "$PR" ]; then
        echo "Usage: ci-wait.sh <pr-number>" >&2
        echo "   or: run from a branch with an open PR (auto-detect)" >&2
        exit 2
    fi
    echo "Auto-detected PR #${PR}"
fi

EXPECTED_SHA="${CI_WAIT_EXPECTED_SHA:-}"
if [ -z "$EXPECTED_SHA" ]; then
    head_ref=$(gh pr view "$PR" --json headRefName --jq '.headRefName' 2>/dev/null || true)
    if [ -n "$head_ref" ] && [ "$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" = "$head_ref" ]; then
        EXPECTED_SHA=$(git rev-parse --verify -q '@{push}' 2>/dev/null || true)
    fi
fi

# ── Poll loop ────────────────────────────────────────────────────────

MAX_API_FAILURES="${CI_WAIT_MAX_API_FAILURES:-5}"

echo "Waiting for CI on PR #${PR} (polling every ${INTERVAL}s, timeout ${TIMEOUT}s)..."
echo ""

START=$(date +%s)
api_failures=0
settled=""
settled_since=""

api_failure() {
    api_failures=$((api_failures + 1))
    if [ "$api_failures" -ge "$MAX_API_FAILURES" ]; then
        echo "" >&2
        echo "Error: ${api_failures} consecutive API failures." >&2
        echo "The gh auth token may have expired. Try: gh auth status" >&2
        exit 3
    fi
    echo "$(date +%H:%M:%S) — $1, retrying (${api_failures}/${MAX_API_FAILURES})..."
}

while true; do
    ELAPSED=$(( $(date +%s) - START ))
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "Timed out after ${ELAPSED}s waiting for CI checks." >&2
        exit 1
    fi

    head="" state=""
    read -r head state < <(gh pr view "$PR" --json headRefOid,state \
        --jq '"\(.headRefOid) \(.state)"' 2>/dev/null) || true
    if [ -z "$head" ]; then
        settled=""
        settled_since=""
        api_failure "could not read PR head"
        sleep "$INTERVAL"
        continue
    fi
    if [ -z "$EXPECTED_SHA" ]; then
        EXPECTED_SHA="$head"
    fi
    if [ "$head" != "$EXPECTED_SHA" ]; then
        # A merged or closed PR's head is frozen: it will never move.
        if [ -n "$state" ] && [ "$state" != "OPEN" ]; then
            echo "Error: PR #${PR} is ${state} at ${head:0:12}; it will never reach ${EXPECTED_SHA:0:12}." >&2
            echo "Commits pushed after the merge need a new PR." >&2
            exit 4
        fi
        api_failures=0
        settled=""
        settled_since=""
        echo "$(date +%H:%M:%S) — PR head is ${head:0:12}, waiting for ${EXPECTED_SHA:0:12}..."
        sleep "$INTERVAL"
        continue
    fi

    checks=$(gh pr checks "$PR" --json name,state,link 2>&1) || true

    # gh silently ignores --json and prints this plain-text message to stderr
    # (exit 1) when a PR has zero checks registered yet — e.g. right after
    # opening a PR, before CI has started reporting. This is normal and
    # transient, not an API/auth failure, so it must not count toward
    # MAX_API_FAILURES. Use printf (echo can misinterpret a leading '-' as an
    # option) and anchor the match to the start of the message so a valid
    # JSON response (which always starts with '[') can never false-match.
    if printf '%s' "$checks" | grep -qi "^no checks reported"; then
        api_failures=0
        settled=""
        settled_since=""
        echo "$(date +%H:%M:%S) — no checks reported yet, waiting for CI to register..."
        sleep "$INTERVAL"
        continue
    fi

    # Guard against transient API errors (empty or non-JSON response).
    # Bail out after MAX_API_FAILURES consecutive failures — a persistent
    # non-JSON response usually means the gh auth token has expired.
    if [ -z "$checks" ] || ! echo "$checks" | jq empty 2>/dev/null; then
        settled=""
        settled_since=""
        api_failure "API returned non-JSON"
        sleep "$INTERVAL"
        continue
    fi

    # Reset counter on any successful API response
    api_failures=0

    pending=$(echo "$checks" | jq '[.[] | select(.state == "IN_PROGRESS" or .state == "PENDING" or .state == "QUEUED")] | length')

    if [ "$pending" -eq 0 ]; then
        signature=$(echo "$checks" | jq -c '[.[] | [.name, .state]] | sort')
        if [ "$signature" = "$settled" ]; then
            now=$(date +%s)
            if [ $((now - settled_since)) -ge "$REGISTRATION_GRACE" ]; then
                break
            fi
            echo "$(date +%H:%M:%S) — checks unchanged; waiting for late registrations (${REGISTRATION_GRACE}s grace)..."
        else
            settled="$signature"
            settled_since=$(date +%s)
            echo "$(date +%H:%M:%S) — checks finished, waiting for late registrations (${REGISTRATION_GRACE}s grace)..."
        fi
    else
        settled=""
        settled_since=""
        echo "$(date +%H:%M:%S) — ${pending} check(s) still running..."
    fi
    sleep "$INTERVAL"
done

# ── Results ──────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  CI Results for PR #${PR} @ ${EXPECTED_SHA:0:12}"
echo "════════════════════════════════════════════════════════════════"

parsed=$(echo "$checks" | jq -r '.[] | [.name, .state, .link] | @tsv')

failed=0
while IFS=$'\t' read -r name state link; do
    case "$state" in
        SUCCESS)  icon="✅" ;;
        SKIPPED)  icon="⬜" ;;
        FAILURE)  icon="❌"; failed=$((failed + 1)) ;;
        *)        icon="⚠️ "; failed=$((failed + 1)) ;;
    esac
    printf "  %s  %-40s %s\n" "$icon" "$name" "$state"
done <<< "$parsed"

echo "════════════════════════════════════════════════════════════════"

if [ "$failed" -gt 0 ]; then
    echo ""
    echo "Failed checks (${failed}):"
    echo ""
    while IFS=$'\t' read -r name state link; do
        if [ "$state" != "SUCCESS" ] && [ "$state" != "SKIPPED" ]; then
            echo "  ❌ ${name}"
            echo "     ${link}"
            echo ""
        fi
    done <<< "$parsed"
    echo "Tip: open the link(s) above to see full logs."
    exit 1
fi

echo ""
echo "All checks passed ✓"
exit 0
