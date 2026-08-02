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

# Create an agent fixture with a valid union tools: list (one name from each vocabulary)
make_md() {
  local path="$1" desc="$2" tools="${3:-\'read\', \'Read\'}"
  mkdir -p "$(dirname "$path")"
  printf -- '---\ndescription: %s\ntools: [%s]\nmode: test\n---\ncontent\n' "$desc" "$tools" >"$path"
}

make_md_multiline() {
  local path="$1" desc1="$2" desc2="$3"
  mkdir -p "$(dirname "$path")"
  printf -- '---\ndescription:\n  %s\n  %s\ntools: [%s]\nmode: test\n---\ncontent\n' \
    "$desc1" "$desc2" "'read', 'Read'" >"$path"
}

# Every check requires its source directories to exist, so scaffold all four.
scaffold() {
  local root="$1"
  mkdir -p "$root/.github/agents" "$root/.kilo/agents" \
           "$root/.github/skills" "$root/.kilo/skills"
}

# Create a skill directory plus its Kilo symlink
make_skill() {
  local root="$1" name="$2"
  mkdir -p "$root/.github/skills/$name"
  printf -- '---\nname: %s\n---\ncontent\n' "$name" >"$root/.github/skills/$name/SKILL.md"
  ln -sfn "../../.github/skills/$name" "$root/.kilo/skills/$name"
}

TMPDIR_BASE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_BASE"' EXIT

# ── Test 1: Perfect match ──────────────────────────────────────
echo "--- Test 1: matching pair"
T="$TMPDIR_BASE/t1"; scaffold "$T"
make_md "$T/.github/agents/foo.agent.md" "Foo agent"
make_md "$T/.kilo/agents/foo.md" "Foo agent"
make_skill "$T" "demo"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 on match" "0" "$ec"
assert_contains "checkmark in output" "✓" "$out"
assert_not_contains "no errors on match" "MISSING" "$out"

# ── Test 2: Missing .kilo/ mirror ─────────────────────────────
echo "--- Test 2: missing kilo mirror"
T="$TMPDIR_BASE/t2"; scaffold "$T"
make_md "$T/.github/agents/bar.agent.md" "Bar agent"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 on missing mirror" "1" "$ec"
assert_contains "MISSING in output" "MISSING" "$out"

# ── Test 3: Description drift ──────────────────────────────────
echo "--- Test 3: description drift"
T="$TMPDIR_BASE/t3"; scaffold "$T"
make_md "$T/.github/agents/baz.agent.md" "Original description"
make_md "$T/.kilo/agents/baz.md" "Changed description"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 on drift" "1" "$ec"
assert_contains "DRIFT in output" "DRIFT" "$out"

# ── Test 4: Known agent rename (orchestrator → implement) ──────
echo "--- Test 4: known agent rename"
T="$TMPDIR_BASE/t4"; scaffold "$T"
make_md "$T/.github/agents/orchestrator.agent.md" "Orchestrator description"
make_md "$T/.kilo/agents/implement.md" "Implement description"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 for known agent rename" "0" "$ec"
assert_not_contains "no MISSING for known agent rename" "MISSING" "$out"

# ── Test 5: Orphan .kilo/ agent (warning, not error) ──────────
echo "--- Test 5: orphan kilo agent"
T="$TMPDIR_BASE/t5"; scaffold "$T"
make_md "$T/.kilo/agents/orphan-agent.md" "Orphan"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 for orphan (warning only)" "0" "$ec"
assert_contains "ORPHAN in output" "ORPHAN" "$out"

# ── Test 6: KNOWN_RENAMES_REVERSE reverse lookup ──────────────
echo "--- Test 6: reverse rename lookup shows 'renamed from'"
T="$TMPDIR_BASE/t6"; scaffold "$T"
make_md "$T/.github/agents/orchestrator.agent.md" "Orchestrator description"
make_md "$T/.kilo/agents/implement.md" "Implement description"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_contains "'renamed from' in reverse check" "renamed from" "$out"

# ── Test 7: Multi-line description matching ────────────────────
echo "--- Test 7: multi-line description matches joined single-line"
T="$TMPDIR_BASE/t7"; scaffold "$T"
make_md_multiline "$T/.github/agents/multi.agent.md" "First part" "second part"
printf -- '---\ndescription: First part second part\ntools: [%s]\nmode: test\n---\ncontent\n' \
  "'read', 'Read'" >"$T/.kilo/agents/multi.md"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 0 multi-line to single-line match" "0" "$ec"

# ── Test 8: set -u safety — unknown .kilo/ files don't crash ──
echo "--- Test 8: unknown kilo files don't crash (set -u safety)"
T="$TMPDIR_BASE/t8"; scaffold "$T"
make_md "$T/.kilo/agents/totally-unknown.md" "Unknown"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "no crash for unknown kilo files" "0" "$ec"
assert_contains "ORPHAN for unknown agent" "ORPHAN" "$out"

# ── Test 9: Missing skill symlink ─────────────────────────────
echo "--- Test 9: skill with no Kilo symlink"
T="$TMPDIR_BASE/t9"; scaffold "$T"
make_md "$T/.github/agents/foo.agent.md" "Foo agent"
make_md "$T/.kilo/agents/foo.md" "Foo agent"
mkdir -p "$T/.github/skills/unlinked"
printf -- '---\nname: unlinked\n---\ncontent\n' >"$T/.github/skills/unlinked/SKILL.md"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when a skill has no Kilo symlink" "1" "$ec"
assert_contains "MISSING for unlinked skill" "MISSING" "$out"

# ── Test 10: Broken skill symlink ─────────────────────────────
echo "--- Test 10: skill symlink that does not resolve"
T="$TMPDIR_BASE/t10"; scaffold "$T"
make_md "$T/.github/agents/foo.agent.md" "Foo agent"
make_md "$T/.kilo/agents/foo.md" "Foo agent"
make_skill "$T" "demo"
ln -sfn "../../.github/skills/does-not-exist" "$T/.kilo/skills/demo"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 on broken skill symlink" "1" "$ec"
assert_contains "BROKEN for dangling symlink" "BROKEN" "$out"

# ── Test 11: Single-vocabulary tools list ─────────────────────
echo "--- Test 11: tools: missing a vocabulary"
T="$TMPDIR_BASE/t11"; scaffold "$T"
make_md "$T/.github/agents/copilot-only.agent.md" "Copilot only" "'search', 'read'"
make_md "$T/.kilo/agents/copilot-only.md" "Copilot only"
make_skill "$T" "demo"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when Claude vocabulary absent" "1" "$ec"
assert_contains "TOOLS in output" "TOOLS" "$out"

T="$TMPDIR_BASE/t11b"; scaffold "$T"
make_md "$T/.github/agents/claude-only.agent.md" "Claude only" "'Read', 'Grep'"
make_md "$T/.kilo/agents/claude-only.md" "Claude only"
make_skill "$T" "demo"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when Copilot vocabulary absent" "1" "$ec"

# ── Test 12: Symlinked agent mirror is an error, not a skip ───
echo "--- Test 12: symlinked agent pair fails"
T="$TMPDIR_BASE/t12"; scaffold "$T"
make_md "$T/.github/agents/foo.agent.md" "Foo agent"
ln -sfn "../../.github/agents/foo.agent.md" "$T/.kilo/agents/foo.md"
make_skill "$T" "demo"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 on symlinked agent mirror" "1" "$ec"
assert_contains "SYMLINK in output" "SYMLINK" "$out"

# ── Test 13: Missing source directory fails loudly ────────────
echo "--- Test 13: deleted source directory is an error"
T="$TMPDIR_BASE/t13"; scaffold "$T"
make_md "$T/.github/agents/foo.agent.md" "Foo agent"
make_md "$T/.kilo/agents/foo.md" "Foo agent"
rmdir "$T/.kilo/skills"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when a configured directory is gone" "1" "$ec"
assert_contains "MISSING DIR in output" "MISSING DIR" "$out"

# ── Test 14: Agent with no tools: key at all ──────────────────
echo "--- Test 14: agent missing tools: key"
T="$TMPDIR_BASE/t14"; scaffold "$T"
mkdir -p "$T/.github/agents"
printf -- '---\ndescription: No tools\nmode: test\n---\ncontent\n' \
  >"$T/.github/agents/notools.agent.md"
printf -- '---\ndescription: No tools\nmode: test\n---\ncontent\n' \
  >"$T/.kilo/agents/notools.md"
make_skill "$T" "demo"
out=$(cd "$T" && bash "$SCRIPT" 2>&1); ec=$?
assert_eq "exit 1 when tools: key is absent" "1" "$ec"
assert_contains "NO TOOLS in output" "NO TOOLS" "$out"

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
