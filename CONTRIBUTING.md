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

| Surface              | Location                           | Notes                                                               |
| -------------------- | ---------------------------------- | ------------------------------------------------------------------- |
| Always-on context    | `AGENTS.md`                        | Claude Code reads it via `CLAUDE.md`                                |
| File-scoped guidance | `.github/instructions/`            | Claude reads it via `.claude/rules/`                                |
| Repeatable workflows | `.github/skills/`                  | Claude via the plugin manifest                                      |
| Specialist agents    | `.github/agents/`                  | Claude via the plugin manifest; no Kilo use                         |
| MCP servers          | three native formats, one per tool | `.vscode/mcp.json`, `.github/.claude-plugin/mcp.json`, `kilo.jsonc` |

Kilo's entire configuration is the root `kilo.jsonc` — see
[How Kilo reaches `.github/`](#how-kilo-reaches-github) below.

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
either. `task check:agents` enforces that every `.github/agents/*.agent.md` names at
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

Adding a rule means creating the file in `.github/instructions/`. For file-scoped rules
add both `applyTo:` (Copilot) and `paths:` (Claude Code), then symlink it. For
unconditional rules use `applyTo: '**'` and omit `paths:` — its absence means "load
every session":

```bash
ln -s ../../.github/instructions/<name>.instructions.md .claude/rules/<name>.md
```

Verified against Claude Code 2.1.220: a rule with `paths: ['**/*.py']` loads when a
`.py` file is read and stays out of context otherwise, and a rule with no `paths:` key
loads every session.

### How Claude Code reaches `.github/skills/` and `.github/agents/`

Claude Code loads both through a **plugin**, which is why they need no duplication:

| File                                 | Role                                                  |
| ------------------------------------ | ----------------------------------------------------- |
| `.github/.claude-plugin/plugin.json` | declares the skills dir and the agent files           |
| `.claude-plugin/marketplace.json`    | repo-root marketplace whose one plugin is `./.github` |
| `.claude/settings.json`              | registers the marketplace and enables the plugin      |

Components appear namespaced: `cosalette:orchestrator`, `/cosalette:pr-review`.

**Adding a skill needs no manifest change** — `plugin.json` registers the whole
`./skills/` directory. **Adding an agent does:** the `agents` key only accepts a list of
individual files, not a directory (a directory value fails `claude plugin validate`).

Check the manifests after editing them:

```bash
claude plugin validate ./.github   # the plugin
claude plugin validate .           # the marketplace
```

Verified against Claude Code 2.1.220: all 9 agents and all 8 skills load, and the
`*.agent.md` filenames are accepted as-is — no renaming needed.

### How Claude Code reaches MCP servers

The same plugin carries the MCP servers: `plugin.json`'s `mcpServers` field points at
`.github/.claude-plugin/mcp.json`, which lists `beads`, `context7` and `cosalette` under
a top-level `mcpServers` key — Claude's own vocabulary, distinct from `.vscode/mcp.json`
(`servers`) and `kilo.jsonc` (`mcp`, `type: local|remote`). **The three files are not
shareable — each is written and maintained independently, never symlinked or generated
from another.**

Project-local paths use `${CLAUDE_PROJECT_DIR}`, not a hardcoded workspace path — unlike
`.vscode/mcp.json`, which still has the old absolute path baked in. Secrets (the
`context7` API key) are never written to the file; `${CONTEXT7_API_KEY}` is expanded
from the environment at connect time, same mechanism as `.vscode/mcp.json`'s
`${env:VAR}` and `kilo.jsonc`'s `{env:VAR}`, spelled Claude's way.

### How Kilo reaches `.github/`

Kilo v7 is an OpenCode fork with **one** `kilo.jsonc` at the repo root driving the VS
Code extension, the CLI and Cloud Agents. `.kilo/` holds runtime state only and is
gitignored — there are no mirrored copies of anything.

| Key            | Value                       | Why                                                      |
| -------------- | --------------------------- | -------------------------------------------------------- |
| `instructions` | `.github/instructions/*.md` | Kilo has no `applyTo:`/`paths:` — all files load, always |
| `skills.paths` | `.github/skills`            | project-relative, read in place                          |
| `mcp`          | beads, context7, cosalette  | `type: local\|remote`; `{env:VAR}` interpolates          |
| `permission`   | ask-by-default `bash` map   | last matching pattern wins, so `*` comes first           |
| `model`        | **absent**                  | a stale pin is what rotted the previous config           |

`.github/agents/` is deliberately **not** wired in. Kilo is allowed to drift and gets
purpose-built agents once it specialises; until then it runs on the shared instructions
and skills alone.

Verified against OpenCode 1.14.25 (the upstream of Kilo v7): `opencode debug config`
accepts the JSONC comments and interpolates `{env:CONTEXT7_API_KEY}`,
`opencode debug skill` loads all 8 skills from `.github/skills`, and
`opencode providers list` shows the opencode-go credential resolved from
`OPENCODE_API_KEY`. Inside the devcontainer, substitute `kilo` for `opencode` — the
subcommands are identical.

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
as a comment in the file. Per-tool pins belong in per-tool copies. `task check:agents`
fails if a `model:` key reappears.

The same probe settled the companion question: **unknown `tools:` entries are dropped
individually, not rejected wholesale.** `['search', 'read', 'Read', 'Grep', 'Glob']`
resolves in Claude Code to exactly `Read, Grep, Glob`, so the read-only reviewers really
are read-only. The union lists are safe.

### Known gaps

Accepted trade-offs, not open work:

- **A new `.github/instructions/` file is not checked.** Nothing fails if you forget the
  `paths:` key or the `.claude/rules/` symlink — Claude Code simply never loads it.

### Checking your changes

```bash
task check:agents        # .claude/rules/ symlinks resolve, claude plugin validate
                          # (if installed), .github/agents/: union tools:, no model:
task check:agents:test   # that script's own test suite
```

Both run in CI (the `shared` job) and as pre-commit hooks. `plugin.json` itself is
validated separately, by a `check-jsonschema` pre-commit hook against SchemaStore's
`claude-code-plugin-manifest.json`.

**Neither check touches content, and neither reaches the gap named above** —
`check:agents` verifies structure (symlinks resolve, tools/model invariants), not that
you remembered to create a symlink or that a skill actually loads.

### Troubleshooting

- **Skill or agent not appearing in Claude Code.** Structural plugin changes (new
  `agents/*.agent.md` file, new `skills/` directory, edits to `plugin.json` or
  `mcp.json`) don't hot-reload — run `/reload-plugins` or restart. Only edits to an
  already-loaded `SKILL.md`'s content apply immediately. Confirm the plugin itself is
  enabled: `.claude/settings.json` → `enabledPlugins`.
- **Rule (`.github/instructions/*.instructions.md`) not loading in Claude Code.** This
  is the known gap above — check for a `.claude/rules/` symlink pointing at the file
  (`ls -la .claude/rules/`) and, for scoped rules, that `paths:` is present and matches
  the file you're editing. `task check:agents` only catches a symlink that exists and is
  dangling, not one that was never created.
- **MCP server not connecting.** Verify `plugin.json`'s `mcpServers` field still points
  at `.github/.claude-plugin/mcp.json` and the file is valid JSON with a top-level
  `mcpServers` key. Check required env vars are set in your shell before Claude Code
  starts — `${VAR}` expansion reads the environment at connect time, it does not source
  `.env` files. Project MCP servers go through a one-time per-server approval prompt the
  first time they're used; if you don't see it, the plugin may not be enabled.

### Do not run `bd setup copilot`

`bd` ships a generic Copilot recipe that scaffolds `.copilot-plugin/plugin.json` and
regenerates `.github/copilot-instructions.md`. Both conflict with this repo's hand-built
config: `.github/copilot-instructions.md` was deliberately deleted in favor of the
top-level `AGENTS.md` (see ADR-003), and a generic `.copilot-plugin/` has no awareness
of the dual-frontmatter scheme or the `.claude-plugin`/`kilo.jsonc` surfaces it must
stay consistent with. If `bd setup --check` flags Copilot as "not installed," that's
expected — this repo's Copilot integration is the `.github/` tree itself, not `bd`'s
recipe.

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
