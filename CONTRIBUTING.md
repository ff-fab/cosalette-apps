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

Every operation runs through [Taskfile](https://taskfile.dev). Run `task --list` for the
full list with descriptions; the overview below groups it by purpose.

### Per-app tasks

Each app under `apps/<app>/` gets the same set of tasks from `taskfiles/PythonApp.yml`,
namespaced by the app name. Replace `<app>` with any app, for example `wiz2mqtt`:

```bash
task <app>:test               # Unit + integration tests with coverage
task <app>:test:unit          # Unit tests only
task <app>:test:integration   # Integration tests only
task <app>:test:file -- f.py  # One test file or pattern
task <app>:test:cov           # Coverage report (test:cov:html for HTML)
task <app>:lint               # Ruff check + format check
task <app>:lint:fix           # Auto-fix lint issues
task <app>:typecheck          # Type check (ty)
task <app>:check              # Lint + typecheck + tests
task <app>:complexity         # Cyclomatic and cognitive complexity
task <app>:similarity         # Code duplication
task <app>:schema:generate    # Regenerate docs/schema.yaml from the registrations
task <app>:schema:check       # Check the registrations against docs/schema.yaml
task <app>:schema:openhab     # Generate openHAB .things/.items
task <app>:docs:serve         # Preview the app documentation site
task <app>:docs:build         # Build the app documentation site
task <app>:docker:smoke IMAGE=<ref>  # Smoke-test a built image offline
```

Some apps add their own tasks (for example `wiz2mqtt:openhab`); `task --list` shows
them.

### All apps

```bash
task test:all                 # Repo-root suite plus every app's tests
task test:apps                # Every app's tests (ONLY_APPS="a b" to narrow)
task lint:all                 # Lint every app
task typecheck:all            # Type check every app
task check:all                # All checks for every app
task complexity:all           # Complexity and duplication for every app
```

### Repo root

These run against the root package (`packages/`) and `scripts/`:

```bash
task test                     # Unit + integration tests with summary
task test:unit                # Unit tests (also test:integration, test:file, test:cov)
task test:scripts             # Shell regression tests for scripts/
task lint                     # Ruff and shellcheck (lint:fix, lint:shell)
task typecheck                # Type check (ty)
task check                    # Lint + typecheck + tests
task complexity               # Complexity gates (complexity:cyclomatic, :cognitive)
task similarity               # Code duplication
```

### Quality gates and security

```bash
task pre-pr                   # Pre-PR gate, scoped to the apps you changed
task pre-pr APPS="a b"        # Gate exactly these apps
task pre-pr:full              # Every app and every file
task quality:summary          # Lint, typecheck and unit tests as a JSON summary
task reuse:lint               # REUSE license compliance
task docker:lint              # hadolint on the Dockerfiles
task check:agents             # Agent config integrity (check:agents:test for its tests)
task security:audit           # All security checks (security:deps, :secrets, :python, :actions)
```

### Pull requests

```bash
task pr:create TITLE="..." BODY="..."   # Open a PR (or BODY_FILE=path)
task pr:list                  # Open PRs, without release PRs
task pr:diff -- <n>           # Show a PR's diff
task pr:feedback -- <n>       # All PR feedback as JSON
task ci:wait -- <n>           # Wait for CI checks on a PR
```

### Documentation, ADRs and scaffolding

```bash
task docs:serve               # Preview the root documentation site
task docs:build               # Build the root documentation site
task adr:create -- in.json    # Create or amend an ADR from validated JSON
task app:new -- myapp "Description"   # Scaffold a new app
```

### Dependencies and planning

```bash
task sync                     # Sync all dependencies
task update:deps              # Update dependencies to the latest compatible versions
task update:template          # Pull copier template changes
task beads:sync               # Export the beads database to .beads/issues.jsonl
task beads:recover            # Restart an orphaned beads dolt server
task plan                     # Progress per phase (plan:ready, plan:phase, plan:task, plan:ui)
```

## Project Structure

The repository is a [uv](https://docs.astral.sh/uv/) workspace: every app is its own
package with its own version, release, image and documentation site, and all apps share
the tooling at the root. [README.md](README.md#apps) lists the apps.

```
cosalette-apps/
├── apps/
│   └── <name>/                  # One app per directory
│       ├── packages/
│       │   ├── src/<name>/      # App source code
│       │   └── tests/
│       │       ├── unit/        # Unit tests
│       │       ├── integration/ # Integration tests
│       │       └── fixtures/    # App test doubles and helpers
│       ├── docs/                # App documentation site (Zensical)
│       │   └── adr/             # App-specific ADRs
│       ├── pyproject.toml       # App package, version and tool config
│       ├── zensical.toml        # App docs site config
│       ├── Dockerfile           # App image
│       ├── compose.yml          # Deployment example
│       ├── CHANGELOG.md         # Written by Release Please
│       └── LICENSE              # The app's license
├── packages/                    # Root package: repo-wide invariant tests
│   └── tests/
│       ├── unit/                # Checks every app at once (images, TLS, health, ...)
│       └── fixtures/            # Test fixtures shared across apps
├── taskfiles/PythonApp.yml      # Per-app task template, included once per app
├── Taskfile.yml                 # Root tasks and the per-app includes
├── scripts/                     # Task backends: pre-pr gate, scaffold, ADR renderer, ...
├── docs/                        # Root documentation site
│   └── adr/                     # Monorepo-wide ADRs
├── .github/                     # CI workflows plus the shared agent config
├── .beads/                      # Issue tracker data (issues.jsonl is committed)
├── .devcontainer/               # DevContainer image and setup
├── LICENSES/                    # License texts for REUSE
├── REUSE.toml                   # Which license applies to which path
└── pyproject.toml               # Workspace members and shared tool config
```

- **`apps/<name>/`** is self-contained: `task <app>:...` runs from that directory, and
  CI builds, tests, releases and publishes each app on its own.
- **`taskfiles/PythonApp.yml`** defines the per-app tasks once; `Taskfile.yml` includes
  it for each app. Set per-app variations in the include's `vars:` and put app-only
  tasks (such as `wiz2mqtt:openhab`) in `Taskfile.yml`; never copy the template's tasks.
- **`packages/tests/fixtures/`** holds fixtures that more than one app uses. Apps import
  them as plain top-level modules through `pythonpath` in their pytest config (see
  [workflow.instructions.md](.github/instructions/workflow.instructions.md)).
  App-specific fixtures stay in `apps/<name>/packages/tests/fixtures/`.
- **`docs/adr/`** records decisions that affect the whole monorepo;
  `apps/<name>/docs/adr/` records decisions for one app. Create both with
  `task adr:create`, never by hand.
- **`.github/`** holds the CI workflows and the agent configuration shared by every AI
  tool: `instructions/`, `skills/` and `agents/` (see
  [AI Agent Setup](#ai-agent-setup)).
- **`scripts/`** holds the scripts behind the tasks. Call them through `task`, not
  directly.
- **`.beads/`** holds the beads (`bd`) issue tracker. The database stays local;
  `issues.jsonl` is its committed export, so run `task beads:sync` after `bd close`.

## AI Agent Setup

Agent configuration lives in `.github/` and is shared by GitHub Copilot, Claude Code and
Kilo. `AGENTS.md` is the always-on instruction file for all three. The one exception is
the response style, which only Claude Code consumes and which it reads from `.claude/`
by path — see the last row below.

| Surface              | Location                           | Notes                                                                  |
| -------------------- | ---------------------------------- | ---------------------------------------------------------------------- |
| Always-on context    | `AGENTS.md`                        | Claude Code reads it via `CLAUDE.md`                                   |
| File-scoped guidance | `.github/instructions/`            | Claude reads it via `.claude/rules/`                                   |
| Repeatable workflows | `.github/skills/`                  | Claude via the plugin manifest                                         |
| Specialist agents    | `.github/agents/`                  | Claude via the plugin manifest; no Kilo use                            |
| MCP servers          | three native formats, one per tool | `.vscode/mcp.json`, `.github/.claude-plugin/mcp.json`, `kilo.jsonc`    |
| Response style       | `.claude/output-styles/`           | Claude Code only; selected by `outputStyle` in `.claude/settings.json` |

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

### Updating Kilo

Kilo-Org/kilocode is a smaller-community fork with less audit history than the other
pinned tools (`task`, `dolt`, `beads`) — Renovate version bumps get extra scrutiny
(finding #6, PR #194 review). Renovate labels these PRs `needs-manual-sha-verification`
(see `renovate.json`) and does not automerge them; green CI alone is not a merge signal.

**Before merging a Kilo version-bump PR:**

1. Open the GitHub release page for the new `KILO_VERSION` tag and manually verify
   `KILO_SHA256_AMD64` and `KILO_SHA256_ARM64` in `.devcontainer/Dockerfile` against it.
2. Build the image for `linux/arm64` and actually **execute** the kilo binary inside it
   — SHA-256 guards against corruption, not a wrong binary packaged into the ARM64
   tarball:
   ```bash
   docker buildx build --load --platform linux/arm64 -t kilo-arm64-check -f .devcontainer/Dockerfile .
   docker run --rm --platform linux/arm64 kilo-arm64-check kilo --version
   ```
3. Leave a PR comment confirming both checks passed before merging.

**Post-rebuild checklist:** after rebuilding the devcontainer, `kilo --version` only
proves the binary is installed. Also run `kilo debug config` to confirm
`OPENCODE_API_KEY` resolves and `kilo.jsonc` loads — this can't be checked at
image-build time since credentials aren't available then.

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
- **Type checking**: [ty](https://docs.astral.sh/ty/)
- **Testing**: [pytest](https://docs.pytest.org/) with pytest-asyncio
- **Coverage**: >= 80% threshold (lines and branches)
- **Pre-commit**: EditorConfig, trailing whitespace, codespell, Prettier, Ruff, ty,
  REUSE and the GPL-header check

All tools are **auto-configured in DevContainer** via `.devcontainer/devcontainer.json`.
Format on save is enabled by default.

## Workflow

This project follows **GitHub Flow**:

1. Create a feature branch from `main`
2. Make changes with [conventional commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, `docs:`, `chore:`, etc.). Scope by app: `feat(gas2mqtt): ...`
3. Run `task pre-pr` to pass all quality gates. It checks only the apps your branch
   changed (every app when a shared path in `.github/ci-shared-paths.txt` changed); use
   `APPS="a b"` to pick apps, or `task pre-pr:full` to check everything (see
   [ADR-012](docs/adr/ADR-012-change-scoped-pre-pr-gate-with-a-shared-path-fallback.md))
4. Open a pull request -- never push directly to `main`

## Docker Hub authentication in CI

Repository maintainers configure Actions repository secrets `DOCKERHUB_USERNAME` and
`DOCKERHUB_TOKEN` for authenticated Docker Hub pulls. Create a dedicated Docker Hub
account and a Personal Access Token with **Read** permission only, then store the
account name and token under Settings → Secrets and variables → Actions. Use an expiry
date; replace the token before expiry and revoke the previous token after a successful
build. Revoke and replace it immediately if exposed.

Release image builds and devcontainer publication require both secrets. CI and
documentation builds treat them as optional and skip login unless both are present. CI
and docs pass credentials only for `push` or `workflow_dispatch` on `refs/heads/main`.
These callers supply empty Docker Hub inputs on PR events, including same-repository
PRs, and use anonymous pulls. PR-controlled actions must never receive a long-lived
registry token. Publication jobs run only from the main workflow ref, including manual
dispatches. A manual app rebuild still checks out the requested release tag for its
build context.

## Image smoke test

CI builds each changed app's image for `linux/amd64` and runs it offline with
`task <app>:docker:smoke IMAGE=<ref>`. Every image must answer `<app> --help`,
`<app> --version` and `cosalette-health --help`. A `--help` returns before most code
runs, so it cannot show a missing runtime dependency. Every further console script in
the app's `[project.scripts]` therefore needs a line in the `SMOKE` var of its
`Taskfile.yml` include, and that line runs the script doing real work.
`packages/tests/unit/test_image_smoke_coverage.py` fails when a script has no line. Run
the check locally after a `docker build`:

```bash
docker build -f apps/wiz2mqtt/Dockerfile -t wiz2mqtt:smoke .
task wiz2mqtt:docker:smoke IMAGE=wiz2mqtt:smoke
```

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
