---
description: 'Development workflow: Git flow, issue tracking, quality gates, session completion'
# applyTo '**' means unconditional. Claude Code's equivalent is the ABSENCE of a
# paths key, so do not add one here.
applyTo: '**'
---

# Workflow

**Git flow, commit convention, PR/merge policy, issue tracking and the session-completion
("Landing the Plane") procedure are defined once in [AGENTS.md](../../AGENTS.md).** That
file is always-on for every tool; this one adds only what is not there.

Do not restate those procedures here — a second copy is how `gh pr create` and
`task pr:create` ended up in the repo simultaneously.

## Branch naming

Branch from `main` with a conventional prefix matching the commit type:
`feature/`, `fix/`, `docs/`, `chore/`, `refactor/`, `test/`.

## Supporting skills

| Step            | Skill            |
| --------------- | ---------------- |
| Commit          | `caveman-commit` |
| Quality gates   | `pre-pr-gate`    |
| Push + open PR  | `create-pr`      |
| Review a PR     | `pr-review`      |

## Test Notes

- Shared fixtures (in `packages/tests/fixtures/` within each app) should be used to
  avoid duplication
- Fixtures shared **across apps** live in the repo-root `packages/tests/fixtures/`.
  Apps reach them through `pythonpath = ["../../packages/tests/fixtures"]` in their
  `[tool.pytest.ini_options]`, so the import is a plain top-level module name
  (`from ha_discovery import ...`). Add the module name to the app's
  `[tool.ruff.lint.isort] known-first-party` so it sorts with the app's own imports.
- Always ensure tests, fixtures, documentation, and features stay in sync
