#!/usr/bin/env bash
# test-check-agent-parity.sh — Integration tests for check-agent-parity.sh
# Usage: bash scripts/test-check-agent-parity.sh
# Exit code: 0 all pass, 1 any fail
#
# The .github/ ↔ .kilo/ mirror tests were removed alongside the checks they covered
# (cap-pm1 phase 3 deleted .kilo/agents/ and .kilo/skills/). What remains guards the two
# frontmatter invariants of .github/agents/: a union tools: list, and no model: key.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${SCRIPT_DIR}/check-agent-parity.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

PASS=0
FAIL=0

assert_eq() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    printf "  ${GREEN}PASS${NC}: %s\n" "$desc"
    ((PASS++))
  else
    printf "  ${RED}FAIL${NC}: %s\n    expected: %s\n    actual:   %s\n" "$desc" "$expected" "$actual"
    ((FAIL++))
  fi
}

assert_contains() {
  local desc="$1" needle="$2" haystack="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    printf "  ${GREEN}PASS${NC}: %s\n" "$desc"
    ((PASS++))
  else
    printf "  ${RED}FAIL${NC}: %s\n    expected to contain: %s\n" "$desc" "$needle"
    ((FAIL++))
  fi
}

assert_not_contains() {
  local desc="$1" needle="$2" haystack="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    printf "  ${GREEN}PASS${NC}: %s\n" "$desc"
    ((PASS++))
  else
    printf "  ${RED}FAIL${NC}: %s (output should not contain '%s')\n" "$desc" "$needle"
    ((FAIL++))
  fi
}

# Create an agent fixture with a valid union tools: list (one name from each vocabulary)
make_md() {
  local path="$1" desc="$2" tools="${3:-\'read\', \'Read\'}"
  mkdir -p "$(dirname "$path")"
  printf -- '---\ndescription: %s\ntools: [%s]\nmode: test\n---\ncontent\n' "$desc" "$tools" >"$path"
}

scaffold() {
  mkdir -p "$1/.github/agents"
}

TMPDIR_BASE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_BASE"' EXIT

# ── Test 1: Valid agent ────────────────────────────────────────
echo "--- Test 1: agent with a union tools: list and no model:"
T="$TMPDIR_BASE/t1"; scaffold "$T"
make_md "$T/.github/agents/foo.agent.md" "Foo agent"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 on a valid agent" "0" "$ec"
assert_contains "checkmark in output" "✓" "$out"
assert_not_contains "no errors on a valid agent" "✗" "$out"

# ── Test 2: Multi-line tools: block ────────────────────────────
# extract_yaml_field joins indented continuation lines; a YAML list must still resolve
# to both vocabularies.
echo "--- Test 2: multi-line tools: block"
T="$TMPDIR_BASE/t2"; scaffold "$T"
printf -- '---\ndescription: Multi\ntools:\n  - read\n  - Read\n---\ncontent\n' \
  >"$T/.github/agents/multi.agent.md"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 for a multi-line tools: list" "0" "$ec"
assert_contains "checkmark in output" "✓" "$out"
assert_not_contains "no errors on multi-line tools" "✗" "$out"

# ── Test 3: Single-vocabulary tools list ───────────────────────
echo "--- Test 3: tools: missing a vocabulary"
T="$TMPDIR_BASE/t3"; scaffold "$T"
make_md "$T/.github/agents/copilot-only.agent.md" "Copilot only" "'search', 'read'"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when Claude vocabulary absent" "1" "$ec"
assert_contains "TOOLS in output" "✗ TOOLS:" "$out"

T="$TMPDIR_BASE/t3b"; scaffold "$T"
make_md "$T/.github/agents/claude-only.agent.md" "Claude only" "'Read', 'Grep'"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when Copilot vocabulary absent" "1" "$ec"
assert_contains "TOOLS error for Claude-absent" "✗ TOOLS:" "$out"

# ── Test 4: Agent with no tools: key at all ────────────────────
echo "--- Test 4: agent missing tools: key"
T="$TMPDIR_BASE/t4"; scaffold "$T"
printf -- '---\ndescription: No tools\nmode: test\n---\ncontent\n' \
  >"$T/.github/agents/notools.agent.md"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when tools: key is absent" "1" "$ec"
assert_contains "NO TOOLS in output" "NO TOOLS" "$out"

# ── Test 5: Missing source directory fails loudly ──────────────
echo "--- Test 5: deleted source directory is an error"
T="$TMPDIR_BASE/t5"; mkdir -p "$T"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when .github/agents/ is gone" "1" "$ec"
assert_contains "MISSING DIR in output" "MISSING DIR" "$out"

# ── Test 6: model: key is rejected ─────────────────────────────
# Probed under cap-wf3: a Copilot/Kilo model value hard-errors in Claude Code the
# moment the agent is launched, so the shared file must carry no model: at all.
echo "--- Test 6: agent carrying model: fails"
T="$TMPDIR_BASE/t6"; scaffold "$T"
printf -- '---\ndescription: Pinned\ntools: [%s]\nmodel: Claude Sonnet 4.6 (copilot)\n---\ncontent\n' \
  "'read', 'Read'" >"$T/.github/agents/pinned.agent.md"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when model: is present" "1" "$ec"
assert_contains "MODEL in output" "✗ MODEL:" "$out"

# A commented-out model: line is documentation, not a pin — the shared agent files
# use exactly this to record the per-tool preference. It must not trip the check.
echo "--- Test 6b: commented model: line passes"
T="$TMPDIR_BASE/t6b"; scaffold "$T"
printf -- '---\ndescription: Documented\ntools: [%s]\n# model: deliberately absent\n---\ncontent\n' \
  "'read', 'Read'" >"$T/.github/agents/documented.agent.md"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 when model: is only a comment" "0" "$ec"
assert_not_contains "no MODEL error for a comment" "✗ MODEL" "$out"

# ── Test 6c: bare model: key (no value) is rejected ────────────
echo "--- Test 6c: bare model: key (no value) fails"
T="$TMPDIR_BASE/t6c"; scaffold "$T"
printf -- '---\ndescription: Bare\ntools: [%s]\nmodel:\n---\ncontent\n' \
  "'read', 'Read'" >"$T/.github/agents/bare.agent.md"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when model: has no value" "1" "$ec"
assert_contains "MODEL error for bare key" "✗ MODEL:" "$out"

# ── Test 6d: multi-line model: block is rejected ───────────────
echo "--- Test 6d: multi-line model: block fails"
T="$TMPDIR_BASE/t6d"; scaffold "$T"
printf -- '---\ndescription: ML\ntools: [%s]\nmodel:\n  opencode-go/deepseek-v4-pro\n---\ncontent\n' \
  "'read', 'Read'" >"$T/.github/agents/multiline.agent.md"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when model: has indented value" "1" "$ec"
assert_contains "MODEL error for multi-line block" "✗ MODEL:" "$out"

# ── Test 6e: leading blank is handled correctly; model: is still detected ─────
echo "--- Test 6e: leading blank before frontmatter; model: still detected"
T="$TMPDIR_BASE/t6e"; scaffold "$T"
printf -- '\n---\ndescription: Leading\ntools: [%s]\nmodel: inline\n---\ncontent\n' \
  "'read', 'Read'" >"$T/.github/agents/leading.agent.md"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when leading blank before ---" "1" "$ec"
assert_contains "MODEL error for leading-blank file" "✗ MODEL:" "$out"

# ── Test 6f: model: in document body is not a false positive ───
echo "--- Test 6f: model: in body does not trip the check"
T="$TMPDIR_BASE/t6f"; scaffold "$T"
printf -- '---\ndescription: Body\ntools: [%s]\n---\nmodel: not-frontmatter\n' \
  "'read', 'Read'" >"$T/.github/agents/body.agent.md"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 when model: is only in body" "0" "$ec"
assert_not_contains "no MODEL error for body content" "✗ MODEL:" "$out"

# ── Test 7: Non-alphabetic tool name entries ──────────────────
# The [a-z]/[A-Z] case heuristic silently skips _ or digit-prefixed entries.
# Valid names alongside non-alphabetic extras must still pass; only non-alphabetic fails.
echo "--- Test 7: non-alphabetic tool name entries"
T="$TMPDIR_BASE/t7a"; scaffold "$T"
make_md "$T/.github/agents/mixed.agent.md" "Mixed" "'read', 'Read', '_helper'"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 with valid names alongside non-alphabetic" "0" "$ec"

T="$TMPDIR_BASE/t7b"; scaffold "$T"
make_md "$T/.github/agents/nonalpha.agent.md" "NonAlpha" "'_read', '_Read'"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when only non-alphabetic names" "1" "$ec"

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "───────────────────────────────────────────"
total=$((PASS + FAIL))
if [[ $FAIL -eq 0 ]]; then
  printf "${GREEN}✓ All %d tests passed${NC}\n" "$PASS"
  exit 0
else
  printf "${RED}✗ %d/%d tests failed${NC}\n" "$FAIL" "$total"
  exit 1
fi
