#!/usr/bin/env bash
# Render task details for the fzf preview pane in plan-interactive.sh.
# Called with: bash plan-task-preview.sh <task-id> [<epic-id>] [<cache-file>]
#
# Shows:
#   - Status & priority header
#   - Description (main content)
#   - Dependencies (excluding the parent epic link)
#   - Acceptance criteria (if present)

set -euo pipefail

if [ "$#" -lt 1 ] || [ -z "${1:-}" ]; then
    echo "Usage: $0 <task-id> [<epic-id>] [<cache-file>]" >&2
    exit 1
fi

TASK_ID="$1"
EPIC_ID="${2:-}"
CACHE_FILE="${3:-}"

# Fetch task data — prefer cache, fall back to bd show
if [ -n "$CACHE_FILE" ] && [ -s "$CACHE_FILE" ]; then
    TASK_JSON=$(jq --arg id "$TASK_ID" '[.[] | select(.id == $id)]' "$CACHE_FILE")
else
    TASK_JSON=$(bd show "$TASK_ID" --json 2>/dev/null)
fi

if [ -z "$TASK_JSON" ] || [ "$TASK_JSON" = "null" ] || [ "$TASK_JSON" = "[]" ]; then
    echo "Task not found: $TASK_ID"
    exit 0
fi

# Extract fields in a single jq call
read -r STATUS PRIORITY <<< $(echo "$TASK_JSON" | jq -r '.[0] | [(.status // "unknown"), (.priority // "-")] | @tsv')
DESCRIPTION=$(echo "$TASK_JSON" | jq -r '.[0].description // ""')
ACCEPTANCE=$(echo "$TASK_JSON" | jq -r '.[0].acceptance_criteria // ""')
DESIGN=$(echo "$TASK_JSON" | jq -r '.[0].design // ""')

# Status indicator
case "$STATUS" in
    closed)     STATUS_ICON="\033[32m✓\033[0m" ;;           # green check
    in_progress) STATUS_ICON="\033[33m●\033[0m" ;;          # yellow dot
    *)          STATUS_ICON="\033[2m○\033[0m" ;;             # dim circle
esac

# --- Render ---------------------------------------------------------------- #

# Header
printf "%b %s  P%s  %s\n" "$STATUS_ICON" "$TASK_ID" "$PRIORITY" "$STATUS"
echo "─────────────────────────────────────────"

# Description
if [ -n "$DESCRIPTION" ] && [ "$DESCRIPTION" != "null" ]; then
    echo ""
    echo "$DESCRIPTION"
fi

# Acceptance criteria
if [ -n "$ACCEPTANCE" ] && [ "$ACCEPTANCE" != "null" ]; then
    echo ""
    printf "\033[1mAcceptance Criteria\033[0m\n"
    echo "$ACCEPTANCE"
fi

# Design notes
if [ -n "$DESIGN" ] && [ "$DESIGN" != "null" ]; then
    echo ""
    printf "\033[1mDesign\033[0m\n"
    echo "$DESIGN"
fi

# Dependencies (excluding parent epic link)
# When using cache, dependencies have raw IDs — resolve titles from cache
if [ -n "$CACHE_FILE" ] && [ -s "$CACHE_FILE" ]; then
    DEPS=$(jq -r --arg task "$TASK_ID" --arg epic "${EPIC_ID}" '
        (map({key: .id, value: {title: .title, status: .status}}) | from_entries) as $lookup
        | .[] | select(.id == $task)
        | .dependencies // []
        | map(select(.type != "parent-child" or .depends_on_id != $epic))
        | map(
            ($lookup[.depends_on_id] // {title: .depends_on_id, status: "unknown"}) as $dep
            | (if $dep.status == "closed" then "✓"
               elif $dep.status == "in_progress" then "●"
               else "○" end)
            + " " + .depends_on_id + ": " + $dep.title
        ) | .[]' "$CACHE_FILE")
else
    DEPS=$(echo "$TASK_JSON" | jq -r --arg epic "${EPIC_ID}" '
        .[0].dependencies // [] | map(
            select(.dependency_type != "parent-child" or .id != $epic)
        ) | if length > 0 then
            map(
                (if .status == "closed" then "✓" elif .status == "in_progress" then "●" else "○" end)
                + " " + .id + ": " + .title
            ) | .[]
        else empty end
    ')
fi

if [ -n "$DEPS" ]; then
    echo ""
    printf "\033[1mDependencies\033[0m\n"
    echo "$DEPS"
fi
