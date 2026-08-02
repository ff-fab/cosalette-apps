#!/usr/bin/env bash
# check-agent-config.sh — Verify the shared multi-agent config surface
#
# Three checks:
#   1. .claude/rules/ symlinks — every symlink must resolve. A dangling symlink
#      (broken target) fails silently at Claude Code runtime: the rule is just not
#      loaded, with no error anywhere. This check makes that loud instead.
#   2. claude plugin validate — runs `claude plugin validate .github` when the
#      `claude` binary is on PATH. It is not installed in the devcontainer image
#      (and we are not adding it), so this check skips gracefully rather than
#      failing CI on a missing binary.
#   3. union `tools:` + no `model:` — the two frontmatter invariants for
#      .github/agents/ files: each agent names at least one tool from the Copilot
#      vocabulary AND one from Claude Code's vocabulary, and none of them carry a
#      model: key (the one key that cannot be shared, cap-wf3). Still relevant:
#      .github/agents/ is still read natively by both tools, so both invariants
#      still matter. Manifest structure itself (name/agents/skills paths) is now
#      covered by the check-jsonschema pre-commit hook against SchemaStore's
#      claude-code-plugin-manifest.json — that is what actually catches manifest
#      errors, so this script does not duplicate it.
#
# cap-pm1 phase 5 replaces check-agent-parity.sh: the .github/ <-> .kilo/ mirror
# checks that script existed for are gone (cap-pm1 phase 3 deleted .kilo/agents/ and
# .kilo/skills/), so its job is now config integrity, not cross-tool parity policing.
#
# Run: bash scripts/check-agent-config.sh
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

# ── Check: .claude/rules/ symlinks all resolve ─────────────────
# `[[ -e "$link" ]]` follows the symlink; it is false for a dangling link even though
# `[[ -L "$link" ]]` (which only checks "is this a symlink") would still be true.
check_claude_rules_symlinks() {
  local dir=".claude/rules"
  require_dir "$dir" || return

  local count=0 link
  while IFS= read -r -d '' link; do
    ((count++))
    if [[ ! -e "$link" ]]; then
      printf "${RED}✗ DANGLING SYMLINK:${NC} %s -> %s (target missing)\n" "$link" "$(readlink "$link")"
      ((errors++))
      continue
    fi
    printf "${GREEN}✓${NC} %s -> %s\n" "$link" "$(readlink "$link")"
  done < <(find "$dir" -maxdepth 1 -type l -print0)

  if [[ $count -eq 0 ]]; then
    printf "${RED}✗ NO SYMLINKS:${NC} %s contains no symlinks\n" "$dir"
    ((errors++))
  fi
}

# ── Check: claude plugin validate (only if the binary is on PATH) ─
# The `claude` binary is not installed in the devcontainer image and we are not adding
# it just for this check, so skip gracefully instead of failing CI in that environment.
check_claude_plugin_validate() {
  if ! command -v claude >/dev/null 2>&1; then
    printf "${YELLOW}⊘ SKIP:${NC} 'claude' binary not on PATH — skipping 'claude plugin validate .github'\n"
    return
  fi

  local out
  if out=$(claude plugin validate .github 2>&1); then
    printf "${GREEN}✓${NC} claude plugin validate .github\n"
  else
    printf "${RED}✗ PLUGIN VALIDATE:${NC} claude plugin validate .github failed\n"
    printf '%s\n' "$out" | sed 's/^/    /'
    ((errors++))
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

  # Scan frontmatter: skip leading blanks, enter at first ---, exit at second ---.
  # Exits 1 when model: is found (bad), 0 when absent (clean).
  if ! awk '/^[[:space:]]*$/{next} !f&&/^---/{f=1;next} f&&/^---/{exit found} f&&/^[[:space:]]*model:/{found=1} END{exit found}' "$source"; then
    printf "${RED}✗ MODEL:${NC} %s carries a model: key\n" "$source"
    printf "    model: is not shareable — it hard-errors in Claude Code. Remove it.\n"
    ((errors++))
    return
  fi

  printf "${GREEN}✓${NC} model: %s (absent, as required)\n" "$source"
}

# ── .claude/rules/ symlinks resolve ────────────────────────────
echo "=== Checking .claude/rules/ symlinks resolve ==="
echo ""
check_claude_rules_symlinks
echo ""

# ── claude plugin validate .github (if available) ──────────────
echo "=== Checking claude plugin validate .github ==="
echo ""
check_claude_plugin_validate
echo ""

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
  printf "${GREEN}✓ Agent config integrity checks passed${NC}\n"
  exit 0
else
  printf "${RED}✗ Agent config check FAILED: %d error(s)${NC}\n" "$errors"
  exit 1
fi
