#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Fabian Koerner <mail@fabiankoerner.com>
# SPDX-License-Identifier: MIT
#
# Regression tests for check-release-notes-markup.sh (cap-fowo).

set -uo pipefail

CHECK="$(cd "$(dirname "$0")/.." && pwd)/check-release-notes-markup.sh"
PASS=0
FAIL=0

expect() {
    local name="$1" want="$2" input="$3" got=0
    bash "$CHECK" <<<"$input" >/dev/null || got=$?
    if [[ "$got" == "$want" ]]; then
        printf '  [ OK] %s\n' "$name"; PASS=$((PASS + 1))
    else
        printf '  [ERR] %s — expected exit %s, got %s\n' "$name" "$want" "$got"; FAIL=$((FAIL + 1))
    fi
}

expect "clean header passes" 0 "fix: upgrade to cosalette 0.12.0"
expect "tag in header fails" 1 "feat(wiz2mqtt): validate <bulb>/set payloads"
expect "tag in squash-body header fails" 1 $'fix: x\n\n* fix(gas2mqtt): use <PREFIX> name'
expect "tag in breaking note fails" 1 \
    $'fix!: x\n\nBREAKING CHANGE: `<PREFIX>_MQTT__ERROR_PUBLISH_VERBOSE` is ignored'
expect "tag on breaking continuation line fails" 1 \
    $'fix!: x\n\nBREAKING CHANGE: the setting\n`<PREFIX>_MQTT__TLS` moved'
expect "tag in ordinary body passes" 0 $'fix: x\n\nThe <PREFIX> placeholder is documented.'
expect "co-author trailer passes" 0 \
    $'fix: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>'
expect "comparison operators pass" 0 "fix(deps): pin cosalette >=0.12.0,<0.13"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
