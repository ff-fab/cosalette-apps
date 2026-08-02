# Contributing to cosalette-apps

Thank you for your interest in contributing to cosalette-apps! This guide covers
everything you need to get a development environment running and start making changes.

## Prerequisites

- Python >= 3.14
- Docker (for DevContainer development)
- VS Code with DevContainers extension

## Setup (2 minutes)

```bash
# Clone the repository
git clone https://github.com/ff-fab/cosalette-apps.git
cd cosalette-apps

# Open in VS Code
code .

# In VS Code: Ctrl+Shift+P -> "Dev Containers: Reopen in Container"
# DevContainer will start automatically, install dependencies, and configure everything
```

That's it! You're ready to develop.

## Common Commands

**Quick reference (via [Taskfile](https://taskfile.dev)):**

```bash
# Per-app tasks (replace <app> with gas2mqtt, jeelink2mqtt, etc.)
task <app>:test           # Run all tests for one app (unit + coverage)
task <app>:test:unit      # Run unit tests only
task <app>:lint           # Lint one app (Ruff check + format)
task <app>:lint:fix       # Auto-fix lint issues
task <app>:typecheck      # Type check one app (mypy strict)
task <app>:check          # Run all checks for one app
task <app>:docs:serve     # Serve app documentation site locally

# Cross-app tasks
task test:all             # Run tests for all apps
task lint:all             # Lint all apps
task check:all            # Run all checks for all apps
task pre-pr               # Full pre-PR quality gate

# Root documentation
task docs:serve           # Serve root documentation site locally

task --list               # Show all available tasks
```

## Project Structure

```
cosalette-apps/
├── .devcontainer/              # DevContainer configuration
│   ├── devcontainer.json       # Container setup + VS Code settings
│   ├── Dockerfile              # Container image
│   └── post-create.sh          # Auto-setup script
├── apps/                       # Application workspaces
│   ├── gas2mqtt/               # Gas meter → MQTT bridge
│   │   ├── packages/
│   │   │   ├── src/gas2mqtt/   # Source code
│   │   │   └── tests/          # Unit & integration tests
│   │   ├── docs/               # App documentation (Zensical)
│   │   │   └── adr/            # App-specific ADRs
│   │   ├── pyproject.toml      # App package config
│   │   └── zensical.toml       # App docs site config
│   └── jeelink2mqtt/           # JeeLink sensor → MQTT bridge
│       ├── packages/
│       │   ├── src/jeelink2mqtt/
│       │   └── tests/
│       ├── docs/
│       │   └── adr/
│       ├── pyproject.toml
│       └── zensical.toml
├── docs/                       # Root documentation (Zensical)
│   └── adr/                    # Monorepo-wide ADRs
├── taskfiles/                  # Reusable Taskfile templates
│   └── PythonApp.yml           # Per-app task definitions
├── pyproject.toml              # Root workspace config (uv)
├── Taskfile.yml                # Root task orchestrator
└── zensical.toml               # Root docs site config
```

## AI Agent Setup

Agent configuration lives in `.github/` and is shared by GitHub Copilot, Claude Code and
Kilo. `AGENTS.md` is the always-on instruction file for all three.

| Surface              | Location                | Notes                                   |
| -------------------- | ----------------------- | --------------------------------------- |
| Always-on context    | `AGENTS.md`             | Claude Code reads it via `CLAUDE.md`    |
| File-scoped guidance | `.github/instructions/` | Claude reads it via `.claude/rules/`    |
| Repeatable workflows | `.github/skills/`       | `.kilo/skills/` symlinks in             |
| Specialist agents    | `.github/agents/`       | `.kilo/agents/` is a separate hand copy |

### Union frontmatter

One physical file serves several tools because **each tool ignores frontmatter keys it
does not recognise**. Two vocabularies therefore coexist in the same file:

| Concept      | Copilot                                      | Claude Code                    |
| ------------ | -------------------------------------------- | ------------------------------ |
| File scoping | `applyTo: '**/*.py'`                         | `paths: ['**/*.py']`           |
| Tool grants  | `search`, `read`, `edit`, `execute/*`, `web` | `Read`, `Grep`, `Edit`, `Bash` |

**The union `tools:` lists are load-bearing, not belt-and-braces.** Claude Code refuses
to launch an agent whose tools resolve to nothing, and Copilot silently drops names it
does not know — so a single-vocabulary list breaks exactly one platform with no error on
either. `task check-parity` enforces that every `.github/agents/*.agent.md` names at
least one tool from each vocabulary.

For `applyTo: '**'` (unconditional), Claude Code's equivalent is the **absence** of a
`paths:` key — do not add one to those files.

### How Claude Code reaches `.github/instructions/`

Claude Code only scans `.claude/rules/`, so each instruction file is symlinked into it:

```
.claude/rules/python.md -> ../../.github/instructions/python.instructions.md
```

Git stores these as symlinks (mode `120000`), not as copies, so there is one physical
file and nothing to keep in sync. `.claude/rules/` officially supports symlinks — unlike
`.claude/skills/`, which has an open discovery bug
([anthropics/claude-code#25367](https://github.com/anthropics/claude-code/issues/25367)).

Adding a rule means creating the file with **both** `applyTo:` and `paths:`, then:

```bash
ln -s ../../.github/instructions/<name>.instructions.md .claude/rules/<name>.md
```

Verified against Claude Code 2.1.220: a rule with `paths: ['**/*.py']` loads when a
`.py` file is read and stays out of context otherwise, and a rule with no `paths:` key
loads every session.

### The one key that cannot be shared: `model:`

Union frontmatter works because tools ignore keys they do not recognise. `model:` is the
exception — **all three tools recognise it, with mutually incompatible vocabularies:**

| Tool        | Vocabulary                                      | Example                       |
| ----------- | ----------------------------------------------- | ----------------------------- |
| Copilot     | display name + `(copilot)`                      | `Claude Sonnet 4.6 (copilot)` |
| Claude Code | `sonnet`/`opus`/`haiku`/`inherit` or a model ID | `sonnet`                      |
| Kilo        | `provider/model`                                | `opencode-go/glm-5.1`         |

A foreign value does **not** degrade gracefully in Claude Code. Probed under `cap-wf3`
against Claude Code 2.1.220: the agent loads and appears in the agent list, then fails
the moment it is launched:

```
Error: Agent terminated early due to an API error: There's an issue with the
selected model (Claude Sonnet 4.6 (copilot)). It may not exist or you may not
have access to it.
```

So `.github/agents/*.agent.md` carries **no `model:` key at all** — Copilot uses the
user-selected model and Claude Code inherits the session model. Where the choice of
model was deliberate (the researcher and security reviewers ran on a non-Anthropic
family on purpose, so the review is not the author's own model), that intent is recorded
as a comment in the file. Per-tool pins belong in per-tool copies; `.kilo/agents/` has
its own. `task check-parity` fails if a `model:` key reappears.

The same probe settled the companion question: **unknown `tools:` entries are dropped
individually, not rejected wholesale.** `['search', 'read', 'Read', 'Grep', 'Glob']`
resolves in Claude Code to exactly `Read, Grep, Glob`, so the read-only reviewers really
are read-only. The union lists are safe.

### Known gaps

These are tracked under the `cap-pm1` epic and are not yet resolved:

- **`.kilo/agents/` is a separate physical copy.** Editing a `.github/agents/*.agent.md`
  body does not update its Kilo mirror; `task check-parity` compares only `description`.

### Checking your changes

```bash
task check-parity        # agents ↔ Kilo mirrors, skill symlinks, union tools:, no model:
task check-parity:test   # the parity script's own test suite
```

Both run in CI (the `shared` job) and as pre-commit hooks.

## Code Quality

- **Linting & formatting**: [Ruff](https://docs.astral.sh/ruff/) (88-char line length,
  double quotes)
- **Type checking**: [mypy](https://mypy-lang.org/) (strict mode)
- **Testing**: [pytest](https://docs.pytest.org/) with pytest-asyncio
- **Coverage**: >= 80% threshold (lines and branches)
- **Pre-commit**: EditorConfig, trailing whitespace, codespell, Ruff, mypy

All tools are **auto-configured in DevContainer** via `.devcontainer/devcontainer.json`.
Format on save is enabled by default.

## Workflow

This project follows **GitHub Flow**:

1. Create a feature branch from `main`
2. Make changes with [conventional commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, `docs:`, `chore:`, etc.). Scope by app: `feat(gas2mqtt): ...`
3. Run `task pre-pr` to pass all quality gates
4. Open a pull request -- never push directly to `main`

## Documentation Preview

PRs that change files under `docs/` or `apps/*/docs/` automatically get a live
documentation preview deployed to Surge.sh. A bot comments on the PR with the preview
URL and links to changed pages.

**How it works:**

- On PR open/update: all doc sites are built and deployed to
  `https://cosalette-apps-pr-<N>.surge.sh`
- On PR close/merge: the preview is torn down automatically

**Setup (repository maintainers only):**

The workflow requires a `SURGE_TOKEN` repository secret. One-time setup:

1. Install Surge CLI: `npm install -g surge`
2. Create an account: `surge login` (follow prompts — email + password)
3. Get your token: `surge token`
4. Add the token to the repository: Settings → Secrets and variables → Actions → New
   repository secret → Name: `SURGE_TOKEN`, Value: (paste token)

Fork PRs skip the preview deploy gracefully (secrets are not available to forks).

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
