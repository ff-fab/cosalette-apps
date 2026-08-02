#!/usr/bin/env bash
# check-agent-parity.sh — Verify the shared agent-config surface in .github/agents/
#
# Two checks:
#   1. union `tools:`  — each agent names at least one tool from the Copilot vocabulary
#                        AND one from Claude Code's
#   2. no `model:`     — the one key that cannot be shared (cap-wf3)
#
# The .github/ ↔ .kilo/ mirror checks are gone: cap-pm1 phase 3 deleted .kilo/agents/ and
# .kilo/skills/. Kilo now reads .github/skills/ directly via `skills.paths` in kilo.jsonc,
# so there is nothing left to keep in parity. cap-pm1.10 renames this script.
#
# Run: bash scripts/check-agent-parity.sh
# Wired into CI (ci.yml `shared` job) and pre-commit.

# NOTE: `-e` is deliberately omitted. `((errors++))` evaluates to 0 on the first
# increment, which bash treats as a failing command — under `-e` the script would abort
# on the first finding instead of reporting all of them.
set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

errors=0

# ── Helper: extract YAML frontmatter value ────────────────────
# Handles: tools: "value", tools: 'value', and
#           tools:
#             multi-line value
extract_yaml_field() {
  local file="$1"
  local field="$2"
  [[ "$field" =~ ^[a-zA-Z_-]+$ ]] || { >&2 printf 'extract_yaml_field: invalid field: %s\n' "$field"; return 1; }
  local inside=0
  local value=""
  while IFS= read -r line; do
    if [[ "$line" == "---" ]]; then
      if [[ $inside -eq 0 ]]; then
        inside=1
        continue
      else
        break
      fi
    fi
    if [[ $inside -eq 1 ]]; then
      # Check for key: value on same line
      if [[ "$line" =~ ^${field}:\ *(.+)$ ]]; then
        value="${BASH_REMATCH[1]}"
        value="${value#\"}"; value="${value%\"}"
        value="${value#\'}"; value="${value%\'}"
        printf '%s' "$value"
        return
      fi
      # Check for key: (multi-line value follows)
      if [[ "$line" =~ ^${field}:\ *$ ]]; then
        # Read subsequent indented lines
        local block=""
        local block_indent=2  # Prettier indents with 2 spaces
        while IFS= read -r next_line; do
          # Stop if line is not indented (another top-level key)
          if [[ ! "$next_line" =~ ^[[:space:]]{${block_indent},} ]]; then
            break
          fi
          local stripped="${next_line:block_indent}"
          if [[ -z "$stripped" ]]; then
            continue
          fi
          if [[ -z "$block" ]]; then
            block="$stripped"
          else
            block="$block $stripped"
          fi
        done
        printf '%s' "$block"
        return
      fi
    fi
  done < "$file"
}

# ── Helper: a configured source directory must exist ──────────
# A deleted directory must fail loudly. Previously the glob simply matched nothing and
# the section reported success while checking zero files.
require_dir() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then
    printf "${RED}✗ MISSING DIR:${NC} %s does not exist — this check cannot run\n" "$dir"
    ((errors++))
    return 1
  fi
}

# ── Helper: verify union tools: frontmatter ───────────────────
# Claude Code refuses to launch an agent whose tools resolve to nothing, and Copilot
# silently drops names it does not know. A single-vocabulary list therefore breaks
# exactly one platform with no error on either — so assert both are represented.
check_union_tools() {
  local source="$1"
  local raw copilot=0 claude=0 entry

  raw=$(extract_yaml_field "$source" "tools")
  if [[ -z "$raw" ]]; then
    printf "${RED}✗ NO TOOLS:${NC} %s has no tools: key\n" "$source"
    ((errors++))
    return
  fi

  raw="${raw//[\[\]\'\"]/ }"
  for entry in $(printf '%s' "$raw" | tr ',' ' '); do
    case "$entry" in
      [a-z]*) copilot=1 ;;
      [A-Z]*) claude=1 ;;
    esac
  done

  if [[ $copilot -eq 0 || $claude -eq 0 ]]; then
    printf "${RED}✗ TOOLS:${NC} %s is missing a vocabulary (copilot=%d claude=%d)\n" \
      "$source" "$copilot" "$claude"
    printf "    tools: %s\n" "$raw"
    ((errors++))
    return
  fi

  printf "${GREEN}✓${NC} tools: %s (both vocabularies present)\n" "$source"
}

# ── Helper: assert model: is absent in shared agent files ───────────
# `model:` is the one frontmatter key all three tools recognise with mutually
# incompatible vocabularies (Copilot "Claude Sonnet 4.6 (copilot)", Claude Code
# sonnet/opus/haiku/inherit, Kilo "opencode-go/..."). Probed under cap-wf3: a foreign
# value does NOT fall back — Claude Code registers the agent and then hard-errors the
# moment it is launched ("There's an issue with the selected model"). So the shared
# file carries no model: at all; per-tool pins belong in per-tool copies.
check_model_absent() {
  local source="$1"

  # Scan frontmatter directly — skip leading blank lines, match indented key.
  if awk '/^[[:space:]]*$/{next} !f&&/^---/{f=1;next} f&&/^---/{exit} f&&/^[[:space:]]*model:/{found=1} END{exit !found}' "$source"; then
    printf "${RED}✗ MODEL:${NC} %s carries a model: key\n" "$source"
    printf "    model: is not shareable — it hard-errors in Claude Code. Remove it.\n"
    ((errors++))
    return
  fi

  printf "${GREEN}✓${NC} model: %s (absent, as required)\n" "$source"
}

# ── Check union tools: frontmatter + model: absence (.github/agents/) ─
echo "=== Checking union tools: frontmatter (.github/agents/) ==="
echo ""

if require_dir ".github/agents"; then
  while IFS= read -r -d '' source; do
    check_union_tools "$source"
  done < <(find .github/agents -maxdepth 1 -name '*.agent.md' -print0)

  echo ""

  echo "=== Checking model: is absent (.github/agents/) ==="
  echo ""

  while IFS= read -r -d '' source; do
    check_model_absent "$source"
  done < <(find .github/agents -maxdepth 1 -name '*.agent.md' -print0)
fi

echo ""

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "───────────────────────────────────────────"
if [[ $errors -eq 0 ]]; then
  printf "${GREEN}✓ union tools: and model: absence hold across .github/agents/${NC}\n"
  exit 0
else
  printf "${RED}✗ Agent config check FAILED: %d error(s)${NC}\n" "$errors"
  exit 1
fi
