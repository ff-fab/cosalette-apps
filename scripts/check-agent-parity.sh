#!/usr/bin/env bash
# check-agent-parity.sh — Verify parity across the shared agent-config surfaces
#
# Three checks:
#   1. .github/agents/ ↔ .kilo/agents/  — every agent has a mirror, descriptions match
#   2. .github/skills/ ↔ .kilo/skills/  — every skill has a resolving Kilo symlink
#   3. .github/agents/ union `tools:`   — each agent names at least one tool from the
#                                          Copilot vocabulary AND one from Claude Code's
#
# Run: bash scripts/check-agent-parity.sh
# Wired into CI (ci.yml `shared` job) and pre-commit.

# NOTE: `-e` is deliberately omitted. `((errors++))` evaluates to 0 on the first
# increment, which bash treats as a failing command — under `-e` the script would abort
# on the first finding instead of reporting all of them.
set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

errors=0
warnings=0

# Known renames: Copilot source filename → Kilo target filename (intentional, not drift).
# MUST stay `declare -A`: subscripts are derived from working-tree filenames, and an
# indexed array would arithmetic-evaluate them (a file named `a[$(id)]` becomes RCE).
declare -A KNOWN_RENAMES=(
  ["orchestrator.agent.md"]="implement.md"
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

  # Reject symlinks — prevents path traversal via malicious PR branches. This is an
  # ERROR, not a skip: silently passing an unverified pair would let a PR disable drift
  # detection for any agent just by converting its mirror into a symlink.
  if [[ -L "$source" || -L "$target" ]]; then
    printf "${RED}✗ SYMLINK:${NC} %s ↔ %s (agent files must be regular files)\n" \
      "$source" "$target"
    ((errors++))
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

# ── Helper: .github/skills/ ↔ .kilo/skills/ symlinks ──────────
check_skill_links() {
  local skill_dir link resolved expected
  for skill_dir in .github/skills/*/; do
    [[ -d "$skill_dir" ]] || continue
    local bname
    bname=$(basename "$skill_dir")
    link=".kilo/skills/${bname}"

    if [[ ! -L "$link" ]]; then
      printf "${RED}✗ MISSING:${NC} skill %s (no Kilo symlink for %s)\n" "$link" "$skill_dir"
      ((errors++))
      continue
    fi
    if [[ ! -e "$link" ]]; then
      printf "${RED}✗ BROKEN:${NC} skill symlink %s does not resolve\n" "$link"
      ((errors++))
      continue
    fi
    resolved=$(readlink -f "$link")
    expected=$(readlink -f "$skill_dir")
    if [[ "$resolved" != "$expected" ]]; then
      printf "${RED}✗ MISPOINTED:${NC} skill %s -> %s (expected %s)\n" \
        "$link" "$resolved" "$expected"
      ((errors++))
      continue
    fi
    printf "${GREEN}✓${NC} skill: %s ↔ %s\n" "$skill_dir" "$link"
  done
}

# ── Check agents ──────────────────────────────────────────────
echo "=== Checking agent parity (.github/agents/ ↔ .kilo/agents/) ==="
echo ""

if require_dir ".github/agents" && require_dir ".kilo/agents"; then
  for source in .github/agents/*.agent.md; do
    [[ -f "$source" ]] || continue
    bname=$(basename "$source" .agent.md)
    target=".kilo/agents/${bname}.md"
    check_pair "$source" "$target" "agent"
  done
fi

echo ""

# ── Check skills ──────────────────────────────────────────────
echo "=== Checking skill parity (.github/skills/ ↔ .kilo/skills/) ==="
echo ""

if require_dir ".github/skills" && require_dir ".kilo/skills"; then
  check_skill_links
fi

echo ""

# ── Check union tools: frontmatter ────────────────────────────
echo "=== Checking union tools: frontmatter (.github/agents/) ==="
echo ""

if require_dir ".github/agents"; then
  for source in .github/agents/*.agent.md; do
    [[ -f "$source" ]] || continue
    check_union_tools "$source"
  done
fi

echo ""

# ── Reverse check: Kilo files without Copilot source ──────────
echo "=== Reverse check: Orphan .kilo/ files ==="
echo ""

check_orphans ".kilo/agents" ".github/agents" ".agent.md" "agent"

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "───────────────────────────────────────────"
if [[ $errors -eq 0 && $warnings -eq 0 ]]; then
  printf "${GREEN}✓ Agents, skills and union tools: frontmatter are all in sync${NC}\n"
  exit 0
elif [[ $errors -eq 0 ]]; then
  printf "${YELLOW}✓ Parity check passed with %d warning(s)${NC}\n" "$warnings"
  exit 0
else
  printf "${RED}✗ Parity check FAILED: %d error(s), %d warning(s)${NC}\n" "$errors" "$warnings"
  exit 1
fi
