#!/usr/bin/env bash
# Format epic children for the fzf preview pane in plan-interactive.sh.
#
# Called with: bash plan-preview.sh <epic-id> [<orphan-cache>] [<cache-file>]
#
# Transforms:
#   - Shows children with status icons and priorities
#   - Dims genuinely blocked tasks for visual de-emphasis

set -euo pipefail

if [ "$#" -lt 1 ] || [ -z "${1:-}" ]; then
    echo "Usage: $0 <epic-id> [<orphan-cache>] [<cache-file>]" >&2
    exit 1
fi

EPIC_ID="$1"
ORPHAN_CACHE="${2:-}"
CACHE_FILE="${3:-}"

# --- Handle virtual "Orphaned tasks" entry -------------------------------- #
if [ "$EPIC_ID" = "_orphan" ]; then
    # Use cached orphan IDs from plan-interactive.sh if available
    if [ -n "$ORPHAN_CACHE" ] && [ -s "$ORPHAN_CACHE" ]; then
        ORPHANS=$(cat "$ORPHAN_CACHE")
    elif [ -n "$CACHE_FILE" ] && [ -s "$CACHE_FILE" ]; then
        ORPHANS=$(jq -r '.[] | select(.issue_type != "epic") | select(.parent == null or .parent == "") | .id' "$CACHE_FILE")
    else
        ORPHANS=$(bd list --all --json --limit 0 2>/dev/null \
            | jq -r '.[] | select(.issue_type != "epic") | select(.parent == null or .parent == "") | .id')
    fi

    if [ -z "$ORPHANS" ]; then
        echo "No orphaned tasks."
        exit 0
    fi

    printf "\033[31m⚠ Tasks not parented to any epic\033[0m\n\n"

    orphan_ids_json=$(echo "$ORPHANS" | jq -R -s 'split("\n") | map(select(. != ""))')

    if [ -n "$CACHE_FILE" ] && [ -s "$CACHE_FILE" ]; then
        SOURCE="$CACHE_FILE"
    else
        SOURCE=<(bd list --all --json --limit 0 2>/dev/null)
    fi

    jq -r --argjson ids "$orphan_ids_json" '
            ($ids | map({key: ., value: true}) | from_entries) as $idset
            | [.[] | select(.issue_type != "epic") | select(.id as $i | $idset[$i])]
            | sort_by(.priority, .title) | .[]
            | "\(.status)\t\(.priority // 2)\t\(.id)\t\(.title)"' "$SOURCE" \
        | while IFS=$'\t' read -r status priority oid title; do
                case "$status" in
                    closed)      icon="✓" ;;
                    in_progress) icon="●" ;;
                    *)           icon="○" ;;
                esac
                printf "%s P%s  %s  %s\n" "$icon" "$priority" "$oid" "$title"
            done
    exit 0
fi

# --- Regular epic preview ------------------------------------------------- #
if [ -n "$CACHE_FILE" ] && [ -s "$CACHE_FILE" ]; then
    # Render children from cache — fast path
    jq -r --arg id "$EPIC_ID" '
        [.[] | select(.parent == $id)]
        | sort_by(.priority, .title) | .[]
        | "\(.status)\t\(.priority // 2)\t\(.id)\t\(.title)"' "$CACHE_FILE" \
        | while IFS=$'\t' read -r status priority tid title; do
                case "$status" in
                    closed)      icon="\033[32m✓\033[0m" ;;
                    in_progress) icon="\033[33m●\033[0m" ;;
                    blocked)     icon="\033[2m⊘\033[0m" ;;
                    *)           icon="\033[2m○\033[0m" ;;
                esac
                printf "%b P%s  %s  %s\n" "$icon" "$priority" "$tid" "$title"
            done
else
    # Fallback: use bd children (slow)
    bd children "$EPIC_ID" 2>/dev/null \
        | sed \
                -e 's/\[[a-z]*\] - //' \
                -e 's/, blocks: [^)]*//' \
                -e 's/ (blocks: [^)]*)//' \
                -e "s/ (blocked by: ${EPIC_ID})//" \
                -e "s/blocked by: ${EPIC_ID}, \([^.]\)/blocked by: \1/" \
                -e "s/blocked by: ${EPIC_ID})/blocked by:)/" \
                -e 's/ (blocked by:)//' \
                -e "s/^○ ${EPIC_ID}\./○ \./" \
                -e 's/blocked by: /← /g' \
        | sed -e ':a' -e 's/\(← [^)]*\)lh-/\1/g' -e 'ta' \
        | awk '/←/{printf "\033[2m%s\033[0m\n",$0; next} {print}'
fi
