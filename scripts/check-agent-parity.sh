#!/usr/bin/env bash
# check-agent-parity.sh — Verify parity between .github/ Copilot config and .kilo/ Kilo config
#
# Ensures every Copilot agent/prompt has a converted Kilo mirror and vice versa.
# Checks that `description` frontmatter matches between corresponding files.
# Run: bash scripts/check-agent-parity.sh
# Used in CI and as a pre-commit hook.

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

errors=0
warnings=0

# Known renames: Copilot source filename → Kilo target filename (intentional, not drift)
declare -A KNOWN_RENAMES=(
  ["orchestrator.agent.md"]="implement.md"
  ["orchestrator.prompt.md"]="implement.md"
)
declare -A KNOWN_RENAMES_REVERSE
for src in "${!KNOWN_RENAMES[@]}"; do
  KNOWN_RENAMES_REVERSE["${KNOWN_RENAMES[$src]}"]="$src"
done

# Known source filenames where description differs intentionally (skip description check)
declare -A KNOWN_DESCRIPTION_SKIP=(
  ["orchestrator.agent.md"]=1
)

# ── Helper: extract YAML frontmatter value ────────────────────
# Handles: description: "value", description: 'value', and
#           description:
#             multi-line value
extract_yaml_field() {
  local file="$1"
  local field="$2"
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

# ── Helper: check file pairs ──────────────────────────────────
check_pair() {
  local source="$1"    # .github/agents/foo.agent.md
  local target="$2"    # .kilo/agents/foo.md
  local label="$3"     # "agent" or "command"

  # Derive source_name from the argument — not from any outer-scope variable
  local source_name
  source_name=$(basename "$source")    # e.g. orchestrator.agent.md
  local target_dir
  target_dir=$(dirname "$target")

  if [[ ! -f "$target" ]]; then
    local alt="${KNOWN_RENAMES[$source_name]:-}"
    if [[ -n "$alt" ]] && [[ -f "${target_dir}/${alt}" ]]; then
      target="${target_dir}/${alt}"
    else
      printf "${RED}✗ MISSING:${NC} %s %s (no mirror for %s)\n" "$label" "$target" "$source"
      ((errors++))
      return
    fi
  fi

  # Guard against symlinks — prevents path traversal via malicious PR branches
  if [[ -L "$source" || -L "$target" ]]; then
    printf "${YELLOW}⚠ SKIP:${NC} %s ↔ %s (symlink — skipping to prevent path traversal)\n" \
      "$source" "$target"
    return
  fi

  local source_desc
  local target_desc
  source_desc=$(extract_yaml_field "$source" "description")
  target_desc=$(extract_yaml_field "$target" "description")

  if [[ -n "${KNOWN_DESCRIPTION_SKIP[$source_name]:-}" ]]; then
    printf "${YELLOW}✓${NC} %s: %s ↔ %s (intentional rename, description skip)\n" \
      "$label" "$source" "$target"
    return
  fi
  if [[ "$source_desc" != "$target_desc" ]]; then
    printf "${RED}✗ DRIFT:${NC} %s description mismatch\n" "$label"
    printf "    Source (%s): %s\n" "$source" "$source_desc"
    printf "    Target (%s): %s\n" "$target" "$target_desc"
    ((errors++))
    return
  fi

  printf "${GREEN}✓${NC} %s: %s ↔ %s\n" "$label" "$source" "$target"
}

# ── Helper: check for orphan .kilo/ files with no Copilot source ─
check_orphans() {
  local kilo_dir="$1"       # .kilo/agents or .kilo/commands
  local source_dir="$2"     # .github/agents or .github/prompts
  local source_suffix="$3"  # .agent.md or .prompt.md
  local label="$4"          # "agent" or "command"

  for target in "${kilo_dir}"/*.md; do
    [[ -f "$target" ]] || continue
    [[ "$(basename "$target")" == ".gitkeep" ]] && continue
    local bname
    bname=$(basename "$target" .md)
    local source="${source_dir}/${bname}${source_suffix}"
    if [[ ! -f "$source" ]]; then
      local alt="${KNOWN_RENAMES_REVERSE[${bname}.md]:-}"
      if [[ -n "$alt" ]]; then
        printf "${GREEN}✓${NC} %s: %s (renamed from %s)\n" "$label" "$target" "$alt"
      else
        printf "${YELLOW}⚠ ORPHAN:${NC} %s %s has no Copilot source at %s\n" \
          "$label" "$target" "$source"
        ((warnings++))
      fi
    fi
  done
}

# ── Check agents ──────────────────────────────────────────────
echo "=== Checking agent parity (.github/agents/ ↔ .kilo/agents/) ==="
echo ""

for source in .github/agents/*.agent.md; do
  [[ -f "$source" ]] || continue
  bname=$(basename "$source" .agent.md)
  target=".kilo/agents/${bname}.md"
  check_pair "$source" "$target" "agent"
done

echo ""

# ── Check commands (prompts) ──────────────────────────────────
echo "=== Checking command parity (.github/prompts/ ↔ .kilo/commands/) ==="
echo ""

for source in .github/prompts/*.prompt.md; do
  [[ -f "$source" ]] || continue
  bname=$(basename "$source" .prompt.md)
  target=".kilo/commands/${bname}.md"
  check_pair "$source" "$target" "command"
done

echo ""

# ── Reverse check: Kilo files without Copilot source ──────────
echo "=== Reverse check: Orphan .kilo/ files ==="
echo ""

check_orphans ".kilo/agents"   ".github/agents"  ".agent.md"  "agent"
check_orphans ".kilo/commands" ".github/prompts" ".prompt.md" "command"

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "───────────────────────────────────────────"
if [[ $errors -eq 0 && $warnings -eq 0 ]]; then
  printf "${GREEN}✓ All agent and command files are in sync${NC}\n"
  exit 0
elif [[ $errors -eq 0 ]]; then
  printf "${YELLOW}✓ Parity check passed with %d warning(s)${NC}\n" "$warnings"
  exit 0
else
  printf "${RED}✗ Parity check FAILED: %d error(s), %d warning(s)${NC}\n" "$errors" "$warnings"
  exit 1
fi
