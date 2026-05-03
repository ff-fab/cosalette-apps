#!/usr/bin/env bash
# test-check-agent-parity.sh — Integration tests for check-agent-parity.sh
# Usage: bash scripts/test-check-agent-parity.sh
# Exit code: 0 all pass, 1 any fail

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

# Create a fixture file with YAML frontmatter
make_md() {
  local path="$1" desc="$2"
  mkdir -p "$(dirname "$path")"
  printf -- '---\ndescription: %s\nmode: test\n---\ncontent\n' "$desc" >"$path"
}

make_md_multiline() {
  local path="$1" desc1="$2" desc2="$3"
  mkdir -p "$(dirname "$path")"
  printf -- '---\ndescription:\n  %s\n  %s\nmode: test\n---\ncontent\n' "$desc1" "$desc2" >"$path"
}

TMPDIR_BASE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_BASE"' EXIT

# Run the parity script in a given directory; capture stdout+stderr and exit code.
# Output format: raw output (exit code accessible via $?)
run_in() {
  local dir="$1"
  (cd "$dir" && bash "$SCRIPT" 2>&1) || true
}

# ── Test 1: Perfect match ──────────────────────────────────────
echo "--- Test 1: matching pair"
T="$TMPDIR_BASE/t1"
make_md "$T/.github/agents/foo.agent.md" "Foo agent"
make_md "$T/.kilo/agents/foo.md" "Foo agent"
mkdir -p "$T/.github/prompts" "$T/.kilo/commands"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 on match" "0" "$ec"
assert_contains "checkmark in output" "✓" "$out"
assert_not_contains "no errors on match" "MISSING" "$out"

# ── Test 2: Missing .kilo/ mirror ─────────────────────────────
echo "--- Test 2: missing kilo mirror"
T="$TMPDIR_BASE/t2"
make_md "$T/.github/agents/bar.agent.md" "Bar agent"
mkdir -p "$T/.kilo/agents" "$T/.github/prompts" "$T/.kilo/commands"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 on missing mirror" "1" "$ec"
assert_contains "MISSING in output" "MISSING" "$out"

# ── Test 3: Description drift ──────────────────────────────────
echo "--- Test 3: description drift"
T="$TMPDIR_BASE/t3"
make_md "$T/.github/agents/baz.agent.md" "Original description"
make_md "$T/.kilo/agents/baz.md" "Changed description"
mkdir -p "$T/.github/prompts" "$T/.kilo/commands"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 on drift" "1" "$ec"
assert_contains "DRIFT in output" "DRIFT" "$out"

# ── Test 4: Known agent rename (orchestrator → implement) ──────
echo "--- Test 4: known agent rename"
T="$TMPDIR_BASE/t4"
make_md "$T/.github/agents/orchestrator.agent.md" "Orchestrator description"
make_md "$T/.kilo/agents/implement.md" "Implement description"
mkdir -p "$T/.github/prompts" "$T/.kilo/commands"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 for known agent rename" "0" "$ec"
assert_not_contains "no MISSING for known agent rename" "MISSING" "$out"

# ── Test 5: Known command rename (orchestrator.prompt → implement) ─
echo "--- Test 5: known command rename"
T="$TMPDIR_BASE/t5"
mkdir -p "$T/.github/agents" "$T/.kilo/agents"
make_md "$T/.github/prompts/orchestrator.prompt.md" "Orchestrator prompt"
make_md "$T/.kilo/commands/implement.md" "Orchestrator prompt"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 for known command rename" "0" "$ec"
assert_not_contains "no MISSING for known command rename" "MISSING" "$out"

# ── Test 6: Orphan .kilo/ agent (warning, not error) ──────────
echo "--- Test 6: orphan kilo agent"
T="$TMPDIR_BASE/t6"
mkdir -p "$T/.github/agents" "$T/.github/prompts"
make_md "$T/.kilo/agents/orphan-agent.md" "Orphan"
mkdir -p "$T/.kilo/commands"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 for orphan (warning only)" "0" "$ec"
assert_contains "ORPHAN in output" "ORPHAN" "$out"

# ── Test 7: KNOWN_RENAMES_REVERSE reverse lookup ──────────────
echo "--- Test 7: reverse rename lookup shows 'renamed from'"
T="$TMPDIR_BASE/t7"
make_md "$T/.github/agents/orchestrator.agent.md" "Orchestrator description"
make_md "$T/.kilo/agents/implement.md" "Implement description"
mkdir -p "$T/.github/prompts" "$T/.kilo/commands"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_contains "'renamed from' in reverse check" "renamed from" "$out"

# ── Test 8: Multi-line description matching ────────────────────
echo "--- Test 8: multi-line description matches joined single-line"
T="$TMPDIR_BASE/t8"
make_md_multiline "$T/.github/agents/multi.agent.md" "First part" "second part"
mkdir -p "$T/.kilo/agents"
printf -- '---\ndescription: First part second part\nmode: test\n---\ncontent\n' \
  >"$T/.kilo/agents/multi.md"
mkdir -p "$T/.github/prompts" "$T/.kilo/commands"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 multi-line to single-line match" "0" "$ec"

# ── Test 9: set -u safety — unknown .kilo/ files don't crash ──
echo "--- Test 9: unknown kilo files don't crash (set -u safety)"
T="$TMPDIR_BASE/t9"
mkdir -p "$T/.github/agents" "$T/.github/prompts"
make_md "$T/.kilo/agents/totally-unknown.md" "Unknown"
make_md "$T/.kilo/commands/totally-unknown.md" "Unknown"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "no crash for unknown kilo files" "0" "$ec"
assert_contains "ORPHAN for unknown agent" "ORPHAN" "$out"

# ── Test 10: Missing command mirror ───────────────────────────
echo "--- Test 10: missing kilo command mirror"
T="$TMPDIR_BASE/t10"
mkdir -p "$T/.github/agents" "$T/.kilo/agents"
make_md "$T/.github/prompts/my-command.prompt.md" "My command"
mkdir -p "$T/.kilo/commands"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 on missing command mirror" "1" "$ec"
assert_contains "MISSING in command output" "MISSING" "$out"

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
