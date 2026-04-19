# CLAUDE.md

This project's conventions are documented in GitHub Copilot instruction files. Read and
follow them.

## Instructions

- [.github/copilot-instructions.md](.github/copilot-instructions.md) — Project overview,
  workflow, code quality, PR policy
- [.github/instructions/tooling.instructions.md](.github/instructions/tooling.instructions.md)
  — Use `task` and `uv`, never bare `python`
- [.github/instructions/workflow.instructions.md](.github/instructions/workflow.instructions.md)
  — Git flow, conventional commits, beads issue tracking, session completion
- [.github/instructions/testing-python.instructions.md](.github/instructions/testing-python.instructions.md)
  — pytest patterns, AAA, ISTQB techniques
- [.github/instructions/documentation.instructions.md](.github/instructions/documentation.instructions.md)
  — Zensical site generator, ADR format

## Monorepo Layout

This is a **uv workspace monorepo**. Apps live under `apps/<name>/`.

- Per-app tasks: `task <app>:test:unit`, `task <app>:lint`, `task <app>:typecheck`
- Cross-app: `task test:all`, `task lint:all`, `task check:all`
- Root-level: `task test:unit`, `task lint`, `task typecheck`, `task check`
- Use `uv run --package <name>` when no task exists
- Commit scoping: `feat(gas2mqtt): ...`, `fix(jeelink2mqtt): ...`

## Available Skills

- **pr-review** — Fetch all PR feedback via `task pr:feedback -- <PR>`, then analyze CI,
  review comments, and code quality
- **pre-pr-gate** — End-of-session workflow: `task pre-pr`, close beads, push, create PR
- **showboat-demo** — Create reproducible proof-of-work demos with `showboat`
- **adr-create** — Create or amend ADRs via schema-conforming JSON
  (`task adr:create -- input.json`)

## Key Rules

- **Never push directly to `main`.** All changes go through PRs.
- **Never merge a PR** unless the user explicitly asks.
- **Conventional Commits required** (`feat:`, `fix:`, `docs:`, `chore:`, etc.). Scope by
  app when app-specific.
- **Use `task <name>`** for all operations (run `task --list`). Fall back to `uv run`
  only when no task exists. Never invoke `python` directly.
- **ADRs** live in `docs/adr/` (monorepo-wide) and `apps/<name>/docs/adr/`
  (app-specific). Follow existing decisions; create new ADRs at the appropriate scope.
- **Beads (`bd`)** for issue tracking. Run `bd prime` for full context.

<!-- BEGIN COSALETTE AI SUPPORT v:1 -->

## cosalette Framework Support

Framework guidance is maintained in
[.github/instructions/cosalette.instructions.md](.github/instructions/cosalette.instructions.md).

**Refresh guidance:** `cosalette ai init --force` **Framework overview:**
`cosalette ai prime` **Topic-specific help:** `cosalette ai help <topic>`

<!-- END COSALETTE AI SUPPORT -->
