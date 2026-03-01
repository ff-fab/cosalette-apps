# GitHub Copilot Instructions

## Project Overview

**vito2mqtt** - a Python project.

## Workflow

- **Branching:** GitHub Flow — branch from `main`, open PR, squash-merge.
- **Commits:** Conventional Commits required (`feat:`, `fix:`, `docs:`, `chore:`, etc.).
- **Releases:** Automated via Release Please (SemVer tags).
- **Never push directly to `main`.**

## GitHub Operations

- Prefer **`gh` CLI** and **`git` CLI** for pull requests, reviews, comments, and issue operations.
- Do not depend on GitKraken MCP authentication in this repository.
- When multiple automation paths exist, choose `gh` commands first.

## Licensing

This project is licensed under **GPL-3.0-or-later**. Every new `.py` and `.sh` file
must include the GPLv3 copyright header. Run `uv run scripts/add_gpl_headers.py <file>`
after creating a new source file, or see `.github/instructions/licensing.instructions.md`
for the full policy.

## Architecture Decision Records

All major decisions are documented in `docs/adr/`. **Follow these decisions.**

Create new ADRs for any major changes or decisions.
