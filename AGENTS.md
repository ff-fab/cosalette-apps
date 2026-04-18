# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd prime` to get started.

## GitHub Tooling Policy

- Use **GitHub CLI (`gh`)** and **git CLI** directly for PR/issue workflows.

## Monorepo Layout

This is a **uv workspace monorepo**. Apps live under `apps/<name>/`, each with its own
`pyproject.toml`, `packages/src/`, and `packages/tests/`.

```
apps/
  gas2mqtt/
  jeelink2mqtt/
  vito2mqtt/
  ...
taskfiles/
  PythonApp.yml    # Reusable per-app task template
```

## Commit Convention

All commits **must** follow
[Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

Common prefixes: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.

Scope by app when the change is app-specific: `feat(gas2mqtt): add retry logic`.

Breaking changes: add `!` after the type (e.g., `feat!: redesign config`).

These prefixes drive automated release versioning (if Release Please is enabled).

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work (assigns + in_progress)
bd close <id>         # Complete work

# Per-app task commands (monorepo)
task gas2mqtt:test:unit        # Run unit tests for gas2mqtt
task gas2mqtt:lint             # Lint gas2mqtt
task gas2mqtt:typecheck        # Type check gas2mqtt
task test:all                  # Run tests for all apps
task pre-pr                    # Full quality gate
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete
until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Close beads tasks and commit** - Beads state MUST be committed before pushing:
   ```bash
   bd close <id>                # Close finished work
   git add .beads/ && git commit -m "chore: update beads state"
   ```
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Create PR** (if new branch):
   ```bash
   gh pr create
   ```
6. **Wait for CI** (if PR exists):

   ```bash
   task ci:wait -- <pr-number>   # polls until all checks complete
   ```

   **Always use `task ci:wait`** — do not use `gh pr checks --watch` (opens alternate
   buffer, breaks agents) or ad-hoc polling loops.

   **STOP here. Do NOT merge the PR.** Do not approve, do not enable auto-merge, do not
   merge even if all CI checks pass. The human reviewer decides when to merge.

7. **Clean up** - Clear stashes, prune remote branches
8. **Verify** - All changes committed AND pushed
9. **Hand off** - Provide context for next session

**CRITICAL RULES:**

- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
- Beads state MUST be committed before pushing — the pre-push hook will reject pushes
  with uncommitted `.beads/` changes
- NEVER merge a PR unless the user explicitly requests it

## Beads vs TODO: Two Systems, Distinct Purposes

| System           | Purpose            | Content type            | Location                        |
| ---------------- | ------------------ | ----------------------- | ------------------------------- |
| **Beads (`bd`)** | Work tracking      | Actionable tasks, epics | `.beads/`                       |
| **TODO folder**  | Deferred decisions | Rich deliberation docs  | `docs/TODO/` (create as needed) |

**Beads** tracks _work_: things to build, fix, or ship.

**TODO items** (T1–Tn) are _deliberation documents_ — deferred decisions, architectural
evaluations, and technical debt. They are mini-ADRs-in-waiting.

### Gate Tasks

Phase-triggered TODOs get a **gate task** in beads as a dependency of the relevant work
item. The gate task references the TODO doc but contains no decision logic itself.

- Date-triggered TODOs stay markdown-only
- When closing a gate task: create an ADR, update the TODO, or create new tasks

<!-- BEGIN BEADS INTEGRATION -->
<!-- END BEADS INTEGRATION -->

<!-- BEGIN COSALETTE AI SUPPORT v:1 -->

## cosalette Framework Support

Framework guidance is maintained in
[.github/instructions/cosalette.instructions.md](.github/instructions/cosalette.instructions.md).

**Refresh guidance:** `cosalette ai init --force` **Framework overview:**
`cosalette ai prime` **Topic-specific help:** `cosalette ai help <topic>`

<!-- END COSALETTE AI SUPPORT -->
