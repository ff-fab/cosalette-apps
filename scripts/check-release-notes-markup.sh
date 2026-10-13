#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Fabian Koerner <mail@fabiankoerner.com>
# SPDX-License-Identifier: MIT
#
# scripts/check-release-notes-markup.sh — Reject HTML-like tags in text that
# Release Please copies into its release PR body (cap-fowo).
#
# Release Please reads its own PR body back with an HTML parser when the PR
# merges. A bare tag such as <PREFIX> — even inside Markdown backticks — opens
# an element that swallows every later <details> section, so only the first
# app gets a tag and GitHub release; the rest are skipped silently and the next
# release PR lists their whole history.
#
# Reads commit messages on stdin and checks the lines that reach release
# notes: conventional-commit headers (also the `* type: ...` lines of a squash
# body) and BREAKING CHANGE paragraphs. Prints each offending line; exits 1.

set -euo pipefail

awk '
    /^[[:space:]]*$/ { in_note = 0; next }
    in_note && /^[[:alnum:]][[:alnum:]-]*: / { in_note = 0 }
    /^(\* )?BREAKING[ -]CHANGE:/ { in_note = 1 }
    in_note || /^(\* )?[a-z]+(\([^)]*\))?!?: / {
        if (match($0, /<\/?[A-Za-z][^<>]*>/)) {
            printf "line %d: %s\n", NR, $0
            bad = 1
        }
    }
    END {
        if (bad) {
            print "Release Please parses its PR body as HTML: drop the angle brackets (write PREFIX or {PREFIX}, not <PREFIX>)."
            exit 1
        }
    }
'
