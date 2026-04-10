#!/usr/bin/env bash
# Interactive epic/task browser using fzf with adaptive preview pane.
# Called by: task plan:ui
#
# Two-level navigation:
#   1. Epic view — colored progress bars, preview shows children backlog
#   2. Task view — status-tagged task list, preview shows task description
#
# Layout adapts to terminal width:
#   ≥120 cols  → preview on the right (60%)
#   80–119     → preview below (50%)
#   <80        → preview hidden (toggle with ?)
#
# Keybindings (Epic view):
#   Enter / →  → drill into selected epic (show tasks)
#   Esc   / ←  → exit
#   ?          → toggle preview pane
#
# Keybindings (Task view):
#   Enter / →  → show full task details, then return to task list
#   Esc   / ←  → go back to epic view
#   ?          → toggle preview pane

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Guard: fzf required -------------------------------------------------- #
if ! command -v fzf &>/dev/null; then
    echo "fzf is required for interactive mode." >&2
    echo "Install: apt install fzf" >&2
    echo "Use 'task plan' for non-interactive overview." >&2
    exit 1
fi

BAR_WIDTH=20

# --- Temp files (shared across functions) --------------------------------- #
ORPHAN_CACHE=$(mktemp)
ALL_TASKS_CACHE=$(mktemp)
CHILD_STATS_CACHE=$(mktemp)
trap 'rm -f "$ORPHAN_CACHE" "$ALL_TASKS_CACHE" "$CHILD_STATS_CACHE"' EXIT

# =========================================================================== #
# Helper: fetch all tasks once into cache                                      #
# =========================================================================== #
fetch_all_tasks() {
    if [ ! -s "$ALL_TASKS_CACHE" ]; then
        printf '\033[2mLoading tasks…\033[0m' >&2
        bd list --all --json --limit 0 2>/dev/null > "$ALL_TASKS_CACHE"
        printf '\r\033[K' >&2
    fi
}

# =========================================================================== #
# Helper: detect orphaned tasks (non-epic, no parent field)                    #
# =========================================================================== #
detect_orphaned_tasks() {
    fetch_all_tasks
    jq -r '.[] | select(.issue_type != "epic") | select(.parent == null or .parent == "") | .id' \
        "$ALL_TASKS_CACHE"
}

# =========================================================================== #
# Helper: build epic fzf lines                                                #
# =========================================================================== #
build_epic_lines() {
    local ALL_EPICS CHILD_STATS MAX_TITLE

    fetch_all_tasks

    ALL_EPICS=$(jq -r '[.[] | select(.issue_type == "epic")] | sort_by(.title) | .[] | [.id, .status, .title] | @tsv' \
        "$ALL_TASKS_CACHE")

    if [ -z "$ALL_EPICS" ]; then
        echo "No epics found." >&2
        return 1
    fi

    # Pre-compute child counts per epic in one jq pass
    jq '
        [.[] | select(.issue_type != "epic" and .parent != null and .parent != "")]
        | group_by(.parent)
        | map({key: .[0].parent, value: {total: length, closed: ([.[] | select(.status == "closed")] | length)}})
        | from_entries' "$ALL_TASKS_CACHE" > "$CHILD_STATS_CACHE"

    # Calculate max title width for aligned columns
    MAX_TITLE=0
    while IFS=$'\t' read -r _ _ title; do
        local len=${#title}
        (( len > MAX_TITLE )) && MAX_TITLE=$len
    done <<< "$ALL_EPICS"

    local FZF_LINES=""
    while IFS=$'\t' read -r id status title; do
        local total closed filled empty pct bar_fill bar_empty bullet bar line

        total=$(jq -r --arg id "$id" '.[$id].total // 0' "$CHILD_STATS_CACHE")
        closed=$(jq -r --arg id "$id" '.[$id].closed // 0' "$CHILD_STATS_CACHE")

        # A closed epic is 100% by definition — regardless of child state
        if [ "$status" = "closed" ] && [ "$total" -gt 0 ] 2>/dev/null; then
            closed=$total
        fi

        # Normalize empty/null to 0
        total=${total:-0}; [ "$total" = "null" ] && total=0
        closed=${closed:-0}; [ "$closed" = "null" ] && closed=0

        if [ "$total" -gt 0 ] 2>/dev/null; then
            filled=$(( closed * BAR_WIDTH / total ))
            empty=$(( BAR_WIDTH - filled ))
            pct=$(( closed * 100 / total ))
        else
            filled=0; empty=$BAR_WIDTH; pct=0
        fi

        bar_fill=""; bar_empty=""
        for ((i=0; i<filled; i++)); do bar_fill+="█"; done
        for ((i=0; i<empty; i++)); do bar_empty+="░"; done

        if [ "$pct" -eq 100 ]; then
            bullet="\033[32m●\033[0m"
            bar="\033[32m${bar_fill}\033[0m"
        elif [ "$pct" -gt 0 ]; then
            bullet="\033[33m○\033[0m"
            bar="\033[33m${bar_fill}\033[2m${bar_empty}\033[0m"
        else
            bullet="\033[2m○\033[0m"
            bar="\033[2m${bar_empty}\033[0m"
        fi

        line=$(printf "%-8s  %b  %-${MAX_TITLE}s  %b  %3d%%  (%d/%d)" \
            "$id" "$bullet" "$title" "$bar" "$pct" "$closed" "$total")

        if [ -z "$FZF_LINES" ]; then
            FZF_LINES="$line"
        else
            FZF_LINES="${FZF_LINES}"$'\n'"${line}"
        fi
    done <<< "$ALL_EPICS"

    # --- Detect orphaned tasks and append virtual epic if any ---------------- #
    local ORPHANED
    ORPHANED=$(detect_orphaned_tasks)
    if [ -n "$ORPHANED" ]; then
        # Cache orphan IDs for build_task_lines
        echo "$ORPHANED" > "$ORPHAN_CACHE"
        local orphan_count
        orphan_count=$(echo "$ORPHANED" | wc -l | tr -d ' ')

        local orphan_bar_fill="" orphan_bar_empty=""
        for ((i=0; i<BAR_WIDTH; i++)); do orphan_bar_empty+="░"; done

        local orphan_line
        orphan_line=$(printf "%-8s  \033[31m⚠\033[0m  %-${MAX_TITLE}s  \033[31m%s\033[0m  %3s   (%d)" \
            "_orphan" "Orphaned tasks" "$orphan_bar_empty" "  —" "$orphan_count")

        FZF_LINES="${FZF_LINES}"$'\n'"${orphan_line}"
    else
        # Clear cache
        : > "$ORPHAN_CACHE"
    fi

    echo -e "$FZF_LINES"
}

# =========================================================================== #
# Helper: build task fzf lines for an epic                                     #
# =========================================================================== #
build_task_lines() {
    local EPIC_ID="$1"
    local TASKS MAX_TITLE FZF_LINES=""

    if [ "$EPIC_ID" = "_orphan" ]; then
        # Virtual epic: list orphaned tasks from cache
        if [ ! -s "$ORPHAN_CACHE" ]; then
            echo "No orphaned tasks." >&2
            return 1
        fi
        fetch_all_tasks
        local orphan_ids_json
        orphan_ids_json=$(jq -R -s 'split("\n") | map(select(. != ""))' "$ORPHAN_CACHE")
        TASKS=$(jq -r --argjson ids "$orphan_ids_json" '
                    ($ids | map({(.): true}) | add) as $idset
                    | [.[]
                        | select(.issue_type != "epic")
                        | select(.id as $i | $idset[$i])
                    ]
                    | sort_by(.priority, .title)
                    | .[]
                    | [.id, .status, (.priority // 2 | tostring), .title]
                    | @tsv' "$ALL_TASKS_CACHE")
    else
        fetch_all_tasks
        TASKS=$(jq -r --arg id "$EPIC_ID" \
            '[.[] | select(.parent == $id)] | sort_by(.priority, .title) | .[] | [.id, .status, .priority, .title] | @tsv' \
            "$ALL_TASKS_CACHE")
    fi

    if [ -z "$TASKS" ]; then
        echo "No tasks in this epic." >&2
        return 1
    fi

    # Calculate max title width
    MAX_TITLE=0
    while IFS=$'\t' read -r _ _ _ title; do
        local len=${#title}
        (( len > MAX_TITLE )) && MAX_TITLE=$len
    done <<< "$TASKS"

    while IFS=$'\t' read -r id status priority title; do
        local icon line

        case "$status" in
            closed)      icon="\033[32m✓\033[0m" ;;     # green check
            in_progress) icon="\033[33m●\033[0m" ;;     # yellow dot
            blocked)     icon="\033[2m⊘\033[0m" ;;      # dim blocked
            *)           icon="\033[2m○\033[0m" ;;       # dim open
        esac

        line=$(printf "%-12s  %b  P%s  %-${MAX_TITLE}s  %s" \
            "$id" "$icon" "$priority" "$title" "$status")

        if [ -z "$FZF_LINES" ]; then
            FZF_LINES="$line"
        else
            FZF_LINES="${FZF_LINES}"$'\n'"${line}"
        fi
    done <<< "$TASKS"

    echo -e "$FZF_LINES"
}

# =========================================================================== #
# State machine: EPICS → TASKS → DETAIL → TASKS → ... → EXIT                 #
# =========================================================================== #
STATE="EPICS"
SELECTED_EPIC_ID=""
SELECTED_EPIC_TITLE=""
TASK_ID=""
CACHED_EPIC_LINES=""

while true; do
    case "$STATE" in

        # ----- Epic picker ----------------------------------------------------- #
        EPICS)
            if [ -z "$CACHED_EPIC_LINES" ]; then
                CACHED_EPIC_LINES=$(build_epic_lines) || exit 1
            fi

            SELECTED=$(echo "$CACHED_EPIC_LINES" \
                | fzf \
                        --ansi \
                        --no-sort \
                        --cycle \
                        --header '→/Enter: drill in │ ←/Esc: quit │ ?: toggle preview' \
                        --preview "bash \"$SCRIPT_DIR/plan-preview.sh\" {1} \"$ORPHAN_CACHE\" \"$ALL_TASKS_CACHE\"" \
                        --preview-window 'right,60%,border-left,wrap,<120(down,50%,border-top,wrap),<80(hidden)' \
                        --bind '?:toggle-preview,right:accept,left:abort' \
                || true)

            if [ -n "$SELECTED" ]; then
                SELECTED_EPIC_ID=$(echo "$SELECTED" | awk '{print $1}')
                if [ "$SELECTED_EPIC_ID" = "_orphan" ]; then
                    SELECTED_EPIC_TITLE="Orphaned tasks"
                else
                    SELECTED_EPIC_TITLE=$(jq -r --arg id "$SELECTED_EPIC_ID" \
                        '.[] | select(.id == $id) | .title' "$ALL_TASKS_CACHE")
                fi
                STATE="TASKS"
            else
                STATE="EXIT"
            fi
            ;;

        # ----- Task picker within an epic -------------------------------------- #
        TASKS)
            TASK_LINES=$(build_task_lines "$SELECTED_EPIC_ID") || { STATE="EPICS"; continue; }

            SELECTED=$(echo "$TASK_LINES" \
                | fzf \
                        --ansi \
                        --no-sort \
                        --cycle \
                        --header "◂ ${SELECTED_EPIC_TITLE} │ ←/Esc: back │ →/Enter: details │ ?: toggle preview" \
                        --preview "bash \"$SCRIPT_DIR/plan-task-preview.sh\" {1} \"$SELECTED_EPIC_ID\" \"$ALL_TASKS_CACHE\"" \
                        --preview-window 'right,60%,border-left,wrap,<120(down,50%,border-top,wrap),<80(hidden)' \
                        --bind '?:toggle-preview,right:accept,left:abort' \
                || true)

            if [ -n "$SELECTED" ]; then
                TASK_ID=$(echo "$SELECTED" | awk '{print $1}')
                STATE="DETAIL"
            else
                # Esc → go back to epic view
                STATE="EPICS"
            fi
            ;;

        # ----- Show full task details, then return to task list ---------------- #
        DETAIL)
            clear
            bd show "$TASK_ID" 2>/dev/null
            echo ""
            printf "\033[2mPress any key to return to task list...\033[0m"
            read -rsn1
            # Drain any trailing bytes from multi-byte sequences (e.g. arrow keys
            # send \e[A — three bytes; read -n1 only consumes the first).
            read -rsn5 -t 0.05 2>/dev/null || true
            STATE="TASKS"
            ;;

        # ----- Exit ------------------------------------------------------------ #
        EXIT)
            break
            ;;
    esac
done
