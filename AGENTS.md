# Agent Instructions

Canonical instructions for every AI coding agent in this repository. GitHub Copilot and
Kilo read this file natively; Claude Code reads it through the `@AGENTS.md` import in
`CLAUDE.md`.

Topic guidance that only applies to certain files lives in `.github/instructions/`. All
three tools load those files automatically — Copilot via `applyTo:`, Claude Code via
`paths:` through the `.claude/rules/` symlinks, Kilo unconditionally. Repeatable
procedures live in `.github/skills/`.

## Project Overview

**cosalette-apps** — a uv workspace monorepo for cosalette-based smart home apps. Each
app under `apps/<name>/` has its own `pyproject.toml`, `packages/src/` and
`packages/tests/`.

```
apps/
  gas2mqtt/
  jeelink2mqtt/
  vito2mqtt/
  ...
taskfiles/
  PythonApp.yml    # Reusable per-app task template
```

## MQTT Transport Posture

- Do not pin `mqtt.tls` in application code.
- Shipped deployments expose `<PREFIX>_MQTT__TLS` next to `<PREFIX>_MQTT__HOST` in
  `compose.yml` and default it with Compose interpolation
  (`${<PREFIX>_MQTT__TLS:-false}`) for the bundled plaintext broker.
- If an app ships `.env.example`, keep `<PREFIX>_MQTT__TLS=false` there so copying the
  template preserves the bundled-broker default while leaving a visible opt-in path to
  `true`.
- The decision and rationale live in
  [docs/adr/ADR-006-mqtt-transport-security-posture.md](docs/adr/ADR-006-mqtt-transport-security-posture.md).

## Tooling

- **Use `task <name>` for all operations** (`task --list` to discover). Fall back to
  `uv run --package <name>` only when no task exists. Never invoke `python` directly.
- Use the **`git`** CLI directly for version control.
- **Never invoke `gh` directly when a task wrapper exists** — `task pr:create`,
  `task pr:diff`, `task pr:feedback`, `task pr:list`, `task ci:wait`. Direct `gh` is
  fine only for subcommands with no wrapper (e.g. `gh issue list`).
- Do not depend on GitKraken MCP authentication in this repository.

Full policy: [tooling.instructions.md](.github/instructions/tooling.instructions.md).

```bash
bd ready                       # Find available work
bd show <id>                   # View issue details
bd update <id> --claim         # Claim work (assigns + in_progress)
bd close <id>                  # Complete work

task gas2mqtt:test:unit        # Run unit tests for one app
task gas2mqtt:lint             # Lint one app
task gas2mqtt:typecheck        # Type check one app
task test:all                  # Run tests for all apps
task pre-pr                    # Full quality gate
```

## Workflow

- **Branching:** GitHub Flow — branch from `main`, open a PR, squash-merge. `main` is
  always deployable.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) required:
  `<type>(<scope>): <description>`. Common types: `feat:`, `fix:`, `docs:`, `chore:`,
  `refactor:`, `test:`. Scope by app when the change is app-specific
  (`feat(gas2mqtt): add retry logic`). Breaking changes add `!` after the type.
- **Releases:** fully automated via Release Please. Agents never create tags or releases
  manually.
- **Never push directly to `main`.**

## Pull Request & Merge Policy

**NEVER merge a pull request unless the user explicitly asks.**

The job ends at creating the PR and waiting for CI. The human reviewer decides when to
merge. Even if all CI checks pass — do NOT merge, do NOT approve-and-merge, do NOT
enable auto-merge. Wait for an explicit instruction: "merge this", "go ahead and merge",
or "land it".

## Code Quality Principles

- **Brevity is a feature.** If you wrote 200 lines and it could be 50, rewrite it.
- **Simplicity test:** "Would a senior engineer say this is overcomplicated?" If yes,
  simplify before submitting.
- Prefer clear, idiomatic code over clever abstractions.
- Every line should earn its place — remove dead code, redundant comments, unnecessary
  indirection.

## Library & API Documentation

This project has **Context7 MCP** configured. When you need documentation for any
library, framework, or API, use Context7 instead of relying on training data. This
applies to code generation, debugging, and review alike. Do not ask whether to use it;
just invoke it when library context would improve accuracy.

Context7 runs as a remote MCP endpoint (`https://mcp.context7.com/mcp`, configured per
tool in `kilo.jsonc` and `.vscode/mcp.json`). It receives the names of the libraries and
APIs you query — no source code or secrets. See [context7.com](https://context7.com) for
the data policy. If working in a sensitive environment, remove the `mcp` block.

## Architecture Decision Records

ADRs are split by scope:

- **Monorepo-wide** decisions: `docs/adr/` (monorepo structure, shared tooling)
- **App-specific** decisions: `apps/<name>/docs/adr/` (framework choice, domain design)

**Follow existing decisions.** Create new ADRs for any major change, at the appropriate
scope level.

**Do not write ADR Markdown directly.** Use the `adr-create` skill — it produces
schema-validated JSON and renders canonical Markdown via `task adr:create`. Input
schema: `.github/agents/schemas/adr-input.schema.json`.

## Issue Tracking (Beads)

This project uses **bd (beads)** — a git-backed graph issue tracker for AI agents.
Issues are stored as JSONL in `.beads/` and committed to git. Run `bd prime` for full
workflow context.

### Beads vs TODO: two systems, distinct purposes

| System           | Purpose            | Content type            | Location                        |
| ---------------- | ------------------ | ----------------------- | ------------------------------- |
| **Beads (`bd`)** | Work tracking      | Actionable tasks, epics | `.beads/`                       |
| **TODO folder**  | Deferred decisions | Rich deliberation docs  | `docs/TODO/` (create as needed) |

**Beads** tracks _work_: things to build, fix, or ship.

**TODO items** (T1–Tn) are _deliberation documents_ — deferred decisions, architectural
evaluations, and technical debt. They are mini-ADRs-in-waiting.

### Gate tasks

Phase-triggered TODOs get a **gate task** in beads as a dependency of the relevant work
item. The gate task references the TODO doc but contains no decision logic itself.

- Date-triggered TODOs stay markdown-only
- When closing a gate task: create an ADR, update the TODO, or create new tasks

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete
until `git push` succeeds.

1. **File issues for remaining work** — create beads tasks for anything unfinished
2. **Run quality gates** (if code changed) — `task pre-pr`
3. **Close beads tasks and commit state** — beads state MUST be committed before
   pushing:
   ```bash
   bd close <id>
   task beads:sync
   git add .beads/ && git commit -m "chore: update beads state"
   ```
4. **PUSH TO REMOTE** — mandatory:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Create PR** (if new branch): `task pr:create TITLE="..." BODY="..."`
6. **Wait for CI** (if a PR exists):

   ```bash
   task ci:wait -- <pr-number>   # polls until all checks complete
   ```

   **Always use `task ci:wait`** — never `gh pr checks --watch` (opens an alternate
   buffer, breaks agents) or ad-hoc polling loops.

   **STOP here. Do NOT merge the PR.**

7. **Clean up** — clear stashes, prune remote branches
8. **Verify** — all changes committed AND pushed
9. **Hand off** — provide context for the next session

**CRITICAL RULES:**

- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing — that leaves work stranded locally
- NEVER say "ready to push when you are" — YOU must push
- If push fails, resolve and retry until it succeeds
- Beads state MUST be committed before pushing — the pre-push hook rejects pushes with
  uncommitted `.beads/` changes
- NEVER merge a PR unless the user explicitly requests it

<!-- BEGIN BEADS INTEGRATION -->
<!-- END BEADS INTEGRATION -->

## AI Agent Configuration

Agent configuration lives in `.github/` and is consumed by every tool:

| Surface              | Location                | Shared how                                                                      |
| -------------------- | ----------------------- | ------------------------------------------------------------------------------- |
| Always-on context    | `AGENTS.md` (this file) | read natively by all three tools                                                |
| File-scoped guidance | `.github/instructions/` | Copilot `applyTo:`; Claude via `.claude/rules/` symlinks; Kilo `instructions[]` |
| Repeatable workflows | `.github/skills/`       | Copilot native; Claude via the plugin manifest; Kilo `skills.paths`             |
| Specialist agents    | `.github/agents/`       | Copilot native; Claude via the plugin manifest; **not wired into Kilo**         |

Claude Code loads the skills and agents through a plugin manifest at
`.github/.claude-plugin/plugin.json`, served by the repo-root local marketplace
`.claude-plugin/marketplace.json` and auto-enabled by `.claude/settings.json`. They
appear as `cosalette:<name>` (e.g. `cosalette:orchestrator`, `/cosalette:pr-review`).
Adding a skill needs no manifest change — the whole `./skills/` directory is registered.
Adding an **agent** does: the manifest lists agent files individually.

Some files carry frontmatter keys for more than one tool at once; each tool ignores the
keys it does not recognise. Do not remove a key because your tool has no use for it. The
one exception is `model:`, which all three tools recognise with incompatible
vocabularies — a foreign value hard-errors in Claude Code, so `.github/agents/` carries
no `model:` at all and `task check:agents` fails if one reappears. See
[CONTRIBUTING.md](CONTRIBUTING.md) > "The one key that cannot be shared".

**Kilo reads `.github/` directly.** Its whole configuration is the root `kilo.jsonc`;
`.kilo/` now holds runtime state only and is gitignored. There are no mirrored copies to
keep in sync. Kilo is deliberately allowed to drift: `.github/agents/` is not wired into
it, and it will get purpose-built agents once it specialises.

## Refreshing cosalette guidance

> This section sits **outside** the generated block below on purpose.
> `cosalette ai init` replaces everything between the `COSALETTE AI SUPPORT` markers, so
> downstream notes only survive out here.

**What `--force` keeps and what it replaces.** A refresh merges
`.github/instructions/cosalette.instructions.md` rather than overwriting it:
template-owned frontmatter keys are updated and every other top-level key — including
the downstream `paths:` this repo adds — is preserved
(`_package_cli/_ai_init.py::_merge_instruction_content`). Two things are still lost:
**comments inside the frontmatter**, and **the entire body**, which is replaced by the
shipped template. Any repo-specific body note (the MQTT TLS posture and the command
`timeout=` correction) must be re-added afterwards. Run `cosalette ai init --check`
first to see the diff.

A refresh also rewrites `.vscode/mcp.json`, pointing the cosalette server at
`uv run --package cosalette`. That fails here — `cosalette` is a dependency, not a
workspace member — so restore the checked-in interpreter path after refreshing.

<!-- BEGIN COSALETTE AI SUPPORT v:1 -->

## cosalette Framework Support

Framework guidance is maintained in
[.github/instructions/cosalette.instructions.md](.github/instructions/cosalette.instructions.md).

**Refresh guidance:** `cosalette ai init --force` **Framework overview:**
`cosalette ai prime` **Topic-specific help:** `cosalette ai help <topic>`

<!-- END COSALETTE AI SUPPORT -->
