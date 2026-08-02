---
name: showboat-demo
argument-hint: '[scope or title]'
description:
  Create a showboat demo — an executable proof-of-work document. Use when the user asks
  for a demo, says "showboat this", "prove it works", "create a demo", or when you want
  to suggest documenting significant work with reproducible proof.
---

# Showboat Demo

[Showboat](https://github.com/simonw/showboat) creates executable demo documents — markdown files
that mix commentary with executable code blocks and their captured output. A demo serves as both:

- **Documentation** — what was changed and why
- **Reproducible proof** — `showboat verify` re-runs all code blocks and confirms outputs match

## When to Create a Demo

Create a showboat demo when:

- The **user explicitly requests** one
- You want to **suggest** documenting a significant change (ask first!)

Do NOT create demos automatically. Demos are opt-in.

## Gather Context First

Before writing anything, establish what the demo has to prove:

```bash
git branch --show-current          # the demo filename
git log main..HEAD --oneline       # what landed on this branch
git diff main...HEAD --stat        # scope — three-dot diffs from the merge-base, so it
                                   # stays reproducible even after main advances
```

Read the changed files. The proof commands must demonstrate *this* work, not generic
health.

## Workflow

```bash
# 1. Initialize (use the branch name as filename)
showboat init docs/planning/demos/<branch-name>.md "<Title describing the work>"

# 2. Add commentary explaining what was done
showboat note docs/planning/demos/<branch-name>.md "Describe the change and its purpose."

# 3. Run commands that prove it works (output is captured automatically)
showboat exec docs/planning/demos/<branch-name>.md bash "<test or verification command>"

# 4. If a command fails, remove it and redo
showboat pop docs/planning/demos/<branch-name>.md
showboat exec docs/planning/demos/<branch-name>.md bash "<corrected command>"

# 5. Verify the demo is reproducible (MUST exit 0)
showboat verify docs/planning/demos/<branch-name>.md

# 6. Commit it as part of the branch
git add docs/planning/demos/<branch-name>.md
git commit -m "docs: add showboat demo for <branch-name>"
```

**Write 2–4 notes in step 2**, covering:

- the problem or feature being addressed
- key design decisions
- what the proof commands will verify

This is the part most easily under-done — a demo of bare command output without
commentary does not explain why the work is correct.

**Choose proof commands that demonstrate _this_ work, not generic health**: `task pre-pr`
or targeted tests for code changes, `git diff main...HEAD --stat` for scope, plus
feature-specific commands (API calls, CLI output). Always use the three-dot form in
proof blocks so they stay reproducible after `main` advances.

## Scoping Guidelines

The agent decides scope based on work complexity:

- **Simple fix:** Note explaining the fix + one `exec` proving the test passes
- **New feature:** Notes on design choices + multiple `exec` blocks showing the feature works
- **Refactoring:** Before/after notes + proof that tests still pass

## Conventions

| Convention    | Value                            |
| ------------- | -------------------------------- |
| **Location**  | `docs/planning/demos/`           |
| **Filename**  | `<branch-name>.md`               |
| **Committed** | Yes — part of the PR             |
| **Zensical**  | Excluded (not published to site) |
| **Verify**    | `showboat verify` must exit 0    |

## Reference

- Installed in devcontainer via `uv tool install showboat`
- Key commands: `init`, `note`, `exec`, `pop`, `verify`, `extract`
- Run `showboat --help` for full CLI reference
