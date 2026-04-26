---
description: 'Documentation - Markdown and Zensical conventions'
applyTo: '**/*.md'
---

# Documentation Instructions

## Documentation System

| Component      | Choice                                                         |
| -------------- | -------------------------------------------------------------- |
| Site Generator | Zensical (`zensical.toml`)                                     |
| Theme          | Zensical (modern theme)                                        |
| Structure      | User Journey (guided flow through tasks along lifecycle)       |

### Documentation Sites

This monorepo has **multiple independent documentation sites**:

| Site           | Config                                | Serve command                    | Build command                    |
| -------------- | ------------------------------------- | -------------------------------- | -------------------------------- |
| Root (monorepo)| `zensical.toml`                       | `task docs:serve`                | `task docs:build`                |
| Per-app        | `apps/<name>/zensical.toml`           | `task <app>:docs:serve`          | `task <app>:docs:build`          |

## App Documentation Conventions

### Navigation

All app documentation sites use **top-bar tab navigation** (`navigation.tabs`), not
sidebar navigation. The `zensical.toml` for every app must include a full
`[project.theme]` section with `navigation.tabs`, `navigation.tabs.sticky`, palette
toggles, and all standard markdown extensions. See any existing app (e.g.
`apps/gas2mqtt/zensical.toml`) as reference. The `task app:new` scaffold generates this
automatically.

### Homepage (`docs/index.md`)

Every app homepage must include:

1. **Badges** — License, Python version, cosalette framework
2. **Bold tagline** — one-sentence description of what the app does
3. **Quick Links** — grid cards (Material `grid cards` syntax) linking to each
   documentation page (Getting Started, Configuration, MQTT Topics, etc.)

The scaffold generates these three automatically. Additionally, each homepage should
include (expand after scaffolding):

4. **Prose paragraph** — brief explanation of how the app works
5. **Features section** — bullet list of key capabilities
6. **Hardware table** (if applicable) — sensor/interface/platform

Do not leave the homepage as just a title and one-liner.

## ADR Format

**Do not write ADR Markdown directly.** Use the `adr-create` skill, which
produces a schema-conforming JSON document. The renderer (`scripts/render_adr.py`)
performs structural validation and renders canonical Markdown via
`task adr:create`.

| Resource | Path |
|----------|------|
| JSON Schema | `.github/agents/schemas/adr-input.schema.json` |
| Renderer | `scripts/render_adr.py` |
| Task | `task adr:create -- <input.json>` |
| Skill | `.github/skills/adr-create/SKILL.md` |

All ADRs include YAML frontmatter with `status`, `date`, `impact`, and `tags`.

### ADR Operations

| Operation | JSON `type` | Description |
|-----------|-------------|-------------|
| New ADR | `"new"` | Creates `docs/adr/ADR-NNN-slug.md` (auto-numbered) |
| Amend ADR | `"amendment"` | Appends amendment section to existing ADR |
| Supersede ADR | `"supersede"` | Creates new ADR, marks old as superseded |

### Impact Levels & Decision Matrix Requirements

| Impact | Decision matrix | Min options | When to use |
|--------|-----------------|-------------|-------------|
| `low` | Optional | 2 | Single-module convention, naming, tooling |
| `moderate` | **Required** (≥3 criteria) | 2 | Multiple modules, new dependency |
| `high` | **Required** (≥5 criteria) | 3 | Architectural pattern, cross-cutting, breaking |

## File Locations

| Content              | Location                              |
| -------------------- | ------------------------------------- |
| Root documentation   | `docs/`                               |
| Root ADRs            | `docs/adr/`                           |
| App documentation    | `apps/<name>/docs/`                   |
| App ADRs             | `apps/<name>/docs/adr/`               |

ADRs are included in their respective documentation site (root or per-app).
