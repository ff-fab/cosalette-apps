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

# Known renames: Copilot source → Kilo target (intentional, not drift)
declare -A KNOWN_RENAMES=(
  ["orchestrator.agent.md"]="implement.md"
  ["orchestrator.prompt.md"]="implement.md"
)
declare -A KNOWN_RENAMES_REVERSE
for src in "${!KNOWN_RENAMES[@]}"; do
  KNOWN_RENAMES_REVERSE["${KNOWN_RENAMES[$src]}"]="$src"
done

# Known renames where description differs intentionally (skip description check)
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
  local indent=""
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
        echo "$value"
        return
      fi
      # Check for key: (multi-line value follows)
      if [[ "$line" =~ ^${field}:\ *$ ]]; then
        # Read subsequent indented lines
        local block=""
        local block_indent=2  # Prettier indents with 2 spaces
        while IFS= read -r next_line; do
          # Stop if line is not indented (another top-level key) or is empty
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
        echo "$block"
        return
      fi
    fi
  done < "$file"
}

# ── Helper: check file pairs ──────────────────────────────────
check_pair() {
  local source="$1"   # .github/agents/foo.agent.md
  local target="$2"    # .kilo/agents/foo.md
  local label="$3"     # "agent" or "prompt/command"

  if [[ ! -f "$target" ]]; then
    alt="${KNOWN_RENAMES[${basename}.agent.md]}"
    if [[ -n "$alt" ]] && [[ -f ".kilo/agents/${alt}" ]]; then
      target=".kilo/agents/${alt}"
    else
      echo -e "${RED}✗ MISSING:${NC} ${label} ${target} (no mirror for ${source})"
      ((errors++))
      return
    fi
  fi

  local source_desc
  local target_desc
  source_desc=$(extract_yaml_field "$source" "description")
  target_desc=$(extract_yaml_field "$target" "description")

  if [[ -n "${KNOWN_DESCRIPTION_SKIP[${basename}.${label}]:-}" ]] || \
     [[ "${label}" == "agent" && -n "${KNOWN_DESCRIPTION_SKIP[${basename}.agent.md]:-}" ]] || \
     [[ "${label}" == "command" && -n "${KNOWN_DESCRIPTION_SKIP[${basename}.prompt.md]:-}" ]]; then
    echo -e "${YELLOW}✓${NC} ${label}: ${source} ↔ ${target} (intentional rename, description skip)"
    return
  fi
  if [[ "$source_desc" != "$target_desc" ]]; then
    echo -e "${RED}✗ DRIFT:${NC} ${label} description mismatch"
    echo "    Source (${source}): ${source_desc}"
    echo "    Target (${target}): ${target_desc}"
    ((errors++))
    return
  fi

  echo -e "${GREEN}✓${NC} ${label}: ${source} ↔ ${target}"
}

# ── Check agents ──────────────────────────────────────────────
echo "=== Checking agent parity (.github/agents/ ↔ .kilo/agents/) ==="
echo ""

for source in .github/agents/*.agent.md; do
  [[ -f "$source" ]] || continue
  basename=$(basename "$source" .agent.md)
  target=".kilo/agents/${basename}.md"
  check_pair "$source" "$target" "agent"
done

echo ""

# ── Check commands (prompts) ──────────────────────────────────
echo "=== Checking command parity (.github/prompts/ ↔ .kilo/commands/) ==="
echo ""

for source in .github/prompts/*.prompt.md; do
  [[ -f "$source" ]] || continue
  basename=$(basename "$source" .prompt.md)
  target=".kilo/commands/${basename}.md"
  check_pair "$source" "$target" "command"
done

echo ""

# ── Reverse check: Kilo files without Copilot source ──────────
echo "=== Reverse check: Orphan .kilo/ files ==="
echo ""

for target in .kilo/agents/*.md; do
  [[ -f "$target" ]] || continue
  [[ "$(basename "$target")" == ".gitkeep" ]] && continue
  basename=$(basename "$target" .md)
  source=".github/agents/${basename}.agent.md"
  if [[ ! -f "$source" ]]; then
    alt="${KNOWN_RENAMES_REVERSE[${basename}.md]}"
    if [[ -n "$alt" ]]; then
      echo -e "${GREEN}✓${NC} agent: ${target} (renamed from ${alt})"
    else
      echo -e "${YELLOW}⚠ ORPHAN:${NC} agent ${target} has no Copilot source at ${source}"
      ((warnings++))
    fi
  fi
done

for target in .kilo/commands/*.md; do
  [[ -f "$target" ]] || continue
  [[ "$(basename "$target")" == ".gitkeep" ]] && continue
  basename=$(basename "$target" .md)
  source=".github/prompts/${basename}.prompt.md"
  if [[ ! -f "$source" ]]; then
    alt="${KNOWN_RENAMES_REVERSE[${basename}.md]}"
    if [[ -n "$alt" ]]; then
      echo -e "${GREEN}✓${NC} command: ${target} (renamed from ${alt})"
    else
      echo -e "${YELLOW}⚠ ORPHAN:${NC} command ${target} has no Copilot source at ${source}"
      ((warnings++))
    fi
  fi
done

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "───────────────────────────────────────────"
if [[ $errors -eq 0 && $warnings -eq 0 ]]; then
  echo -e "${GREEN}✓ All agent and command files are in sync${NC}"
  exit 0
elif [[ $errors -eq 0 ]]; then
  echo -e "${YELLOW}✓ Parity check passed with ${warnings} warning(s)${NC}"
  exit 0
else
  echo -e "${RED}✗ Parity check FAILED: ${errors} error(s), ${warnings} warning(s)${NC}"
  exit 1
fi
