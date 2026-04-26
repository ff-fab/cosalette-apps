---
description: 'Development workflow: Git flow, issue tracking, quality gates, session completion'
applyTo: '**'
---

# Workflow

## Git Workflow (GitHub Flow)

**CRITICAL: Never push directly to main. All changes go through PRs.**

1. **Create feature branch from main**

   ```bash
   git checkout main && git pull
   git checkout -b feature/description  # or fix/, docs/, chore/, etc.
   ```

2. **Commit** (skill `caveman-commit`)

3. **Quality gates** (skill `pre-pr-gate`)

4. **Push and create PR** (skill `create-pr`)

5. **Wait for CI**

   ```bash
   task ci:wait -- <pr-number>   # polls until all checks complete
   ```

   **NEVER merge PR unless user explicitly requests it.**

**Key principle:** `main` is always deployable.


## Releases

Project uses **Release Please**, releases fully automated.

Agents do NOT manually create tags or releases — bot handles it.

## Issue Tracking (Beads)

Project uses **bd (beads)** — git-backed graph issue tracker for AI agents.
Issues stored as JSONL in `.beads/` and committed to git.

Run `bd prime` for full workflow context.

## Session Completion ("Landing the Plane")

**End every session** completing ALL steps. Work NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** — create beads tasks for unfinished items
2. **Run quality gates** (if code changed) — `task pre-pr`
3. **Close beads tasks and commit state**:

   ```bash
   bd close <id>
   task beads:sync
   git add .beads/ && git commit -m "chore: update beads state"
   ```

4. **PUSH TO REMOTE** — MANDATORY:

   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```

5. **Create PR** (if new branch): `task pr:create -- --title "..." --body "..."`
6. **Clean up** — clear stashes, prune remote branches
7. **Verify** — all changes committed AND pushed
8. **Hand off** — provide context for next session

**CRITICAL RULES:**

- Work NOT complete until `git push` succeeds
- NEVER stop before pushing — leaves work stranded locally
- NEVER say "ready to push when you are" — YOU must push
- If push fails, resolve and retry
- Beads state MUST be committed before pushing — pre-push hook rejects uncommitted `.beads/` changes
- NEVER merge PR — only user decides when to merge

## Test Notes

- Shared fixtures (in `packages/tests/fixtures/` within each app) should be used to
  avoid duplication
- Always ensure tests, fixtures, documentation, and features stay in sync
