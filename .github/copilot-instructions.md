# GitHub Copilot Instructions

## Project Overview

**cosalette-apps** — a uv workspace monorepo for cosalette-based smart home apps.
Apps live under `apps/<name>/`, each with its own `pyproject.toml` and `packages/` tree.

## Workflow

- **Branching:** GitHub Flow — branch from `main`, open PR, squash-merge.
- **Commits:** Conventional Commits required (`feat:`, `fix:`, `docs:`, `chore:`, etc.).
  Scope by app when app-specific: `feat(gas2mqtt): add retry logic`.
- **Releases:** Automated via Release Please (SemVer tags).
- **Never push directly to `main`.**

## Pull Request & Merge Policy

**NEVER merge a pull request unless user explicitly asks.**

Job ends at creating the PR and waiting for CI. Human reviewer decides when to merge. Even if all CI checks pass — do NOT merge. Do NOT approve-and-merge. Do NOT enable auto-merge. Wait for explicit instruction: "merge this", "go ahead and merge", or "land it".

## Code Quality Principles

- **Brevity is a feature.** If you wrote 200 lines and it could be 50, rewrite it.
- **Simplicity test:** "Would a senior engineer say this is overcomplicated?" If yes, simplify before submitting.
- Prefer clear, idiomatic code over clever abstractions.
- Every line should earn its place — remove dead code, redundant comments, unnecessary indirection.

## GitHub Operations

- Use **task wrappers** when available (`task pr:diff`, `task pr:feedback`, `task ci:wait`). For `gh` subcommands without a wrapper, use `gh` directly.
- Prefer **`git` CLI** for version control operations.
- Do not depend on GitKraken MCP authentication in this repository.
- See `tooling.instructions.md` for the full wrapper policy.

## Library & API Documentation

This project has **Context7 MCP** configured. When you need documentation for any
library, framework, or API — use Context7 automatically instead of relying on
training data. This applies to code generation, debugging, and review tasks.

Do not ask the user whether to use Context7; just invoke it when library context
would improve accuracy.

## Architecture Decision Records

ADRs are split by scope:

- **Monorepo-wide** decisions: `docs/adr/` (e.g. monorepo structure, shared tooling)
- **App-specific** decisions: `apps/<name>/docs/adr/` (e.g. framework choice, domain design)

**Follow existing decisions.** Create new ADRs for any major changes, placing them at
the appropriate scope level.

**Do not write ADR Markdown directly.** Use the `adr-create` skill (`.github/skills/adr-create/SKILL.md`) — produces schema-validated JSON, renders canonical Markdown via `task adr:create`. See `.github/agents/schemas/adr-input.schema.json` for input schema.
