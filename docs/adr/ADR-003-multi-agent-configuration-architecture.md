---
status: Accepted
date: 2026-08-02
impact: high
tags: [architecture, agents, documentation]
---

# ADR-003: Multi-Agent Configuration Architecture

## Status

Accepted **Date:** 2026-08-02

## Context

This repo is read by three AI coding tools — GitHub Copilot, Claude Code, and Kilo — each with its own native config format and none of them originally sharing a source of truth. Before cap-pm1, Claude Code had no native config at all, Kilo was an OpenCode-derived setup that had rotted (stale model pin, drifted from the other two), and a fragile parity script tried to keep hand-copied files in sync across trees. That is the same N-tool x M-surface duplication problem ADR-001 solved for the app repos themselves, now recurring one layer up in the agent tooling. The surface area is not small: 6 scoped instruction files, 8 skills, and 9 specialist agents, plus always-on context and now MCP server definitions for 3 tools. cap-pm1 (14 sub-issues across 6 phases) consolidated all of it.

## Decision

Use `.github/` as the single master configuration tree for GitHub Copilot, Claude Code, and Kilo — read natively by Copilot, through a Claude Code plugin manifest (`.github/.claude-plugin/plugin.json` plus a repo-root local marketplace) for Claude Code, and as a thin, deliberately-driftable `kilo.jsonc` for Kilo — because one physical file per surface with union frontmatter (every tool ignores frontmatter keys it does not recognise) eliminates N-tool x M-surface duplicate maintenance while leaving each tool's own native format authoritative.

Key choices:

- **`.github/` stays the single master tree, loaded into Claude via a plugin manifest** — rejected: moving skills natively into `.claude/skills/` (duplicates agents, which still need a Copilot-visible home, across two trees), and symlinking `.claude/skills/` into `.github/skills/` (known Claude Code discovery bug, anthropics/claude-code#25367).
- **Union frontmatter** (one physical file per prompt/instruction/agent, carrying keys for multiple tools, each tool ignoring the keys it doesn't recognise) **over generating per-platform files** — rejected: a generator script plus committed generated artifacts (a second build step, a bigger review surface, and a staleness class of bug — generated files drifting from their source when the generator isn't rerun).
- **`AGENTS.md` is canonical; `.github/copilot-instructions.md` was deleted** — rejected: keeping `.github/` as the only literal master with no top-level `AGENTS.md` (breaks the root-level always-on-context convention every tool, including Copilot itself, expects to find).
- **Scoped instructions symlinked from `.github/instructions/` into `.claude/rules/`**, using `paths:` frontmatter for Claude Code's file scoping — rejected: `@`-importing all instruction content unconditionally into every Claude Code session (~27KB of guidance, most of it irrelevant to any given file, loaded on every turn regardless).
- **Prompts collapsed into the skills they wrap** (no separate Copilot prompt-wrapper files) — rejected: keeping per-tool prompt wrapper files (duplicate content with no behavioural gain, since Copilot loads skills natively too).
- **Kilo rebuilt as a thin consumer of `.github/`**, deliberately not wired to the shared `.github/agents/`, and explicitly allowed to drift until it specialises.
- **OpenCode dropped entirely from the toolchain** — Kilo v7 is itself an OpenCode fork, so running both was redundant duplication of the same runtime.
- **A thin bash config-integrity checker (`scripts/check-agent-config.sh`) plus JSON-schema validation** (a `check-jsonschema` pre-commit hook against SchemaStore's plugin-manifest schema) **instead of installing the full Claude CLI into CI/devcontainer images** just to validate config.

```yaml
---
description: Python coding conventions
applyTo: "**/*.py"   # Copilot: file-scoping glob
paths: ["**/*.py"]    # Claude Code: file-scoping glob, same meaning
---

```

## Decision Drivers

- Eliminate N-tool x M-surface duplicate maintenance (the same class of problem ADR-001 solved for app repos, recurring in agent tooling)
- Avoid Claude Code's known .claude/skills/ symlink discovery bug (anthropics/claude-code#25367)
- Keep genuinely non-shareable keys (model:) from silently breaking one platform when frontmatter is unioned across tools
- Avoid installing the full Claude CLI into CI/devcontainer images just to validate plugin structure
- Let Kilo specialise independently later without blocking on, or breaking, cross-tool agent parity

## Considered Options

### Option 1: Single master tree (.github/), native per-tool consumption (chosen)

One physical file per surface lives in .github/. Copilot reads it natively; Claude Code reads it through a plugin manifest and .claude/rules/ symlinks; Kilo reads it via a thin kilo.jsonc. Union frontmatter lets each tool ignore keys it doesn't recognise.

- *Advantages:* Exactly one place to edit for any surface — no cross-tree sync step; Each tool still gets its own native format where the two are incompatible (MCP servers, model: pins); Structural drift is catchable by a thin checker plus schema validation, no extra CLI installs
- *Disadvantages:* A new .github/instructions/ file that's missing its .claude/rules/ symlink or paths: key fails silently in Claude Code — nothing currently checks for this; Requires every contributor to understand the union-frontmatter convention rather than just editing 'their' tool's file

### Option 2: Generator script + committed per-platform artifacts

Author configuration once in a canonical source format, run a generator script to produce and commit each tool's native files (.claude/, .kilo/, .vscode/, etc.).

- *Advantages:* Each generated file can be 100% idiomatic to its own tool, no union-frontmatter compromises; The canonical source can be validated once, independent of any tool's parser
- *Disadvantages:* Adds a build step and a second thing that can go stale — generated files silently drift when the generator isn't rerun and committed; Doubles the review surface: reviewers see both the source edit and the generated diff; This is exactly the class of problem cap-pm1's predecessor parity script existed to police, and it was retired for being fragile

### Option 3: Independent hand-maintained per-tool configs

Each tool keeps its own hand-written configuration tree with no shared source of truth, updated independently.

- *Advantages:* Zero cross-tool coupling — a change to one tool's config can never break another's; No union-frontmatter convention to learn
- *Disadvantages:* Reintroduces the exact N-tool x M-surface duplication this decision exists to eliminate; Is the pre-cap-pm1 state that had already rotted once (Kilo's stale model pin, no Claude Code config at all)

### Option 4: Symlink-everywhere from .claude/

Make .claude/ the physical master and symlink Copilot's and Kilo's config trees to it instead of the reverse.

- *Advantages:* Claude Code, the tool with the most surfaces (skills, agents, rules, MCP, plugin manifest), gets first-class native files with no plugin indirection; Symlinking is the same low-maintenance mechanism already used successfully for .claude/rules/
- *Disadvantages:* Hits Claude Code's own .claude/skills/ discovery bug (anthropics/claude-code#25367) for the skills surface specifically; Copilot and Kilo have no natural home for a .claude-shaped tree, so their own symlink targets would need constant remapping as Claude's layout evolves

## Decision Matrix

| Criterion | Single master tree (.github/), native per-tool consumption | Generator script + committed per-platform artifacts | Independent hand-maintained per-tool configs | Symlink-everywhere from .claude/ |
| --- | --- | --- | --- | --- |
| Maintenance burden (single edit propagates) | 5 | 3 | 1 | 4 |
| Drift / staleness risk | 5 | 2 | 1 | 4 |
| Per-tool native format fidelity | 4 | 5 | 5 | 3 |
| Claude Code discovery reliability | 5 | 4 | 5 | 2 |
| Review surface size (diff clarity) | 5 | 2 | 3 | 4 |
| CI / devcontainer validation cost | 5 | 3 | 4 | 3 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Single edit point for always-on context, scoped instructions, skills, agents, and now MCP servers — no cross-tree sync step
- task check:agents plus a check-jsonschema pre-commit hook catch the structural invariants (union tools:, absent model:, valid plugin manifest) without installing the Claude CLI anywhere in CI or the devcontainer image
- Kilo can specialise with its own purpose-built agents later without waiting on, or breaking, the shared Claude Code/Copilot surface
- Dropping OpenCode removes a redundant runtime, since Kilo v7 is itself an OpenCode fork

### Negative

- A new .github/instructions/ file silently fails to load in Claude Code if its .claude/rules/ symlink or paths: key is forgotten — nothing currently checks for this (tracked as a known gap in CONTRIBUTING.md)
- model: cannot be unioned like other keys — a foreign value hard-errors Claude Code at agent launch, so it must be omitted from .github/agents/*.agent.md entirely, and per-tool model pins have no home in the shared file
- Kilo is explicitly allowed to drift from .github/agents/, so its agent capabilities lag behind Copilot and Claude Code until it specialises
- Running bd setup copilot would regenerate the deliberately-deleted .github/copilot-instructions.md and scaffold a conflicting .copilot-plugin/ — a foot-gun documented in CONTRIBUTING.md rather than prevented by tooling

_2026-08-02_
