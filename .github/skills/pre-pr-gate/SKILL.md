---
name: pre-pr-gate
description: Pre-PR quality gate. Runs deterministic checks, syncs beads state, and pushes. Delegates PR creation to create-pr skill. Use when the user says "prepare a PR", "let's wrap up", "land the plane", "session complete", "pre-pr", "ready to push", or any variation of finishing work and opening a pull request.
---

# Pre-PR Quality Gate

Automate full pre-PR workflow: quality checks → beads sync → push. Follow these steps
strictly in order. Every step must succeed before moving to the next.

**Cardinal rule: never leave work unpushed.** If something fails partway
through, fix it and continue — do not abandon the workflow.

## Step 1 — Preflight checks

Before running anything, verify basics:

```bash
git status
git branch --show-current
```

- If on `main` or `master`, stop and tell user. Do not run quality gates on default
  branch.
- If there are uncommitted changes, stage and commit them first (ask user for commit
  message if intent is unclear).
- If working tree is clean and no new commits ahead of origin, tell user there's nothing
  to push.

## Step 2 — Run quality gates

```bash
task pre-pr
```

This runs pre-commit hooks, lint, typecheck, tests, coverage thresholds,
complexity and duplication, Dockerfile lint (skipped without Docker or a running
daemon) and security checks in two phases: the cheap and I/O-bound checks run in
parallel, then the app tests run alone so they never share the CPU with heavy
steps. Every step runs, so one pass reports every failure; result lines print in
a fixed order and each step group keeps its own log under
`/tmp/cosalette-pre-pr.log.steps/`. `PRE_PR_JOBS=1 task pre-pr` runs the same
steps one at a time with live progress, for debugging.

It is **change-scoped** (ADR-012). It diffs against the merge-base with
`origin/main`, plus uncommitted and untracked files, then:

- checks every app under `apps/<app>/` that changed;
- checks every app when a shared path in `.github/ci-shared-paths.txt` changed.

Its first lines print the selected apps and the reason. Root unit tests always run.
Secrets are scanned only in changed files. pip-audit runs only when `uv.lock` or a
`pyproject.toml` changed.

- `task pre-pr APPS="a b"` checks exactly those apps.
- `task pre-pr:full` checks every app and every file and runs the full security
  audit. Use it after changing shared tooling you suspect the scoping misses, or
  when the scope output looks wrong. A missing `origin/main` falls back to the full
  run automatically.

**If any step fails:** identify the specific failure, fix it, and re-run
`task pre-pr` from scratch. Do not skip failures. Do not move on until the
full pipeline passes. If you cannot fix a failure after two attempts, stop
and explain the issue to the user rather than looping indefinitely.

## Step 3 — Close beads tasks

Check for completed beads tasks and sync state:

```bash
bd list
```

If there are tasks to close:

```bash
bd close <id>        # for each completed task
task beads:sync      # export DB state to .beads/issues.jsonl
git add .beads/ && git commit -m "chore: update beads state"
```

If there are no completed tasks to close, check whether `.beads/` has any
uncommitted changes (user may have modified state manually). Commit them if so.

## Step 4 — Push

```bash
git pull --rebase origin "$(git branch --show-current)"
git push -u origin "$(git branch --show-current)"
```

If rebase produces conflicts, resolve them and continue rebase. After pushing, verify:

```bash
git status
```

Must show branch is up to date with origin. If push fails for any other reason
(permissions, protected branch), explain error and stop.

## Step 5 — Report

Provide brief summary:

- Quality gate result (pass, or which step failed and how it was fixed)
- Beads tasks closed (list IDs and titles, or "none")
- Any remaining work that should be filed as new tasks
- If push succeeded, confirm PR can now be created with `create-pr` skill.
